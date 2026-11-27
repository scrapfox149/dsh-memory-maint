#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""按时间窗口召回记忆——「上周我们干了什么」「那天记了什么」。

五思（2026-11-27，新建 = 第 1 级）
  目的：issue #10。`timeline` 只生成文档、不能过滤；想看「最近 7 天新增/更新了什么」
        得自己翻 PDF。这个补的是**即时查询**。
  方案：读 `created_at` / `updated_at`（毫秒时间戳），按窗口过滤，按 `updated_at` 倒序。
        窗口三种写法：`7d`（最近 7 天）/ `2026-11-20`（那一天）/ `2026-11`（那个月）。
  边界：① 只读，不改任何东西
        ② `--by created` 只看新增，默认看「新增或更新」
        ③ 窗口写错（如 `7x`、`2026-13`）→ 明说，不猜
        ④ 超过 `--top` 条只显示前 N，但总数照样报
  验证：① `7d` 与「手工算 7 天前的时间戳再 count」对得上
        ② 未来的日期 → 0 条，不崩
        ③ 非法窗口 → 明确报错
        ④ 跑完库 sha256 不变
  退路：独立脚本，删掉即可。

用法：
    python mem.py recall 7d
    python mem.py recall 2026-11-20
    python mem.py recall 2026-11
    python mem.py recall 7d --by created --top 20 --json
"""
import io
import json
import os
import re
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


def parse_window(s):
    """把窗口写法转成 (start_ms, end_ms, label)。写不对返回 (None, None, None)。"""
    s = (s or "").strip()
    now = time.time() * 1000

    # ① 相对：7d / 24h / 3mo / 1y
    m = re.fullmatch(r"(\d+)\s*(d|h|mo|y)", s, re.I)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        mul = {"h": 3600, "d": 86400, "mo": 30 * 86400, "y": 365 * 86400}[unit]
        start = now - n * mul * 1000
        return start, now, "最近 %d %s" % (n, {"h": "小时", "d": "天", "mo": "月", "y": "年"}[unit])

    # ② 某一天：2026-11-20
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            st = time.mktime((y, mo, d, 0, 0, 0, 0, 0, -1)) * 1000
        except (ValueError, OverflowError):
            return None, None, None
        return st, st + 86400 * 1000, "%04d-%02d-%02d" % (y, mo, d)

    # ③ 某个月：2026-11
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if not 1 <= mo <= 12:
            return None, None, None
        st = time.mktime((y, mo, 1, 0, 0, 0, 0, 0, -1)) * 1000
        ny, nm = (y + 1, 1) if mo == 12 else (y, mo + 1)
        en = time.mktime((ny, nm, 1, 0, 0, 0, 0, 0, -1)) * 1000
        return st, en, "%04d-%02d" % (y, mo)

    return None, None, None


def _ts(v):
    """字段可能是 int / float / str，统一成毫秒浮点。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # 有些库存的是秒（10 位）而不是毫秒（13 位）
    if f < 1e11:
        f *= 1000
    return f


def fmt(ms):
    if not ms:
        return "?"
    return time.strftime("%m-%d %H:%M", time.localtime(ms / 1000.0))


def collect(con, start, end, by):
    """按窗口收条目。by='created' 只看新增，否则看「新增或更新」。"""
    out = []
    for t in TIERS:
        try:
            rows = con.execute(
                'SELECT id, created_at, updated_at, substr(content,1,80) AS c '
                'FROM "%s"' % t).fetchall()
        except sqlite3.OperationalError:
            continue
        for r in rows:
            iid, ca, ua, c = r[0], _ts(r[1]), _ts(r[2]), r[3] or ""
            hit_c = ca is not None and start <= ca < end
            hit_u = ua is not None and start <= ua < end
            if by == "created":
                if not hit_c:
                    continue
                stamp, kind = ca, "新增"
            else:
                if not (hit_c or hit_u):
                    continue
                stamp, kind = (ca, "新增") if hit_c else (ua, "更新")
            out.append({"tier": t, "id": iid, "at": stamp, "kind": kind,
                        "content": c.replace("\n", " ")})
    out.sort(key=lambda x: -(x["at"] or 0))
    return out


import sqlite3  # noqa: E402  （collect 里用到，放这里避免上面 import 顺序乱）


