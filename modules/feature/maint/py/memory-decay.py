# -*- coding: utf-8 -*-
"""记忆衰减扫描（只读）。分两节输出，解决"没有访问记录 ≠ 该归档"的混淆。

五思（2026-11-17，第 1 级：造工具必须走）
  目的：衰减现在只影响检索排序，记忆从不真正退场——找出该提示归档/降权的条目。
  方案：半衰期指数衰减 decay = 0.5 ** (天数/半衰期)，与 memory-expand / hipporag 一致
        （importance>=3 → 180 天，其余 14 天）。
  边界：只读；不自动改；不碰 archived/stale；**只对"有访问记录"的条目算衰减**。
  验证：① 抽样核对时间戳 ② 异常用例——user/soul 层天然无访问记录（每轮注入
        不走检索），必须排除，否则会把最重要的信息判成"死记忆"（v1 就是这么错的）
  退路：纯只读，无副作用。

**关键区分（v2 修正）**：
  A 节「真·衰减」= last_accessed_at > 0 的条目 → 真的久未被检索命中
  B 节「从未被召回」= 无访问记录且不是 user/soul → 多半是关键词写得不准，
      不按衰减处理，而是提示"该修关键词"
  user / soul 层不参与任何一节（它们每轮注入，不需要被检索）

用法：
  python memory-decay.py                # A 节 15 条 + B 节 10 条
  python memory-decay.py --top 30
"""
import argparse
import datetime
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break
from decay import decay_of as _u_decay, halflife as _u_hl
from mem_db import load as _load  # 契约层


if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from mem_db import DB  # 契约层统一（支持 DSH_MEMORY_DB 覆盖）
TIERS = ["rules", "project", "topic", "fact", "lesson"]   # user/soul 不参与
LABEL = {"rules": "rule", "project": "proj", "topic": "topic",
         "fact": "fact", "lesson": "less"}


def halflife(imp):
    """委托 py-core/decay.py（2026-11-19 统一，别在这里改参数）"""
    return _u_hl(imp)


def fmt_date(ms):
    return datetime.datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB, help="数据库路径（默认活库）")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--top-b", type=int, default=10)
    args = ap.parse_args()

    now = datetime.datetime.now().timestamp() * 1000
    accessed, never = [], []
    for r in _load(db=args.db, status="active", tiers=TIERS):
        content = r["content"]
        if not content:
            continue
        upd, acc = r["updated_at"] or 0, r["last_accessed_at"] or 0
        rec = {"tier": r["tier"], "id": r["id"], "c": content,
               "imp": r["importance"] or 1, "upd": upd, "acc": acc,
               "hit": r["hit_count"] or 0}
        if acc > 0:
            # 2026-11-19 修：未来时间（时钟错乱）会算出负天数 → 0.5^负数 > 1。
            # memory-expand / hipporag 都有 max(...,0)，这里又漏了。
            days = max((now - acc) / 86400000.0, 0.0)
            rec["days"] = days
            # 2026-11-19 修：原来是 math.exp(-days/hl)，那是「e 衰减」，14 天给 0.368；
            # 而 memory-expand / memory-hipporag 都用的 0.5 ** (days/hl)（真半衰期，14 天给 0.5）。
            # 三者必须一致，否则同一个条目在检索和归档判断里衰减速度不同。
            rec["decay"] = 0.5 ** (days / halflife(rec["imp"]))
            accessed.append(rec)
        else:
            rec["days"] = (now - upd) / 86400000.0 if upd else 0
            never.append(rec)

    print("全库可参与衰减 %d 条｜其中 有访问记录 %d、从未被召回 %d"
          % (len(accessed) + len(never), len(accessed), len(never)))
    print("半衰期：importance>=3 为 180 天，其余 14 天\n")

    accessed.sort(key=lambda x: x["decay"])
    print("=== A 节｜真·衰减（按最后一次被检索命中算，共 %d 条）===" % len(accessed))
    print("    decay 越小 = 越久没被用到")
    for i in accessed[:args.top]:
        print("  decay %.3f  [%s] %-12s imp=%d  %.1f 天未命中  最后 %s"
              % (i["decay"], LABEL[i["tier"]], i["id"][:12], i["imp"],
                 i["days"], fmt_date(i["acc"])))
        print("        %s" % i["c"].replace("\n", " ")[:74])

    never.sort(key=lambda x: -x["days"])
    # B 节只列"靠检索召回"的层（fact/lesson/topic）；rules/user/soul 是注入型，
    # project 多用 memory_project 按需取——它们没有访问记录属正常，不能算关键词问题。
    # 另外排除写入不足 3 天的（还没机会被召回）
    idle = [i for i in never if i["tier"] in ("fact", "lesson", "topic") and i["days"] >= 3]
    never_retrieval = [i for i in never if i["tier"] in ("fact", "lesson", "topic")]
    print("\n=== B 节｜从未被召回（%d 条，不是衰减问题，多半是关键词不准）===" % len(idle))
    # 2026-11-19 加：说明口径，否则"A 节说 225 条 / B 节说 0 条"会让人困惑
    print("    全部从未召回 %d 条（含刚写入的），其中**写入满 3 天、真该怀疑关键词的 %d 条**；"
          % (len(never_retrieval), len(idle)))
    print("    其余 %d 条太新，还没机会被召回——不用管" % (len(never_retrieval) - len(idle)))
    print("    （只看靠检索召回的 fact/lesson/topic；user/soul/rules 是注入型，不参与）")
    if idle:
        print("    这类不该按衰减归档，应该补/改关键词，让它下次能被命中")
    for i in idle[:args.top_b]:
        print("  [%s] %-12s imp=%d  写入 %d 天前  更新 %s"
              % (LABEL[i["tier"]], i["id"][:12], i["imp"], int(i["days"]), fmt_date(i["upd"])))
        print("        %s" % i["c"].replace("\n", " ")[:74])

    print("\n（只读扫描，未修改任何数据；user / soul / rules 全量注入，不参与本扫描）")
    print()
    print("结论：%d 条能算衰减（%d 条有访问记录），%d 条从未被召回"
      % (len(accessed), len(accessed), len(idle)))


if __name__ == "__main__":
    main()
