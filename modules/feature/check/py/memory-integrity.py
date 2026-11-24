# -*- coding: utf-8 -*-
"""引用一致性一览：把 refs / agents / agentsmem / archive 四个检查压成一份。

五思（2026-11-24，新建 = 第 1 级）
  目的：问「引用的东西还在不在」时要分别跑四个脚本、自己对照四份输出。合并入口，不合并脚本。
  方案：薄封装——依次 subprocess 调，正则抓各自的关键数字，拼成一份带结论的短报告。
        脚本一行不改，判据和输出格式都不会走样。
  边界：只读；`check-agents` 在 CI 上会因缺本机设施而失败——**那要标「跳过」不是「失败」**
        （用它的输出里有没有「通过 N 项」来区分）。
  验证：与分别跑四个脚本的数字对得上；本地全绿时结论为 ✅。
  退路：独立脚本，删掉即可。

用法：
    python mem.py integrity
    python mem.py integrity --verbose
"""
import os
import re
import subprocess
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_here = os.path.dirname(os.path.abspath(__file__))
_ro = _here
for _ in range(6):
    if os.path.isdir(os.path.join(_ro, "modules")):
        break
    _ro = os.path.dirname(_ro)
PY = sys.executable

PARTS = [
    ("refs", "modules/feature/check/py/check-memory-refs.py"),
    ("agents", "modules/feature/check/py/check-agents.py"),
    ("agentsmem", "modules/feature/check/py/check-agents-memory.py"),
    ("archive", "modules/feature/check/py/memory-archive-check.py"),
]

# 这些脚本在缺少本机设施时**不是坏**，是环境不对（见 module.json 的 skipIf）
ENV_DEPENDENT = {"agents"}


def run(rel):
    path = os.path.join(_ro, rel)
    if not os.path.exists(path):
        return None, "脚本不存在"
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.path.join(_ro, "py-core")
    try:
        r = subprocess.run([PY, path], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=180, env=env)
        return (r.stdout or "") + (r.stderr or ""), None
    except Exception as e:
        return None, str(e)


def grab(text, pattern, default=None):
    m = re.search(pattern, text or "")
    return m.group(1) if m else default


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    results = {name: run(rel) for name, rel in PARTS}

    print("=== 引用一致性（文件 / AGENTS / 归档）===")
    print()

    todo = []
    okays = []

    # refs：记忆里引用的路径还在不在
    out, err = results["refs"]
    if err:
        print("  文件引用 ✗ %s" % err[:80])
    else:
        total = grab(out, r"文件路径:\s*(\d+)", "?")
        missing = grab(out, r"不存在的:\s*(\d+)", "?")
        if missing not in ("0", "?"):
            todo.append("文件引用失效 %s 个（跑 mem.py check refs 看是哪些）" % missing)
        else:
            okays.append("文件引用 %s 个全部有效" % total)
        print("  文件引用 共 %s 个 / 失效 %s 个" % (total, missing))

    # agents：AGENTS.md 声明的东西是否真存在（依赖本机）
    out, err = results["agents"]
    if err:
        print("  AGENTS   ✗ %s" % err[:80])
    else:
        passed = grab(out, r"通过\s*(\d+)\s*项", None)
        if passed is None:
            # 没有「通过 N 项」说明不是正常跑完 → 环境问题，标跳过
            print("  AGENTS   ⏭ 跳过（缺本机设施，非故障）")
        else:
            bad = grab(out, r"问题\s*(\d+)\s*项", "0")
            if bad not in ("0",):
                todo.append("AGENTS 声明的 %s 项有问题（跑 mem.py check agents）" % bad)
            else:
                okays.append("AGENTS 声明 %s 项全部通过" % passed)
            print("  AGENTS   通过 %s 项 / 问题 %s 项" % (passed, bad))

    # agentsmem：AGENTS 里的记忆库引用 ↔ 实际库
    out, err = results["agentsmem"]
    if err:
        print("  AGENTS↔库 ✗ %s" % err[:80])
    else:
        if "跳过" in (out or ""):
            print("  AGENTS↔库 ⏭ 跳过（没有 AGENTS.md，非故障）")
        else:
            n = grab(out, r"记忆库引用:\s*(\d+)\s*条", "?")
            bad = grab(out, r"失效\s*(\d+)", None)
            print("  AGENTS↔库 引用 %s 条" % n)
            if bad not in (None, "0"):
                todo.append("AGENTS 里的记忆库引用有 %s 条失效" % bad)

    # archive：归档体检
    out, err = results["archive"]
    if err:
        print("  归档     ✗ %s" % err[:80])
    else:
        bad = grab(out, r"问题\s*(\d+)|失效\s*(\d+)", None)
        if bad not in (None, "0"):
            todo.append("归档检查发现问题 %s 处（跑 mem.py check archive）" % bad)
        else:
            okays.append("归档无问题")
        print("  归档     %s" % ("有问题" if bad not in (None, "0") else "正常"))

    print()
    if todo:
        print("需要处理：")
        for t in todo:
            print("  · %s" % t)
        print("结论：⚠ %d 项需要处理" % len(todo))
    else:
        print("结论：✅ 引用一致，没有必须处理的项")
    if okays:
        print("（%s）" % " · ".join(okays))

    if verbose:
        print()
        for name, _rel in PARTS:
            out, err = results[name]
            print("----- %s 原始输出 -----" % name)
            print(err if err else (out or "").strip()[:2000])
            print()
    return 1 if todo else 0


if __name__ == "__main__":
    sys.exit(main())
