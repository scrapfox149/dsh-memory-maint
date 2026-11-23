# -*- coding: utf-8 -*-
"""从 meow 记忆库生成可读索引 docs/memory-index.md（只读库）。

用途：需要"全局扫一眼"时读这个文件，比现场查库快，也比 SQL 好读。
设计：按 project 分组，组内按层分，每条一行（id 前缀 + 一句话）。
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break
import time

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from mem_db import DB, fetch  # 契约层统一（支持 DSH_MEMORY_DB 覆盖）
OUT = r"C:\Users\24172\Documents\deepseek-harness\default-workspace\docs\memory-index.md"
TIERS = ["soul", "user", "rules", "project", "topic", "fact", "lesson"]
TIER_CN = {
    "soul": "身份", "user": "用户", "rules": "准则", "project": "项目",
    "topic": "话题", "fact": "事实", "lesson": "教训",
}
STALE_MARK = "（已归档）"


def one_line(text, limit=70):
    s = (text or "").replace("\n", " ").strip()
    return s if len(s) <= limit else s[:limit] + "…"


def main():
    if not os.path.exists(DB):
        print("找不到记忆库")
        return 1
    rows = []
    for t in TIERS:
        try:
            for iid, content, status, project, imp in fetch(t, ["id", "content", "status", "project", "importance"]):
                rows.append((t, iid, content, status, project or "未标记", imp))
        except Exception:
            import traceback, os as _os, sys as _sys
            try:
                from mem_db import report_exception as _rep_exc
                _rep_exc(_os.path.basename(__file__), traceback.format_exc()[-400:])
            except Exception:
                pass
            continue

    # 按 project 分组
    groups = {}
    for r in rows:
        groups.setdefault(r[4], []).append(r)

    lines = [
        "# 记忆索引（自动生成）",
        "",
        "> 由 `tools/dsh-memory-maint/modules/feature/maint/py/memory-index.py` 从 `.dsh-meow/memory.db` 生成，**不要手改**。",
        "> 用途：需要全局扫一眼时读它；查细节用 `memory_read` 或 `memory_search`。",
        "> 生成时间：%s" % time.strftime("%Y-%m-%d %H:%M"),
        "> 总条目：%d" % len(rows),
        "",
    ]

    # 全局组优先
    order = ["全局"] + sorted(k for k in groups if k != "全局")
    for proj in order:
        items = groups.get(proj, [])
        if not items:
            continue
        lines.append("## %s（%d 条）" % (proj, len(items)))
        lines.append("")
        for t in TIERS:
            sub = [x for x in items if x[0] == t]
            if not sub:
                continue
            # active 在前
            sub.sort(key=lambda x: (x[3] != "active", -int(x[5] or 1)))
            lines.append("### %s（%s，%d 条）" % (TIER_CN.get(t, t), t, len(sub)))
            for _t, iid, content, status, _p, _imp in sub:
                mark = "" if status == "active" else STALE_MARK
                lines.append("- `%s`%s %s" % (iid[:12], mark, one_line(content)))
            lines.append("")

    io.open(OUT, "w", encoding="utf-8").write("\n".join(lines))
    print("已生成：", OUT)
    print("条目数：", len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
