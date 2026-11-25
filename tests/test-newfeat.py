# -*- coding: utf-8 -*-
"""新功能的边界测试（这些不在 test-full.py 的 15 组里）。

覆盖：
① agent_name() 的空/超长/环境变量覆盖
② backup.targets 的 0 / 1 / N
③ audit --all 能不能真的看全
④ mem.py 的 args 转发（clear 必须带 --clear-errors --yes）
⑤ help 里必须有「可以改的」段
"""
import json
import os
import subprocess
import sys
import tempfile

# 脚本在 tests/ 里；插件根是它的父，工作区是插件的父（tools/）的父
# 2026-11-24：CI（windows-latest）的 Python 默认用 cp1252 打 stdout，
# 中文一 print 就 UnicodeEncodeError。其他测试脚本都有这段，这个补上。
if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 2026-11-24：CI 的目录是 <repo>/<repo>/ 两层同名，dirname(dirname(BASE)) 会算到
# /home/runner/work 去。所以**环境变量优先**（workflow 里设了 DSH_MEMORY_WORKSPACE），
# 没设才按本地布局推。
WORKSPACE = (os.environ.get("DSH_MEMORY_WORKSPACE")
             or os.path.dirname(os.path.dirname(BASE)))
PY = sys.executable
MEM = os.path.join(BASE, "py-core", "mem.py")
sys.path.insert(0, os.path.join(BASE, "py-core"))

passed, failed, skipped = [], [], []

# 2026-11-24：CI 的 checkout 里**没有 memory.db**（也不该有）。
# 依赖真库的项（audit / status 的库检查）在没库时**跳过**，不算失败——
# 否则 CI 永远是红的，而那是环境差异，不是代码问题。
_DB = os.environ.get("DSH_MEMORY_DB") or os.path.join(WORKSPACE, ".dsh-meow", "memory.db")
HAS_DB = os.path.exists(_DB)


def check(name, ok, detail=""):
    (passed if ok else failed).append(name)
    print("  %s %s%s" % ("✅" if ok else "❌", name, ("  → " + detail) if detail else ""))


def skip(name, why):
    skipped.append(name)
    print("  ⏭ %s（跳过：%s）" % (name, why))


def run(args, env_extra=None, timeout=120):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.path.join(BASE, "py-core")
    env["DSH_MEMORY_WORKSPACE"] = WORKSPACE
    if env_extra:
        env.update(env_extra)
    r = subprocess.run([PY, MEM] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout, env=env)
    return r


