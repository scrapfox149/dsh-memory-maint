# -*- coding: utf-8 -*-
"""约定/提醒扫描：从 todo 类记忆里解析期限，输出临期与已过期（只读）。

约定写法（写记忆时遵守）：
- 在 project 层 subcategory=todo，或任意层但内容含「期限：YYYY-MM-DD」
- 形如「期限：2026-11-20」或「截止 2026-11-20」
"""
import datetime
import os
import re

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from mem_db import DB, fetch  # 契约层统一（支持 DSH_MEMORY_DB 覆盖）
TIERS = ["project", "fact", "lesson", "topic", "rules", "user"]
DATE_RE = re.compile(r"(?:期限|截止|到期)[:：\s]*(\d{4}-\d{2}-\d{2})")

today = datetime.date.today()
rows = []
for t in TIERS:
    try:
        for iid, content, status, imp in fetch(t, ["id", "content", "status", "importance"],
                                               status="active"):
            m = DATE_RE.search(content or "")
            if not m:
                continue
            due = datetime.datetime.strptime(m.group(1), "%Y-%m-%d").date()
            days = (due - today).days
            rows.append((days, due, t, iid, imp, content))
    except Exception:
        import traceback, os as _os, sys as _sys
        try:
            from mem_db import report_exception as _rep_exc
            _rep_exc(_os.path.basename(__file__), traceback.format_exc()[-400:])
        except Exception:
            pass
        continue

rows.sort(key=lambda x: x[0])
if not rows:
    print("没有带期限的约定（写约定时在 content 里加「期限：YYYY-MM-DD」即可被扫到）")
    sys.exit(0)

print("今天:", today, "| 带期限的约定:", len(rows), "条")
print()
for days, due, t, iid, imp, content in rows:
    if days < 0:
        tag = "已过期 %d 天" % (-days)
    elif days == 0:
        tag = "今天到期"
    elif days <= 3:
        tag = "剩 %d 天" % days
    else:
        tag = "剩 %d 天" % days
    print("[%s] %s | %s" % (tag, due, (content or "")[:70].replace("\n", " ")))
    print("      %s %s" % (t, iid[:12]))
