# -*- coding: utf-8 -*-
"""数字正确性：动作输出里的数字 vs 直接查库/数文件。

冒烟只验"有结论行"，这里验"算得对不对"。
在隔离库上跑（复制生产库），不碰生产。
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
TIERS = ("project", "fact", "lesson", "topic", "rules", "user", "soul")

passed, failed = [], []


def check(name, ok, detail=""):
    (passed if ok else failed).append(name)
    print("  %s %s%s" % ("✅" if ok else "❌", name, ("  → " + detail) if detail else ""))


def main():
    iso = tempfile.mkdtemp(prefix="numcheck-")
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
    c = sqlite3.connect(dst)

    def run(*args):
        r = subprocess.run([PY, mem, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180, env=env)
        return (r.stdout or "") + (r.stderr or "")

    def cnt(sql, params=()):
        return c.execute(sql, params).fetchone()[0]

    # ① active 总数：daily / dump / status 三处应一致
    real_active = sum(cnt("select count(*) from \"%s\" where status='active'" % t) for t in TIERS)
    print("库里的 active 总数: %d\n" % real_active)

    print("【① daily 的总数】")
    out = run("daily")
    m = re.search(r"·\s*(\d+)\s*条 active", out)
    check("daily 报的 active 数 == 库", m and int(m.group(1)) == real_active,
          "报 %s / 实际 %d" % (m.group(1) if m else "?", real_active))

    print("\n【② dump 的全量条数】")
    out = run("dump")
    m = re.search(r"active 条数[:：]\s*(\d+)", out)
    check("dump 报的条数 == 库", m and int(m.group(1)) == real_active,
          "报 %s / 实际 %d" % (m.group(1) if m else "?", real_active))

    print("\n【③ dump --json 的 total】")
    out = run("dump", "--json")
    try:
        d = json.loads(out)
        check("dump --json total == 库", d.get("total") == real_active,
              "报 %s / 实际 %d" % (d.get("total"), real_active))
    except Exception as e:
        check("dump --json total == 库", False, str(e)[:50])

    print("\n【④ project dsh 的条数】")
    real_proj = 0
    for t in TIERS:
        cols = [r[1] for r in c.execute('pragma table_info("%s")' % t).fetchall()]
        if "project" not in cols:
            continue
        rows = c.execute('select project from "%s" where status=\'active\'' % t).fetchall()
        for (p,) in rows:
            names = [x.strip() for x in (p or "").replace("，", ",").split(",") if x.strip()]
            if "dsh" in names:
                real_proj += 1
    out = run("project", "dsh", "--json")
    try:
        d = json.loads(out)
        check("project dsh --json total == 库", d.get("total") == real_proj,
              "报 %s / 实际 %d" % (d.get("total"), real_proj))
    except Exception as e:
        check("project dsh --json total == 库", False, str(e)[:50])

    print("\n【⑤ assets dsh 的记忆条数 == project dsh】")
    out = run("assets", "dsh", "--json")
    try:
        a = json.loads(out)
        check("assets 的记忆数 == project 的条数",
              a["memories"]["total"] == real_proj,
              "assets %s / project %d" % (a["memories"]["total"], real_proj))
    except Exception as e:
        check("assets 的记忆数 == project 的条数", False, str(e)[:50])

    print("\n【⑥ people 的各组数加起来 == 有来源标记的条数】")
    out = run("people", "--json")
    try:
        d = json.loads(out)
        # counts 现在按 groups 的实际 key 生成，所以逐 key 对得上才算对
        ok = all(d["counts"].get(k) == len(v) for k, v in d["groups"].items())
        total = sum(len(v) for v in d["groups"].values())
        check("people 每个 counts[k] == len(groups[k])", ok,
              "groups 合计 %d / counts 未标 %s" % (total, d["counts"].get("未标来源")))
    except Exception as e:
        check("people counts 之和 == groups 条目数", False, str(e)[:50])

    print("\n【⑦ project dsh --todo 的条数 == 库里 todo 子类】")
    real_todo = 0
    for t in TIERS:
        cols = [r[1] for r in c.execute('pragma table_info("%s")' % t).fetchall()]
        if "subcategory" not in cols or "project" not in cols:
            continue
        rows = c.execute('select project from "%s" where status=\'active\' and subcategory=\'todo\'' % t).fetchall()
        for (p,) in rows:
            names = [x.strip() for x in (p or "").replace("，", ",").split(",") if x.strip()]
            if "dsh" in names:
                real_todo += 1
    out = run("project", "dsh", "--json", "--todo")
    try:
        d = json.loads(out)
        check("--todo 条数 == 库", d.get("total") == real_todo,
              "报 %s / 实际 %d" % (d.get("total"), real_todo))
    except Exception as e:
        check("--todo 条数 == 库", False, str(e)[:50])

    c.close()
    print("\n" + "=" * 52)
    print("数字正确性：%d 通过 / %d 失败 / 共 %d" % (len(passed), len(failed), len(passed) + len(failed)))
    for f in failed:
        print("  ❌ %s" % f)
    shutil.rmtree(iso, ignore_errors=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
