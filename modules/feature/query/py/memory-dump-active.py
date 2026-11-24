# -*- coding: utf-8 -*-
"""导出 174 条 active 全文，按层分组、分组内按 id 排序，供逐条通读。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break

from paths import workspace_root  # noqa: E402
if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from mem_db import DB, fetch  # 契约层统一（支持 DSH_MEMORY_DB 覆盖）
OUT = os.path.join(workspace_root(), "tmp/active-full.txt")
TIERS = ["soul", "user", "rules", "project", "topic", "fact", "lesson"]

lines = []
count = 0
for t in TIERS:
    # 契约层负责探列 + 缺列补 None + 坏库上报
    rows = fetch(t, ["id", "content", "keywords", "importance", "project", "subcategory"],
                 status="active")
    lines.append("\n########## %s（%d 条）##########" % (t, len(rows)))
    for i, (iid, content, kws, imp, proj, sub) in enumerate(rows, 1):
        count += 1
        lines.append("\n[%s-%02d] w%s proj=%s%s" % (t[:4], i, imp, proj or "空", (" sub=" + sub) if sub else ""))
        lines.append("内容: " + (content or "").replace("\n", " "))
        lines.append("关键词: " + (kws or ""))
with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("active 条数:", count)
print("写入:", OUT)
