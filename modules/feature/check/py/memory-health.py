# -*- coding: utf-8 -*-
"""记忆体检（只读）：统计各层条目、状态分布、久未更新的 active 条目、疑似重复。

不修改任何数据，只输出报告，供人工决定要不要整理。
"""
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

from mem_db import DB, fetch, count_status_sql  # 契约层统一
TIERS = ["soul", "user", "project", "fact", "lesson", "topic", "rules"]
STALE_DAYS = 90

if not os.path.exists(DB):
    print("找不到记忆库：", DB)
    raise SystemExit(0)

cnt = count_status_sql(DB)      # 契约层用 SQL 数
now = time.time()
print("=== 各层条目与状态 ===")
total = 0
active_items = []
for t in TIERS:
    try:
        # 保持与原 SQL group by 一致的顺序（active → archived → stale）
        rows = sorted(((st, n) for st, n in cnt.get(t, {}).items() if n),
                      key=lambda x: (x[0] != "active", x[0] != "archived"))
    except Exception as exc:  # noqa: BLE001
        print("  %-8s 读取失败: %s" % (t, exc))
        continue
    if not rows:
        print("  %-8s （空）" % t)
        continue
    parts = []
    n_total = 0
    for st, c in rows:
        parts.append("%s=%d" % (st or "?", c))
        n_total += c
    total += n_total
    print("  %-8s %s" % (t, " ".join(parts)))

    # 收集久未更新的 active 条目
    try:
        items = fetch(t, ["id", "title", "updated_at", "keywords"], status="active")
        for iid, title, upd, kw in items:
            if not upd:
                continue
            try:
                ts = float(upd)
            except (TypeError, ValueError):
                continue
            days = (now - ts) / 86400.0
            if days > STALE_DAYS:
                active_items.append((days, t, iid, title or "", kw or ""))
    except Exception:
        pass

print("总条目：", total)

print()
print("=== 超过 %d 天未更新的 active 条目（共 %d 条）===" % (STALE_DAYS, len(active_items)))
for days, t, iid, title, kw in sorted(active_items, reverse=True)[:20]:
    print("  [%4.0f天] %-8s %s | %s" % (days, t, iid[:12], (title or kw)[:50]))

print()
print("=== 疑似重复（同标题前缀，粗筛）===")
seen = {}
dups = 0
for t in TIERS:
    try:
        items = fetch(t, ["id", "title"], status="active")
    except RuntimeError:
        # 2026-11-26（极限边界测试抓到）：库损坏不能当"这层是空的"，要往上抛
        raise
    except Exception:
        import traceback, os as _os, sys as _sys
        try:
            from mem_db import report_exception as _rep_exc
            _rep_exc(_os.path.basename(__file__), traceback.format_exc()[-400:])
        except Exception:
            pass
        continue
    for iid, title in items:
        key = (title or "").strip()[:12]
        if len(key) < 4:
            continue
        if key in seen:
            dups += 1
            if dups <= 10:
                print("  %s: %s <-> %s" % (key, seen[key][:12], iid[:12]))
        else:
            seen[key] = iid
print("疑似重复计数：", dups)

# WAL 检查：WAL 过大说明长时间没 checkpoint（数据都在 WAL 里，备份/读取都会变慢）
print()
print("=== WAL 状态 ===")
db_path = DB
wal_path = DB + "-wal"
db_kb = os.path.getsize(db_path) / 1024.0 if os.path.exists(db_path) else 0
wal_mb = os.path.getsize(wal_path) / 1024.0 / 1024.0 if os.path.exists(wal_path) else 0
print("  memory.db: %.1f KB" % db_kb)
print("  WAL:       %.2f MB" % wal_mb)
if wal_mb > 10:
    print("  [!!] WAL 超过 10 MB，建议跑一次备份（会自动 checkpoint）")
elif wal_mb > 1:
    print("  [OK] WAL 偏大但可接受（下次备份会合并）")
else:
    print("  [OK] WAL 正常")

print()
_sum = {"active": 0, "stale": 0, "archived": 0}
if isinstance(cnt, dict):
    for _t, _v in cnt.items():
        for _k in _sum:
            try:
                _sum[_k] += int((_v or {}).get(_k, 0) or 0)
            except (TypeError, ValueError):
                pass
print("结论：共 %d 条（active %d / stale %d / archived %d）"
      % (total, _sum["active"], _sum["stale"], _sum["archived"]))
