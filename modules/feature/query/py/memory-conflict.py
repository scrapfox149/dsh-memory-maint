#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""找「说法可能打架」的记忆——候选，不判决。

五思（2026-11-27，新建 = 第 1 级）
  目的：issue #9。用户担心过「规则被写两遍且措辞不同时，可能互相矛盾，
        我每次加载会精神分裂」。这个找**同一主题下说法可能冲突**的条目。
  方案：粗筛（只筛不判）——
        ① 共享**稀有词**（IDF 加权，排除泛词）→ 说明在讲同一件事
        ② 其中至少一条含**否定/转折信号**（不是/改为/不再/但/however…）
        ③ 输出候选对，**明确写「需人工复核」**
  边界：① **规则只能筛不能判**——矛盾要靠人看，工具只缩小范围
        ② 和 `dedup` 的分工：dedup 找「太像」，conflict 找「像但打架」
        ③ 只读
        ④ 候选可能很多 → 默认 top 20，`--all` 全看
  验证：① 造一对真矛盾的（「要 A」vs「不要 A」）应被找出来
        ② 造一对只是相似的（「要 A」vs「要 A 的细节」）应不被判为矛盾信号
        ③ 空库不崩
        ④ 跑完库 sha256 不变
  退路：独立脚本，删掉即可。

用法：
    python mem.py conflict
    python mem.py conflict --top 50 --json
