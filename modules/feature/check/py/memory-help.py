# -*- coding: utf-8 -*-
"""列出插件全部工具与动作（自报家门，不用记）。

为什么要它（2026-11-19）：6 个工具 / 30 个动作，想查某个东西时得先回忆"它叫什么"。
用户说「不能削足适履」——不该让人去适应工具的命名，工具应该能自报。

做法：扫 `modules/*/*/module.json`，每个动作再读对应脚本的 docstring 第一行当说明。
**全部自动发现**，加新动作不用改这里。

用法：
    python memory-help.py           # 全部
    python memory-help.py maint     # 只看某一层/某工具
"""
import io
import json
import os
import re
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_here = os.path.dirname(os.path.abspath(__file__))
ROOT = _here
for _ in range(6):
    if os.path.isdir(os.path.join(ROOT, "modules")):
        break
    ROOT = os.path.dirname(ROOT)

MODULES = os.path.join(ROOT, "modules")


def first_doc(path):
    """取脚本 docstring 的第一行当说明"""
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            txt = f.read(2000)
    except Exception:
        return ""
    # 不能用 ^\s* 配 re.S（\s 会跨行，匹配错位置）——直接找三引号段
    m = re.search(r'"""(.*?)"""', txt, re.S)
    if not m:
        return ""
    line = m.group(1).strip().split("\n")[0].strip()
    return line[:60]


def collect():
    out = []
    if not os.path.isdir(MODULES):
        return out
    for layer in sorted(os.listdir(MODULES)):
        lp = os.path.join(MODULES, layer)
        if not os.path.isdir(lp) or layer.startswith("_"):
            continue
        for mod in sorted(os.listdir(lp)):
            mp = os.path.join(lp, mod, "module.json")
            if not os.path.exists(mp):
                continue
            try:
                d = json.load(io.open(mp, encoding="utf-8"))
            except Exception:
                continue
            cmds = d.get("commands", {})
            rows = []
            for act, spec in cmds.items():
                script = spec if isinstance(spec, str) else spec.get("script", "")
                sp = os.path.join(lp, mod, script)
                desc = first_doc(sp) if script and os.path.exists(sp) else ""
                rows.append((act, desc))
            out.append({
                "layer": layer,
                "module": mod,
                "tool": d.get("tool", ""),
                "desc": (d.get("description") or "")[:70],
                "rows": rows,
            })
    return out


# 「我想干什么 → 用哪个」——比按工具列清单更贴近"要用时想得起来"（2026-11-24）
INTENTS = [
    ("今天有什么要做的", "mem_check daily"),
    ("记忆写得对不对（写法/信号/来源）", "mem_check quality"),
    ("引用的东西还在不在", "mem_check integrity"),
    ("某条为什么被命中", 'mem_query why "<查询>"'),
    ("跟这个相关的还有哪些", 'mem_query expand "<关键词>"'),
    ("间接相关、1 跳够不着的", 'mem_query hipporag "<查询>"'),
    ("有没有该退场/重复的", "mem_maint decay / dedup / dream"),
    ("某一天的记忆脉络", "mem_maint timeline"),
    ("备份 / 恢复", "mem_backup export / restore"),
    ("出问题了看告警", "mem_alert"),
    ("插件自己有没有毛病", "mem_status"),
]


# 「低频」——不是没用，是平时不用。
# 2026-11-24 晚：用户提「低频功能变成同功能的高级功能」——`health` / `weight2` / `sample`
# 已并进 `mem_check daily --advanced`，`agentsmem` / `archive` 并进 `integrity`。
# 这个集合只留给**真的还需要单独跑**的（目前是 source 和 mapexport 的替代者 map）。
# 动作保留但不在常用清单里出现，靠 `--advanced` 或显式调用。
LOW_FREQ = {"health", "sample", "weight2", "archive", "source", "agentsmem"}


def show_group(g, compact=False):
    print("%s（%s/%s，%d 个）" % (g["tool"], g["layer"], g["module"], len(g["rows"])))
    rows = g["rows"]
    if compact:
        # 紧凑模式：一行列完，只给名字
        print("  " + " / ".join(a for a, _d in rows))
        print()
        return
    for act, desc in rows:
        print("  %-12s %s" % (act, ("—— " + desc) if desc else ""))
    print()


def main():
    filt = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    groups = collect()
    if filt:
        groups = [g for g in groups
                  if filt in (g["layer"] + g["module"] + g["tool"]).lower()]

    total = sum(len(g["rows"]) for g in groups)
    if not groups:
        print("没找到匹配「%s」的工具/动作。" % filt)
        print("跑 `mem_check help`（不带参数）看全部。")
        return 1

    # 先按「我想干什么」列——要记接口才能用，说明工具没适应人
    if not filt:
        print("=== 我想干什么？ ===")
        print()
        for what, how in INTENTS:
            print("  %-32s →  %s" % (what, how))
        print()
        print("（下面按工具列完整清单；忘了某个动作名也跑这个）")
        print()

    print("=== 插件动作清单（%d 个工具 / %d 个动作）===" % (len(groups), total))
    print()

    # 分成「常用」「低频」两组：动作多不是问题，不知道哪个该用才是。
    common, low = [], []
    for g in groups:
        rows_c = [(a, d) for a, d in g["rows"] if a not in LOW_FREQ]
        rows_l = [(a, d) for a, d in g["rows"] if a in LOW_FREQ]
        if rows_c:
            common.append({"tool": g["tool"], "layer": g["layer"],
                           "module": g["module"], "rows": rows_c})
        if rows_l:
            low.append({"tool": g["tool"], "layer": g["layer"],
                        "module": g["module"], "rows": rows_l})

    for g in common:
        show_group(g)
    if low:
        print("--- 低频（不是没用，是平时不用）---")
        print()
        for g in low:
            show_group(g, compact=True)
    print("提示：`mem_check daily` 是日常体检（默认动作，不传 action 也是它）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
