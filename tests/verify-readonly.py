# -*- coding: utf-8 -*-
"""只读性验证：对每个只读动作跑一次，比执行前后 memory.db 的 sha256。

判定：
  不变 → ✅ 只读（真的没动用户数据）
  变了 → ❌ 这个动作实际会写库（要么改它是只读的，要么在文档里标清楚）

排除（已知会写）：
  restore       —— 重建库（设计如此）
  export/backup —— 写归档目录，不写库（但它读库，sha 应该不变）

跑法：
  python tests/verify-readonly.py            # 在插件根跑
"""
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 2026-11-25：环境变量优先（CI 上没有这个硬编码路径）
WS = os.environ.get("DSH_MEMORY_WORKSPACE") or r"C:\Users\24172\Documents\deepseek-harness\default-workspace"
PY = sys.executable

# 会写库的（设计如此，不参与"只读"验证）
WRITERS = {"restore"}

# 会改文件但不改库的（也参与，只是说明一下）
FILE_WRITERS = {"dream", "index", "timeline", "map", "export", "changelog", "sample"}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    iso = tempfile.mkdtemp(prefix="readonly-")
    dsh_meow = os.path.join(iso, ".dsh-meow")
    os.makedirs(dsh_meow)
    src = os.path.join(WS, ".dsh-meow", "memory.db")
    dst = os.path.join(dsh_meow, "memory.db")

    # CI 的 checkout 里没有 memory.db（也不该有）→ 跳过，不算失败
    if not os.path.exists(src):
        print("SKIP：没有 memory.db（CI 环境），跳过")
        print("结论：⏭ 跳过（无库）")
        return 0

    # 用 sqlite backup API 复制（正确处理 WAL），再 VACUUM 掉 WAL 影响
    con = sqlite3.connect(src)
    bak = sqlite3.connect(dst)
    con.backup(bak)
    bak.close()
    con.close()
    print("隔离库: %s（%.0f KB）" % (dst, os.path.getsize(dst) / 1024))

    env = dict(os.environ)
    env["DSH_MEMORY_WORKSPACE"] = iso
    env["DSH_MEMORY_LOG_DIR"] = os.path.join(iso, "state")
    env["PYTHONIOENCODING"] = "utf-8"

    mem = os.path.join(BASE, "py-core", "mem.py")

    # 查所有动作
    r = subprocess.run([PY, mem, "list"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    actions = []
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("mem.py "):
            parts = line.split()
            if len(parts) >= 3 and parts[2] not in ("→", "-"):
                act = parts[2]
                if act and act not in actions and not act.startswith("-"):
                    actions.append(act)
    # 去掉分组名（check/maint/query 是组名，后面跟动作）
    actions = [a for a in actions if a not in ("check", "maint", "query")]
    print("待验动作: %d 个 -> %s\n" % (len(actions), ", ".join(actions)))

    ok, bad, skipped = [], [], []
    for act in actions:
        if act in WRITERS:
            skipped.append((act, "会写库（设计如此）"))
            continue
        before = sha(dst)
        try:
            subprocess.run([PY, mem, act], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180, env=env)
        except subprocess.TimeoutExpired:
            bad.append((act, "超时"))
            continue
        after = sha(dst)
        if before == after:
            ok.append(act)
        else:
            bad.append((act, "库变了"))

    print("=" * 56)
    print("✅ 只读（库 sha 不变）: %d 个" % len(ok))
    if bad:
        print("❌ 会写库（必须改或必须标清楚）: %d 个" % len(bad))
        for a, why in bad:
            print("   %-14s %s" % (a, why))
    if skipped:
        print("⏭  跳过: %s" % ", ".join("%s（%s）" % (a, w) for a, w in skipped))
    print("\n说明：改 docs/ 的动作（%s）库 sha 也不会变——它们只写文件。"
          % ", ".join(sorted(FILE_WRITERS)))
    print("结论：%s" % ("✅ 全部只读" if not bad else "❌ %d 个动作会写库" % len(bad)))
    shutil.rmtree(iso, ignore_errors=True)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
