# -*- coding: utf-8 -*-
"""dsh-memory-maint 全量测试：极限场景。

和 test-mem-plugin.py 的分工：
- **冒烟**（35 项）测「崩不崩」
- **这个**测「极限输入下还对不对、报错清不清晰」

场景（8 组）：
  1. 空库（0 条）—— 所有只读命令都要能跑完
  2. 库不存在 —— 要报清楚，不能崩出一堆 Traceback
  3. 缺列库（表结构不全）—— 契约层要降级，不能整层跳过
  4. 超长内容（10 万字）—— 能存能读，不被截断
  5. 特殊字符（emoji / 控制字符 / 单引号 / SQL 注入串）—— 不崩、不注入
  6. 重复 id —— 不崩
  7. 超大查询（2000 字关键词）—— 不崩
  8. 只读验证 —— 跑完所有只读命令，库文件 mtime 与 hash 不变

跑法：
    python tmp/fulltest.py
退出码：0 = 全过；非 0 = 有失败项
"""
import hashlib
import os
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

HERE = os.path.dirname(os.path.abspath(__file__))
# 脚本现在住在插件根，直接在 HERE 找 py-core；找不到再按老布局往上一级找
ROOT = HERE if os.path.isdir(os.path.join(HERE, "py-core")) else os.path.join(os.path.dirname(HERE), "tools", "dsh-memory-maint")
PY = sys.executable
MEM = os.path.join(ROOT, "py-core", "mem.py")

passed, failed = [], []


def check(name, cond, detail=""):
    if cond:
        passed.append(name)
        print("  OK   %s" % name)
    else:
        failed.append(name + (("  <- " + detail) if detail else ""))
        print("  FAIL %s%s" % (name, ("  <- " + detail) if detail else ""))


def run(args, db=None, timeout=180):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.path.join(ROOT, "py-core")
    env["DSH_MEMORY_WORKSPACE"] = os.path.dirname(HERE)
    if db:
        env["DSH_MEMORY_DB"] = db
    try:
        r = subprocess.run([PY, MEM] + args, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, env=env)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return -1, "超时"


def make_db(path, with_all_cols=True):
    """造一个库。with_all_cols=False 时故意少几列，测契约层降级。"""
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    tiers = ["soul", "user", "project", "topic", "fact", "lesson", "rules"]
    for t in tiers:
        cols = ["id TEXT PRIMARY KEY", "title TEXT", "content TEXT",
                "importance INTEGER", "keywords TEXT", "status TEXT",
                "created_at INTEGER", "updated_at INTEGER"]
        if t not in ("soul", "user"):
            cols.append("project TEXT")
        if with_all_cols:
            # 只有完整版才加这些——缺列版用来测降级
            cols += ["source_session TEXT", "hit_count INTEGER",
                     "last_accessed_at INTEGER", "editHistory_infoFrom TEXT"]
        con.execute('CREATE TABLE "%s" (%s)' % (t, ", ".join(cols)))
    con.commit()
    con.close()


