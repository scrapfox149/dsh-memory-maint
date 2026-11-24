# -*- coding: utf-8 -*-
"""单元测试：decay / text 两个纯函数模块。

为什么单独有它（2026-11-24）：`test-mem-plugin.py` 的 30 项冒烟只验「跑得动」，
不验「算得对」。而 decay 的公式曾经散落三处、三种写法，出过两次不一致——
这类纯函数最该有断言。

五思：
① 目的：给衰减公式和分词/相似度加断言，防止以后改动悄悄改错数值。
② 方案：不引入 pytest（宿主环境不一定有），用标准 assert + 自己数通过/失败。
③ 边界：正常值 + 边界（0 天/未来时间/空串/单字/None）+ 层间关系（importance 分档）。
④ 验证：本文件自身跑通即验证；故意改坏公式应当失败（已人工验过一次）。
⑤ 退路：独立文件，删掉不影响插件运行。

跑法：
    python test-units.py
退出码 0 = 全过。
"""
import os
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_here = os.path.dirname(os.path.abspath(__file__))
# 本文件在插件根目录，py-core 就在旁边；也兼容被放到 modules/*/py/ 下的情况（向上找）
if os.path.isdir(os.path.join(_here, "py-core")):
    sys.path.insert(0, os.path.join(_here, "py-core"))
else:
    for _up in range(1, 5):
        _pc = os.path.join(_here, *([".."] * _up), "py-core")
        if os.path.isdir(_pc):
            sys.path.insert(0, _pc)
            break
from decay import decay_of, halflife, days_since, HALF_LIFE_DEFAULT, HALF_LIFE_HIGH  # noqa: E402
from text import bigrams, jaccard, kw_set  # noqa: E402

DAY = 86400000.0
NOW = 1_800_000_000_000.0          # 固定时间，避免测试依赖真实时钟
passed = []
failed = []


def check(name, cond, detail=""):
    if cond:
        passed.append(name)
    else:
        failed.append("%s %s" % (name, detail))


# ── halflife：按重要度分档 ──────────────────────────────────────────
check("halflife(1)=14", halflife(1) == HALF_LIFE_DEFAULT)
check("halflife(2)=14", halflife(2) == HALF_LIFE_DEFAULT)
check("halflife(3)=180", halflife(3) == HALF_LIFE_HIGH)
check("halflife(4)=180", halflife(4) == HALF_LIFE_HIGH)
check("halflife(None)=14（None 当 1）", halflife(None) == HALF_LIFE_DEFAULT)

# ── decay_of：核心公式 ─────────────────────────────────────────────
check("decay 0 天 = 1.0", abs(decay_of(NOW, 1, now=NOW) - 1.0) < 1e-9)
check("decay 14 天(importance1) = 0.5",
      abs(decay_of(NOW - 14 * DAY, 1, now=NOW) - 0.5) < 1e-9)
check("decay 28 天(importance1) = 0.25",
      abs(decay_of(NOW - 28 * DAY, 1, now=NOW) - 0.25) < 1e-9)
check("decay 180 天(importance3) = 0.5",
      abs(decay_of(NOW - 180 * DAY, 3, now=NOW) - 0.5) < 1e-9)
check("decay 14 天(importance3) ≈ 0.947（半衰期 180，几乎不掉）",
      abs(decay_of(NOW - 14 * DAY, 3, now=NOW) - 0.5 ** (14 / 180)) < 1e-9)

# ── decay_of：边界 ─────────────────────────────────────────────────
check("decay(None) = 0.0", decay_of(None, 1, now=NOW) == 0.0)
check("decay(0) = 0.0", decay_of(0, 1, now=NOW) == 0.0)
check("未来时间按 0 天 → 1.0（2026-11-19 修过的坑）",
      abs(decay_of(NOW + 999 * DAY, 1, now=NOW) - 1.0) < 1e-9)
check("decay 永远非负", all(decay_of(NOW - d * DAY, 1, now=NOW) >= 0
                            for d in (0, 1, 30, 365, 3650)))
check("decay 永远 ≤ 1", all(decay_of(NOW - d * DAY, 1, now=NOW) <= 1.0 + 1e-9
                            for d in (-5, 0, 10, 100)))

# ── days_since ─────────────────────────────────────────────────────
check("days_since 14 天", abs(days_since(NOW - 14 * DAY, now=NOW) - 14.0) < 1e-6)
check("days_since(None) = 0 或大数（不应崩）",
      isinstance(days_since(None, now=NOW), (int, float)))

# ── bigrams ────────────────────────────────────────────────────────
check("bigrams 空串 = 空集", bigrams("") == set())
check("bigrams 单字 = 空集", bigrams("鱼") == set())
check("bigrams 两字 = 1 个", bigrams("记忆") == {"记忆"})
check("bigrams 四字 = 3 个", len(bigrams("记忆维护")) == 3)
check("bigrams 中文按 2-gram", "记忆" in bigrams("记忆库里"))

# ── jaccard ────────────────────────────────────────────────────────
check("jaccard 完全相同 = 1.0", abs(jaccard(bigrams("记忆维护"), bigrams("记忆维护")) - 1.0) < 1e-9)
check("jaccard 完全不同 = 0.0", jaccard(bigrams("记忆"), bigrams("图表")) == 0.0)
check("jaccard 空 vs 非空 = 0.0", jaccard(bigrams(""), bigrams("记忆")) == 0.0)
check("jaccard 空 vs 空 = 1.0（按文档：都为空时算 1.0）", jaccard(bigrams(""), bigrams("")) == 1.0)
check("jaccard 对称", abs(jaccard(bigrams("记忆维护"), bigrams("记忆修复")) - jaccard(bigrams("记忆修复"), bigrams("记忆维护"))) < 1e-9)

# ── kw_set ─────────────────────────────────────────────────────────
k = kw_set(["记忆", "维护", "记忆"])
check("kw_set 去重", len(k) == 2)
check("kw_set 接受逗号分隔字符串", len(kw_set("记忆,维护")) == 2)
check("kw_set 空 = 空集", kw_set([]) == set())

# ── 汇总 ───────────────────────────────────────────────────────────
print("单元测试：%d 通过 / %d 失败 / 共 %d" % (len(passed), len(failed), len(passed) + len(failed)))
if failed:
    print()
    for f in failed:
        print("  ❌", f)
    print()
    print("（公式或分词改坏了，先修再继续）")
    sys.exit(1)
print()
print("（decay 与 text 的数值都对）")
