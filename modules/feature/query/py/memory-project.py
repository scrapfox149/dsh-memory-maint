# -*- coding: utf-8 -*-
"""一个项目的记忆全景（统计视角，给人看）。

五思（2026-11-24，新建 = 第 1 级）
  目的：34 个动作全是「全库」视角，想问「盾构激光靶现在什么样」得自己拼：
        多少条？各层分布？最近动了什么？有没有待办？有没有重复嫌疑？
        注意：`memory_project`（MCP 工具）已有类似能力，但那是**注入给模型的格式**，
        信息密、不适合人快速扫。这个脚本是**统计视角**，短、可读、一眼看完。
  方案：`load()` 全库一遍，按 project 字段过滤（支持 `dsh` / `盾构激光靶` / 逗号多项目），
        输出：总数 + 各层分布 + 最近 5 条 + 待办 + 重复嫌疑（按 bigram 相似度粗筛）。
  边界：只读；项目不存在时列出所有可用项目名；重复嫌疑只是**粗筛**（阈值宽松），要点进去看。
  验证：与 `memory_project` 的条数对得上；空项目不崩。
  退路：独立脚本，删掉即可。

用法：
    python mem.py project 盾构激光靶
    python mem.py project dsh --recent 10
"""
import os
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break
from mem_db import load  # noqa: E402
from text import bigrams, jaccard  # noqa: E402

TIERS = ("project", "fact", "lesson", "topic", "rules", "user", "soul")
TIER_CN = {"project": "项目", "fact": "事实", "lesson": "经验", "topic": "话题",
           "rules": "规则", "user": "用户", "soul": "自身"}
DUP_TH = 0.55          # 重复嫌疑的粗筛阈值（宽松，只用来提示）


def projects_of(row):
    raw = (row.get("project") or "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.replace("，", ",").split(",") if p.strip()]


def main():
    args = [a for a in sys.argv[1:]]
    if not args:
        print("用法：mem.py project <项目名> [--recent N]")
        print()
        # 列出所有项目名，方便直接复制
        names = {}
        for tier in TIERS:
            for r in load([tier]):
                if r.get("status") not in (None, "active"):
                    continue
                for p in projects_of(r):
                    names[p] = names.get(p, 0) + 1
        if names:
            print("现有项目（按条目数）：")
            for p, n in sorted(names.items(), key=lambda x: -x[1]):
                print("  %-20s %d 条" % (p, n))
        return 0

    recent_n = 5
    if "--recent" in args:
        i = args.index("--recent")
        try:
            recent_n = max(1, min(50, int(args[i + 1])))
            del args[i:i + 2]
        except Exception:
            print("--recent 需要一个数字")
            return 1

    want = args[0]
    rows = []
    for tier in TIERS:
        for r in load([tier]):
            if r.get("status") not in (None, "active"):
                continue
            if want in projects_of(r):
                rows.append((tier, r))

    if not rows:
        print("项目「%s」下没有 active 条目。" % want)
        print("（跑 `mem.py project` 不带参数，看现有项目名）")
        return 1

    print("=== 项目：%s ===" % want)
    print()
    print("active 条目：%d 条" % len(rows))

    # 各层分布
    by_tier = {}
    for tier, _r in rows:
        by_tier[tier] = by_tier.get(tier, 0) + 1
    parts = ["%s %d" % (TIER_CN.get(t, t), n)
             for t, n in sorted(by_tier.items(), key=lambda x: -x[1])]
    print("分布：" + " / ".join(parts))
    print()

    # 最近更新
    def ts(tier_r):
        r = tier_r[1]
        return r.get("updated_at") or r.get("created_at") or 0

    print("最近 %d 条更新：" % recent_n)
    for tier, r in sorted(rows, key=ts, reverse=True)[:recent_n]:
        iid = str(r.get("id") or "")[:12]
        content = (r.get("content") or "").replace("\n", " ")
        if len(content) > 56:
            content = content[:56] + "…"
        print("  [%s] [%s] %s" % (tier, iid, content))
    print()

    # 待办（project 层的 todo 子类）
    todos = [(t, r) for t, r in rows
             if t == "project" and (r.get("subcategory") or "") == "todo"]
    if todos:
        print("待办 %d 条：" % len(todos))
        for _t, r in todos[:8]:
            content = (r.get("content") or "").replace("\n", " ")
            if len(content) > 60:
                content = content[:60] + "…"
            print("  · %s" % content)
        print()

    # 重复嫌疑（粗筛：bigram jaccard > 阈值）
    dups = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a = (rows[i][1].get("content") or "")[:400]
            b = (rows[j][1].get("content") or "")[:400]
            if not a or not b:
                continue
            sim = jaccard(bigrams(a), bigrams(b))
            if sim >= DUP_TH:
                dups.append((sim, rows[i], rows[j]))
    if dups:
        dups.sort(key=lambda x: -x[0])
        print("重复嫌疑 %d 组（粗筛，阈值 %.2f）：" % (len(dups), DUP_TH))
        for sim, (t1, r1), (t2, r2) in dups[:5]:
            print("  %.2f  [%s] %s" % (sim, t1, str(r1.get("id") or "")[:12]))
            print("        [%s] %s" % (t2, str(r2.get("id") or "")[:12]))
        print("  （要处理跑 mem.py dedup，别照这个直接删）")
        print()

    print("结论：%s 有 %d 条 active%s%s" % (
        want, len(rows),
        "，%d 条待办" % len(todos) if todos else "",
        "，%d 组重复嫌疑" % len(dups) if dups else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
