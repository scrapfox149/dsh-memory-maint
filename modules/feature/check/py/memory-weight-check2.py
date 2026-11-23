# -*- coding: utf-8 -*-
"""权重逐条复查（更严格规则）：输出「建议权重 ≠ 当前权重」的完整清单。"""
import json
import re
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SNAP = r"C:\Users\24172\Documents\deepseek-harness\default-workspace\tmp\memory-snapshot.json"
if not os.path.exists(SNAP):
    print("快照不存在：%s" % SNAP)
    print("先跑 memory-map-export.py（mem.py maint mapexport）生成快照")
    sys.exit(1)
with open(SNAP, encoding="utf-8") as f:
    items = json.load(f)

# 4 级：红线/不可逆/安全
W4 = re.compile(r"红线|禁止|绝不|不可逆|丢失|丢数据|安全|宕机|不可恢复|只能人工|彻底消失|用户原话|沉没成本|底线")
# 3 级：会再遇到的规律 / 用户强调 / 全局适用
W3 = re.compile(r"依据|实测|源码|根因|规律|判断标准|用户要求|用户授权|用户提醒|用户红线|必须|应该|教训|框架|机制|原则")
# 2 级：一次性事件 / 项目专属 / 历史数字
W2 = re.compile(r"2026-\d{2}-\d{2}.*(当时|当天|这次)|配额|验证码|某版本|一次性|项目专属")

print("%-6s %-6s %-4s %-4s %s" % ("层", "项目", "现", "建", "内容"))
print("-" * 100)
changed = 0
for it in items:
    c = (it["content"] or "") + " " + (it["title"] or "")
    cur = it["importance"]
    sug = cur
    if it["tier"] in ("rules", "soul"):
        sug = max(cur, 3)
    if W4.search(c):
        sug = 4
    elif W3.search(c):
        sug = max(sug, 3)
    elif W2.search(c):
        sug = min(sug, 2)
    if sug != cur:
        changed += 1
        print("%-6s %-6s w%-3d w%-3d %s" % (it["tier"], (it["project"] or "空")[:4], cur, sug,
                                            (it["content"] or "")[:58].replace("\n", " ")))
print()
print("偏差条数:", changed, "/", len(items))
