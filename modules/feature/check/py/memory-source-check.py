# -*- coding: utf-8 -*-
"""社交来源检查：找出提及他人、但没标清来源的记忆（只读）。

来源标记约定（2026-11-13）：
- 用户原话：「……」
- 用户的事：……
- 离瞳转达：……
- 离瞳转述[某人]：……
- 大肥鱼说：……
"""
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
TIERS = ["project", "topic", "fact", "lesson", "user", "rules", "soul"]

# 提到第三方
MENTION = re.compile(r"离瞳|大肥鱼|年轻人|群里|群友|朋友|同事")
# 有来源标记
SOURCE = re.compile(r"用户原话|用户说|用户转达|离瞳转达|离瞳说|离瞳转述|大肥鱼说|大肥鱼给|转述|听说|据.{0,8}说|本人说")
bad = []
for t in TIERS:
    try:
        for iid, content, status in fetch(t, ["id", "content", "status"], status="active"):
            c = content or ""
            if MENTION.search(c) and not SOURCE.search(c):
                bad.append((t, iid, c))
    except Exception:
        import traceback, os as _os, sys as _sys
        try:
            from mem_db import report_exception as _rep_exc
            _rep_exc(_os.path.basename(__file__), traceback.format_exc()[-400:])
        except Exception:
            pass
        continue

print("提及他人但没有来源标记:", len(bad), "条")
print()
for t, iid, c in bad[:20]:
    print("[%s] %s" % (t, c[:90].replace("\n", " ")))
    print("      %s" % iid[:14])
