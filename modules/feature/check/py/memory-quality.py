# -*- coding: utf-8 -*-
"""内容质量一览：把 audit / signal / source 三个检查压成一份可读结果。

五思（2026-11-24，新建 = 第 1 级）
  目的：`mem_check` 有 13 个动作，问「这条记忆写得对不对」时要分别跑 audit、signal、
        source 三个，还要自己对照三份输出。**合并入口，不合并脚本**。
  方案：**薄封装**——依次 subprocess 调那三个脚本，解析它们已有的输出（正则抓数字），
        再拼成一份带结论的短报告。**脚本一行不改**，所以判据和输出格式都不会走样。
  边界：只读；任一子脚本失败不影响其余（记录并继续）；数字抓不到就标 "?"，不猜。
  验证：与分别跑三个脚本的数字对得上；空库不崩。
  退路：独立脚本，删掉即可。

用法：
    python mem.py quality            # 内容质量一览
    python mem.py quality --verbose  # 附带各脚本原始输出
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
    ("audit", "modules/feature/check/py/memory-audit.py"),
    ("signal", "modules/feature/check/py/memory-signal-check.py"),
    ("source", "modules/feature/check/py/memory-source-check.py"),
]


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
    results = {}
    for name, rel in PARTS:
        out, err = run(rel)
        results[name] = (out, err)

    print("=== 内容质量（写法 / 信号 / 来源）===")
    print()

    todo = []
    okays = []

    # audit：必须修 / 建议修
    out, err = results["audit"]
    if err:
        print("  audit   ✗ %s" % err[:80])
    else:
        must = grab(out, r"必须修（(\d+)）", "?")
        minor = grab(out, r"建议修（(\d+)）", "?")
        if must not in ("0", "?"):
            todo.append("audit 必须修 %s 条（跑 mem.py check audit 看明细）" % must)
        else:
            okays.append("写法无必须修项")
        print("  写法     必须修 %s / 建议修 %s（建议多为「偏长」，不影响检索）" % (must, minor))

    # signal：importance 越级（候选，需人工复核）
    out, err = results["signal"]
    if err:
        print("  signal  ✗ %s" % err[:80])
    else:
        n = grab(out, r"共\s*(\d+)\s*条", "?")
        print("  权重信号 %s 条（候选，规则会误报，需人工看）" % n)
        if n not in ("0", "?"):
            okays.append("权重信号 %s 条属候选" % n)

    # source：提到他人却没标来源
    out, err = results["source"]
    if err:
        print("  source  ✗ %s" % err[:80])
    else:
        # 它的输出是「提及他人但没有来源标记: 7 条」，不是「共 N 条」（2026-11-24 踩到）
        n = grab(out, r"没有来源标记:\s*(\d+)\s*条", None)
        if n is None:
            n = grab(out, r":\s*(\d+)\s*条", "?")
        if n not in ("0", "?"):
            todo.append("来源缺失 %s 条（跑 mem.py check source 看明细）" % n)
        else:
            okays.append("来源标记齐全")
        print("  来源标记 %s 条缺失" % n)

    print()
    if todo:
        print("需要处理：")
        for t in todo:
            print("  · %s" % t)
        # 检查类脚本的契约：**无论有没有问题都要打一行「结论：」**——
        # 冒烟测试靠它区分「跑完了但有警告」和「跑崩了」（2026-11-24 踩到）
        print("结论：⚠ %d 项需要处理" % len(todo))
    else:
        print("结论：✅ 内容质量没有必须处理的项")
    if okays:
        print("（%s）" % " · ".join(okays))

    if verbose:
        print()
        for name, _rel in PARTS:
            out, err = results[name]
            print("----- %s 原始输出 -----" % name)
            if err:
                print(err)
            else:
                print((out or "").strip()[:2000])
            print()
    return 1 if todo else 0


if __name__ == "__main__":
    sys.exit(main())
