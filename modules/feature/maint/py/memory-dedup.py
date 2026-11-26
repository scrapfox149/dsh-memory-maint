# -*- coding: utf-8 -*-
"""全库去重聚类（只读）。筛选候选，不做任何修改。

判据（2026-11-17 实测定，见 docs/memory-dedup-log.md）：
  第一道  bigram Jaccard ≥ 0.25（共同 bigram ≥ 5 才计，降噪）
  第二道  keywords 交集 ≥ 50%（真重复的关键词会高度重叠）
  聚类    并查集把相邻候选连成"簇"——输出簇而不是对
  打分    importance / 更新时间 / 内容长度 / 关键词数 → 推荐保留哪条

三档：
  🔴 高度重复  ≥0.30 且关键词重合 → 基本可直接归档一条
  🟡 疑似重复  0.25-0.30 且关键词重合 → 需人工看一眼
  ⚪ 部分重叠  ≥0.30 但关键词不重合 → 可能互补，默认不动

用法：
  python memory-dedup.py                  # 终端输出三档清单
  python memory-dedup.py --min-sim 0.30   # 调阈值
  python memory-dedup.py --out report.md  # 同时写报告
"""
import argparse
import itertools
import json
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
from text import bigrams as _u_bigrams
from mem_db import load as _load  # 契约层：统一读库，插件改 schema 只改 mem_db.py

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from mem_db import DB  # 契约层统一（支持 DSH_MEMORY_DB 覆盖）
TIERS = ["soul", "user", "rules", "project", "topic", "fact", "lesson"]
MIN_SHARED_GRAMS = 5      # 共同 bigram 少于这个数，不算候选
KW_OVERLAP = 0.3          # 关键词重合阈值（overlap 系数：交集/较小集合）
SIM_ALONE = 0.70          # 内容相似到这个程度，不必再看关键词（文献级重复）
KW_ALONE = 0.40           # 仅关键词重合到达标度 → 疑似同义改写，单列待确认
TIER_LABEL = {"soul": "soul", "user": "user", "rules": "rules", "project": "proj",
              "topic": "topic", "fact": "fact", "lesson": "less"}


def bigrams(s):
    """委托 py-core/text.py（2026-11-19 统一）"""
    return _u_bigrams(s)


def kw_set(raw):
    try:
        v = json.loads(raw or "[]")
        return set(str(x) for x in v)
    except Exception:
        return set()


def load(db, min_len=10):
    items = []
    for r in _load(db=db, status="active"):
        c = (r["content"] or "").strip()
        if len(c) < min_len:
            continue
        items.append({"tier": r["tier"], "id": r["id"], "c": c,
                      "kw": kw_set(r["keywords"]), "imp": r["importance"] or 1,
                      "upd": r["updated_at"] or 0, "acc": r["last_accessed_at"] or 0})
    return items


