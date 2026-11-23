# -*- coding: utf-8 -*-
"""全量导出记忆（只读）：时间线 + 权重分布 + 关系候选。"""
import json
import os
import sqlite3
import sys

_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import time

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from mem_db import DB, fetch  # 契约层统一（支持 DSH_MEMORY_DB 覆盖）
TIERS = ["soul", "user", "rules", "project", "topic", "fact", "lesson"]
OUT = r"C:\Users\24172\Documents\deepseek-harness\default-workspace\tmp\memory-snapshot.json"

items = []
FIELDS = ["id", "title", "content", "keywords", "importance", "status",
          "project", "subcategory", "goal", "created_at", "updated_at", "corrected"]
for t in TIERS:
    for row in fetch(t, FIELDS):
        d = dict(zip(["id", "title", "content", "keywords", "importance", "status",
                      "project", "subcategory", "goal", "created_at", "updated_at", "corrected"], row))
        if d["status"] != "active":
            continue
        d["tier"] = t
        items.append(d)
items.sort(key=lambda x: (x["created_at"] or 0))
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(items, f, ensure_ascii=False, indent=1)

# 统计
print("active 条目总数:", len(items))
print()
from collections import Counter
print("按层:", dict(Counter(x["tier"] for x in items)))
print("按项目:", dict(Counter(x["project"] or "(空)" for x in items)))
print("按重要性:", dict(sorted(Counter(x["importance"] for x in items).items())))
print()
if items:
    t0 = time.strftime("%Y-%m-%d %H:%M", time.localtime((items[0]["created_at"] or 0) / 1000))
    t1 = time.strftime("%Y-%m-%d %H:%M", time.localtime((items[-1]["created_at"] or 0) / 1000))
    print("时间跨度:", t0, "→", t1)
print("导出的快照:", OUT)
