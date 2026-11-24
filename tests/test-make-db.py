# -*- coding: utf-8 -*-
"""造一个和真实记忆库结构对齐的空库，给测试用。

为什么单独成文件（2026-11-24）：写进 GitHub Actions 的 `shell: python` 块里时，
heredoc 的处理方式和 bash 不同，CI 上直接失败。落成脚本两边都能跑。

结构要点（与 meow-memory 真实库对齐）：
- **soul / user 没有 project 列** —— 2026-11-18 就是因为这个，
  `memory-index` 的 `select ... project` 抛异常被 `except: continue` 吞掉，
  整层静默少读 34 条，几个月没发现。CI 里不能再造一个错误的库。
- rules/project/topic/fact/lesson 有 project；project 另有 subcategory；topic 有 goal

用法：
    python test-make-db.py [目标路径]      # 默认 tmp/test-empty.db
"""
import os
import sqlite3
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TIERS = ("soul", "user", "rules", "project", "topic", "fact", "lesson")

BASE_COLS = [
    ("id", "TEXT"), ("title", "TEXT"), ("content", "TEXT"),
    ("importance", "INTEGER"), ("keywords", "TEXT"), ("status", "TEXT"),
    ("source_session", "TEXT"), ("hit_count", "INTEGER"),
    ("created_at", "INTEGER"), ("updated_at", "INTEGER"),
    ("last_accessed_at", "INTEGER"),
]


def make(target):
    d = os.path.dirname(os.path.abspath(target))
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    if os.path.exists(target):
        os.unlink(target)

    con = sqlite3.connect(target)
    for tier in TIERS:
        cols = list(BASE_COLS)
        if tier not in ("soul", "user"):        # ← 关键：这两层没有 project
            cols.append(("project", "TEXT"))
        if tier == "project":
            cols.append(("subcategory", "TEXT"))
        if tier == "topic":
            cols.append(("goal", "TEXT"))
        if tier == "fact":
            cols.append(("editHistory_infoFrom", "TEXT"))
        ddl = ", ".join('"%s" %s' % (c, t) for c, t in cols)
        con.execute('CREATE TABLE "%s" (%s)' % (tier, ddl))
    con.commit()
    con.close()
    return target


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join("tmp", "test-empty.db")
    p = make(target)
    n = sqlite3.connect(p).execute(
        "select count(*) from sqlite_master where type='table'").fetchone()[0]
    print("空库就绪：%s（%d 张表）" % (p, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
