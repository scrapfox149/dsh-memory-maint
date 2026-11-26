# -*- coding: utf-8 -*-
"""人物索引：按"开头来源标记"归属，不再按"提到谁"。

归属规则（2026-11-13）：
- `[用户说]` 开头 → 用户
- `[离瞳转达]` 开头 → 离瞳（转达者）
- `[大肥鱼说]` 开头 → 大肥鱼（说话人）
- 无标记 → 归到「未标来源」，提示补标
"""
import json
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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from mem_db import DB, fetch  # 契约层统一（支持 DSH_MEMORY_DB 覆盖）
OUT = os.path.join(workspace_root(), "docs/people.md")
TIERS = ["user", "project", "topic", "fact", "lesson", "rules", "soul"]

TAGS = [
    (re.compile(r"^\s*[\[【（(]?\s*\[大肥鱼说"), "大肥鱼（说话人）"),
    (re.compile(r"^\s*[\[【（(]?\s*\[离瞳说"), "离瞳（说话人）"),
    (re.compile(r"^\s*[\[【（(]?\s*用户说|^\s*用户原话|^\s*用户明确|^\s*用户授权|^\s*用户偏好|^\s*用户要求|^\s*用户红线|^\s*用户提醒|^\s*用户澄清|^\s*用户纠正"), "用户（菜包狐）"),
    (re.compile(r"^\s*[\[【（(]?\s*离瞳转达|^\s*离瞳转述"), "离瞳（转达）"),
    (re.compile(r"^\s*[\[【（(]?\s*大肥鱼说|^\s*大肥鱼给|^\s*大肥鱼（"), "大肥鱼（说话人）"),
    (re.compile(r"^\s*[\[【（(]?\s*离瞳"), "离瞳（直接）"),
]

rows = []
for t in TIERS:
    try:
        for iid, content, imp, status in fetch(t, ["id", "content", "importance", "status"],
                                               status="active"):
            rows.append((iid, content or "", imp or 1, t))
    except (RuntimeError, FileNotFoundError):
        # 2026-11-26（极限边界测试抓到）：库损坏/不存在都不能当"这层是空的"，要往上抛
        raise
    except Exception:
        continue
groups = {}
untagged = []
for iid, content, imp, t in rows:
    who = None
    for rx, name in TAGS:
        if rx.search(content):
            who = name
            break
    if who:
        groups.setdefault(who, []).append((imp, t, content, iid))
    elif re.search(r"离瞳|大肥鱼|年轻人", content):
        untagged.append((imp, t, content, iid))

# 2026-11-25 #12：--json 给程序/agent 用——只出数据，不写 docs/people.md
if "--json" in sys.argv:
    def pack(items):
        return [{"id": iid, "tier": t, "importance": imp, "content": c}
                for imp, t, c, iid in items]
    # 2026-11-25：counts 原来写死了 4 个组名，和 groups 的实际 key 对不上
    # （groups 里是「离瞳（说话人）」，counts 里写的是「离瞳直接」）→ 差 1。
    # 改成**按 groups 的实际 key 生成**，再加一个「未标来源」。
    counts = {k: len(v) for k, v in groups.items()}
    counts["未标来源"] = len(untagged)
    print(json.dumps({
        "counts": counts,
        "groups": {k: pack(v) for k, v in groups.items()},
        "untagged": pack(untagged),
    }, ensure_ascii=False, indent=1))
    sys.exit(0)


lines = ["# 人物索引（按来源标记归属）", "",
         "> 归属看 content 开头的标记，不看文中提到谁。", ""]
for name in ["用户（菜包狐）", "离瞳（转达）", "大肥鱼（说话人）", "离瞳（直接）"]:
    hits = sorted(groups.get(name, []), reverse=True, key=lambda x: x[0])
    if not hits:
        continue
    lines.append("## %s（%d 条）" % (name, len(hits)))
    lines.append("")
    for imp, t, content, iid in hits[:15]:
        lines.append("- `%s` [w%d] %s" % (t, imp, content[:88].replace("\n", " ")))
    if len(hits) > 15:
        lines.append("- …还有 %d 条" % (len(hits) - 15))
    lines.append("")

if untagged:
    lines.append("## ⚠ 提到他人但没开头标记（需补标来源）")
    lines.append("")
    for imp, t, content, iid in untagged[:20]:
        lines.append("- `%s` [w%d] %s" % (t, imp, content[:88].replace("\n", " ")))
    lines.append("")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
print("写入:", OUT)
print("用户:%d 离瞳转达:%d 大肥鱼:%d 离瞳直接:%d 未标:%d" % (
    len(groups.get("用户（菜包狐）", [])), len(groups.get("离瞳（转达）", [])),
    len(groups.get("大肥鱼（说话人）", [])), len(groups.get("离瞳（直接）", [])), len(untagged)))
