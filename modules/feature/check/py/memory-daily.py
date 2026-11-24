# -*- coding: utf-8 -*-
"""日常体检：不只报状态，还告诉你「今天该做什么」。

演进（2026-11-19）：
  v1 只汇总 5 个检查的原始输出 → 判定太糙，3 个红里 1 个真问题
  v2 修正判定（建议≠必须、降级≠异常、只看本次新增）→ 全绿但只是"镜子"
  v3 **改成分区**：该做的（按优先级 + 带动作）/ 不用管的（说明原因）/ 其余正常

设计：只读；任一项失败继续；`--verbose` 展开明细；`--quiet` 只列该做的。
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

from mem_db import DB, count_status_sql  # noqa: E402

ROOT = _here
for _ in range(6):
    if os.path.isdir(os.path.join(ROOT, "modules")):
        break
    ROOT = os.path.dirname(ROOT)

PY = sys.executable


def run(rel_script, args=None, timeout=180):
    path = os.path.join(ROOT, rel_script)
    if not os.path.exists(path):
        return False, "脚本不存在: " + rel_script
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.path.join(ROOT, "py-core")
    try:
        r = subprocess.run([PY, path] + (args or []), capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=timeout, env=env)
        return r.returncode == 0, ((r.stdout or "") + (r.stderr or "")).strip()
    except Exception as exc:
        return False, str(exc)


def grep_int(text, pattern, default=0):
    import re
    m = re.search(pattern, text or "")
    return int(m.group(1)) if m else default


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    quiet = "--quiet" in sys.argv or "-q" in sys.argv
    # 2026-11-24：`--advanced` 把原来几个低频动作（health / weight2 / sample）的排障信息
    # 并进日报——**同功能的高级模式**，平时不吵，要排障时加一个开关就有。
    advanced = "--advanced" in sys.argv or "-a" in sys.argv

    todo = []      # (优先级 1-9 小在前, 标题, 动作提示, 明细)
    ignore = []    # (标题, 为什么不用管)
    okay = []      # 一句话

    # ---- 1. 到期约定（最高优先级）----
    ok, out = run("modules/feature/check/py/memory-promises.py")
    # promises 的输出形如「今天: 2026-11-19 | 带期限的约定: 1 条」+「[剩 179 天] ...」
    # 不能抓「今天:」后面的数字（那是年份），要数「剩 0 天」和「已过期」的行
    n_due = len([l for l in out.split("\n") if "剩 0 天" in l])
    n_over = len([l for l in out.split("\n") if "已过期" in l])
    if n_over:
        todo.append((1, "⏰ 已过期约定 %d 条" % n_over,
                     "→ 跑 `mem_check promises` 看是哪些，该做完的做完、该改期的改期", out))
    elif n_due:
        todo.append((2, "⏰ 今天到期约定 %d 条" % n_due,
                     "→ 跑 `mem_check promises` 看详情", out))

    # ---- 2. 写作规则：只有「必须修」算该做 ----
    ok, out = run("modules/feature/check/py/memory-audit.py")
    n_must = grep_int(out, r"必须修（(\d+)）", 999)
    n_minor = grep_int(out, r"建议修（(\d+)）", 0)
    if n_must:
        todo.append((3, "📝 必须修 %d 条写作问题" % n_must,
                     "→ 跑 `mem_check audit` 看明细", out))
    if n_minor:
        ignore.append(("audit 建议修 %d 条" % n_minor, "都是「偏长」这类，不影响检索"))

    # ---- 3. 文件引用：真问题 ----
    ok, out = run("modules/feature/check/py/check-memory-refs.py")
    n_missing = grep_int(out, r"不存在的:\s*(\d+)")
    if n_missing:
        todo.append((2, "🔗 %d 个文件引用失效" % n_missing,
                     "→ 跑 `mem_check refs` 看是哪些记忆指向了不存在的文件", out))
    else:
        okay.append("文件引用 %s 个全部有效" % (grep_int(out, r"文件路径:\s*(\d+)") or "?"))

    # ---- 4. 自检 ----
    ok, out = run("modules/observe/status/py/memory-status.py")
    if "一切正常" not in out:
        todo.append((1, "🔧 插件自检不通过",
                     "→ 跑 `mem_status` 看哪块有问题", out))
    else:
        okay.append("插件自检 %s" % (("模块%s" % grep_int(out, r"模块\s*(\d+)")) if "模块" in out else "通过"))

    # ---- 5. 告警：只看本次新增异常 ----
    err_file = os.path.join(os.environ.get("DSH_MEMORY_LOG_DIR") or os.path.join(ROOT, "state"),
                            "errors.jsonl")

    def exc_count(path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return sum(1 for l in f if '"exception"' in l or '"anomaly"' in l)
        except Exception:
            return 0

    before = exc_count(err_file)
    ok, out = run("modules/observe/alert/py/memory-alert.py")
    new_exc = max(0, exc_count(err_file) - before)
    if new_exc:
        todo.append((1, "🚨 本次新增异常 %d 条" % new_exc,
                     "→ 跑 `mem_alert` 看具体是什么", out))
    n_deg = grep_int(out, r"降级[^\d]*\s*(\d+)")
    if n_deg:
        ignore.append(("告警里的降级 %d 条" % n_deg, "缺列补 None，是正常现象"))
    if not new_exc:
        okay.append("本次无新异常")

    # ---- 6. signal 噪音说明 ----
    ok, sig = run("modules/feature/check/py/memory-signal-check.py")
    n_sig = grep_int(sig, r"共\s*(\d+)\s*条")
    if n_sig:
        ignore.append(("signal %d 条" % n_sig, "长文没命中信号词表，多数是语义重要但措辞不同"))

    # ---- 输出（2026-11-24 压缩：原来 7 段，现在 3-4 行）----
    # 压缩原则：结论先说，能合并的合并，解释留给 --verbose。
    # 原来每行都带「为什么不用管」，读完 3 行才看到结论——顺序反了。
    cnt = count_status_sql()
    total = sum(v["active"] for v in cnt.values())

    if quiet:
        for pri, title, action, detail in sorted(todo, key=lambda x: x[0]):
            print("%s  %s" % (title, action))
        return 0 if not todo else 1

    print("=== 日常体检（%s）· %d 条 active ===" % (os.path.basename(DB), total))

    if todo:
        todo.sort(key=lambda x: x[0])
        print("⚠ %d 件事要做：" % len(todo))
        for pri, title, action, detail in todo:
            print("  %s  %s" % (title, action))
            if verbose:
                for l in detail.split("\n")[:10]:
                    if l.strip():
                        print("       " + l.strip()[:96])
        # 检查类脚本的契约：**无论有没有问题都要打一行「结论：」**——
        # 冒烟靠它区分「跑完了但有警告」和「跑崩了」。
        # 2026-11-24 压缩输出时漏了这行，有 todo 时冒烟就判失败（自己引入的 bug）。
        print("结论：⚠ %d 件事要做" % len(todo))
    else:
        # 结论行本身就说明了"没事要做"，不必再单独打一行 ✅（压缩的目的就是别啰嗦）
        print("结论：✅ 没事要做")

    if ignore:
        print("不用管的：%s" % " / ".join(t for t, _ in ignore))
    if okay:
        print("正常：%s" % " · ".join(okay))

    # ---- 高级模式：把低频动作的排障信息并进来 ----
    # health / weight2 / sample 原来各是一个独立动作，一年用不上几次；
    # 但"库有没有毛病"这类问题又确实需要它们。并进 --advanced，平时不占位置。
    if advanced:
        print()
        print("--- 高级：排障信息 ---")
        for label, rel in (
            ("库状态", "modules/feature/check/py/memory-health.py"),
            ("权重清单", "modules/feature/check/py/memory-weight-check2.py"),
            ("抽样覆盖", "modules/feature/check/py/memory-sample.py"),
        ):
            ok_a, out_a = run(rel)
            print()
            print("【%s】" % label)
            if not ok_a:
                print("  （跑失败）")
                continue
            # 只显示前 12 行，避免把日报撑爆
            for line in (out_a or "").split("\n")[:12]:
                if line.strip():
                    print("  " + line.strip()[:100])

    if verbose:
        print()
        for t, why in ignore:
            print("  · %s —— %s" % (t, why))
        print("  （忘了动作名就跑 `mem_check help`）")
    elif todo and not advanced:
        # 有问题时提示"要看全部信息加 --advanced"，没问题时不提——**提示本身也是噪音**。
        # 这比"要用户记得有这个参数"贴「自然想起来」：它在该出现的时候出现。
        print("（要看完整排障信息：`mem.py daily --advanced`）")
    return 0 if not todo else 1


if __name__ == "__main__":
    sys.exit(main())
