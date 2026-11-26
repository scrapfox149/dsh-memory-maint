# -*- coding: utf-8 -*-
"""极限边界测试：构造各种"极端/罕见"环境，看插件是优雅失败还是裸崩。

判据：**退出码 0/1 + 有可读输出 = 通过**；**Traceback 指向自己脚本 + 退出码怪 = 失败**。

2026-11-26 第一版抓到 1 个真 bug：
  库文件损坏时 `audit` / `health` / `people` 的 `except Exception: continue`
  把「读不到」当成「这层是空的」→ 输出「审计范围：0 条」→ 退出码 0
  → 上层 `quality` 报「写法无必须修项」。**库坏了却报全绿**。
  修法：这三个脚本加 `except RuntimeError: raise`（库损坏往上抛）。
"""
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WS = r"C:\Users\24172\Documents\deepseek-harness\default-workspace"
BASE = os.path.join(WS, "tools", "dsh-memory-maint")
MEM = os.path.join(BASE, "py-core", "mem.py")
PY = sys.executable
TIERS = ["soul", "user", "project", "topic", "fact", "lesson", "rules"]

ok = bad = 0
fails = []


def chk(name, cond, detail=""):
    global ok, bad
    if cond:
        ok += 1
        print("  ✅ %s%s" % (name, ("  → " + detail) if detail else ""))
    else:
        bad += 1
        fails.append((name, detail))
        print("  ❌ %s%s" % (name, ("  → " + detail) if detail else ""))


