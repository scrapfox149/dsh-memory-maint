# -*- coding: utf-8 -*-
"""补充验：上一轮 verify-badinput 没覆盖的几种坏输入。
   paths.* 填坏 / checklist 指向不存在 / 库里的脏数据 / 路径超长"""
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
ok, warn, bad = [], [], []


def check(name, level, detail=""):
    ({"ok": ok, "warn": warn, "bad": bad}[level]).append(name)
    print("  %s %s%s" % ({"ok": "✅", "warn": "⚠", "bad": "❌"}[level], name,
                        ("  → " + detail) if detail else ""))


def self_crashed(out, rc):
    if rc in (0, 1):
        return False
    if "Traceback (most recent call last)" not in out:
        return False
    import re
    return re.search(r'File ".*(py-core|modules)[\\/]', out) is not None


def fresh(tag, copy_db=True):
    iso = tempfile.mkdtemp(prefix="bad2-%s-" % tag)
    os.makedirs(os.path.join(iso, ".dsh-meow"))
    if copy_db:
        src = os.path.join(PROD, ".dsh-meow", "memory.db")
        if os.path.exists(src):
            con = sqlite3.connect(src)
            bak = sqlite3.connect(os.path.join(iso, ".dsh-meow", "memory.db"))
            con.backup(bak)
            bak.close()
            con.close()
    os.makedirs(os.path.join(iso, "tools", "dsh-memory-maint"), exist_ok=True)
    return iso


def run(iso, *args):
    r = subprocess.run([PY, os.path.join(BASE, "py-core", "mem.py"), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120,
                       env={**os.environ, "DSH_MEMORY_WORKSPACE": iso,
                            "DSH_MEMORY_LOG_DIR": os.path.join(iso, "state"),
                            "PYTHONIOENCODING": "utf-8"})
    return ((r.stdout or "") + (r.stderr or "")), r.returncode


def write_cfg(iso, cfg):
    io.open(os.path.join(iso, "tools", "dsh-memory-maint", "config.json"), "w",
            encoding="utf-8").write(json.dumps(cfg, ensure_ascii=False, indent=2))


print("=== ① paths.* 填坏 ===")
iso = fresh("paths")
write_cfg(iso, {"paths": {"archives": ["不存在的目录", "afile"], "snapshotDir": "nope",
                          "historyDir": "", "backupLog": None}})
io.open(os.path.join(iso, "afile"), "w").write("x")
out, rc = run(iso, "agents")
check("paths 填不存在的/文件/空/None", "bad" if self_crashed(out, rc) else "ok",
      (out.strip().splitlines()[-1] if out.strip() else "")[:60])
shutil.rmtree(iso, ignore_errors=True)

print("\n=== ② start.checklist 指向不存在的文件 ===")
iso = fresh("checklist")
write_cfg(iso, {"start": {"checklist": "不存在的清单.md"}})
out, rc = run(iso, "start")
check("checklist 指向不存在的文件", "bad" if self_crashed(out, rc) else "ok",
      "有默认兜底" if "四问" in out else "没显示清单")
shutil.rmtree(iso, ignore_errors=True)

print("\n=== ③ 库里的脏数据 ===")
iso = fresh("dirty")
dbp = os.path.join(iso, ".dsh-meow", "memory.db")
con = sqlite3.connect(dbp)
cols = [r[1] for r in con.execute('pragma table_info("fact")')]
print("   fact 表的列: %s" % ", ".join(cols))
if "project" in cols and "content" in cols:
    # NULL project / 超长 content / 特殊字符 / 非法 JSON keywords
    # （created_at 是 NOT NULL，必须给）
    import time as _t
    now = int(_t.time() * 1000)
    rows = [
        ("dirty-1", "x" * 100000, None, "不是JSON", 99, "active"),
        ("dirty-2", "", "", "", -5, "weird-status"),
        ("dirty-3", "带 '单引号' 和 \"双引号\" 和 emoji 🐟 和 %s", "dsh", '["a"]', 2, "active"),
    ]
    for rid, content, project, kw, imp, st in rows:
        con.execute(
            'insert into "fact" (id, content, project, keywords, importance, status, created_at, updated_at) '
            'values (?,?,?,?,?,?,?,?)',
            (rid, content, project, kw, imp, st, now, now))
    con.commit()
con.close()
for cmd in (["daily"], ["project", "dsh", "--json"], ["dump", "--json"], ["quality"]):
    out, rc = run(iso, *cmd)
    label = " ".join(cmd)
    if self_crashed(out, rc):
        check("脏数据 + %s" % label, "bad", "崩了")
    elif cmd[0] == "dump":
        try:
            json.loads(out)
            check("脏数据 + %s" % label, "ok", "JSON 仍合法")
        except Exception as e:
            check("脏数据 + %s" % label, "warn", "JSON 坏了: %s" % str(e)[:40])
    else:
        check("脏数据 + %s" % label, "ok", "rc=%d" % rc)
shutil.rmtree(iso, ignore_errors=True)

print("\n=== ④ 路径超长（Windows 260 限制）===")
iso = fresh("longpath")
longname = "a" * 300
write_cfg(iso, {"assets": {"proj": [longname]}})
out, rc = run(iso, "assets", "proj")
check("assets 路径超长", "bad" if self_crashed(out, rc) else "ok",
      (out.strip().splitlines()[-1] if out.strip() else "")[:60])
shutil.rmtree(iso, ignore_errors=True)

print("\n" + "=" * 56)
print("补充坏输入：✅ %d 正常 / ⚠ %d 需注意 / ❌ %d 崩了" % (len(ok), len(warn), len(bad)))
for w in warn:
    print("  ⚠ " + w)
for b in bad:
    print("  ❌ " + b)
sys.exit(0 if not bad else 1)
