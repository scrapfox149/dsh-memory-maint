# -*- coding: utf-8 -*-
"""HippoRAG 风格的多跳记忆检索：种子 + Personalized PageRank。

做法：
1. 用查询词给每条记忆打分（bigram + IDF），取 top-N 当种子
2. 在「共享稀有词」构成的图上做 PPR（随机游走 + 传送回种子）
3. 输出收敛后权重最高的条目——包含 1 跳找不到的间接相关条目

与 memory-expand 的区别：expand 只看 1 跳词重叠；这里能走到 2-3 跳。
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
from collections import Counter

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from decay import decay_of as _u_decay
from text import bigrams as _u_bigrams
from mem_db import DB, fetch  # 契约层统一（支持 DSH_MEMORY_DB 覆盖）
TIERS = ["soul", "user", "rules", "project", "topic", "fact", "lesson"]
DAY_MS = 86400000.0


def tokenize(s):
    """委托 py-core/text.py（2026-11-19 统一）"""
    return _u_bigrams(s)


def now_ms():
    return time.time() * 1000.0


def decay_of(updated, importance):
    hl = 180.0 if (importance or 1) >= 3 else 14.0
    if not updated:
        return 0.0
    return 0.5 ** (max((now_ms() - float(updated)) / DAY_MS, 0.0) / hl)


def load():
    items = []
    for t in TIERS:
        try:
            for iid, content, kws, imp, upd in fetch(t, ["id", "content", "keywords", "importance", "updated_at"], status="active"):
                items.append({
                    "id": iid, "tier": t, "content": content or "",
                    "imp": imp or 1, "upd": upd,
                    "tok": tokenize((content or "") + " " + (kws or "")),
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


def ppr(seed_scores, adj, alpha=0.15, iters=20):
    """Personalized PageRank：alpha 是传送回种子的概率。"""
    nodes = list(adj.keys())
    total_seed = sum(seed_scores.values()) or 1.0
    seed_norm = {n: seed_scores.get(n, 0.0) / total_seed for n in nodes}
    rank = dict(seed_norm)
    for _ in range(iters):
        nxt = {n: 0.0 for n in nodes}
        for n in nodes:
            if rank[n] == 0:
                continue
            neighbors = adj[n]
            wsum = sum(neighbors.values()) or 1.0
            for m, w in neighbors.items():
                nxt[m] += (1 - alpha) * rank[n] * (w / wsum)
        for n in nodes:
            nxt[n] += alpha * seed_norm[n]
        rank = nxt
    return rank


def run(query, top=8):
    items = load()
    q_tok = tokenize(query)
    if not q_tok:
        return []

    # IDF
    df = Counter()
    for it in items:
        for t in it["tok"]:
            df[t] += 1
    N = len(items)
    idf = {t: math.log(N / (1 + c)) for t, c in df.items()}

    by_id = {it["id"]: it for it in items}

    # 种子：查询与条目的稀有词重叠
    seed = {}
    for it in items:
        common = q_tok & it["tok"]
        if not common:
            continue
        s = sum(idf.get(t, 0) for t in common) * (1.0 + 0.3 * (it["imp"] - 1))
        if s > 0:
            seed[it["id"]] = s

    # 图：共享至少 2 个稀有词的条目互连
    adj = {it["id"]: {} for it in items}
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            common = a["tok"] & b["tok"]
            if not common:
                continue
            rare = [t for t in common if df.get(t, N) <= 4]
            if len(rare) < 2:
                continue
            w = sum(idf.get(t, 0) for t in rare)
            adj[a["id"]][b["id"]] = w
            adj[b["id"]][a["id"]] = w

    if not seed:
        return []
    rank = ppr(seed, adj, alpha=0.15, iters=20)

    out = []
    for iid, score in rank.items():
        if score <= 0:
            continue
        it = by_id[iid]
        d = decay_of(it["upd"], it["imp"])
        out.append((score * max(d, 0.05), score, d, it))
    out.sort(reverse=True, key=lambda x: x[0])
    return out[:top]


if __name__ == "__main__":
    # 2026-11-25 #12：--json 给程序/agent 用（只出数据，不打印格式文本）
    _args = [a for a in sys.argv[1:] if a != "--json"]
    _want_json = "--json" in sys.argv[1:]
    q = _args[0] if _args else "备份体系"
    _hits = run(q, top=8)

    if _want_json:
        print(json.dumps({
            "query": q,
            "items": [{"id": it["id"], "tier": it["tier"], "importance": it["imp"],
                       "final": round(float(f), 4), "ppr": round(float(r), 4),
                       "decay": round(float(d), 4),
                       "content": it["content"], "keywords": it.get("kw", "")}
                      for f, r, d, it in _hits],
        }, ensure_ascii=False, indent=1))
        sys.exit(0)

    print("查询:", q)
    print()
    for final, raw, d, it in _hits:
        print("%.4f (ppr %.3f, decay %.2f) [%s·w%d] %s" % (
            final, raw, d, it["tier"], it["imp"], (it["content"] or "")[:66].replace("\n", " ")))
