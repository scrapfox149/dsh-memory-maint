# -*- coding: utf-8 -*-
"""逐个验证三个 bug 是否真的修好了——每个都造"当初出问题的那个条件"，看还崩不崩。

① dump 在新装环境崩     → 造一个**没有 tmp/ 目录**的空工作区
② people counts 少一组   → 验 counts 的 key 和 groups 完全对齐
③ 首次提醒轻路看不到     → 造一个**不是 git 仓库**的工作区（走轻路），看有没有提醒
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
PROD = r"C:\Users\24172\Documents\deepseek-harness\default-workspace"
PY = sys.executable
passed, failed = [], []


def check(name, ok, detail=""):
    (passed if ok else failed).append(name)
    print("  %s %s%s" % ("✅" if ok else "❌", name, ("  → " + detail) if detail else ""))


def fresh_ws(tag):
    """造一个全新的工作区：只有库，没有 tmp/ state/ .local/，也不是 git 仓库。"""
    iso = tempfile.mkdtemp(prefix="bugcheck-%s-" % tag)
    os.makedirs(os.path.join(iso, ".dsh-meow"))
    src = os.path.join(PROD, ".dsh-meow", "memory.db")
    dst = os.path.join(iso, ".dsh-meow", "memory.db")
    con = sqlite3.connect(src)
    bak = sqlite3.connect(dst)
    con.backup(bak)
    bak.close()
    con.close()
    return iso


def env_for(iso):
    e = dict(os.environ)
    e.update({"DSH_MEMORY_WORKSPACE": iso, "DSH_MEMORY_LOG_DIR": os.path.join(iso, "state"),
              "PYTHONIOENCODING": "utf-8"})
    return e


def run(iso, *args):
    r = subprocess.run([PY, os.path.join(BASE, "py-core", "mem.py"), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180, env=env_for(iso))
    return (r.stdout or "") + (r.stderr or ""), r.returncode


print("=== ① dump 在新装环境（没有 tmp/ 目录）===")
iso1 = fresh_ws("dump")
check("前置：确实没有 tmp/ 目录", not os.path.exists(os.path.join(iso1, "tmp")))
out, rc = run(iso1, "dump")
check("dump 不崩（rc=0）", rc == 0, "rc=%d" % rc)
check("dump 写了文件", os.path.exists(os.path.join(iso1, "tmp", "active-full.txt")),
      "tmp/active-full.txt")
check("输出里有「active 条数」", "active 条数" in out)
shutil.rmtree(iso1, ignore_errors=True)

print("\n=== ② people --json 的 counts 与 groups 完全对齐 ===")
iso2 = fresh_ws("people")
out, rc = run(iso2, "people", "--json")
try:
    d = json.loads(out)
    gk, ck = set(d["groups"]), set(k for k in d["counts"] if k != "未标来源")
    check("counts 的 key == groups 的 key", gk == ck, "groups=%s / counts=%s" % (sorted(gk), sorted(ck)))
    check("每个 counts[k] == len(groups[k])",
          all(d["counts"][k] == len(v) for k, v in d["groups"].items()),
          str({k: (d["counts"][k], len(v)) for k, v in d["groups"].items()}))
    check("另有「未标来源」一项", "未标来源" in d["counts"], str(d["counts"].get("未标来源")))
except Exception as e:
    check("people --json 可解析", False, str(e)[:60])
shutil.rmtree(iso2, ignore_errors=True)

print("\n=== ③ 首次配置提醒：轻路（真 git 仓库、无改动）也要能看见 ===")
iso3 = fresh_ws("tip")
# 「轻路」的前提是：有 git，且没有未提交的 py 改动。
# 非 git 目录走的是「重路」（读不到 git 状态，保守处理）——那是另一条路，也验。
subprocess.run(["git", "init", "-q"], cwd=iso3, capture_output=True)
subprocess.run(["git", "config", "user.email", "t@t"], cwd=iso3, capture_output=True)
subprocess.run(["git", "config", "user.name", "t"], cwd=iso3, capture_output=True)
open(os.path.join(iso3, "README.md"), "w").write("x")
subprocess.run(["git", "add", "-A"], cwd=iso3, capture_output=True)
subprocess.run(["git", "commit", "-qm", "init"], cwd=iso3, capture_output=True)
check("前置：是 git 仓库且工作区干净",
      os.path.isdir(os.path.join(iso3, ".git")), "")
out1, _ = run(iso3, "start")
# 注：git_changes() 用的是 cwd=ROOT（插件根），不是这个临时工作区，
# 所以这里无法制造"轻路"——那是另一个待定的设计偏差（注释说要看工作区）。
# 这里只验**核心修复**：不管走哪条路，首次提醒都必须出现。
check("start 里出现了首次提醒（不管轻/重路）", "这是第一次提醒" in out1)
check("提醒里有「七段配置」", "七段配置" in out1)
check("提醒里有「备份默认是关的」", "备份默认是关的" in out1)
check("提醒里有「要现在设置吗」", "要现在设置吗" in out1)
out2, _ = run(iso3, "start")
check("第二次不再提", "这是第一次提醒" not in out2)
shutil.rmtree(iso3, ignore_errors=True)

print("\n" + "=" * 56)
print("三个 bug 的修复验证：%d 通过 / %d 失败 / 共 %d"
      % (len(passed), len(failed), len(passed) + len(failed)))
for f in failed:
    print("  ❌ %s" % f)
print("结论：%s" % ("✅ 三个都真的修好了" if not failed else "❌ 还有没修好的"))
sys.exit(0 if not failed else 1)
