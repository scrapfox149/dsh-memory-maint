# -*- coding: utf-8 -*-
"""文件式检索 v4：加文档长度归一化（修复"长文档什么都命中"），再测。"""
import math
import os
import re
import sys
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break

from paths import workspace_root  # noqa: E402
from text import bigrams as _u_bigrams   # 2026-11-19 统一分词（py-core/text.py）

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WS = workspace_root()
EXPORT = os.path.join(WS, "memory-export")
DOCS = os.path.join(WS, "docs")

TIER_W = {
    "soul": 1.4, "rules": 1.3, "user": 1.25,
    "topic": 1.2, "doc": 1.1, "project": 1.0, "lesson": 1.0, "fact": 0.95,
}
AVG_LEN = 800.0   # 记忆条目平均长度（字符）
K1 = 1.2
B = 0.7


def load_docs(quiet=False):
    out = []
    # 2026-11-25：新装环境**没有** memory-export/（那是 backup 导出才生成的），
    # 原来直接 os.listdir 就崩（FileNotFoundError）。目录不在 = 没有导出副本，跳过即可。
    # quiet=True 给 --json 用：JSON 模式下 stdout 里不能混进任何非 JSON 文本。
    if not os.path.isdir(EXPORT) and not quiet:
        print("（还没有 memory-export/ 导出副本——跑一次 `mem_backup export` 就有了；"
              "现在只搜 docs/ 下的文档）")
        print()
    for name in sorted(os.listdir(EXPORT)) if os.path.isdir(EXPORT) else []:
        if not name.endswith(".md") or name == "README.md":
            continue
        text = open(os.path.join(EXPORT, name), encoding="utf-8").read()
        parts = re.split(r"\n## `([0-9a-zA-Z\-]+)`[^\n]*\n", text)
        for i in range(1, len(parts), 2):
            out.append({"tier": name[:-3], "id": parts[i],
                        "body": parts[i + 1] if i + 1 < len(parts) else ""})
    if os.path.isdir(DOCS):
        for name in sorted(os.listdir(DOCS)):
            if name.endswith(".md"):
                out.append({"tier": "doc", "id": name,
                            "body": open(os.path.join(DOCS, name), encoding="utf-8").read()})
    return out


def bigrams(s):
    """委托 py-core/text.py（2026-11-19 统一）"""
    return _u_bigrams(s)


def build_stats(docs):
    df = {}
    total_len = 0
    for d in docs:
        total_len += len(d["body"] or "")
        for g in bigrams(d["body"]):
            df[g] = df.get(g, 0) + 1
    n = max(len(docs), 1)
    idf = {g: math.log((n + 1.0) / (c + 1.0)) + 1.0 for g, c in df.items()}
    return idf, total_len / float(n)


def score(query, doc, idf, avg_len):
    qg = bigrams(query)
    if not qg:
        return 0.0
    dg = bigrams(doc["body"])
    total_w = sum(idf.get(g, 1.0) for g in qg)
    if total_w <= 0:
        return 0.0
    hit_w = sum(idf.get(g, 0.5) for g in qg if g in dg)

    # 长度归一化（BM25 风格）：长文档天然命中多，要压
    dl = len(doc["body"] or "")
    norm = 1.0 - B + B * (dl / max(avg_len, 1.0))

    head_hit = len(qg & bigrams(doc["body"][:40])) / float(len(qg))
    return ((hit_w / total_w) / norm + 0.15 * head_hit) * TIER_W.get(doc["tier"], 1.0)


def search(query, docs, idf, avg_len, top=5):
    sc = [(score(query, d, idf, avg_len), d) for d in docs]
    sc = [x for x in sc if x[0] > 0.01]
    sc.sort(reverse=True, key=lambda x: x[0])
    return sc[:top]


def snippet(body, limit=60):
    return re.sub(r"\s+", " ", body or "").strip()[:limit] + "…"


QUERIES = [
    ("备份坏了怎么办", ["备份体系", "history"]),
    ("出图为什么这么慢", ["出图", "ComfyUI"]),
    ("点击器还能加什么功能", ["定时点击器", "待扩展"]),
    ("测试先行 上线前要测什么", ["测试先行", "副本"]),
    ("记忆库结构该怎么改", ["memory-structure", "结构诊断", "四模块", "分层维度"]),
    ("代理怎么开怎么关", ["proxy-control", "fail-safe", "on/off"]),
    ("命令窗一闪而过", ["闪窗", "CREATE_NO_WINDOW", "pythonw"]),
    ("WAL 越来越大", ["WAL", "checkpoint"]),
    ("计划任务为什么没跑", ["计划任务", "Arguments"]),
    ("Edge 扩展丢了怎么恢复", ["Edge", "扩展"]),
    ("用户说过的最重要的话", ["用户原话", "测试先行", "宝贵"]),
    ("我自己重视什么", ["自我认知", "重视", "失忆"]),
    ("我要不要重构记忆插件", ["重构", "文件式", "四模块"]),
]

if __name__ == "__main__":
    docs = load_docs()
    idf, avg_len = build_stats(docs)
    print("可检索 %d 条（文档 %d 份），平均长度 %.0f 字\n" % (
        len(docs), sum(1 for d in docs if d["tier"] == "doc"), avg_len))
    good = 0
    for q, expects in QUERIES:
        hits = search(q, docs, idf, avg_len, top=3)
        first = hits[0] if hits else None
        text = first[1]["body"] if first else ""
        ok = any(e in text for e in expects)
        good += 1 if ok else 0
        print("%s %s" % ("✅" if ok else "❌", q))
        for s, d in hits:
            print("     %.3f [%s] %s | %s" % (s, d["tier"], str(d["id"])[:14], snippet(d["body"])))
    print("\n首位命中：%d/%d" % (good, len(QUERIES)))
