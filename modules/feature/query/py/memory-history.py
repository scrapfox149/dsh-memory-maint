#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""某条记忆的变更史——它被改过几次、每次是哪件事改的。

五思（2026-11-27，新建 = 第 1 级）
  目的：用户想知道「这条记忆被改过几次、每次是哪次 reflect 改的」（issue #8）。
        以前只能靠 `updated_at` 看最后一次，中间过程全是黑的。
  方案：读库里已有的 `editHistory_infoFrom` 字段——**不新增表、不改数据**。
        格式 `dream-update-<session>-turnRange(a,b); reflect-remember-...`
        → 切成一条条，按顺序列出「来源 / 会话 / 轮次」。
  边界：① 库不存内容 diff，只能回答「改过几次」，回答不了「改了什么」
        ② 没有该字段的条目 → 明说「没有变更记录」
        ③ id 不存在 → 明说，不猜
        ④ 只读，不改任何东西
  验证：① 拿一条有两条记录的（如 0mwqfwla1）应列出 2 条
        ② 拿一条没有记录的应说「没有变更记录」
        ③ 不存在的 id 应给提示
        ④ 跑完库 sha256 不变
  退路：独立脚本，删掉即可。

用法：
    python mem.py history <id>
    python mem.py history <id> --json
"""
import io
import json
import os
import sqlite3
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_here, "..", "..", "..", "..", "py-core")))
from mem_db import connect  # noqa: E402

TIERS = ("soul", "user", "project", "topic", "fact", "lesson", "rules")
TIER_CN = {"soul": "自身", "user": "用户", "project": "项目", "topic": "话题",
           "fact": "事实", "lesson": "教训", "rules": "规则"}
COL = "editHistory_infoFrom"


def find(con, mid):
    """按 id 前缀在七层里找，返回 (tier, id, raw, content_head) 或 None。"""
    for t in TIERS:
        try:
            row = con.execute(
                'SELECT id, "%s" AS h, substr(content,1,60) AS c FROM "%s" WHERE id LIKE ?'
                % (COL, t), (mid + "%",)).fetchone()
        except sqlite3.OperationalError:
            continue          # 这层没这一列（老库）
        if row:
            # connect() 没设 row_factory，只能按位置取
            return t, row[0], row[1] or "", row[2] or ""
    return None


def parse(raw):
    """把 `a-...-turnRange(1,15); b-...-turn(6)` 切成 [{source, session, turns, raw}]。"""
    out = []
    for chunk in (raw or "").split(";"):
        s = chunk.strip()
        if not s:
            continue
        # 形如 <source>-<session>-turnRange(a,b) 或 <source>-<session>-turn(n)
        parts = s.rsplit("-", 1)
        tail = parts[-1] if len(parts) > 1 else ""
        head = parts[0] if len(parts) > 1 else s
        turns = ""
        if tail.startswith("turnRange(") or tail.startswith("turn("):
            turns = tail
            head = head
        # head 形如 dream-update-9741e4e2
        segs = head.split("-")
        source = "-".join(segs[:-2]) if len(segs) >= 3 else (segs[0] if segs else "?")
        action = segs[-2] if len(segs) >= 2 else ""
        session = segs[-1] if segs else ""
        out.append({"source": source, "action": action,
                    "session": session, "turns": turns, "raw": s})
    return out


def main():
    if "--selftest" in sys.argv:
        return selftest()

    args = [a for a in sys.argv[1:] if a != "--json"]
    want_json = "--json" in sys.argv[1:]

    if not args:
        print("用法：mem.py history <记忆 id>")
        print("  例：mem.py history 0mwqfwla1")
        return 1

    mid = args[0].strip()
    try:
        con = connect()
    except Exception as e:
        if want_json:
            print(json.dumps({"id": mid, "error": str(e)}, ensure_ascii=False))
            return 1
        print("找不到记忆库：%s" % e)
        print("结论：⚠ 库读不了")
        return 1

    try:
        found = find(con, mid)
    finally:
        con.close()

    if not found:
        if want_json:
            print(json.dumps({"id": mid, "found": False, "items": []}, ensure_ascii=False))
            return 1
        print("=== %s 的变更史 ===" % mid)
        print()
        print("⚠ 七层里都找不到这个 id（前 12 位对不上）")
        print()
        print("结论：⚠ 没有这条记忆")
        return 1

    tier, full_id, raw, head = found
    items = parse(raw)

    if want_json:
        print(json.dumps({"id": full_id, "tier": tier, "found": True,
                          "content_head": head, "count": len(items),
                          "items": items,
                          "note": "库里不存内容 diff，只能回答改过几次"},
                         ensure_ascii=False, indent=2))
        return 0

    print("=== %s 的变更史 ===" % full_id)
    print()
    print("  层：%s" % TIER_CN.get(tier, tier))
    print("  内容：%s…" % head.replace("\n", " "))
    print()
    if not items:
        print("  （没有变更记录——可能写了就没改过，或者库版本早于这个字段）")
        print()
        print("结论：✅ 没有变更记录（改过 0 次或无从得知）")
        return 0

    for i, it in enumerate(items, 1):
        print("  %2d. %s%s%s%s" % (
            i,
            (it["source"] or "?"),
            (" / " + it["action"]) if it["action"] else "",
            (" / " + it["turns"]) if it["turns"] else "",
            ("   会话 " + it["session"]) if it["session"] else ""))
    print()
    print("  （库里不存内容 diff——这里只能看「谁在哪一轮改过」，看不到「改了什么」）")
    print()
    print("结论：改过 %d 次" % len(items))
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

    # parse：单条带 turnRange
    r = parse("dream-update-9741e4e2-turnRange(1,15)")
    chk("解析单条", len(r) == 1, str(r[0] if r else None))
    chk("source = dream", r[0]["source"] == "dream", r[0]["source"])
    chk("session = 9741e4e2", r[0]["session"] == "9741e4e2", r[0]["session"])
    chk("轮次带 turnRange", "turnRange(1,15)" in r[0]["turns"], r[0]["turns"])

    # parse：分号分隔多条
    r2 = parse("jot-update-9741e4e2-turn(6); reflect-update-9741e4e2-turnRange(6,10)")
    chk("分号切成 2 条", len(r2) == 2, str(len(r2)))
    chk("第一条是 jot", r2[0]["source"] == "jot", r2[0]["source"])
    chk("第二条是 reflect", r2[1]["source"] == "reflect", r2[1]["source"])

    # parse：空
    chk("空串 → 空列表", parse("") == [])
    chk("None → 空列表", parse(None) == [])

    # parse：turn(n) 形式
    r3 = parse("jot-remember-d749d1b3-turn(86)")
    chk("turn(86) 能解", len(r3) == 1 and "turn(86)" in r3[0]["turns"], str(r3))

    print()
    print("memory-history 自测：%d 通过 / %d 失败 / 共 %d" % (ok, bad, ok + bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
