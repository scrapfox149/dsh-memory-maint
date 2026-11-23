# -*- coding: utf-8 -*-
"""中文文本处理的统一实现（与 mem_db.py / out.py / decay.py 并列的基础层）。

为什么要有它（2026-11-19）：`memory-dedup` / `memory-file-search` / `memory-hipporag`
三个脚本各写了一份完全相同的 bigram 分词（连名字都不一样：`bigrams` / `tokenize`）。

约定：中文不分词，用字符 bigram（连续两个字符），去空白。
"""

import re


def bigrams(s):
    """字符 bigram 集合（中文检索的基本单位）"""
    t = re.sub(r"\s+", "", s or "")
    return set(t[i:i + 2] for i in range(len(t) - 1))


# 兼容旧脚本里 tokenize 的命名
tokenize = bigrams


def jaccard(a, b):
    """两个集合的 Jaccard 相似度（都为空时算 1.0）"""
    if not a and not b:
        return 1.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def kw_set(raw):
    """把 keywords 字段（JSON 字符串或列表）转成集合"""
    import json
    if not raw:
        return set()
    if isinstance(raw, (list, tuple, set)):
        return set(str(x).strip() for x in raw if str(x).strip())
    try:
        v = json.loads(raw)
        if isinstance(v, list):
            return set(str(x).strip() for x in v if str(x).strip())
    except Exception:
        pass
    return set(x.strip() for x in str(raw).replace("，", ",").split(",") if x.strip())
