# -*- coding: utf-8 -*-
"""从快照生成时间线文档（按天分组）。"""
import os
import json
import sys
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break
from paths import workspace_root  # noqa: E402
import time

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SNAP = os.path.join(workspace_root(), "tmp/memory-snapshot.json")
OUT = os.path.join(workspace_root(), "docs/memory-timeline.md")

with open(SNAP, encoding="utf-8") as f:
    items = json.load(f)

by_day = {}
for it in items:
    ts = (it["created_at"] or 0) / 1000.0
    day = time.strftime("%Y-%m-%d", time.localtime(ts))
    by_day.setdefault(day, []).append(it)

lines = ["# 记忆时间线（按创建日）", "",
         "> 由 tools/dsh-memory-maint/modules/feature/maint/py/memory-map-export.py + 本脚本生成。每条一行：层 · 项目 · 权重 · 内容摘要。", ""]
for day in sorted(by_day):
    day_items = sorted(by_day[day], key=lambda x: x["created_at"] or 0)
    lines.append("## %s（%d 条）" % (day, len(day_items)))
    lines.append("")
    for it in day_items:
        content = (it["content"] or "").replace("\n", " ")
        content = content[:70] + ("…" if len(content) > 70 else "")
        proj = it["project"] or "—"
        lines.append("- `%s` [%s · %s · w%s] %s" % (
            it["tier"], proj, it["id"][:8], it["importance"], content))
    lines.append("")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
print("天数:", len(by_day))
print("写入:", OUT)
