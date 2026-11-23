# -*- coding: utf-8 -*-
"""把记忆库导出成「格式无关」的 Markdown + JSON（只读库）。

目的（依据自我安全红线 §零）：
- 记忆是目的，工具是手段。任何插件失效时，从这里都能把记忆读出来、重建回去。
- 导出不依赖 meow 的 schema 细节，是纯文本，人可读、可 diff、可版本控制。

输出：
  workspace/memory-export/README.md   总览（各层条数、生成时间）
  workspace/memory-export/<层>.md     每层一个文件（含完整元数据）
  workspace/memory-export/memory-all.json  完整结构化数据
"""
import io
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import time

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 【自包含】不依赖插件/契约层——本脚本要能在插件坏掉时独立运行。
# 库路径：环境变量 DSH_MEMORY_DB > 默认活库路径
DB = (os.environ.get("DSH_MEMORY_DB")
      or r"C:\Users\24172\Documents\deepseek-harness\default-workspace\.dsh-meow\memory.db")
# 【内联告警】不 import 插件——但失败时仍要能被 mem_alert 看到。
_LOG_DIR = (os.environ.get("DSH_MEMORY_LOG_DIR")
            or r"C:\Users\24172\Documents\deepseek-harness\default-workspace\tools\dsh-memory-maint\state")


def report(msg, kind="exception"):
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        rec = {"kind": kind, "script": "memory-export.py",
               "error": str(msg)[:500], "time": int(time.time() * 1000)}
        with open(os.path.join(_LOG_DIR, "errors.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


OUT_DIR = (os.environ.get("DSH_MEMORY_EXPORT_DIR")
           or r"C:\Users\24172\Documents\deepseek-harness\default-workspace\memory-export")
TIERS = ["soul", "user", "rules", "project", "topic", "fact", "lesson"]
TIER_CN = {
    "soul": "身份", "user": "用户", "rules": "准则", "project": "项目",
    "topic": "话题", "fact": "事实", "lesson": "教训",
}

COLS = ["id", "title", "content", "importance", "keywords", "status",
        "project", "subcategory", "goal", "source_session",
        "created_at", "updated_at", "last_accessed_at", "hit_count", "corrected"]


def main():
    if not os.path.exists(DB):
        print("找不到记忆库：", DB)
        report("找不到记忆库：" + str(DB))
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)

    con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)
    all_data = {}
    counts = {}

    for t in TIERS:
        rows = []
        try:
            cur = con.execute('select * from "%s"' % t)
            names = [d[0] for d in cur.description]
            for raw in cur.fetchall():
                item = dict(zip(names, raw))
                rows.append({k: item.get(k) for k in COLS if k in item})
        except Exception as exc:  # noqa: BLE001
            print("读取失败 %s: %s" % (t, exc))
            report("读取 %s 失败: %s" % (t, exc))
            continue
        all_data[t] = rows
        counts[t] = len(rows)

        # 写该层的 Markdown
        lines = ["# %s（%s）· %d 条" % (TIER_CN.get(t, t), t, len(rows)), "",
                 "> 由 dsh-memory-maint 的 backup 层（memory-export.py）自动生成，勿手改。", ""]
        for r in rows:
            status = r.get("status") or "?"
            mark = "" if status == "active" else "（%s）" % status
            lines.append("## `%s` %s" % (r.get("id"), mark))
            lines.append("")
            if r.get("title"):
                lines.append("- 标题：%s" % r["title"])
            if r.get("project"):
                lines.append("- 项目：%s" % r["project"])
            if r.get("importance") is not None:
                lines.append("- 重要性：%s" % r["importance"])
            if r.get("keywords"):
                lines.append("- 关键词：%s" % r["keywords"])
            if r.get("subcategory"):
                lines.append("- 子类：%s" % r["subcategory"])
            if r.get("goal"):
                lines.append("- 目标：%s" % r["goal"])
            lines.append("")
            lines.append((r.get("content") or "").strip())
            lines.append("")
        io.open(os.path.join(OUT_DIR, t + ".md"), "w", encoding="utf-8").write("\n".join(lines))

    con.close()

    total = sum(counts.values())
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")

    # 完整 JSON
    payload = {"exported_at": stamp, "source": DB, "counts": counts, "tiers": all_data}
    io.open(os.path.join(OUT_DIR, "memory-all.json"), "w", encoding="utf-8").write(
        json.dumps(payload, ensure_ascii=False, indent=1))

    # 总览
    lines = [
        "# 记忆导出（格式无关）",
        "",
        "> 由 `dsh-memory-maint/modules/backup/core/py/memory-export.py` 自动生成。**这是记忆的独立副本**：",
        "> 任何插件失效/升级/换掉，都能从这里读回全部记忆。",
        "",
        "- 导出时间：%s" % stamp,
        "- 总条数：%d" % total,
        "- 源库：`%s`" % DB,
        "",
        "| 层 | 条数 | 文件 |",
        "|---|---|---|",
    ]
    for t in TIERS:
        lines.append("| %s（%s） | %d | `%s.md` |" % (TIER_CN.get(t, t), t, counts.get(t, 0), t))
    lines += ["", "完整结构化数据见 `memory-all.json`（含全部元数据，可用于重建）。"]
    io.open(os.path.join(OUT_DIR, "README.md"), "w", encoding="utf-8").write("\n".join(lines))

    print("已导出到：", OUT_DIR)
    print("总条数：", total)
    for t in TIERS:
        print("  %-8s %d" % (t, counts.get(t, 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
