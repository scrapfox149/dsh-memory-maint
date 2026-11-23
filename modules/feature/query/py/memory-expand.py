# -*- coding: utf-8 -*-
"""记忆关系展开：给一条记忆（或关键词），找出它的关联集，按"关系强度 × 时间衰减"排序。

用途：补 top-2 的不足——命中的条目只是入口，顺着它展开能看到关联的其他条目。
时间衰减：太久没动过的沉下去（不主动出现），但 memory_search 仍能查到。
"""
import json
import math
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
import time

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from decay import decay_of as _u_decay
from mem_db import DB, fetch  # 契约层统一（支持 DSH_MEMORY_DB 覆盖）
TIERS = ["soul", "user", "rules", "project", "topic", "fact", "lesson"]
DAY = 86400.0
# 半衰期（天）：承诺/重要类 180，其余 14
HALF_LIFE_HIGH = 180.0
HALF_LIFE_DEFAULT = 14.0


def now_ms():
    return time.time() * 1000.0


def tokenize(s):
    s = re.sub(r"\s+", "", s or "")
    return set(s[i:i + 2] for i in range(len(s) - 1))


def decay_of(updated, importance):
    """委托 py-core/decay.py（2026-11-19 统一）"""
    return _u_decay(updated, importance, now_ms())


def load_all():
    items = []
    for t in TIERS:
        try:
            for iid, content, kws, imp, upd, status in fetch(t, ["id", "content", "keywords", "importance", "updated_at", "status"]):
                if status != "active":
                    continue
                items.append({
                    "tier": t, "id": iid, "content": content or "",
                    "kw": kws or "", "imp": imp or 1, "upd": upd,
                })
        except Exception:
            import traceback, os as _os, sys as _sys
            try:
                from mem_db import report_exception as _rep_exc
                _rep_exc(_os.path.basename(__file__), traceback.format_exc()[-400:])
            except Exception:
                pass
            continue
    return items


def expand(seed_text, top=8, min_decay=0.02):
    items = load_all()
    seed_tokens = tokenize(seed_text)
    if not seed_tokens:
        return []

    # 关系强度 = 词重叠 + 正文里出现的 id 片段
    scored = []
    for it in items:
        body_tokens = tokenize(it["content"] + " " + it["kw"])
        overlap = len(seed_tokens & body_tokens)
        if overlap == 0:
            continue
        # 关系强度：重叠数 × 层权重（topic 是枢纽，加权）
        tier_w = {"topic": 1.4, "rules": 1.2, "project": 1.1}.get(it["tier"], 1.0)
        rel = overlap * tier_w
        d = decay_of(it["upd"], it["imp"])
        score = rel * d
        scored.append((score, d, it))

    scored.sort(reverse=True, key=lambda x: x[0])
    # 衰减过低的不主动出现
    return [(s, d, it) for s, d, it in scored if d >= min_decay][:top]


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "备份体系"
    print("入口：", q)
    print()
    for score, d, it in expand(q, top=8):
        print("%.3f (decay %.2f) [%s] %s" % (score, d, it["tier"], it["id"][:12]))
        print("   ", it["content"][:90].replace("\n", " "))