def main():
    tmpd = tempfile.mkdtemp(prefix="newfeat-")
    print("=== 新功能边界测试 ===\n临时目录: %s\n" % tmpd)

    # ── ① agent_name() ────────────────────────────────────────────
    print("【① agent_name()】")
    import importlib
    import paths
    importlib.reload(paths)

    got = paths.agent_name()
    check("默认/配置值可取到", bool(got), "得到 %r" % got)

    old = os.environ.pop("DSH_AGENT_NAME", None)
    os.environ["DSH_AGENT_NAME"] = ""
    importlib.reload(paths)
    check("空环境变量不覆盖（回落配置）", paths.agent_name() == got,
          "得到 %r" % paths.agent_name())

    os.environ["DSH_AGENT_NAME"] = "x" * 300
    importlib.reload(paths)
    check("超长名字不崩", paths.agent_name() == "x" * 300, "长度 %d" % len(paths.agent_name()))

    os.environ["DSH_AGENT_NAME"] = "带 空格/斜杠\\和\"引号\""
    importlib.reload(paths)
    v = paths.agent_name()
    check("特殊字符不崩", isinstance(v, str) and len(v) > 0)

    if old is not None:
        os.environ["DSH_AGENT_NAME"] = old
    else:
        os.environ.pop("DSH_AGENT_NAME", None)
    importlib.reload(paths)

    # ── ② backup.targets 的 0 / 1 / N ────────────────────────────
    print("\n【② backup.targets】")
    cfg_path = os.path.join(BASE, "config.json")
    orig = open(cfg_path, encoding="utf-8-sig").read()
    try:
        for n, label in ((0, "空数组（应回落默认）"), (1, "1 个"), (3, "3 个")):
            d = json.loads(orig)
            d.setdefault("backup", {})["targets"] = ["X:\\t%d" % i for i in range(n)]
            open(cfg_path, "w", encoding="utf-8", newline="\n").write(
                json.dumps(d, ensure_ascii=False, indent=2) + "\n")
            r = run(["status", "status"])
            if HAS_DB:
                check("targets=%d（%s）status 不崩" % (n, label), "已知问题" in r.stdout,
                      "rc=%d" % r.returncode)
            else:
                check("targets=%d（%s）status 能跑完" % (n, label),
                      "记忆库" in r.stdout or "status" in r.stdout, "rc=%d" % r.returncode)
    finally:
        open(cfg_path, "w", encoding="utf-8", newline="\n").write(orig)
    check("config.json 已还原", open(cfg_path, encoding="utf-8").read() == orig)

    # ── ③ audit --all ────────────────────────────────────────────
    print("\n【③ audit --all】")
    if not HAS_DB:
        skip("audit --all（三小项）", "没有记忆库，CI 环境")
    else:
        r1 = run(["audit"])
        r2 = run(["audit", "--all"])
        n1 = len(r1.stdout.splitlines())
        n2 = len(r2.stdout.splitlines())
        check("--all 比默认长", n2 > n1, "%d 行 → %d 行" % (n1, n2))
        check("--all 含「建议修」总数", "建议修（" in r2.stdout)
        check("默认版有截断提示", "还有" in r1.stdout or n1 == n2)

    # ── ④ mem.py 的 args 转发（clear 必须带 --clear-errors）──────
    print("\n【④ args 转发】")
    logd = os.path.join(tmpd, "state")
    os.makedirs(logd, exist_ok=True)
    errf = os.path.join(logd, "errors.jsonl")
    with open(errf, "w", encoding="utf-8") as f:
        for i in ("A", "B"):
            f.write(json.dumps({"kind": "exception", "script": "t.py",
                                "error": "假告警 " + i, "time": 1}, ensure_ascii=False) + "\n")
    before = sum(1 for _ in open(errf, encoding="utf-8"))
    r = run(["clear"], {"DSH_MEMORY_LOG_DIR": logd})
    after = sum(1 for _ in open(errf, encoding="utf-8")) if os.path.exists(errf) else 0
    check("clear 真的清空了（args 传到了）", before == 2 and after == 0,
          "%d 行 → %d 行" % (before, after))

    # ── ⑤ help 里要有「可以改的」段 ─────────────────────────────
    print("\n【⑤ help 的可配置摘要】")
    r = run(["help"])
    check("help 含「可以改的」", "可以改的" in r.stdout)
    check("help 含 CONFIG.md 指引", "CONFIG.md" in r.stdout)

    # ── ⑥ project 的子类过滤（#13）与 --json（#12）──────────────
    print("\n【⑥ project --decisions / --quotes / --json】")
    if not HAS_DB:
        skip("project 子类过滤", "CI 无 memory.db")
        skip("project --json", "CI 无 memory.db")
    else:
        r = run(["project", "dsh", "--decisions"])
        check("--decisions 有「--- 决策」段", "--- 决策（" in r.stdout)

        r = run(["project", "dsh", "--quotes"])
        check("--quotes 不崩（空子类有提示）", "原话（" in r.stdout)

        r = run(["project", "dsh", "--json"])
        try:
            d = json.loads(r.stdout)
            ok = isinstance(d, dict) and d.get("project") == "dsh" and d.get("total", 0) > 0 \
                and isinstance(d.get("items"), list) and len(d["items"]) == d["total"]
            check("--json 可解析且 items==total", ok,
                  "total=%s items=%s" % (d.get("total"), len(d.get("items", []))))
        except Exception as e:
            check("--json 可解析且 items==total", False, str(e)[:60])

        r = run(["project", "dsh", "--json", "--todo"])
        try:
            d = json.loads(r.stdout)
            check("--json --todo 组合只出 todo",
                  d.get("subcategories") == ["todo"] and
                  all(i.get("subcategory") == "todo" for i in d.get("items", [])),
                  "subcategories=%s" % d.get("subcategories"))
        except Exception as e:
            check("--json --todo 组合只出 todo", False, str(e)[:60])

    # ── ⑦ people / dump 的 --json（#12）──────────────────────────
    print("\n【⑦ people --json / dump --json】")
    if not HAS_DB:
        skip("people --json", "CI 无 memory.db")
        skip("dump --json", "CI 无 memory.db")
    else:
        for cmd, key in (("people", "counts"), ("dump", "tiers")):
            r = run([cmd, "--json"])
            try:
                d = json.loads(r.stdout)
                check("%s --json 可解析（含 %s）" % (cmd, key), key in d)
            except Exception as e:
                check("%s --json 可解析（含 %s）" % (cmd, key), False, str(e)[:60])

    # ── 汇总 ────────────────────────────────────────────────────
    total = len(passed) + len(failed)
    print("\n" + "=" * 60)
    print("新功能边界：%d 通过 / %d 失败 / %d 跳过 / 共 %d"
          % (len(passed), len(failed), len(skipped), total))
    for f in failed:
        print("  ❌ %s" % f)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