def run(ws, *args, timeout=180, extra_env=None):
    env = dict(os.environ)
    env.update({"DSH_MEMORY_WORKSPACE": ws, "DSH_MEMORY_LOG_DIR": os.path.join(ws, ".state"),
                "PYTHONIOENCODING": "utf-8"})
    if extra_env:
        env.update(extra_env)
    try:
        r = subprocess.run([PY, MEM, *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, env=env)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"


def is_self_crash(rc, out):
    return (rc not in (0, 1)
            and "Traceback (most recent call last)" in out
            and bool(re.search(r'File ".*(py-core|modules)[\\/]', out)))


def bad_lib_msg(out):
    """输出里有没有"库读不了"的人话（RuntimeError / 损坏 / 不是 SQLite）。"""
    return bool(re.search(r"(记忆库损坏|不是 SQLite|无法读取|记忆库不存在|库损坏)", out))


def mkws(with_db=True, garbage=False):
    d = tempfile.mkdtemp(prefix="edge-")
    os.makedirs(os.path.join(d, "tools", "dsh-memory-maint"))
    os.makedirs(os.path.join(d, "docs"))
    open(os.path.join(d, "AGENTS.md"), "w", encoding="utf-8").write("# t\n")
    db = os.path.join(d, ".dsh-meow", "memory.db")
    os.makedirs(os.path.dirname(db))
    if garbage:
        open(db, "wb").write(b"this is not a database " * 100)
    elif with_db:
        con = sqlite3.connect(db)
        for t in TIERS:
            con.execute('CREATE TABLE "%s" (id TEXT PRIMARY KEY, content TEXT, status TEXT,'
                        ' project TEXT, importance INTEGER, keywords TEXT,'
                        ' created_at TEXT, updated_at TEXT)' % t)
        con.commit()
        con.close()
    return d, db


def insert(db, tier, rows):
    con = sqlite3.connect(db)
    for r in rows:
        con.execute('INSERT OR REPLACE INTO "%s" (id,content,status,project,importance,'
                    'keywords,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)' % tier, r)
    con.commit()
    con.close()


# ── ① 空库 ────────────────────────────────────────
print("=== ① 空库（0 条记忆）===")
d1, db1 = mkws()
ACTS = [("daily", []), ("quality", []), ("integrity", []), ("start", []), ("help", []),
        ("list", []), ("diag", []), ("status", ["status"]), ("agents", []), ("refs", []),
        ("promises", []), ("signal", []), ("source", []), ("audit", []), ("health", []),
        ("sample", []), ("archive", []), ("changelog", []), ("decay", []), ("dedup", []),
        ("dream", []), ("index", []), ("timeline", []), ("map", []), ("assets", ["dsh"]),
        ("project", ["dsh"]), ("people", []), ("why", ["备份"]), ("expand", ["备份"]),
        ("hipporag", ["备份"]), ("file", ["备份"]), ("hotfiles", ["--top", "2"]),
        ("dump", []), ("weight2", []), ("alert", ["list"]), ("clear", [])]
crashed = []
for act, args in ACTS:
    rc, out = run(d1, act, *args, timeout=120)
    if is_self_crash(rc, out):
        crashed.append(act)
chk("空库 36 个动作都不裸崩", not crashed, "崩了: %s" % crashed if crashed else "36 个都跑了")
shutil.rmtree(d1, ignore_errors=True)

# ── ② 库文件损坏 ──────────────────────────────────
print("\n=== ② 库文件损坏（不是 SQLite）===")
d2, db2 = mkws(garbage=True)
for act, _a in (("daily", []), ("quality", []), ("audit", []), ("health", []),
                ("people", []), ("project", ["dsh"]), ("dump", [])):
    rc, out = run(d2, act, *_a, timeout=120)
    chk("%-10s 损坏库给出可读错误" % act,
        (not is_self_crash(rc, out)) and bad_lib_msg(out),
        (out.strip().splitlines()[-1][:60] if out.strip() else "无输出"))
shutil.rmtree(d2, ignore_errors=True)

# ── ③ 库被独占锁 ─────────────────────────────────
print("\n=== ③ 库被独占锁 ===")
d3, db3 = mkws()
con = sqlite3.connect(db3, timeout=1)
con.execute("BEGIN EXCLUSIVE")
try:
    rc, out = run(d3, "daily", timeout=90)
    chk("daily 库被锁不裸崩", not is_self_crash(rc, out), "rc=%d" % rc)
finally:
    con.rollback()
    con.close()
    shutil.rmtree(d3, ignore_errors=True)

# ── ④ 路径错误 ────────────────────────────────────
print("\n=== ④ DSH_MEMORY_DB 指向目录 / 不存在 ===")
d4, db4 = mkws()
rc, out = run(d4, "daily", extra_env={"DSH_MEMORY_DB": os.path.dirname(db4)})
chk("指向目录给出可读提示", (not is_self_crash(rc, out)) and
    bool(re.search(r"(目录|不是文件|应该是|文件路径)", out)),
    (out.strip().splitlines()[-1][:70] if out.strip() else ""))
rc, out = run(d4, "daily", extra_env={"DSH_MEMORY_DB": os.path.join(d4, "nope", "x.db")})
chk("指向不存在的路径不裸崩", not is_self_crash(rc, out), "rc=%d" % rc)
shutil.rmtree(d4, ignore_errors=True)

# ── ⑤ 超长输入 ────────────────────────────────────
print("\n=== ⑤ 超长查询（10000 字）===")
d5, db5 = mkws()
insert(db5, "fact", [("e1", "备份怎么做" * 10, "active", "dsh", 2, "备份",
                      "2026-11-26", "2026-11-26")])
huge = "备份怎么写" * 2000
for act in ("why", "file", "expand"):
    t0 = time.time()
    rc, out = run(d5, act, huge, timeout=120)
    dt = time.time() - t0
    chk("%-8s 超长输入不裸崩" % act, not is_self_crash(rc, out), "%.1f 秒" % dt)
    chk("%-8s 超长输入 30 秒内" % act, dt < 30, "%.1f 秒" % dt)
shutil.rmtree(d5, ignore_errors=True)

# ── ⑥ 特殊字符 ────────────────────────────────────
print("\n=== ⑥ 特殊字符（emoji / 换行 / 控制字符 / 引号 / 注入）===")
d6, db6 = mkws()
insert(db6, "fact", [
    ("a1", "🎉🐟 备份 💾 emoji", "active", "dsh", 2, '["emoji"]', "2026-11-26", "2026-11-26"),
    ("a2", "第一行\n第二行\r\n第三行\t制表", "active", "dsh", 2, '["换行"]', "2026-11-26", "2026-11-26"),
    ("a3", "控制字符 \x01\x1f 结尾", "active", "dsh", 2, '["控制"]', "2026-11-26", "2026-11-26"),
    ("a4", "单引号 ' 双引号 \" 反斜杠 \\ 百分号 %", "active", "dsh", 2, '["引号"]', "2026-11-26", "2026-11-26"),
    ("a5", "'; DROP TABLE fact; --", "active", "dsh", 2, '["注入"]', "2026-11-26", "2026-11-26"),
])
for q in ("emoji", "单引号", "'; DROP TABLE fact; --", "控制字符"):
    rc, out = run(d6, "why", q, timeout=120)
    chk("why %-18s 不裸崩" % q[:16], not is_self_crash(rc, out), "rc=%d" % rc)
rc, out = run(d6, "dump", "--json", timeout=180)
chk("dump --json 含特殊字符仍可解析", out.strip().startswith("{"),
    out.strip()[:40].replace("\n", " "))
con = sqlite3.connect(db6)
n = con.execute("select count(*) from fact").fetchone()[0]
con.close()
chk("SQL 注入没删表（5 条还在）", n == 5, "现在 %d 条" % n)
shutil.rmtree(d6, ignore_errors=True)

# ── ⑦ 单条超大（约 1 MB）──────────────────────────
print("\n=== ⑦ 单条记忆约 1 MB ===")
d7, db7 = mkws()
big = "备份 " + ("很长的内容" * 140000)
insert(db7, "fact", [("b1", big, "active", "dsh", 2, '["超大"]', "2026-11-26", "2026-11-26")])
t0 = time.time()
rc, out = run(d7, "dump", timeout=180)
chk("dump 1MB 条目不裸崩", not is_self_crash(rc, out), "%.1f 秒" % (time.time() - t0))
rc, out = run(d7, "why", "备份", timeout=180)
chk("why 1MB 条目不裸崩", not is_self_crash(rc, out), "rc=%d" % rc)
chk("why 输出没被 1MB 撑爆", len(out) < 300000, "%d 字" % len(out))
shutil.rmtree(d7, ignore_errors=True)

# ── ⑧ 5000 条 ────────────────────────────────────
print("\n=== ⑧ 5000 条记忆 ===")
d8, db8 = mkws()
insert(db8, "fact", [("c%d" % i, "备份测试条目 %d 内容" % i, "active", "dsh", 2,
                      '["批量"]', "2026-11-26", "2026-11-26") for i in range(5000)])
for act in ("daily", "quality", "index", "dedup", "timeline", "map", "health"):
    t0 = time.time()
    rc, out = run(d8, act, timeout=300)
    dt = time.time() - t0
    chk("%-9s 5000 条不裸崩" % act, not is_self_crash(rc, out), "%.1f 秒" % dt)
    chk("%-9s 5000 条 120 秒内" % act, dt < 120, "%.1f 秒" % dt)
shutil.rmtree(d8, ignore_errors=True)

print("\n" + "=" * 60)
print("极限边界：%d 通过 / %d 失败 / 共 %d" % (ok, bad, ok + bad))
for n, d in fails:
    print("  ❌ %s  %s" % (n, d))
sys.exit(0 if bad == 0 else 1)
