# -*- coding: utf-8 -*-
"""验「新用户出 BUG 时，能不能拿到日志、能不能提交」。
   造几种典型故障，看插件留了什么、用户能不能找到。"""
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


def fresh(tag):
    iso = tempfile.mkdtemp(prefix="diag-%s-" % tag)
    os.makedirs(os.path.join(iso, ".dsh-meow"))
    src = os.path.join(PROD, ".dsh-meow", "memory.db")
    if os.path.exists(src):
        con = sqlite3.connect(src)
        bak = sqlite3.connect(os.path.join(iso, ".dsh-meow", "memory.db"))
        con.backup(bak)
        bak.close()
        con.close()
    return iso


def run(iso, *args):
    r = subprocess.run([PY, os.path.join(BASE, "py-core", "mem.py"), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180,
                       env={**os.environ, "DSH_MEMORY_WORKSPACE": iso,
                            "DSH_MEMORY_LOG_DIR": os.path.join(iso, "state"),
                            "PYTHONIOENCODING": "utf-8"})
    return (r.stdout or "") + (r.stderr or ""), r.returncode


print("=== ① 注入一个故障（坏掉的 config.json），看它怎么报 ===")
iso = fresh("badcfg")
cfgdir = os.path.join(iso, "tools", "dsh-memory-maint")
os.makedirs(cfgdir)
io.open(os.path.join(cfgdir, "config.json"), "w", encoding="utf-8").write("{ 这不是合法 JSON ")
out, rc = run(iso, "daily")
print("  daily 的 rc=%d" % rc)
print("  输出前 200 字: %s" % out[:200].replace("\n", " | "))
state = os.path.join(iso, "state")
print("  state/ 里有: %s" % (os.listdir(state) if os.path.isdir(state) else "（state 目录都不存在）"))

print("\n=== ② 坏库（磁盘上是垃圾数据）===")
iso2 = fresh("badb")
io.open(os.path.join(iso2, ".dsh-meow", "memory.db"), "wb").write(b"\x00" * 2048)
out2, rc2 = run(iso2, "daily")
print("  daily 的 rc=%d" % rc2)
print("  输出前 240 字: %s" % out2[:240].replace("\n", " | "))
state2 = os.path.join(iso2, "state")
print("  state/ 里有: %s" % (os.listdir(state2) if os.path.isdir(state2) else "（state 目录都不存在）"))
ep = os.path.join(state2, "errors.jsonl")
if os.path.exists(ep):
    print("  errors.jsonl 内容:")
    for line in io.open(ep, encoding="utf-8").read().splitlines()[:3]:
        print("    " + line[:150])

print("\n=== ③ 有没有「导出诊断包」的命令 ===")
r = subprocess.run([PY, os.path.join(BASE, "py-core", "mem.py"), "list"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
acts = []
import re
for m in re.finditer(r"mem\.py (\w+) +([a-z0-9]+) ", r.stdout or ""):
    acts.append(m.group(2))
diag = [a for a in acts if a in ("diag", "diagnose", "report", "doctor", "info", "debug")]
print("  诊断类动作: %s" % (diag or "❌ 没有（用户拿到问题不知该交什么）"))
print("  全部动作: %s" % ", ".join(sorted(set(acts))))

for d in (iso, iso2):
    shutil.rmtree(d, ignore_errors=True)
