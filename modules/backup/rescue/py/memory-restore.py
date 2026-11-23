# -*- coding: utf-8 -*-
"""从 memory-export/memory-all.json 恢复到指定 SQLite 库（演练/重建用）。

用法：
  python memory-restore.py <目标库路径>
  python memory-restore.py --verify   # 恢复到 tmp/restore-test.db 并校验条数
不覆盖活库——目标必须显式指定。
"""
import json
import os
import sqlite3
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 【自包含】源路径可覆盖，方便在别的机器上恢复
SRC = (os.environ.get("DSH_MEMORY_EXPORT_DIR")
       or r"C:\Users\24172\Documents\deepseek-harness\default-workspace\memory-export")
SRC = os.path.join(SRC, "memory-all.json")
LIVE = r"C:\Users\24172\Documents\deepseek-harness\default-workspace\.dsh-meow\memory.db"
DEFAULT_TEST = r"C:\Users\24172\Documents\deepseek-harness\default-workspace\tmp\restore-test.db"

TIERS = ["soul", "user", "rules", "project", "topic", "fact", "lesson"]


def restore(target):
    data = json.load(open(SRC, encoding="utf-8"))
    tiers = data.get("tiers", {})

    if os.path.exists(target):
        os.remove(target)
    con = sqlite3.connect(target)
    total = 0
    for t in TIERS:
        rows = tiers.get(t, [])
        if not rows:
            continue
        cols = []
        for r in rows:
            for k in r:
                if k not in cols:
                    cols.append(k)
        col_sql = ", ".join('"%s"' % c for c in cols)
        con.execute('create table "%s" (%s)' % (t, col_sql))
        for r in rows:
            vals = [r.get(c) for c in cols]
            con.execute(
                'insert into "%s" values (%s)' % (t, ",".join("?" * len(cols))), vals
            )
        total += len(rows)
        print("  %-8s %d" % (t, len(rows)))
    con.commit()
    con.close()
    return total, data.get("counts", {})


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        target = DEFAULT_TEST
    elif len(sys.argv) > 1:
        target = sys.argv[1]
        if os.path.abspath(target) == os.path.abspath(LIVE):
            print("拒绝覆盖活库：", LIVE)
            return 2
    else:
        print("用法：memory-restore.py <目标库> | --verify")
        return 1

    print("恢复目标：", target)
    total, counts = restore(target)
    print("恢复总条数：", total)

    if sys.argv[1] == "--verify":
        expected = sum(counts.values()) if counts else None
        ok = expected is None or total == expected
        print("导出时记录条数：", expected)
        print("校验：", "通过" if ok else "不一致")
        return 0 if ok else 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
