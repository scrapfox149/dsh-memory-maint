# -*- coding: utf-8 -*-
"""归档三要素体检：按「谁说的 / 渠道 / 时间」查每条记忆的标记完整度（只读）。

约定格式：content 开头 `[谁说的·渠道]`，正文里写「事件时间」。
- 谁说的：用户 / 离瞳 / 大肥鱼 / 鱼
- 渠道：直接对话 / 群里 / 经X转达 / 读源码 / 实测
- 时间：正文事件时间 + created_at 记录时间（自动）
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
import time

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from mem_db import DB, fetch  # 契约层统一（支持 DSH_MEMORY_DB 覆盖）
TIERS = ["user", "project", "topic", "fact", "lesson", "rules", "soul"]

# 需要来源标记的层（rules/soul 是鱼自己的准则，不必标）
# user 层按规则不需要方括号来源标记（记忆 rules 0mwgc47qu：条目开头就是"用户偏好/用户说"，
# 来源天然明确）；soul 同理。故只检查下面四层。
NEED_MARK = {"project", "topic", "fact", "lesson"}
# 来源标记的判定放宽（2026-11-18）：标记格式是我自己定的（[鱼决策]/[实测]/[产出]/
# [鱼记]/[读文档]/[用户说]...），不能只认几个固定词，否则大量误报。
# 判据改为：开头有任意方括号标记 = 有来源；标记里带 `·` = 写了渠道。
# 开头可能带 markdown 标记（`[xxx]` / **`[xxx]`），要容忍
WHO = re.compile(r"^[\s`*_]{0,4}[\[【]\s*[^\]】]{1,30}[\]】]")
CHANNEL = re.compile(r"[\[【][^\]】]{1,30}·[^\]】]{1,30}[\]】]|·")
DATE = re.compile(r"20\d{2}-\d{2}-\d{2}|20\d{2}/\d{2}/\d{2}|20\d{2}年")

# 日期豁免（2026-11-18 用户提议）：这类是「技术事实/经验」，长期有效，不必挂日期。
#   实测 / 读源码 / 经验 / 鱼经验 / 鱼经历  → 豁免
# 需要日期的是「事件性」内容：鱼决策、鱼记·待办、用户说、大肥鱼说 等。
DATE_EXEMPT = ("实测", "读源码", "经验", "鱼经验", "鱼经历")
# 防止「误豁免」：如果内容里有时间参照词，说明写的是"事件"不是"事实"，照样要求日期。
# 依据 2026-11-18 边界测试：[实测] 今天修了 bug 这类必须先报出来。
TIME_HINT = re.compile(r"今天|昨天|前天|刚才|本周|这周|上周|最近|刚刚|这次|上次|今晚|今早|近日|日前|当天|次日|今儿")
MARK_RE = re.compile(r"^[\s`*_]{0,4}[\[【]\s*([^\]】·]{1,12})")
rows = []
for t in TIERS:
    try:
        for iid, content, status, created in fetch(t, ["id", "content", "status", "created_at"]):
            if status == "active":
                rows.append((t, iid, content or "", created))
    except Exception:
        import traceback, os as _os, sys as _sys
        try:
            from mem_db import report_exception as _rep_exc
            _rep_exc(_os.path.basename(__file__), traceback.format_exc()[-400:])
        except Exception:
            pass
        continue

no_who, no_channel, no_date = [], [], []
for t, iid, content, created in rows:
    if t not in NEED_MARK:
        continue
    if not WHO.search(content):
        no_who.append((t, content))
    # 「渠道」不再单独检查：`[读文档]`/`[鱼写]`/`[用户说]` 这类标记本身已说明来源，
    # 强求 `·` 分隔只会制造噪音（2026-11-18 改）。
    if not DATE.search(content):
        m = MARK_RE.match(content or "")
        mark = m.group(1) if m else ""
        exempt = any(ex in mark for ex in DATE_EXEMPT)
        if not exempt or TIME_HINT.search(content):
            no_date.append((t, content))

print("active 条目:", len(rows))
print()
print("== 缺「谁说的」：%d 条 ==" % len(no_who))
for t, c in no_who[:8]:
    print("  [%s] %s" % (t, c[:70].replace("\n", " ")))
print()

print()
print("== 缺「事件时间」：%d 条 ==" % len(no_date))
for t, c in no_date[:8]:
    print("  [%s] %s" % (t, c[:70].replace("\n", " ")))
print()
_tot = len(no_date)
print("结论：%s" % ("⚠ %d 条缺事件时间" % _tot if _tot else "✅ 条目的时间信息齐全"))
