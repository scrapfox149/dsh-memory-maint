# -*- coding: utf-8 -*-
"""记忆变更摘要（只读）。回答"这周记忆库怎么变的"。

五思（2026-11-17，第 1 级：造工具必须走）
  目的：现在只能看到总数（287 条），看不到趋势——这周写了什么、改了什么、
        归档了什么、dream 整理了几次。给自己和用户一个"变化视图"。
  方案：① 新增 = created_at 落在窗口内  ② 修改 = updated_at 在窗口内但
        created_at 在窗口外（不是新建）  ③ 归档 = status 为 archived/stale
        且 updated_at 在窗口内  ④ dream 记录来自 dream_log 表。
        不用估算，全部走时间戳（实测各层 created_at 100% 有值）。
  边界：只读；只统计，不评价好坏；窗口内无变化时输出"无变化"而不是报错；
        不含被删除的条目（库里没有硬删，只有 archived）。
  验证：① 正常用例——7 天窗口的数字回 SQL 核对
        ② 异常用例——--days 0 或未来窗口，必须正常输出"无变化"不崩
  退路：纯只读，无副作用。

用法：
  python memory-changelog.py              # 最近 7 天
  python memory-changelog.py --days 30    # 最近 30 天
  python memory-changelog.py --days 1     # 只看今天
"""
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break
from mem_db import load as _load, dream_log as _dream_log  # 契约层


if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from mem_db import DB  # 契约层统一（支持 DSH_MEMORY_DB 覆盖）
TIERS = ["soul", "user", "rules", "project", "topic", "fact", "lesson"]
CN = {"soul": "soul", "user": "user", "rules": "规则", "project": "项目",
      "topic": "话题", "fact": "事实", "lesson": "教训"}


def day(ms):
    return datetime.datetime.fromtimestamp(ms / 1000).strftime("%m-%d %H:%M")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB, help="数据库路径（默认活库）")
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    now = datetime.datetime.now().timestamp() * 1000
    start = now - args.days * 86400000
    span = "%s ~ %s" % (day(start), day(now))

    new, mod, arch = {}, {}, {}
    allrows = _load(db=args.db)
    for r in allrows:
        t, iid = r["tier"], r["id"]
        if not iid:
            continue
        ca, ua, st = r["created_at"] or 0, r["updated_at"] or 0, r["status"]
        if ca >= start:
            new.setdefault(t, []).append((iid, ca))
        elif ua >= start:
            mod.setdefault(t, []).append((iid, ua))
        if st in ("archived", "stale") and ua >= start:
            arch.setdefault(t, []).append((iid, ua, st))
    dreams = [(d.get("run_at"), d.get("summary")) for d in _dream_log(since_ms=start, db=args.db)]
    total = sum(1 for r in allrows if r["status"] == "active")

    n_new, n_mod, n_arch = sum(len(v) for v in new.values()), sum(len(v) for v in mod.values()), sum(len(v) for v in arch.values())

    print("=== 记忆库变化｜最近 %d 天（%s）===\n" % (args.days, span))
    if n_new == 0 and n_mod == 0 and n_arch == 0 and not dreams:
        print("（这个窗口内没有任何变化）")
        print("当前 active 共 %d 条。" % total)
        return

    print("当前 active %d 条\n" % total)
    print("【新增 %d 条】" % n_new)
    for t in TIERS:
        if t in new:
            print("  %-4s %3d 条" % (CN[t], len(new[t])))
    print("\n【修改 %d 条】（不是新建，但被改动过）" % n_mod)
    for t in TIERS:
        if t in mod:
            print("  %-4s %3d 条" % (CN[t], len(mod[t])))
    print("\n【归档/完结 %d 条】" % n_arch)
    for t in TIERS:
        if t in arch:
            for iid, ua, st in arch[t][:6]:
                print("  %-4s %-12s %s  %s" % (CN[t], iid[:12],
                                               "archived" if st == "archived" else "stale", day(ua)))
    print("\n【dream 整理 %d 次】" % len(dreams))
    for ra, sm in dreams:
        print("  %s  %s" % (day(ra), (sm or "")[:70]))

    # 最近写入的 5 条，看得到在记什么
    newest = []
    for t in TIERS:
        newest += [(ca, t, iid) for iid, ca in new.get(t, [])]
    newest.sort(reverse=True)
    if newest:
        print("\n【最近写入的 5 条】")
        by_key = {(r["tier"], r["id"]): r for r in allrows}   # 复用已读数据，不再直连
        for ca, t, iid in newest[:5]:
            r = by_key.get((t, iid))
            txt = (r["content"] if r else "") or ""
            print("  %s [%s] %s" % (day(ca), CN[t], txt.replace("\n", " ")[:62]))

    print("\n（只读统计，未修改任何数据）")


if __name__ == "__main__":
    main()
