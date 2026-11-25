# -*- coding: utf-8 -*-
"""为什么这条记忆会被命中：看查询里哪些词撞上了它的关键词。

五思（2026-11-24，新建脚本 = 第 1 级）
  目的：`memory_search` 只给分数（bm25/importance/recency），**不知道是哪几个词撞上的**。
        调关键词时就没法判断「是我写得太泛，还是它匹配错了」。
  方案：**不复现 BM25**——那要把 JS 侧的 tokenize / classify / ZH_HIT_STOPWORDS /
        Porter stemmer 全翻译过来，几百行，差一处结论就错，反而误导。
        改成**纯集合重叠**：查询切成 2-gram，看每条记忆的关键词里有哪些出现在查询里。
        它回答「**哪几个词撞上了**」，不回答「**为什么排第一**」——后者归 memory_search。
  边界：只读；不改库；不假装精确（输出里明确写"这是词面重叠，不是 BM25 分数"）；
        没命中任何词的条目不返回；上限 20 条。
  验证：拿已知词（如"记忆""插件"）跑，看结果是否符合直觉；空查询要报错不崩。
  退路：独立脚本，删掉即可。

用法：
    python mem.py why "记忆 插件 改进"
    python mem.py query why "备份 恢复"          # 等价
"""
import json
import os
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break
from mem_db import DB, load  # noqa: E402
from text import bigrams  # noqa: E402

TIERS = ("fact", "lesson", "topic", "rules", "project", "user", "soul")
MAX_SHOW = 20


def keywords_of(row):
    """keywords 字段可能是 JSON 数组字符串、逗号分隔、或列表。"""
    import json
    raw = row.get("keywords")
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    s = str(raw).strip()
    try:
        v = json.loads(s)
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
    except Exception:
        pass
    return [x.strip() for x in s.replace("，", ",").split(",") if x.strip()]


def main():
    # 2026-11-25 #12：--json 给程序/agent 用（只出数据，不打印格式文本）
    args = [a for a in sys.argv[1:] if a not in ("--full", "--json")]
    full = "--full" in sys.argv[1:]
    want_json = "--json" in sys.argv[1:]
    if not args:
        print("用法：mem.py why \"<查询>\" [--full]")
        print()
        print("输出：查询里哪些词撞上了每条记忆（词面重叠，不是 BM25 分数）")
        print("      --full 强制连正文一起扫（默认只在关键词命中少于 3 条时才扫正文）")
        # 不带参数 = 看用法，不是失败（冒烟测试会无参调用每个脚本）
        return 0

    query = " ".join(args)
    q_grams = bigrams(query)
    # 把查询拆成"词"也放进候选（英文/数字等不含中文 2-gram 的情况）
    q_words = set(w.lower() for w in query.replace("，", " ").replace(",", " ").split() if w)
    q_all = set(q_grams) | q_words

    if not q_all:
        print("查询太短（切不出 2-gram，也没有独立词），换几个字再试。")
        return 1

    rows = []
    for tier in TIERS:
        # load 的第一个参数是**层列表**，不是单个层名——
        # 传字符串会被当成 'f','a','c','t' 四个层名，全不存在，静默返回 0 条（2026-11-24 踩到）
        for r in load([tier]):
            if r.get("status") not in (None, "active"):
                continue
            kws = keywords_of(r)
            if not kws:
                continue
            # 双向 2-gram 重叠：关键词的 2-gram 出现在查询里，或查询的 2-gram 出现在关键词里。
            # 2026-11-24 第一版写成 `k in q_all`（拿整个关键词去比查询的 gram）——
            # 关键词是 4 个字、查询只切出 2-gram，永远匹配不上。
            hit = []
            for k in kws:
                k_grams = bigrams(k) | {k.lower()}
                if (k_grams & q_all) or any(g in k for g in q_grams):
                    hit.append(k)
            if hit:
                rows.append((len(hit), tier, r, hit, "关键词"))

    # 2026-11-24：关键词命中太少时，**自动再扫一遍正文**——
    # memory_search 会读 content，所以"关键词没重叠"不等于"不会命中"。
    # 阈值 3 条：够 3 条说明关键词已经能解释清楚，不必做全库扫描（慢）；
    # 不到 3 条才值得花时间看正文。`--full` 可以强制扫。
    scanned = False
    if len(rows) < 3 or full:
        scanned = True
        seen = set((r.get("tier"), r.get("id")) for _n, _t, r, _h, _src in rows)
        for tier in TIERS:
            for r in load([tier]):
                if r.get("status") not in (None, "active"):
                    continue
                if (r.get("tier"), r.get("id")) in seen:
                    continue
                content = str(r.get("content") or "")
                if not content:
                    continue
                c_grams = bigrams(content)
                hit = sorted(q_all & c_grams)
                if hit:
                    rows.append((len(hit), tier, r, hit, "正文"))

    if not rows:
        if want_json:
            print(json.dumps({"query": query, "tokens": sorted(q_all),
                              "total": 0, "items": []}, ensure_ascii=False, indent=1))
            return 0
        print("没有记忆的关键词与这个查询有词面重叠。")
        print("（这不代表 memory_search 也搜不到——它走 BM25，还会吃正文内容）")
        return 0

    rows.sort(key=lambda x: -x[0])
    total = len(rows)

    if want_json:
        print(json.dumps({
            "query": query,
            "tokens": sorted(q_all),
            "scanned_body": bool(full or scanned),
            "total": total,
            "items": [{"tier": tier, "id": str(r.get("id") or ""),
                        "hits": hit, "where": src, "n": n,
                        "content": r.get("content") or ""}
                       for n, tier, r, hit, src in rows],
        }, ensure_ascii=False, indent=1))
        return 0

    print("=== 为什么会被命中（词面重叠，不是 BM25 分数）===")
    print("查询：%s" % query)
    print("查询切出的词：%s" % " / ".join(sorted(q_all)))
    print("扫描范围：关键词%s" % (" + 正文（--full）" if full else
                                  (" + 正文（关键词命中不足 3 条，自动补扫）" if scanned else "")))
    print()
    print("有 %d 条记忆与查询有词面重叠，显示前 %d 条：" % (total, min(total, MAX_SHOW)))
    print()
    for n, tier, r, hit, src in rows[:MAX_SHOW]:
        iid = str(r.get("id") or "")[:12]
        content = (r.get("content") or "").replace("\n", " ")
        if len(content) > 60:
            content = content[:60] + "…"
        print("[%s] [%s] 撞上 %d 个（%s）：%s" % (tier, iid, n, src, " / ".join(hit)))
        print("   %s" % content)
    print()
    print("说明：这里只比**词面**（关键词，必要时补正文）；memory_search 还会算 BM25、")
    print("      按重要性/新鲜度加权，所以排序和命中范围都会不同。要精确请用它。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
