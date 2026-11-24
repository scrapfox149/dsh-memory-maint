# -*- coding: utf-8 -*-
"""生成记忆图谱（IDF 加权版）：topic 当枢纽，按稀有词的重叠连出关联簇。"""
import os
import json
import math
import re
import sys
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break
from paths import workspace_root  # noqa: E402
from collections import Counter

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SNAP = os.path.join(workspace_root(), "tmp/memory-snapshot.json")
OUT = os.path.join(workspace_root(), "docs/memory-map.md")


def tokenize(s):
    s = re.sub(r"\s+", "", s or "")
    return set(s[i:i + 2] for i in range(len(s) - 1))


# 2026-11-24：快照不存在就自己先导一份，不用再手动跑两次。
# 原来要 `mem.py mapexport` -> `mem.py map`，两步才能看图谱；现在 `mem.py map` 一步。
if not os.path.exists(SNAP):
    _exp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory-map-export.py")
    if os.path.exists(_exp):
        print("（快照不存在，先导出……）")
        import subprocess
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        r = subprocess.run([sys.executable, _exp], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env, timeout=180)
        if r.returncode != 0:
            print("导出失败：" + ((r.stdout or "") + (r.stderr or "")).strip()[:200])
            raise SystemExit(1)

with open(SNAP, encoding="utf-8") as f:
    items = json.load(f)

for it in items:
    it["_tok"] = tokenize((it["content"] or "") + " " + (it["keywords"] or "") + " " + (it["title"] or ""))

# IDF：在多少条里出现过
df = Counter()
for it in items:
    for t in it["_tok"]:
        df[t] += 1
N = len(items)
idf = {t: math.log(N / (1 + c)) for t, c in df.items()}

topics = [x for x in items if x["tier"] == "topic"]
others = [x for x in items if x["tier"] != "topic"]

lines = ["# 记忆图谱（topic 为枢纽 · IDF 加权）", "",
         "> 生成 2026-11-13。连线强度 = 共享词的 IDF 之和（稀有词权重高，常见词几乎不计）。", ""]

for tp in topics:
    lines.append("## %s" % ((tp["content"] or "")[:42].replace("\n", " ") + "…"))
    lines.append("")
    lines.append("> %s" % ((tp["content"] or "")[:150].replace("\n", " ")))
    lines.append("")
    scored = []
    for other in others:
        common = tp["_tok"] & other["_tok"]
        if not common:
            continue
        score = sum(idf.get(t, 0) for t in common)
        # 至少两个稀有词同时命中
        rare = sum(1 for t in common if df.get(t, N) <= 3)
        if rare >= 2:
            scored.append((score, other))
    scored.sort(reverse=True, key=lambda x: x[0])
    for score, other in scored[:8]:
        lines.append("- `%s` [w%d] %s" % (other["tier"], other["importance"],
                                          (other["content"] or "")[:58].replace("\n", " ")))
    lines.append("")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
print("topic:", len(topics), "| 写入:", OUT)
