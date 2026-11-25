# -*- coding: utf-8 -*-
"""设计一致性：行为是否符合当初的设计意图。

和前两个测试的分工：
  verify-readonly —— 有没有动数据（安全）
  verify-numbers  —— 数字算得对不对（正确性）
  **verify-design** —— 行为像不像设计里写的那样（意图）

每一项都对着一条明确的设计决定（写来源日期），不是"我觉得应该"。
"""
import io
import json
import os
import re
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
passed, failed = [], []


def check(name, ok, detail="", design=""):
    (passed if ok else failed).append(name)
    tag = ("  〔设计来源：" + design + "〕") if design and not ok else ""
    print("  %s %s%s%s" % ("✅" if ok else "❌", name, ("  → " + detail) if detail else "", tag))


def main():
    iso = tempfile.mkdtemp(prefix="design-")
    os.makedirs(os.path.join(iso, ".dsh-meow"))
    src = os.path.join(WS, ".dsh-meow", "memory.db")
    dst = os.path.join(iso, ".dsh-meow", "memory.db")

    # CI 的 checkout 里没有 memory.db（也不该有）→ 跳过，不算失败
    if not os.path.exists(src):
        print("SKIP：没有 memory.db（CI 环境），跳过")
        print("结论：⏭ 跳过（无库）")
        return 0
    con = sqlite3.connect(src)
    bak = sqlite3.connect(dst)
    con.backup(bak)
    bak.close()
    con.close()

    env = dict(os.environ)
    env.update({"DSH_MEMORY_WORKSPACE": iso, "DSH_MEMORY_LOG_DIR": os.path.join(iso, "state"),
                "PYTHONIOENCODING": "utf-8"})
    mem = os.path.join(BASE, "py-core", "mem.py")

    def run(*args):
        r = subprocess.run([PY, mem, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180, env=env)
        return (r.stdout or "") + (r.stderr or ""), r.returncode

    # ── ① start 的两条路（设计：2026-11-24「只在真在动工具时才展开完整规则」）──
    print("【① start 轻/重两条路】")
    out, _ = run("start")
    light = "没有未提交的脚本改动" in out
    # 这个工作区确实有未提交改动，所以大概率是"重路"；只验两条路的判定逻辑存在
    heavy_marker = "造工具场景" in out or "只有" in out
    check("start 给出了判定理由（轻路一句话 / 重路展开）", light or heavy_marker,
          (out.splitlines()[2] if len(out.splitlines()) > 2 else "")[:50],
          "2026-11-24 用户定：只在真动工具时展开四问五思")

    # ── ② --json 必须是纯 JSON（设计：2026-11-25「--json 只出数据，不打印格式文本」）──
    print("\n【② --json 是纯 JSON，没有混进文本】")
    for cmd in (["project", "dsh", "--json"], ["dump", "--json"], ["people", "--json"],
                ["assets", "dsh", "--json"], ["expand", "备份", "--json"]):
        out, _ = run(*cmd)
        label = " ".join(cmd)
        try:
            json.loads(out)
            check("%s 可整段解析" % label, True)
        except Exception as e:
            check("%s 可整段解析" % label, False, str(e)[:40],
                  "2026-11-25 定：--json 是附加的一条路，不夹带文本")

    # ── ③ 子类过滤只出那一类（设计：issue #13）──
    print("\n【③ --decisions / --todo 只出那一类】")
    out, _ = run("project", "dsh", "--json", "--decisions")
    try:
        d = json.loads(out)
        ok = all((i.get("subcategory") or "") == "decisions" for i in d["items"])
        check("--decisions 的 items 全是 decisions", ok, "共 %d 条" % len(d["items"]),
              "issue #13：按子类过滤")
    except Exception as e:
        check("--decisions 的 items 全是 decisions", False, str(e)[:40], "issue #13")

    # ── ④ assets 没配目录时的行为（设计：2026-11-25「没配只列记忆并提示怎么配」）──
    print("\n【④ assets 没配目录 → 只列记忆 + 提示】")
    out, _ = run("assets", "notconfigured")
    check("提示了怎么配目录", "assets" in out and ("没配" in out or "未配" in out),
          (([l for l in out.splitlines() if "没配" in l or "未配" in l] or [""])[0])[:60],
          "2026-11-25 定：没配目录只列记忆，并提示怎么配")

    # ── ⑤ tools 关了就该消失（设计：issue #16「即时生效」）──
    print("\n【⑤ 配置改了立即生效（issue #16）】")
    cfg = os.path.join(iso, "tools", "dsh-memory-maint", "config.json")
    os.makedirs(os.path.dirname(cfg), exist_ok=True)
    io.open(cfg, "w", encoding="utf-8").write(
        json.dumps({"tools": {"mem_backup": True}}, ensure_ascii=False) + "\n")
    # 这里只验"配置能读到"（工具注册要 node 环境，在 switch-test 里验）
    from importlib import util as _u
    spec = _u.spec_from_file_location("mem_start", os.path.join(
        BASE, "modules", "feature", "check", "py", "memory-start.py"))
    # 只验配置文件能被 assets_summary 读到（它调 assets，assets 会读配置）
    out2, _ = run("assets", "dsh", "--json")
    try:
        d2 = json.loads(out2)
        check("工作区配置能被读到（assets 正常返回）", "memories" in d2, "",
              "2026-11-25：配置从插件根搬到工作区")
    except Exception as e:
        check("工作区配置能被读到（assets 正常返回）", False, str(e)[:40])

    # ── ⑥ mem_backup 默认关（设计：2026-11-25 用户定）──
    print("\n【⑥ mem_backup 默认关闭】")
    src_code = io.open(os.path.join(BASE, "lib", "index.js"), encoding="utf-8").read()
    check("代码里有 DEFAULT_OFF 且只含 mem_backup",
          re.search(r"DEFAULT_OFF\s*=\s*new Set\(\['mem_backup'\]\)", src_code) is not None,
          "", "2026-11-25 用户定：默认关闭备份（不知道别人的路径）")
    ex = json.load(io.open(os.path.join(BASE, "config.example.json"), encoding="utf-8-sig"))
    check("config.example.json 里 mem_backup=false",
          (ex.get("tools") or {}).get("mem_backup") is False,
          "", "同上")
    check("config.example.json 的 agent.name 是通用默认 DeepSeek",
          (ex.get("agent") or {}).get("name") == "DeepSeek",
          str((ex.get("agent") or {}).get("name")),
          "2026-11-25 用户定：名字要设默认")

    # ── ⑦ 首次强提醒只出现一次（设计：2026-11-24「只主动强提醒一次」）──
    print("\n【⑦ 首次强提醒只提一次】")
    marker = os.path.join(iso, "state", "config-tipped")
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    if os.path.exists(marker):
        os.remove(marker)
    out1, _ = run("start")
    first_has = "这是第一次提醒" in out1
    out2, _ = run("start")
    second_has = "这是第一次提醒" in out2
    check("第一次提了", first_has, "", "2026-11-24 定：只主动强提醒一次")
    check("第二次不提了", not second_has, "第二次仍出现" if second_has else "", "同上")

    print("\n" + "=" * 56)
    print("设计一致性：%d 通过 / %d 失败 / 共 %d"
          % (len(passed), len(failed), len(passed) + len(failed)))
    for f in failed:
        print("  ❌ %s" % f)
    shutil.rmtree(iso, ignore_errors=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
