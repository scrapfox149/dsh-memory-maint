# -*- coding: utf-8 -*-
"""验 issue #12：`mem_query` 的所有动作是否都支持 `--json`（输出是合法 JSON）。

判据：
  ✅ 输出能整段 json.loads
  ⏭ 不适用（不需要 --json 的动作，如 dump 之外的纯文本工具）
  ❌ 传了 --json 但输出不是 JSON
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

iso = tempfile.mkdtemp(prefix="jsonchk-")
os.makedirs(os.path.join(iso, ".dsh-meow"))
con = sqlite3.connect(os.path.join(PROD, ".dsh-meow", "memory.db"))
bak = sqlite3.connect(os.path.join(iso, ".dsh-meow", "memory.db"))
con.backup(bak)
bak.close()
con.close()
os.makedirs(os.path.join(iso, "tools", "dsh-memory-maint"), exist_ok=True)

env = dict(os.environ)
env.update({"DSH_MEMORY_WORKSPACE": iso, "DSH_MEMORY_LOG_DIR": os.path.join(iso, "state"),
            "PYTHONIOENCODING": "utf-8"})
mem = os.path.join(BASE, "py-core", "mem.py")

# mem_query 的 8 个动作 + 各自的参数
QUERY_ACTS = {
    "expand": ["备份"],
    "hipporag": ["备份"],
    "file": ["备份"],
    "dump": [],
    "people": [],
    "why": ["备份"],
    "project": ["dsh"],
    "assets": ["dsh"],
}

ok, bad = [], []
for act, args in QUERY_ACTS.items():
    r = subprocess.run([PY, mem, act, *args, "--json"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180, env=env)
    out = (r.stdout or "")
    try:
        json.loads(out)
        ok.append(act)
        print("  ✅ %-10s JSON 合法（%d 字）" % (act, len(out)))
    except Exception as e:
        bad.append((act, str(e)[:50]))
        print("  ❌ %-10s %s" % (act, str(e)[:50]))

print("\n" + "=" * 52)
print("mem_query 的 --json 覆盖：%d/%d" % (len(ok), len(QUERY_ACTS)))
if bad:
    for a, why in bad:
        print("  ❌ " + a + "：" + why)
shutil.rmtree(iso, ignore_errors=True)
sys.exit(0 if not bad else 1)
