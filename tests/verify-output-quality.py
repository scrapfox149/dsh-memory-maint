# -*- coding: utf-8 -*-
"""实测每个动作的**输出质量**——不只看"跑没跑通"，看**出来的是不是有用的东西**。

判据（三类，都不要求"内容对"，只要求"不是空的/不是占位"）：
  ✅ 有实质内容：输出里有过百字或有多行结构化内容
  ⚠ 可疑：只有一行、或只有"用法"、或输出极短
  ❌ 空：没有任何输出
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
PROD = r"C:\Users\24172\Documents\deepseek-harness\default-workspace"
PY = sys.executable

iso = tempfile.mkdtemp(prefix="quality-")
os.makedirs(os.path.join(iso, ".dsh-meow"))
src = os.path.join(PROD, ".dsh-meow", "memory.db")
con = sqlite3.connect(src)
bak = sqlite3.connect(os.path.join(iso, ".dsh-meow", "memory.db"))
con.backup(bak)
bak.close()
con.close()
os.makedirs(os.path.join(iso, "tools", "dsh-memory-maint"), exist_ok=True)

env = dict(os.environ)
env.update({"DSH_MEMORY_WORKSPACE": iso, "DSH_MEMORY_LOG_DIR": os.path.join(iso, "state"),
            "PYTHONIOENCODING": "utf-8"})
mem = os.path.join(BASE, "py-core", "mem.py")

# 每个动作给一组"能触发实质输出"的参数
ARGS = {
    "agents": [], "agentsmem": [], "archive": [], "assets": ["dsh"],
    "audit": [], "changelog": [], "clear": [],          # clear 不带参数=只列不清 "daily": [],
    "decay": [], "dedup": [], "diag": [], "dream": [], "dump": [],
    "export": [], "file": ["备份"], "health": [], "help": [],
    "index": [], "integrity": [], "list": [], "map": [], "people": [],
    "project": ["dsh"], "promises": [], "quality": [], "refs": [],
    "restore": ["--verify", os.path.join(iso, "verify-target.db")],
    "sample": [], "signal": [], "source": [], "start": [], "status": ["status"],  # 组名和动作名都是 status
    "timeline": [], "weight2": [], "why": ["备份"],
}

good, suspect, empty = [], [], []
print("=== 逐个动作实测输出质量 ===")
for act in sorted(ARGS):
    r = subprocess.run([PY, mem, act, *ARGS[act]], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180, env=env)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    lines = [l for l in out.splitlines() if l.strip()]
    chars = len(out)

    if not out:
        empty.append((act, "无任何输出"))
        print("  ❌ %-12s 无输出" % act)
    elif chars < 80 or (len(lines) <= 2 and "用法：" in out):
        suspect.append((act, "%d 字 / %d 行：%s" % (chars, len(lines), lines[0][:50] if lines else "")))
        print("  ⚠ %-12s %d 字 / %d 行" % (act, chars, len(lines)))
    else:
        good.append(act)
        print("  ✅ %-12s %d 字 / %d 行" % (act, chars, len(lines)))

print("\n" + "=" * 56)
print("输出质量：✅ %d 有实质内容 / ⚠ %d 可疑 / ❌ %d 空" % (len(good), len(suspect), len(empty)))
if suspect:
    print("\n可疑（可能是用法提示或极简输出，需人工判断）：")
    for a, d in suspect:
        print("  ⚠ %-12s %s" % (a, d))
if empty:
    print("\n空输出：")
    for a, d in empty:
        print("  ❌ %-12s %s" % (a, d))
shutil.rmtree(iso, ignore_errors=True)