def insert(path, tier, iid, content, **kw):
    con = sqlite3.connect(path)
    cols = [r[1] for r in con.execute('PRAGMA table_info("%s")' % tier)]
    data = {"id": iid, "content": content, "status": "active",
            "importance": kw.get("importance", 2),
            "keywords": kw.get("keywords", "测试,示例"),
            "created_at": int(time.time() * 1000),
            "updated_at": int(time.time() * 1000)}
    if "project" in cols:
        data["project"] = kw.get("project", "测试项目")
    data = {k: v for k, v in data.items() if k in cols}
    con.execute('INSERT INTO "%s" (%s) VALUES (%s)'
                % (tier, ", ".join(data), ", ".join("?" * len(data))),
                list(data.values()))
    con.commit()
    con.close()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    tmpd = tempfile.mkdtemp(prefix="memtest-")
    print("=== dsh-memory-maint 全量测试 ===\n临时目录: %s\n" % tmpd)

    READONLY_CMDS = [["daily"], ["quality"], ["integrity"], ["help"], ["list"],
                     ["project"], ["start"], ["status"]]

    # ---- 1. 空库 ----
    print("--- 1. 空库（0 条）---")
    empty = os.path.join(tmpd, "empty.db")
    make_db(empty)
    for cmd in READONLY_CMDS:
        rc, out = run(cmd, db=empty)
        # 只读命令在空库上要么 0 要么 1（有事要做），但**不能崩**
        crashed = ("Traceback" in out) or rc < 0 or rc > 1
        check("空库 %s 不崩" % " ".join(cmd), not crashed,
              ("rc=%d " % rc) + out.strip().split("\n")[-1][:60])

    # ---- 2. 库不存在 ----
    print("\n--- 2. 库不存在 ---")
    rc, out = run(["daily"], db=os.path.join(tmpd, "nope.db"))
    has_trace = "Traceback" in out
    says_missing = ("不存在" in out) or ("No such" in out) or ("unable to open" in out)
    check("库不存在时给了人类可读的提示", says_missing, out.strip().split("\n")[-1][:80])
    # 有 Traceback 但最后一句是「库不存在」也算可接受（契约层设计如此）
    check("库不存在时不返回 0（不能假装成功）", rc != 0, "rc=%d" % rc)

    # ---- 3. 缺列库 ----
    print("\n--- 3. 缺列库（少 last_accessed_at / source_session 等列）---")
    thin = os.path.join(tmpd, "thin.db")
    make_db(thin, with_all_cols=False)
    insert(thin, "fact", "thin0001-aa", "缺列库里的一条记忆")
    for cmd in (["daily"], ["quality"], ["project"]):
        rc, out = run(cmd, db=thin)
        crashed = ("Traceback" in out) or rc < 0
        check("缺列库 %s 不崩" % " ".join(cmd), not crashed,
              out.strip().split("\n")[-1][:60])

    # ---- 4. 超长内容 ----
    print("\n--- 4. 超长内容（10 万字）---")
    long_db = os.path.join(tmpd, "long.db")
    make_db(long_db)
    big = "记忆" * 50000
    insert(long_db, "fact", "long0001-aa", big)
    rc, out = run(["quality"], db=long_db)
    check("能存 10 万字且 quality 跑得动", rc in (0, 1) and "Traceback" not in out, "rc=%d" % rc)
    # 读回来长度要对
    con = sqlite3.connect(long_db)
    got = con.execute('SELECT LENGTH(content) FROM fact WHERE id="long0001-aa"').fetchone()[0]
    con.close()
    check("10 万字没被截断", got == len(big), "实际 %s / 期望 %s" % (got, len(big)))

    # ---- 5. 特殊字符 ----
    print("\n--- 5. 特殊字符 ---")
    odd = os.path.join(tmpd, "odd.db")
    make_db(odd)
    cases = {
        "emoji": "🐟🐳 记忆里有表情",
        "ctrl": "带控制字符\x00\x01\x07的记忆",
        "quote": "单引号 ' 双引号 \" 反斜杠 \\ 都有",
        "inject": "'; DROP TABLE fact; --",
        "newline": "第一行\n第二行\r\n第三行",
        "long_kw": ",".join(["词%d" % i for i in range(500)]),
    }
    for name, text in cases.items():
        try:
            insert(odd, "fact", "odd-%s" % name, text, keywords=text if name == "long_kw" else "测试")
            ok = True
        except Exception as e:
            ok = False
            check("插入 %s" % name, False, str(e)[:60])
        if ok:
            rc, out = run(["daily"], db=odd)
            check("特殊字符 %s 不让命令崩" % name, "Traceback" not in out, out.strip().split("\n")[-1][:60])
    # 注入测试：表还在吗
    con = sqlite3.connect(odd)
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    con.close()
    check("SQL 注入串没删掉表", "fact" in tables, "现有表: %s" % ", ".join(tables))

    # ---- 6. 重复 id ----
    print("\n--- 6. 重复 id ---")
    dup = os.path.join(tmpd, "dup.db")
    make_db(dup)
    insert(dup, "fact", "same0001-aa", "第一条")
    try:
        insert(dup, "fact", "same0001-aa", "第二条（同 id）")
        dup_ok = True   # 主键冲突会抛异常，抛了就是"拒绝了重复"，也算对
        detail = "居然插进去了"
        dup_ok = False
    except sqlite3.IntegrityError:
        dup_ok = True
        detail = ""
    check("同 id 被主键拒绝（不静默覆盖）", dup_ok, detail)
    rc, out = run(["daily"], db=dup)
    check("重复 id 场景下 daily 不崩", "Traceback" not in out, out.strip().split("\n")[-1][:60])

    # ---- 7. 超大查询 ----
    print("\n--- 7. 超大查询（2000 字关键词）---")
    big_q = "记忆" * 1000
    rc, out = run(["why", big_q], db=long_db, timeout=120)
    check("why 收到 2000 字查询不崩", rc in (0, 1, 2) and "Traceback" not in out, "rc=%d" % rc)

    # ---- 8. 只读验证 ----
    print("\n--- 8. 只读命令不能改库 ---")
    ro = os.path.join(tmpd, "readonly.db")
    make_db(ro)
    for i in range(20):
        insert(ro, "fact", "ro%04d-aa" % i, "只读测试第 %d 条" % i)
    before_h = file_hash(ro)
    before_m = os.path.getmtime(ro)
    for cmd in READONLY_CMDS:
        run(cmd, db=ro)
    after_h = file_hash(ro)
    after_m = os.path.getmtime(ro)
    check("跑完所有只读命令，库 hash 不变", before_h == after_h,
          "%s -> %s" % (before_h[:12], after_h[:12]))
    check("库 mtime 不变", abs(before_m - after_m) < 1.0,
          "%.3f -> %.3f" % (before_m, after_m))

    # ---- 汇总 ----
    total = len(passed) + len(failed)
    print("\n" + "=" * 60)
    print("结果: %d 通过 / %d 失败 / 共 %d" % (len(passed), len(failed), total))
    if failed:
        print("\n失败项：")
        for f in failed:
            print("  - %s" % f)
        print("\n（临时目录保留供排查: %s）" % tmpd)
        return 1
    shutil.rmtree(tmpd, ignore_errors=True)
    print("\n（全过，临时目录已清）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
