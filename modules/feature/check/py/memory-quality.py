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
    except Exception as e:
        return None, str(e)[:120]
    out = (r.stdout or "") + (r.stderr or "")
    # 2026-11-26（极限边界测试抓到）：**子脚本崩了不能当成功**。
    # 之前 `return out, None` 不看退出码 → `audit` 崩了（输出里是报错）
    # → 后面 grab() 抓不到数字得到 "?" → 落进 else 分支写「写法无必须修项」。
    # **库损坏了还报"全绿"**，比崩溃危险得多。
    if err_like(out):
        tail = [l for l in out.strip().splitlines() if l.strip()]
        return out, ("子脚本报错（退出码 %d）：%s"
                     % (r.returncode, tail[-1][:100] if tail else "无输出"))
    return out, None


def err_like(out):
    """输出里有没有"这次跑坏了"的痕迹。

    三条都认，缺一不可：
      ① Traceback 指向自己脚本
      ② `[stderr]` 里有 Error/错误
      ③ 任何位置出现 RuntimeError / FileNotFoundError 等异常名
         （**不能用行首锚点**——out 是 stdout+stderr 拼的，异常往往在中间）
    """
    if re.search(r'File ".*(py-core|modules)[\\/]', out):
        return True
    if re.search(r"\b(RuntimeError|FileNotFoundError|ValueError|KeyError|"
                 r"OperationalError|DatabaseError|PermissionError)\b", out):
        return True
    if re.search(r"(记忆库损坏|不是 SQLite|无法读取|记忆库不存在|找不到记忆库)", out):
        return True
    return False


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
    broken = []      # 2026-11-26：子检查跑不成的名字（库坏了/脚本崩了）

    # audit：必须修 / 建议修
    out, err = results["audit"]
    if err:
        print("  audit   ✗ %s" % err[:80])
        broken.append("audit")
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
        broken.append("signal")
    else:
        n = grab(out, r"共\s*(\d+)\s*条", "?")
        print("  权重信号 %s 条（候选，规则会误报，需人工看）" % n)
        if n not in ("0", "?"):
            okays.append("权重信号 %s 条属候选" % n)

    # source：提到他人却没标来源
    out, err = results["source"]
    if err:
        print("  source  ✗ %s" % err[:80])
        broken.append("source")
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
    elif broken:
        # 2026-11-26（极限边界测试抓到）：**子检查跑不成时不能说"没有必须处理的项"**。
        # 之前库损坏 → audit 报错但被当"0 条" → 这里仍打 ✅，用户会以为库是好的。
        print("结论：⚠ %d 项检查没跑成（%s）—— 数字不可信，先修库/脚本"
              % (len(broken), "、".join(broken)))
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
    return 1 if (todo or broken) else 0


if __name__ == "__main__":
    sys.exit(main())