def score(item):
    """簇内排序分：importance 权重最高，其次新旧、信息量、关键词完整度"""
    s = (item["imp"] or 1) * 3.0
    s += 1.0 if len(item["c"]) >= 120 else 0.0        # 信息更全
    s += 1.0 if len(item["kw"]) >= 8 else 0.0         # 关键词够数
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB, help="数据库路径（默认活库）")
    ap.add_argument("--min-sim", type=float, default=0.25)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    items = load(args.db)
    n = len(items)
    grams = [bigrams(i["c"]) for i in items]

    # 1) 两两比较：内容判据 与 关键词并列判据（同义改写靠后者）
    pairs, kw_only = [], []
    for a, b in itertools.combinations(range(n), 2):
        ga, gb = grams[a], grams[b]
        ka, kb = items[a]["kw"], items[b]["kw"]
        small = min(len(ka), len(kb))
        kw_ov = (len(ka & kb) / float(small)) if small else 0.0
        inter = len(ga & gb) if (ga and gb) else 0
        sim = (inter / len(ga | gb)) if (ga and gb) else 0.0
        cross = items[a]["tier"] != items[b]["tier"]

        if inter >= MIN_SHARED_GRAMS and sim >= args.min_sim:
            pairs.append({"sim": sim, "a": a, "b": b, "kw_ov": kw_ov, "cross": cross})
        elif kw_ov >= KW_ALONE and sim < args.min_sim:
            # 内容不像但关键词高度重合 → 疑似同义改写，单列（不参与聚类）
            kw_only.append({"sim": sim, "a": a, "b": b, "kw_ov": kw_ov, "cross": cross})

    # 3) 并查集聚类
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    # 确认条件：内容几乎一样（SIM_ALONE）就算；否则要关键词佐证
    def confirmed(p):
        return p["sim"] >= SIM_ALONE or p["kw_ov"] >= KW_OVERLAP
    linked = [p for p in pairs if confirmed(p)]
    for p in linked:
        union(p["a"], p["b"])

    clusters = {}
    for p in linked:
        clusters.setdefault(find(p["a"]), []).append(p)

    # 4) 分档
    red, yellow, gray = [], [], []
    for root, ps in clusters.items():
        members = sorted({x for p in ps for x in (p["a"], p["b"])})
        sim = max(p["sim"] for p in ps)
        rec = {"members": members, "sim": sim,
               "kw_ov": max(p["kw_ov"] for p in ps),
               "cross": any(p["cross"] for p in ps)}
        (red if sim >= 0.30 else yellow).append(rec)
    for p in pairs:
        if not confirmed(p) and p["sim"] >= 0.30:
            gray.append(p)

    # 5) 输出
    lines = []
    lines.append("全库 active %d 条，扫描 %d 对，候选 %d 对（关键词确认 %d）\n"
                 % (n, n * (n - 1) // 2, len(pairs), len(linked)))
    lines.append("🔴 高度重复 %d 簇 / 🟡 疑似重复 %d 簇 / ⚪ 部分重叠 %d 对\n"
                 % (len(red), len(yellow), len(gray)))

    def show_cluster(idx, rec):
        lines.append("\n【簇 %d】相似 %.2f  关键词重合 %.0f%%  %s"
                     % (idx, rec["sim"], rec["kw_ov"] * 100,
                        "跨层" if rec["cross"] else "同层"))
        ranked = sorted((items[m] for m in rec["members"]),
                        key=score, reverse=True)
        for i, it in enumerate(ranked):
            tag = "→ 建议保留" if i == 0 else "  归档候选"
            lines.append("  %s [%s] %s  imp=%d  %d 字  %d 关键词"
                         % (tag, TIER_LABEL[it["tier"]], it["id"][:12],
                            it["imp"], len(it["c"]), len(it["kw"])))
            lines.append("         %s" % it["c"].replace("\n", " ")[:78])

    for kind, arr in (("🔴 高度重复", red), ("🟡 疑似重复", yellow)):
        if arr:
            lines.append("\n" + "=" * 56)
            lines.append(kind)
            lines.append("=" * 56)
            for i, rec in enumerate(sorted(arr, key=lambda r: -r["sim"]), 1):
                show_cluster(i, rec)

    if gray:
        lines.append("\n" + "=" * 56)
        lines.append("⚪ 部分重叠（关键词不重合，可能互补，默认不动）")
        lines.append("=" * 56)
        for p in sorted(gray, key=lambda x: -x["sim"])[:10]:
            ia, ib = items[p["a"]], items[p["b"]]
            lines.append("  %.2f [%s/%s]" % (p["sim"], TIER_LABEL[ia["tier"]],
                                             TIER_LABEL[ib["tier"]]))
            lines.append("      %s %s" % (ia["id"][:12], ia["c"][:52].replace("\n", " ")))
            lines.append("      %s %s" % (ib["id"][:12], ib["c"][:52].replace("\n", " ")))

    if kw_only:
        lines.append("\n" + "=" * 56)
        lines.append("📎 仅关键词相似（内容用词不同，疑似同义改写 → 需人工确认）")
        lines.append("=" * 56)
        lines.append("   这类不能自动判重复：关键词高也可能只是同一主题的不同侧面。")
        for p in sorted(kw_only, key=lambda x: -x["kw_ov"])[:10]:
            ia, ib = items[p["a"]], items[p["b"]]
            lines.append("  kw重合 %.0f%%  内容 %.2f  [%s/%s]"
                         % (p["kw_ov"] * 100, p["sim"], TIER_LABEL[ia["tier"]], TIER_LABEL[ib["tier"]]))
            lines.append("      %s %s" % (ia["id"][:12], ia["c"][:56].replace("\n", " ")))
            lines.append("      %s %s" % (ib["id"][:12], ib["c"][:56].replace("\n", " ")))

    lines.append("\n（只读扫描，未修改任何数据）")
    text = "\n".join(lines)
    print(text)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(text)
        print("\n报告已写入：%s" % args.out)

    print()
    print("结论：%s" % ("⚠ %d 对候选，其中 %d 对关键词也重叠（这两个更值得看）"
                      % (len(pairs), len(linked)) if pairs else "✅ 没发现重复"))

if __name__ == "__main__":
    main()
