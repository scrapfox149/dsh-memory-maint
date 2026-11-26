# -*- coding: utf-8 -*-
"""记忆库里的文件引用检查：提取所有 tools/ docs/ art/ 路径，检查是否真实存在。

2026-11-17 改用契约层 mem_db.load() 读库（原来自己写死表名列名）：
插件改 schema 时只需改 mem_db.py 一处，本脚本不用动。
"""
import os
import re
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break
from paths import workspace_root  # noqa: E402
from mem_db import load  # noqa: E402

WS = workspace_root()

# 匹配 tools/xxx.py、docs/xxx.md、art/xxx、scripts/xxx
# 2026-11-25：左边加负向后视——`tools/dsh-memory-maint/docs/CONFIG.md` 这种
# 「插件内部的 docs/」不该被当成工作区的 `docs/CONFIG.md`。
# 判据：这 4 个词前面必须是「行首 / 空白 / 反引号 / 括号 / 冒号」，不能是路径字符。
PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_\-./\\])"
    r"(tools|docs|art|scripts)[/\\]([A-Za-z0-9_\-\u4e00-\u9fa5.]+)")

refs = {}
# 2026-11-19 改：只查 active —— archived 条目不参与检索了，
# 它的旧路径不该再报警（否则永久挂着一条假问题）。
for it in load(status="active"):
    c = it["content"]
    if not c:
        continue
    for m in PATH_RE.finditer(c):
        key = "%s/%s" % (m.group(1), m.group(2))
        refs.setdefault(key, []).append((it["tier"], it["id"]))

missing = []
for key, where in sorted(refs.items()):
    # 跳过通配符截断（如 "tools/memory-*.py" 被正则切出 "tools/memory-"）
    if key.endswith(("-", "_", "/")):
        continue
    # 跳过占位符与示例（2026-11-23）：记忆正文里常写 "tools/xxx.py"、
    # "docs/<名字>.md" 这类模板文本，它们不是真引用，报了就是永久假红。
    if "xxx" in key.lower() or "*" in key or "<" in key:
        continue
    p = os.path.join(WS, key.replace("/", os.sep))
    if not os.path.exists(p):
        missing.append((key, where))

print("记忆库里引用的文件路径:", len(refs), "个")
print("不存在的:", len(missing))
print()
for key, where in missing:
    print("[X] %s" % key)
    for t, iid in where[:3]:
        print("   [%s] %s" % (t, iid[:12]))
print()
print("结论：%s" % ("⚠ %d 个引用失效" % len(missing) if missing
                  else "✅ 引用的文件都在"))
