# -*- coding: utf-8 -*-
"""全局整理助手（只读）：补 dream 的盲区——它只看本窗口，管不到全库。

扫描全库，输出四类候选：
1. 疑似重复（内容 bigram 相似度高）
2. 疑似矛盾（同主题但内容不同，供人工判断）
3. 该退场（todo 已完成、一次性事件特征、90 天未更新）
4. importance 可疑（高重要性但内容极短/琐碎）

只出清单，不自动改任何东西。
"""
import json
import os
import re

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break
import sys
import time

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from mem_db import DB, fetch  # 契约层统一（支持 DSH_MEMORY_DB 覆盖）
TIERS = ["soul", "user", "rules", "project", "topic", "fact", "lesson"]
DUP_THRESHOLD = 0.45
STALE_DAYS = 90


def bigrams(s):
    s = re.sub(r"\s+", "", s or "")
    return set(s[i:i + 2] for i in range(len(s) - 1))


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / float(len(a | b))


def load():
    items = []
    for t in TIERS:
        try:
            for iid, content, kws, st, imp, upd in fetch(t, ["id", "content", "keywords", "status", "importance", "updated_at"]):
                items.append({
                    "tier": t, "id": iid, "content": content or "",
                    "kw": kws or "", "status": st, "imp": imp or 1, "upd": upd or 0,
                })
        except Exception:
            import traceback, os as _os, sys as _sys
            try:
                from mem_db import report_exception as _rep_exc
                _rep_exc(_os.path.basename(__file__), traceback.format_exc()[-400:])
            except Exception:
                pass
            continue
    return items


def main():
    items = load()
    active = [i for i in items if i["status"] == "active"]
    print("全库 %d 条，active %d 条\n" % (len(items), len(active)))

    # 1) 疑似重复
    grams = {i["id"]: bigrams(i["content"]) for i in active}
    dups = []
    for a in range(len(active)):
        for b in range(a + 1, len(active)):
            ia, ib = active[a], active[b]
            if ia["tier"] != ib["tier"]:
                continue
            s = jaccard(grams[ia["id"]], grams[ib["id"]])
            if s >= DUP_THRESHOLD:
                dups.append((s, ia, ib))
    dups.sort(reverse=True, key=lambda x: x[0])
    print("=== 疑似重复（%d 对）===" % len(dups))
    for s, a, b in dups[:10]:
        print("  %.2f [%s] %s" % (s, a["tier"], a["id"][:12]))
        print("       %s" % a["content"][:60].replace("\n", " "))
        print("       %s | %s" % (b["id"][:12], b["content"][:60].replace("\n", " ")))

    # 2) 该退场候选
    now = time.time() * 1000
    retire = []
    for i in active:
        c = i["content"]
        # todo 已完成但还 active
        if i["tier"] == "project" and ("已完成" in c or "已收尾" in c or "已交付" in c):
            retire.append(("todo 已完成", i))
        # 90 天未更新
        if i["upd"] and (now - i["upd"]) / 86400000.0 > STALE_DAYS:
            retire.append(("90 天未更新", i))
    print("\n=== 该退场候选（%d 条）===" % len(retire))
    for reason, i in retire[:10]:
        print("  [%s] %s %s | %s" % (reason, i["tier"], i["id"][:12], i["content"][:50].replace("\n", " ")))

    # 3) importance 可疑
    sus = [i for i in active if (i["imp"] or 1) >= 3 and len(i["content"]) < 40 and i["tier"] not in ("rules", "soul")]
    print("\n=== importance 可疑（%d 条）===" % len(sus))
    for i in sus[:8]:
        print("  imp=%d %s %s | %s" % (i["imp"], i["tier"], i["id"][:12], i["content"][:50]))

    # 4) 关键词异常
    kw_bad = []
    for i in active:
        try:
            kws = json.loads(i["kw"] or "[]")
        except Exception:
            kws = []
        if not kws:
            kw_bad.append(("无关键词", i))
        elif len(kws) < 8:
            kw_bad.append(("关键词 %d 个" % len(kws), i))
    print("\n=== 关键词异常（%d 条）===" % len(kw_bad))
    for reason, i in kw_bad[:10]:
        print("  [%s] %s %s" % (reason, i["tier"], i["id"][:12]))

    print("\n（以上均为只读扫描，未修改任何数据）")
    print()
    _n = len(dups) + len(retire) + len(sus) + len(kw_bad)
    print("结论：扫了 %d 条，发现 %d 个值得看一眼的"
          "（重复 %d / 该退场 %d / 权重可疑 %d / 关键词异常 %d）"
          % (len(items), _n, len(dups), len(retire), len(sus), len(kw_bad)))


if __name__ == "__main__":
    main()
