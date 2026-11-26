# -*- coding: utf-8 -*-
"""全量导出（含所有状态）+ 分层抽样，保证覆盖每个层/项目/权重/状态/时间段。"""
import json
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break

from paths import workspace_root  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collections import defaultdict

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from mem_db import DB, fetch  # 契约层统一（支持 DSH_MEMORY_DB 覆盖）
OUT = os.path.join(workspace_root(), "tmp/memory-all-status.json")
SAMPLE_OUT = os.path.join(workspace_root(), "tmp/memory-sample.json")
TIERS = ["soul", "user", "rules", "project", "topic", "fact", "lesson"]

items = []
for t in TIERS:
    # 契约层负责探列（下面这段只用于展示，取数走 fetch）
    cols_list = ["id", "title", "content", "keywords", "importance", "status",
                 "project", "subcategory", "created_at", "updated_at"]
    for row in fetch(t, cols_list):
        d = dict(zip(["id", "title", "content", "keywords", "importance", "status",
                      "project", "subcategory", "created_at", "updated_at"], row))
        d["tier"] = t
        d["project"] = d["project"] or "空"
        items.append(d)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(items, f, ensure_ascii=False, indent=1)

# 分层抽样：每个 (tier, project, importance) 组合按最近更新时间取一条，再按状态补
groups = defaultdict(list)
for it in items:
    groups[(it["tier"], it["project"], it["importance"], it["status"])].append(it)

sample = []
for key, group in sorted(groups.items()):
    group.sort(key=lambda x: x["updated_at"] or 0, reverse=True)
    sample.append(group[0])  # 每组取最新一条

# 再补：每组最老一条（时间覆盖）
old_sample = []
for key, group in groups.items():
    group.sort(key=lambda x: x["created_at"] or 0)
    if group and group[0] not in sample:
        old_sample.append(group[0])

with open(SAMPLE_OUT, "w", encoding="utf-8") as f:
    json.dump(sample + old_sample, f, ensure_ascii=False, indent=1)

print("全部条目（含非active）:", len(items))
print("组合数（层×项目×权重×状态）:", len(groups))
print("抽样条数:", len(sample) + len(old_sample))
print()
print("=== 组合分布 ===")
for key in sorted(groups):
    print("%-8s %-6s w%s %-8s → %d 条" % (key[0], key[1], key[2], key[3], len(groups[key])))
print()
print("结论：从 %d 种组合里抽了 %d 条（含 %d 条太久没碰的）"
      % (len(groups), len(sample) + len(old_sample), len(old_sample)))
