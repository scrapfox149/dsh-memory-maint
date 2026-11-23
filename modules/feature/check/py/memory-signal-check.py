# -*- coding: utf-8 -*-
"""按「信号」检查 importance 是否越级（只读，出清单不改）。

信号规则（2026-11-13 起，抄 dsh-memory 的"不让模型打分"）：
- w4：含用户红线/安全/不可逆词
- w3：含 依据/实测/用户强调/全局适用 词
- w2：一次性事件 / 项目细节
- w1：琐碎

本脚本只找「给了高权重但没有任何高权信号」和「给了低权重但明显是红线」的。
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
TIERS = ["rules", "project", "topic", "fact", "lesson", "user", "soul"]

# 2026-11-19 扩表：原来只有 12 个词，42 条报告里 28 条是"有约束语义但没命中词"的误报
# （如「**必须先确认**」——"必须"不在旧表里）。补祈使/禁令/强调类。
W4 = re.compile(r"红线|禁止|绝不|不可逆|永久|安全|宕机|不可恢复|只能人工|彻底消失|用户原话|硬要求|"
                r"必须|务必|严禁|不准|不能用|不要再|牢记|永远|底线|准则|硬性|铁律|守则|"
                r"用户强调|用户要求|用户说|硬标准")
W3 = re.compile(r"依据|实测|源码|根因|规律|判断标准|用户要求|用户授权|用户提醒|必须|应该|教训|机制|原则|会再遇到")
W1 = re.compile(r"^\)|临时|随口")
bad_high, bad_low = [], []
for t in TIERS:
    try:
        for iid, content, imp in fetch(t, ["id", "content", "importance"], status="active"):
            c = content or ""
            if imp >= 4 and not W4.search(c):
                bad_high.append((t, iid, imp, c))
            elif imp <= 1 and (W4.search(c) or W3.search(c)):
                bad_low.append((t, iid, imp, c))
    except Exception:
        import traceback, os as _os, sys as _sys
        try:
            from mem_db import report_exception as _rep_exc
            _rep_exc(_os.path.basename(__file__), traceback.format_exc()[-400:])
        except Exception:
            pass
        continue

# 2026-11-19 改：分级 + 说明理由
# 「没有信号词」不等于「权重虚高」——很多是语义重要但措辞不同。
short = [(t, i, imp, c) for t, i, imp, c in bad_high if len((c or "").strip()) < 40]
long_ = [(t, i, imp, c) for t, i, imp, c in bad_high if len((c or "").strip()) >= 40]
print("== 高权重但没有高权信号（共 %d 条）==" % len(bad_high))
print("   注意：**没有这些词 ≠ 权重虚高**，很多是语义重要但措辞不同，需人工判断。")
print()
if short:
    print("  【更可疑】内容不到 40 字却很重，%d 条：" % len(short))
    for t, iid, imp, c in short:
        print("    w%d [%s] %s" % (imp, t, (c or "").strip()[:60].replace(chr(10), " ")))
    print()
print("  【待人工看】内容较长、只是没命中词表，%d 条：" % len(long_))
for t, iid, imp, c in long_[:10]:
    print("    w%d [%s] %s" % (imp, t, (c or "").strip()[:50].replace(chr(10), " ")))
if len(long_) > 10:
    print("    …… 另有 %d 条" % (len(long_) - 10))
print()
print("== 低权重但内容像红线/规律（可能压低了）==")
for t, iid, imp, c in bad_low:
    print("  w%d [%s] %s" % (imp, t, c[:64].replace("\n", " ")))
print()
print("越级条数:", len(bad_high) + len(bad_low))
