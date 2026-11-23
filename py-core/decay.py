# -*- coding: utf-8 -*-
"""时间衰减的统一实现（与 mem_db.py / out.py 并列的基础层）。

为什么要有它（2026-11-19）：`memory-expand` / `memory-hipporag` / `memory-decay`
三个脚本各写了一份衰减计算，**同一天里出了两次不一致**：
  ① `decay` 用了 `math.exp(-d/h)`（e 衰减，14 天给 0.368），另两个用 `0.5**(d/h)`（真半衰期，0.5）
  ② `decay` 漏了 `max(..., 0)`，未来时间（时钟错乱）算出负数 → decay 4.4

**收进一份后，"一致"由结构保证，不用每次靠人检查。**

约定：
  半衰期：importance >= 3 → 180 天；否则 14 天
  公式：  decay = 0.5 ** (天数 / 半衰期)
  未来时间（负天数）按 0 天处理（= 1.0，即"刚访问"）
"""
import time

HALF_LIFE_HIGH = 180.0
HALF_LIFE_DEFAULT = 14.0
DAY_MS = 86400000.0


def halflife(importance):
    """按重要度取半衰期（天）"""
    return HALF_LIFE_HIGH if (importance or 1) >= 3 else HALF_LIFE_DEFAULT


def now_ms():
    return time.time() * 1000.0


def decay_of(updated_ms, importance, now=None):
    """统一的衰减值：0~1，越小越久没用。

    updated_ms 为空/0 → 返回 0.0（从未用过）
    updated_ms 在未来（时钟错乱）→ 按 0 天处理，返回 1.0
    """
    if not updated_ms:
        return 0.0
    n = now if now is not None else now_ms()
    days = max((n - float(updated_ms)) / DAY_MS, 0.0)   # ← 负天数在这里被吃掉
    return 0.5 ** (days / halflife(importance))


def days_since(updated_ms, now=None):
    """距今天数（同样不允许负数）"""
    if not updated_ms:
        return 0.0
    n = now if now is not None else now_ms()
    return max((n - float(updated_ms)) / DAY_MS, 0.0)
