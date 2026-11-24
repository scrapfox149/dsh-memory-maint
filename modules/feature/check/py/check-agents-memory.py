# -*- coding: utf-8 -*-
"""AGENTS 规则 vs 记忆库 对照（ID 显式关联版）。

架构（2026-11-13 用户要求先想架构再动手）：
- AGENTS 每条规则末尾标 `→ 记忆库 <层> `<id>``
- 本工具只做一件事：正则提 id → 查库 → 报「缺 / 在」
- 不靠文本相似，所以**不会假阳性**（只要标注诚实）

用法：改完 AGENTS 规则跑一次；异常测试见文件末尾注释。
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
from paths import workspace_root  # noqa: E402
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

AGENTS = os.path.join(workspace_root(), "AGENTS.md")
from mem_db import DB, fetch  # 契约层统一（支持 DSH_MEMORY_DB 覆盖）
TIERS = ("soul", "user", "rules", "project", "topic", "fact", "lesson")

ID_RE = re.compile(r"→\s*记忆库\s*(\w+)?\s*`?([0-9a-z]{7,})`?")

text = open(AGENTS, encoding="utf-8").read()
refs = ID_RE.findall(text)  # [(tier, id), ...]

present = {}
for t in TIERS:
    for (iid,) in fetch(t, ["id"]):
        present[iid] = t

print("AGENTS 里的记忆库引用:", len(refs), "条")
print()
missing, found = [], 0
for tier, iid in refs:
    # 按前缀查（AGENTS 里可写前缀，也可写全 id）
    hits = [k for k in present if k.startswith(iid)]
    if not hits:
        missing.append((tier, iid))
        print("  ❌ %s `%s` —— 记忆库里没有" % (tier or "?", iid))
    else:
        found += 1
        print("  ✅ %s `%s` → %s（%s）" % (tier or "?", iid[:12], present[hits[0]], hits[0][:12]))
print()
print("有效引用: %d / %d，缺失: %d" % (found, len(refs), len(missing)))

# 异常测试（手工验证用）：
# 在 AGENTS 里加一行 `→ 记忆库 rules `zzzzzzzz``，应报「记忆库里没有」
