# -*- coding: utf-8 -*-
"""输出格式的统一约定（与 mem_db.py 并列：一个管数据，一个管呈现）。

为什么要有它（2026-11-19）：30 个动作的输出混着 `===` / `【】` / `[` 三种风格，
连起来看很累。统计下来 `=== 标题 ===` 已是主流（11 个脚本），所以**跟随主流**，
把剩下的少数派统一过来，并给新脚本一套现成的写法。

用法（不必全用，按需挑）：

    from out import title, section, item, action, ok, warn, bad

    print(title("日常体检（memory.db）"))
    print(section("今天该做的"))
    print(item("过期约定 2 条"))
    print(action("跑 mem_check promises 看详情"))
    print(ok("文件引用 36 个全部有效"))

输出效果：

    === 日常体检（memory.db）===

    -- 今天该做的 --
      · 过期约定 2 条
         → 跑 mem_check promises 看详情
      ✅ 文件引用 36 个全部有效

约定（不强制，但新脚本请遵守）：
- 一级标题：`=== 标题 ===`（唯一入口用一次）
- 二级分区：`-- 分区名 --`
- 条目：`  · 内容`
- 动作/下一步：`     → 具体命令`
- 状态行：`  ✅ / ⚠ / ❌ 内容`
"""
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def title(text):
    """一级标题"""
    return "=== %s ===" % text


def section(text):
    """二级分区（前面留空行）"""
    return "\n-- %s --" % text


def item(text, indent=2):
    """普通条目"""
    return "%s· %s" % (" " * indent, text)


def action(text, indent=6):
    """下一步动作"""
    return "%s→ %s" % (" " * indent, text)


def ok(text):
    return "  ✅ %s" % text


def warn(text):
    return "  ⚠ %s" % text


def bad(text):
    return "  ❌ %s" % text


def kv(key, value):
    """键值对（对齐用）"""
    return "  %-10s %s" % (key, value)


def fmt_count(n, unit="条"):
    return "%d %s" % (n, unit)

def ensure_parent(path):
    """确保 path 的父目录存在（2026-11-24，CI 暴露的坑）。

    这些脚本会往 docs/ tmp/ 里写产物，本地因为目录一直在所以从没出过事；
    CI 上 checkout 只有仓库内容，父目录不存在 → FileNotFoundError。
    写之前调一次，比在每个脚本里各写一遍 makedirs 省事。
    """
    import os
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    return path