def main():
    if "--selftest" in sys.argv:
        return selftest()

    raw = sys.argv[1:]
    want_json = "--json" in raw
    by = "any"
    top = 30
    rest = []
    i = 0
    while i < len(raw):
        a = raw[i]
        if a == "--json":
            i += 1
            continue
        if a == "--by" and i + 1 < len(raw):
            by = "created" if raw[i + 1].lower().startswith("c") else "any"
            i += 2
            continue
        if a == "--top" and i + 1 < len(raw):
            try:
                top = int(raw[i + 1])
            except ValueError:
                print("（--top 后面要跟数字，给的是 %r，按 30 算）" % raw[i + 1])
            i += 2
            continue
        rest.append(a)
        i += 1

    if not rest:
        print("用法：mem.py recall <窗口> [--by created] [--top N] [--json]")
        print("  窗口可以是：7d（最近 7 天）/ 2026-11-20（那一天）/ 2026-11（那个月）")
        return 1

    start, end, label = parse_window(rest[0])
    if start is None:
        print("认不出这个窗口：%r" % rest[0])
        print("  支持：7d / 24h / 3mo / 1y / 2026-11-20 / 2026-11")
        print()
        print("结论：⚠ 窗口写法不对，没查")
        return 1

    try:
        con = connect()
    except Exception as e:
        if want_json:
            print(json.dumps({"window": label, "error": str(e)}, ensure_ascii=False))
            return 1
        print("找不到记忆库：%s" % e)
        print("结论：⚠ 库读不了")
        return 1

    try:
        items = collect(con, start, end, by)
    finally:
        con.close()

    if want_json:
        print(json.dumps({"window": label, "by": by, "total": len(items),
                          "items": [{"tier": x["tier"], "id": x["id"],
                                     "at": fmt(x["at"]), "kind": x["kind"],
                                     "content": x["content"]} for x in items[:top]]},
                         ensure_ascii=False, indent=2))
        return 0

    print("=== 回忆：%s（%s）===" % (label, "只算新增" if by == "created" else "新增或更新"))
    print()
    if not items:
        print("  （这个窗口里没有条目）")
        print()
        print("结论：✅ %s 没有记忆变化" % label)
        return 0

    for x in items[:top]:
        print("  %s [%s] %-7s %s" % (fmt(x["at"]), x["kind"], TIER_CN.get(x["tier"], x["tier"]),
                                     x["content"][:58]))
        print("      %s" % x["id"][:14])
    if len(items) > top:
        print()
        print("  …… 还有 %d 条（要全看加 --top %d）" % (len(items) - top, len(items)))
    print()
    print("结论：%s 有 %d 条（新增 %d / 更新 %d）"
          % (label,
             len(items),
             sum(1 for x in items if x["kind"] == "新增"),
             sum(1 for x in items if x["kind"] == "更新")))
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

    now = time.time() * 1000

    # 相对窗口
    st, en, lb = parse_window("7d")
    chk("7d 能解析", st is not None, lb)
    chk("7d 的跨度 ≈ 7 天", abs((en - st) / 86400000 - 7) < 0.01,
        "%.2f 天" % ((en - st) / 86400000))
    chk("7d 的终点 ≈ 现在", abs(en - now) < 5000, "%.0f 秒" % ((now - en) / 1000))

    # 某一天
    st, en, lb = parse_window("2026-11-20")
    chk("单日能解析", st is not None, lb)
    chk("单日跨度 = 1 天", abs((en - st) / 86400000 - 1) < 0.01,
        "%.2f 天" % ((en - st) / 86400000))
    chk("单日 label 对", lb == "2026-11-20", lb)

    # 某个月
    st, en, lb = parse_window("2026-11")
    chk("单月能解析", st is not None, lb)
    chk("单月跨度 = 30 天", abs((en - st) / 86400000 - 30) < 0.01,
        "%.2f 天" % ((en - st) / 86400000))

    # 12 月跨年
    st, en, lb = parse_window("2026-12")
    chk("12 月跨年到次年", st is not None and en > st, lb)

    # 非法
    chk("7x 认不出", parse_window("7x")[0] is None)
    chk("2026-13 认不出", parse_window("2026-13")[0] is None)
    chk("空串认不出", parse_window("")[0] is None)
    chk("abc 认不出", parse_window("abc")[0] is None)

    # _ts：秒 vs 毫秒
    chk("秒转毫秒", abs(_ts(1795782793) - 1795782793000) < 1, str(_ts(1795782793)))
    chk("毫秒不动", abs(_ts(1795782793000) - 1795782793000) < 1)
    chk("None 返回 None", _ts(None) is None)
    chk("坏字符串返回 None", _ts("abc") is None)

    print()
    print("memory-recall 自测：%d 通过 / %d 失败 / 共 %d" % (ok, bad, ok + bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
