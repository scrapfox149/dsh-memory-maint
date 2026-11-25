# -*- coding: utf-8 -*-
"""组合测试：参数叠加 / 连续跑 / 并发。

前面几个 verify 验的是"单次、单动作、默认参数"。
这里补三个前面没覆盖的：
  ① 参数组合（--json × --decisions × --recent × --limit）
  ② 连续跑（同一动作多次、多动作交替 —— 会不会状态污染 / 结果不一致）
  ③ 并发（两个进程同时跑 —— 库会不会坏、会不会崩）
"""
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
PROD = os.environ.get("DSH_MEMORY_WORKSPACE") or r"C:\Users\24172\Documents\deepseek-harness\default-workspace"
PY = sys.executable
passed, failed = [], []


def check(name, ok, detail=""):
    (passed if ok else failed).append(name)
    print("  %s %s%s" % ("✅" if ok else "❌", name, ("  → " + detail) if detail else ""))


def main():
    iso = tempfile.mkdtemp(prefix="combo-")
    os.makedirs(os.path.join(iso, ".dsh-meow"))
    src = os.path.join(PROD, ".dsh-meow", "memory.db")
    dst = os.path.join(iso, ".dsh-meow", "memory.db")
    if not os.path.exists(src):
        print("SKIP：没有 memory.db（CI 环境）")
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

    def run(*args, timeout=180):
        r = subprocess.run([PY, mem, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, env=env)
        return (r.stdout or "") + (r.stderr or ""), r.returncode

    # ── ① 参数组合：每个都必须输出合法 JSON ──
    print("【① 参数组合（--json 与其它 flag 叠加）】")
    combos = [
        ["project", "dsh", "--json", "--decisions"],
        ["project", "dsh", "--json", "--quotes"],
        ["project", "dsh", "--json", "--todo"],
        ["project", "dsh", "--json", "--decisions", "--quotes"],
        ["project", "dsh", "--json", "--decisions", "--quotes", "--todo"],
        ["dump", "--json"],
        ["people", "--json"],
        ["assets", "dsh", "--json", "--limit", "5"],
        ["expand", "备份", "--json"],
        ["why", "备份", "--json"],
        ["hipporag", "备份", "--json"],
        # ⚠ `file` 故意不列在这里：`memory-file-search.py` 的 __main__ 跑的是**硬编码自测**，
        #   还没有"按词搜索 + --json"的命令行入口（issue #12 差的就是它）。
        #   等实现了再加回来。
    ]
    # 显式确认 `file` 现在**真的能搜**（2026-11-26 补上命令行入口；之前只跑硬编码自测）
    out, _ = run("file", "备份", "--json")
    try:
        d = json.loads(out)
        check("file 现在接受查询词并返回 JSON（issue #12 已补）",
              "items" in d and "query" in d,
              "query=%s, total=%s" % (d.get("query"), d.get("total")))
    except Exception as e:
        check("file 现在接受查询词并返回 JSON（issue #12 已补）", False, str(e)[:50])
    for c in combos:
        out, rc = run(*c)
        label = " ".join(c)
        try:
            d = json.loads(out)
            ok = isinstance(d, dict)
            check(label, ok, "total=%s" % d.get("total", "-") if ok else "不是 dict")
        except Exception as e:
            check(label, False, "%s | 前 60 字: %r" % (str(e)[:30], out[:60]))

    # ── ② 连续跑：同一动作 3 次结果一致 ──
    print("\n【② 连续跑：同一动作 3 次，结果要一致】")
    for args in (["project", "dsh", "--json"], ["people", "--json"], ["assets", "dsh", "--json"]):
        totals = []
        for _ in range(3):
            out, _ = run(*args)
            try:
                d = json.loads(out)
                if "counts" in d:                     # people：没有 total，用各组之和
                    totals.append(sum(v for k, v in d["counts"].items()
                                      if k != "未标来源"))
                elif "memories" in d:                 # assets
                    totals.append(d["memories"]["total"])
                else:
                    totals.append(d.get("total"))
            except Exception:
                totals.append(None)
        same = len(set(map(str, totals))) == 1 and totals[0] is not None
        check("%s 三次一致" % " ".join(args), same, str(totals))

    # ── ③ 多动作交替：会不会互相影响 ──
    print("\n【③ 多动作交替跑（状态污染？）】")
    seq = [["daily"], ["quality"], ["project", "dsh", "--json"], ["integrity"],
           ["project", "dsh", "--json"], ["daily"]]
    results = []
    for c in seq:
        out, rc = run(*c)
        results.append((c[0], "结论" in out))
    check("交替跑每个都有「结论」", all(ok for _, ok in results), str(results))
    # 首尾 daily 的 active 数应一致
    out1, _ = run("daily")
    out2, _ = run("daily")
    import re
    m1 = re.search(r"(\d+)\s*条 active", out1)
    m2 = re.search(r"(\d+)\s*条 active", out2)
    check("首尾 daily 的 active 数一致",
          m1 and m2 and m1.group(1) == m2.group(1),
          "%s vs %s" % (m1.group(1) if m1 else "?", m2.group(1) if m2 else "?"))

    # ── ④ 并发：4 个进程同时跑只读动作 ──
    print("\n【④ 并发：4 个进程同时跑】")
    procs = []
    for args in (["daily"], ["project", "dsh", "--json"], ["people", "--json"], ["assets", "dsh"]):
        procs.append((args, subprocess.Popen([PY, mem, *args], stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE, env=env)))
    ok_count = 0
    for args, p in procs:
        out, err = p.communicate(timeout=180)
        text = (out or b"").decode("utf-8", "replace") + (err or b"").decode("utf-8", "replace")
        # daily/quality/integrity **有警告时返回 1 是设计**，不是崩。
        # 判成功 = 出了结果，不是退出码为 0。
        if p.returncode in (0, 1) and ("结论" in text or text.strip().startswith("{")):
            ok_count += 1
        else:
            print("     并发失败: %s rc=%d %r" % (" ".join(args), p.returncode, text[:80]))
    check("4 个并发全部成功", ok_count == 4, "%d/4" % ok_count)

    # 并发之后库还完好
    c = sqlite3.connect(dst)
    try:
        n = c.execute("select count(*) from sqlite_master").fetchone()[0]
        check("并发后库结构完好（表数 > 0）", n > 0, "%d 张表" % n)
        c.execute("select count(*) from project").fetchone()
        check("并发后能正常查表", True)
    except Exception as e:
        check("并发后库结构完好", False, str(e)[:60])
    finally:
        c.close()

    print("\n" + "=" * 56)
    print("组合测试：%d 通过 / %d 失败 / 共 %d" % (len(passed), len(failed), len(passed) + len(failed)))
    for f in failed:
        print("  ❌ %s" % f)
    shutil.rmtree(iso, ignore_errors=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
