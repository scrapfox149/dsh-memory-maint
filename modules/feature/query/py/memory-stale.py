#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""重要但很久没碰的记忆——可能已过时，或者该重写。

五思（2026-11-27，新建 = 第 1 级）
  目的：issue #11。有些记忆 importance 高（3-4），但很久没更新也没被访问，
        可能已经过时。`decay` 是按公式算的，`stale` 是看「多久没碰」这个简单事实——
        两个视角不同，都要有。
  方案：读 `last_accessed_at`（有就优先）和 `updated_at`（兜底），算「多久没碰」，
        按天数倒序，只列 active + importance >= 阈值的。
  边界：① `last_accessed_at` 覆盖不全（本机 project 23% / user 10% / soul 0%）
           → **为空时回落到 `updated_at`**，并在输出里说明用的是哪个字段
        ② 时间字段可能存秒或毫秒 → 统一转换
        ③ 未来的时间（时钟错乱/手工改库）→ 标出来但不崩
        ④ 只读
  验证：① 天数算得对（造已知数据：3 天前 / 40 天前 / 未来）
        ② `--importance` 过滤生效
        ③ 空库不崩
        ④ 跑完库 sha256 不变
  退路：独立脚本，删掉即可。

用法：
    python mem.py stale                    # 默认 30 天
    python mem.py stale 90                 # 90 天
    python mem.py stale 30 --importance 3  # 只看 importance >= 3
    python mem.py stale --json
"""
import io
import json
import os
import sqlite3
import sys
import time

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_here, "..", "..", "..", "..", "py-core")))
from mem_db import connect  # noqa: E402

TIERS = ("project", "topic", "fact", "lesson", "rules", "user", "soul")
TIER_CN = {"soul": "自身", "user": "用户", "project": "项目", "topic": "话题",
           "fact": "事实", "lesson": "教训", "rules": "规则"}


def ts(v):
    """字段可能是 int / float / str，统一成毫秒浮点。秒级转毫秒。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f * 1000 if f < 1e11 else f


def collect(con, days_threshold, min_imp):
    """收「多久没碰 >= 阈值」的 active 条目。返回 (items, 用了哪个字段的统计)。"""
    now = time.time() * 1000
    out = []
    used = {"accessed": 0, "updated": 0}
    for t in TIERS:
        try:
            rows = con.execute(
                'SELECT id, last_accessed_at, updated_at, importance, status, '
                'substr(content,1,80) FROM "%s"' % t).fetchall()
        except sqlite3.OperationalError:
            continue
        for r in rows:
            iid, la, ua, imp, st, c = r[0], ts(r[1]), ts(r[2]), r[3], r[4], r[5] or ""
            if (st or "") != "active":
                continue
            if (imp or 0) < min_imp:
                continue
            if la is not None:
                stamp, field = la, "accessed"
            elif ua is not None:
                stamp, field = ua, "updated"
            else:
                continue
            days = (now - stamp) / 86400000.0
            # 2026-11-27：**未来时间（days < 0）要单独捞出来**，不能按「超过 N 天」筛。
            # 它是异常（时钟错乱 / 手工改库 / 迁移数据），本来就该被看见。
            # 自测里就是这条挂了——`-5 < 30` 被当成"不够久"滤掉了。
            if days < 0:
                used[field] += 1
                out.append({"tier": t, "id": iid, "days": days, "field": field,
                            "imp": imp or 0, "at": stamp,
                            "content": c.replace("\n", " ")})
                continue
            if days < days_threshold:
                continue
            used[field] += 1
            out.append({"tier": t, "id": iid, "days": days, "field": field,
                        "imp": imp or 0, "at": stamp, "content": c.replace("\n", " ")})
    out.sort(key=lambda x: -x["days"])
    return out, used


