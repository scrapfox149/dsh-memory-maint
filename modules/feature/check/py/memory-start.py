# -*- coding: utf-8 -*-
"""开工前的一句话摘要：把「四问 + 五思」摆到眼前，别靠记。

五思（2026-11-24，新建 = 第 1 级）
  目的：四问/五思写在记忆里，但**干活时不会想起它们**（2026-11-24 实测：当天两条都没执行）。
        用户提议「开始的时候先注入四问、五思」——把"想起来"变成"看一眼"。
  方案：一个只读命令，打印：
        ① 四问（每条带**具体该跑什么命令**，不是抽象问题）
        ② 五思（含"④验证要实测数字"的硬要求）
        ③ 当前库状态（条数 / 待办数 / 最近提交），让人知道身处何处
  边界：只读、不查全库（只数条数，快）；不发散、不教学，一屏内。
  验证：空库不崩；输出 < 20 行。
  退路：独立脚本，删掉即可。

用法：
    python mem.py start
    python mem.py start dsh        # 顺便看某个项目
"""
import os
import subprocess
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break
from mem_db import count_status_sql, load  # noqa: E402

ROOT = _here
for _ in range(6):
    if os.path.isdir(os.path.join(ROOT, "modules")):
        break
    ROOT = os.path.dirname(ROOT)


def git_head():
    try:
        r = subprocess.run(["git", "log", "--oneline", "-1"], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=10)
        return (r.stdout or "").strip()[:60]
    except Exception:
        return ""


def main():
    print("=== 开工前 ===")
    print()
    print("四问（每次必过，答不上来先别动手）：")
    print("  ① 说明书在哪？    grep -l \"<关键词>\" DEVELOPING.md README.md")
    print("  ② 功能做过没？    mem.py list | grep <关键词>")
    print("  ③ 工具够不够？    看上面清单里有没有现成的")
    print("  ④ 记忆怎么说？    memory_search \"<关键词>\"")
    print()
    print("五思（造工具类必上；删/移/批量/不可逆按硬条件；短操作可省）：")
    print("  目的 / 方案 / 边界 / 验证 / 退路")
    print("  ⚠ ④验证要写**实测数字**，不是「应该对得上」；新脚本自带 --selftest")
    print()

    try:
        cnt = count_status_sql()
        total = sum(v["active"] for v in cnt.values())
        print("当前：%d 条 active" % total)
    except Exception as e:
        print("当前：(读库失败：%s)" % str(e)[:60])

    # 待办条数（project 层的 todo）
    try:
        todos = [r for r in load(["project"])
                 if (r.get("subcategory") or "") == "todo"
                 and r.get("status") in (None, "active")]
        if todos:
            print("待办：%d 条" % len(todos))
    except Exception:
        pass

    head = git_head()
    if head:
        print("最近提交：%s" % head)
    return 0


if __name__ == "__main__":
    sys.exit(main())