"""
import io
import json
import math
import os
import re
import sqlite3
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_here, "..", "..", "..", "..", "py-core")))
from mem_db import connect  # noqa: E402
from text import bigrams, jaccard, kw_set  # noqa: E402

TIERS = ("project", "topic", "fact", "lesson", "rules")
TIER_CN = {"soul": "自身", "user": "用户", "project": "项目", "topic": "话题",
           "fact": "事实", "lesson": "教训", "rules": "规则"}

# 否定 / 转折 / 变更信号（中文 + 少量英文）
SIGNALS = (
    "不是", "不再", "不用", "不要", "不许", "不能", "禁止", "避免",
    "改为", "改成", "换成", "废弃", "作废", "取消", "撤销", "撤回", "取代",
    "但是", "只是", "然而", "不过", "相反", "反而", "其实不",
    "however", "instead", "no longer", "deprecated", "replaced",
)

# 稀有词阈值：IDF >= 中位数 × 这个系数。
# 2026-11-27 实测：直接用中位数太严（库里 36196 个 bigram，中位数 = 只出现 1 次的词），
# 479 条 active 跑出来 0 对；不用 IDF 又变成 9 万对。0.6 是这两头之间试出来的。
RARE_FACTOR = 0.6

# 同一主题的判据：共享稀有词**同时**满足「绝对数」和「占比」。
# 2026-11-27 实测：只看绝对数时，两条都很长的记忆能"共享 142 个"却毫无关系
# （那对 jaccard 才 0.26）——计数会随长度膨胀，占比不会。
MIN_SHARE = 3
MIN_RATIO = 0.12

# 泛词（共享这些不算「同一主题」）
GENERIC = set("""
记忆 记忆库 条目 内容 项目 事情 东西 这样 那样 什么 怎么 如何 可以 应该 需要
一个 这个 那个 我们 你们 他们 自己 已经 还是 就是 因为 所以 但是 如果 然后
时候 现在 之前 之后 问题 方法 情况 地方 方式 时间 结果 影响
""".split())


def _has_word_char(g):
    """bigram 里每个字都必须是「汉字或字母」，**不能含数字、标点**。

    2026-11-27：用来滤掉没有语义的组合。两轮实测收窄的：
      第一轮 `(M`、`)\\`、`*8`（纯符号）漏了数字；
      第二轮 `37`、`3短`、`6G`、`76`、`92` 还在——**含数字的碎片同样没语义**，
      它们是路径/版本号/时间戳的残渣，会把不相干的条目连起来。
    保留 `QQ`、`vs` 这种纯字母（可能是有意义的产品名/缩写）。
    """
    if not g:
        return False
    for ch in g:
        if ch.isdigit():
            return False
        if not (ch.isalpha() or "\u4e00" <= ch <= "\u9fff"):
            return False
    return len(g) >= 2


def has_signal(text):
    """这条里有没有否定/转折/变更信号。返回命中的词列表。"""
    t = text or ""
    low = t.lower()
    hit = []
    for s in SIGNALS:
        if s in low:
            hit.append(s)
    return hit


def main():
    if "--selftest" in sys.argv:
        return selftest()

    raw = sys.argv[1:]
    want_json = "--json" in raw
    top = 999 if "--all" in raw else 20
    for i, a in enumerate(raw):
        if a == "--top" and i + 1 < len(raw):
            try:
                top = int(raw[i + 1])
            except ValueError:
                pass

    try:
        con = connect()
    except Exception as e:
        if want_json:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
            return 1
        print("找不到记忆库：%s" % e)
        print("结论：⚠ 库读不了")
        return 1

    rows = []
    try:
        for t in TIERS:
            try:
                for r in con.execute(
                        'SELECT id, content, keywords, importance, project FROM "%s" '
                        'WHERE status = ?' % t, ("active",)):
                    rows.append({"tier": t, "id": r[0], "content": r[1] or "",
                                 "kw": r[2] or "", "imp": r[3] or 0,
                                 "project": r[4] or ""})
            except sqlite3.OperationalError:
                continue
    finally:
        con.close()

    if len(rows) < 2:
        if want_json:
            print(json.dumps({"pairs": [], "note": "条目太少"}, ensure_ascii=False))
            return 0
        print("=== 说法可能打架的记忆 ===")
        print()
        print("（active 条目不足 2 条，没法比）")
        print()
        print("结论：✅ 没有可疑的（条目太少）")
        return 0

    # ① 算 IDF（稀有词权重高）
    df = {}
    for r in rows:
        for g in set(bigrams(r["content"])):
            df[g] = df.get(g, 0) + 1
    n = len(rows)
    idf = {g: math.log((n + 1.0) / (c + 1.0)) + 1.0 for g, c in df.items()}
    # 稀有 = IDF 高于中位数的一个比例（2026-11-27：中位数太严，实测 0 对）
    if idf:
        med = sorted(idf.values())[len(idf) // 2]
    else:
        med = 1.0

    def rare_set(text):
        """这条的稀有 bigram 集合（排除泛词 + 排除纯符号）。"""
        gs = set(bigrams(text))
        out = set()
        for g in gs:
            if g in GENERIC:
                continue
            # 2026-11-27：**纯符号/标点的 bigram 没语义**，留着会把无关的条目连起来
            # （实测候选里出现 `(M`、`)\`、`*8`、`"文` 这种，两条根本没在讲一件事）
            if not _has_word_char(g):
                continue
            if idf.get(g, 1.0) >= med * RARE_FACTOR:
                out.add(g)
        return out

    rar = [rare_set(r["content"]) for r in rows]

    # ② 两两比：共享稀有词 >= 2，且至少一条有信号
    cands = []
    for i in range(len(rows)):
        if not rar[i]:
            continue
        for j in range(i + 1, len(rows)):
            if not rar[j]:
                continue
            share = rar[i] & rar[j]
            # 2026-11-27：**只看共享数量不行**——两条都几百个 bigram 时，共享 142 个
            # 也只占一小部分（实测那对的 jaccard 才 0.26）。改成「共享数量 + 占比」双条件。
            union = rar[i] | rar[j]
            share_ratio = len(share) / float(len(union)) if union else 0.0
            if len(share) < MIN_SHARE or share_ratio < MIN_RATIO:
                continue
            si = has_signal(rows[i]["content"])
            sj = has_signal(rows[j]["content"])
            if not (si or sj):
                continue
            # jaccard 要 set（text.py 里是 a | b），不是字符串
            sim = jaccard(set(bigrams(rows[i]["content"])), set(bigrams(rows[j]["content"])))
            cands.append({
                "a": rows[i], "b": rows[j], "share": sorted(share),
                "ratio": share_ratio, "sa": si, "sb": sj, "sim": sim,
                "score": share_ratio * 10 + (1.5 if si else 0) + (1.5 if sj else 0),
            })

    cands.sort(key=lambda x: -x["score"])

    if want_json:
        print(json.dumps({
            "total": len(cands),
            "pairs": [{
                "a": {"tier": x["a"]["tier"], "id": x["a"]["id"],
                      "content": x["a"]["content"][:80], "signals": x["sa"]},
                "b": {"tier": x["b"]["tier"], "id": x["b"]["id"],
                      "content": x["b"]["content"][:80], "signals": x["sb"]},
                "shared_rare": x["share"][:8],
                "jaccard": round(x["sim"], 3),
            } for x in cands[:top]],
            "note": "候选，需人工复核——规则只能筛不能判",
        }, ensure_ascii=False, indent=2))
        return 0

    print("=== 说法可能打架的记忆（候选，需人工看）===")
    print()
    if not cands:
        print("  （没找到共享稀有词 + 带否定/转折信号的组合）")
        print()
        print("结论：✅ 没发现可疑的")
        return 0

    for idx, x in enumerate(cands[:top], 1):
        print("  [%d] 相似 %.2f  共同稀有词 %d 个：%s"
              % (idx, x["sim"], len(x["share"]), "、".join(x["share"][:5])))
        for side, rec, sig in (("A", x["a"], x["sa"]), ("B", x["b"], x["sb"])):
            mark = ("  ⚠信号:" + "/".join(sig[:3])) if sig else ""
            print("    %s [%s] %s%s" % (side, TIER_CN.get(rec["tier"], rec["tier"]),
                                       rec["content"][:66].replace("\n", " "), mark))
            print("         %s" % rec["id"][:14])
        print()

    if len(cands) > top:
        print("  …… 还有 %d 对（要全看加 --all）" % (len(cands) - top))
        print()

    print("  ⚠ 这是**候选，不是判决**——规则只能从字面找「共享稀有词 + 否定/转折」，")
    print("    真正的矛盾要靠人读一遍才能确认。")
    print()
    print("结论：⚠ %d 对候选（需人工复核）" % len(cands))
    return 0


def selftest():
    ok = bad = 0

    def chk(name, cond, detail=""):
        nonlocal ok, bad
        if cond:
            ok += 1
            print("  ✅ %s%s" % (name, ("  → " + detail) if detail else ""))
        else:
            bad += 1
            print("  ❌ %s%s" % (name, ("  → " + detail) if detail else ""))

    # has_signal
    chk("「不要」能识别", has_signal("这条不要做") == ["不要"], str(has_signal("这条不要做")))
    chk("「改为」能识别", "改为" in has_signal("规则改为 X"))
    chk("「不再」能识别", "不再" in has_signal("以后不再用它"))
    chk("普通句子没信号", has_signal("这是一条正常的记忆") == [],
        str(has_signal("这是一条正常的记忆")))
    chk("英文 however", "however" in has_signal("However this is wrong"))
    chk("None 不崩", has_signal(None) == [])

    # 泛词不该当稀有词
    chk("泛词表含「记忆」", "记忆" in GENERIC)
    chk("泛词不算稀有", len(set(bigrams("记忆")) & GENERIC) >= 1)

    # jaccard 可复用
    # jaccard 要 set（text.py 里是 a | b），不是字符串
    j = jaccard(set(bigrams("备份恢复")), set(bigrams("备份恢复步骤")))
    chk("jaccard 相似度高", j > 0.3, "%.2f" % j)
    j2 = jaccard(set(bigrams("备份恢复")), set(bigrams("完全无关的内容")))
    chk("jaccard 无关低", j2 < 0.15, "%.2f" % j2)

    # 真矛盾的一对应该共享稀有词 + 有信号
    a = "备份策略是每天全量"
    b = "备份策略不要每天全量，改为增量"
    ra, rb = set(bigrams(a)), set(bigrams(b))
    share = ra & rb
    chk("矛盾对共享 bigram", len(share) >= 2, "%d 个" % len(share))
    chk("B 侧有信号", len(has_signal(b)) > 0, str(has_signal(b)))

    print()
    print("memory-conflict 自测：%d 通过 / %d 失败 / 共 %d" % (ok, bad, ok + bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