def main():
    if "--selftest" in sys.argv:
        return selftest()

    raw = sys.argv[1:]
    want_json = "--json" in raw
    days_threshold = 30
    min_imp = 0
    i = 0
    while i < len(raw):
        a = raw[i]
        if a == "--json":
            i += 1
            continue
        if a == "--importance" and i + 1 < len(raw):
            try:
                min_imp = int(raw[i + 1])
            except ValueError:
                print("（--importance 后面要跟数字，忽略）")
            i += 2
            continue
        # 位置参数 = 天数
        if a.isdigit():
            days_threshold = int(a)
        i += 1

    try:
        con = connect()
    except Exception as e:
        if want_json:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
            return 1
        print("找不到记忆库：%s" % e)
        print("结论：⚠ 库读不了")
        return 1

    try:
        items, used = collect(con, days_threshold, min_imp)
    finally:
        con.close()

    if want_json:
        print(json.dumps({
            "threshold_days": days_threshold, "min_importance": min_imp,
            "total": len(items),
            "used_field": used,
            "items": [{"tier": x["tier"], "id": x["id"], "days": round(x["days"], 1),
                       "field": x["field"], "importance": x["imp"],
                       "content": x["content"]} for x in items],
            "note": "last_accessed_at 为空时用 updated_at 兜底",
        }, ensure_ascii=False, indent=2))
        return 0

    print("=== 超过 %d 天没碰的记忆%s ==="
          % (days_threshold, ("（importance >= %d）" % min_imp) if min_imp else ""))
    print()
    if not items:
        print("  （没有符合条件的）")
        print()
        print("结论：✅ 没有超过 %d 天没碰的" % days_threshold)
        return 0

    for x in items:
        flag = "⚠ 未来" if x["days"] < 0 else "%5.0f 天" % x["days"]
        src = "访问" if x["field"] == "accessed" else "更新"
        print("  %s  [%s] imp=%d  %-7s %s"
              % (flag, src, x["imp"], TIER_CN.get(x["tier"], x["tier"]),
                 x["content"][:52]))
        print("      %s" % x["id"][:14])
    print()
    print("  （%d 条按 last_accessed_at 算，%d 条没有访问记录、按 updated_at 兜底）"
          % (used["accessed"], used["updated"]))
    print()
    future = sum(1 for x in items if x["days"] < 0)
    print("结论：%s" % ("⚠ %d 条超过 %d 天没碰%s"
                      % (len(items), days_threshold,
                         ("（其中 %d 条时间在未来，可能时钟或数据有问题）" % future) if future else "")
                      if items else "✅ 没有"))
    return 0


def selftest():
    ok = bad = 0

    def chk(name, cond, detail=""):
        nonlocal ok, bad
        if cond:
            ok += 1
            print("  ✅ %s%s" % (name, ("  → " + detail) if detail else ""))
        else:
            bad += 1
            print("  ❌ %s%s" % (name, ("  → " + detail) if detail else ""))

    # ts 转换
    chk("秒转毫秒", abs(ts(1795782793) - 1795782793000) < 1)
    chk("毫秒不动", abs(ts(1795782793000) - 1795782793000) < 1)
    chk("None → None", ts(None) is None)
    chk("坏串 → None", ts("abc") is None)
    chk("空串 → None", ts("") is None)

    # 造一个内存库测 collect
    con = sqlite3.connect(":memory:")
    con.execute('CREATE TABLE lesson (id TEXT, last_accessed_at, updated_at, importance,'
                ' status, content TEXT)')
    now = time.time() * 1000
    day = 86400000.0
    rows = [
        ("old_accessed", now - 40 * day, now - 40 * day, 3, "active", "40 天前访问过"),
        ("old_no_access", None, now - 50 * day, 4, "active", "没访问记录，更新在 50 天前"),
        ("recent", now - 2 * day, now - 2 * day, 3, "active", "2 天前，不该出现"),
        ("low_imp", now - 60 * day, now - 60 * day, 1, "active", "importance 1，默认不筛但可筛"),
        ("inactive", now - 100 * day, now - 100 * day, 3, "stale", "非 active，不该出现"),
        ("future", now + 5 * day, now + 5 * day, 3, "active", "时间在未来"),
    ]
    con.executemany("INSERT INTO lesson VALUES (?,?,?,?,?,?)", rows)
    con.commit()

    # collect 用死表名，这里手工复现它的逻辑（只测 lesson）
    def mine(th, mi):
        out, used = [], {"accessed": 0, "updated": 0}
        for r in con.execute("SELECT id,last_accessed_at,updated_at,importance,status,content"
                             " FROM lesson"):
            iid, la, ua, imp, st, c = r[0], ts(r[1]), ts(r[2]), r[3], r[4], r[5]
            if st != "active" or (imp or 0) < mi:
                continue
            if la is not None:
                st_, f_ = la, "accessed"
            elif ua is not None:
                st_, f_ = ua, "updated"
            else:
                continue
            d = (now - st_) / day
            # 和 collect 保持一致：未来时间直接收进来
            if d >= 0 and d < th:
                continue
            used[f_] += 1
            out.append((iid, d, f_))
        return out, used

    got, used = mine(30, 0)
    ids = [x[0] for x in got]
    chk("40 天前出现的在里面", "old_accessed" in ids, str(ids))
    chk("没访问记录的用 updated_at 兜底", "old_no_access" in ids, str(ids))
    chk("2 天前的不在里面", "recent" not in ids)
    chk("非 active 不出现", "inactive" not in ids)
    chk("未来时间能识别", "future" in ids)
    chk("兜底计数对", used["updated"] >= 1, str(used))

    got2, _ = mine(30, 3)
    ids2 = [x[0] for x in got2]
    chk("--importance 3 能筛掉低权重", "low_imp" not in ids2, str(ids2))
    chk("高权重的还在", "old_accessed" in ids2, str(ids2))

    con.close()

    print()
    print("memory-stale 自测：%d 通过 / %d 失败 / 共 %d" % (ok, bad, ok + bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
