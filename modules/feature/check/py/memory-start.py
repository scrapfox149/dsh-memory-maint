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

# 配置：插件根目录的 config.json（有就用，没有就全默认）。
# 2026-11-24：用户要"可选功能"，但设置页（UI）是 B 方案、以后再做；
# 先给配置文件，改 JSON 即生效。
DEFAULTS = {
    "expandOnPyChanges": True,
    "expandOnDocsOnly": False,
    "timeoutSeconds": 10,
    "showTodoCount": True,
}


def load_config():
    cfg = dict(DEFAULTS)
    path = os.path.join(ROOT, "config.json")
    if not os.path.isfile(path):
        return cfg
    try:
        import json
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        sec = raw.get("start") or {}
        for k, v in DEFAULTS.items():
            if k in sec and not isinstance(sec[k], dict):
                cfg[k] = sec[k]
    except Exception:
        pass          # 配置坏了就用默认，不因为配置让命令崩
    return cfg


CFG = load_config()


def git_changes():
    """看工作区里有没有未提交改动，按类型分开数。

    2026-11-24：用户提「普通小项目小事没必要动这套规则，问题是怎么让它被需要时出现」。
    不能靠"我自己判断今天算不算大事"（那又是自觉），要看**可观测的信号**：
    工作区里有没有真在被改的脚本 / 文档。
    """
    try:
        r = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=CFG["timeoutSeconds"])
        lines = [l for l in (r.stdout or "").splitlines() if l.strip()]
    except Exception:
        return None, None
    py = [l for l in lines if l.rstrip().endswith(".py")]
    md = [l for l in lines if l.rstrip().endswith((".md", ".json", ".yml"))]
    return py, md


def git_head():
    try:
        r = subprocess.run(["git", "log", "--oneline", "-1"], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=10)
        return (r.stdout or "").strip()[:60]
    except Exception:
        return ""


def selftest():
    """自测：只验自己的逻辑，不依赖真实库和 git。

    2026-11-24（B 方案）：清单外的新脚本必须支持 --selftest。
    它跑的是**边界用例**——空配置、坏配置、缺项——而不是"能不能跑"。

    跑法：python memory-start.py --selftest
    """
    import json
    import tempfile
    passed, failed = [], []

    def check(name, cond, detail=""):
        (passed if cond else failed).append(name + ((" " + detail) if detail and not cond else ""))

    # ① 默认配置的形状
    check("DEFAULTS 四个键齐全", set(DEFAULTS) == {
        "expandOnPyChanges", "expandOnDocsOnly", "timeoutSeconds", "showTodoCount"})

    # ② 配置文件不存在 → 全用默认
    old_root = globals().get("ROOT")
    try:
        tmpd = tempfile.mkdtemp()
        globals()["ROOT"] = tmpd
        cfg = load_config()
        check("无 config.json 时用默认", cfg == DEFAULTS)

        # ③ 坏 JSON → 不崩，仍用默认
        with open(os.path.join(tmpd, "config.json"), "w", encoding="utf-8") as f:
            f.write("{ 这不是 json ")
        cfg = load_config()
        check("坏 config.json 不崩且用默认", cfg == DEFAULTS)

        # ④ 部分配置 → 只覆盖写了的，其余保持默认
        with open(os.path.join(tmpd, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"start": {"expandOnPyChanges": False}}, f)
        cfg = load_config()
        check("部分配置只覆盖写了的", cfg["expandOnPyChanges"] is False
              and cfg["timeoutSeconds"] == DEFAULTS["timeoutSeconds"])
    finally:
        if old_root is not None:
            globals()["ROOT"] = old_root

    # ⑤ 输出的关键字样（保证四问/五思真的会打出来）
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    for word in ("四问", "五思", "说明书在哪", "验证要写"):
        check("输出含「%s」" % word, word in src)

    total = len(passed) + len(failed)
    print("memory-start 自测：%d 通过 / %d 失败 / 共 %d" % (len(passed), len(failed), total))
    for f in failed:
        print("  ❌ %s" % f)
    return 0 if not failed else 1


def main():
    if "--selftest" in sys.argv:
        return selftest()

    py_changes, md_changes = git_changes()

    # 判断场景：只在"真在动工具"时才把完整规则摆出来，否则一句话就够。
    # 不靠感觉，靠工作区里有没有未提交的脚本改动。
    if py_changes is None:
        heavy = True          # 读不到 git 就保守当"重"（宁可多提醒）
        reason = "读不到 git 状态，保守处理"
    elif py_changes and CFG["expandOnPyChanges"]:
        heavy = True
        reason = "检测到 %d 处脚本改动 —— 造工具场景" % len(py_changes)
    elif md_changes:
        heavy = bool(CFG["expandOnDocsOnly"])
        reason = "只有 %d 处文档/配置改动 —— 按硬条件看要不要五思" % len(md_changes)
    else:
        heavy = False
        reason = "没有未提交的脚本改动"

    print("=== 开工前 ===")
    print()

    if not heavy:
        print("✅ %s（今天大概是查 / 看 / 说）" % reason)
        print("   四问可省；真要改东西了，跑一次 `mem.py start` 会展开完整版")
        print()
        try:
            cnt = count_status_sql()
            print("当前：%d 条 active" % sum(v["active"] for v in cnt.values()))
        except Exception:
            pass
        head = git_head()
        if head:
            print("最近提交：%s" % head)
        return 0

    print("🔧 %s" % reason)
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

    if py_changes:
        print("正在改的脚本：")
        for l in py_changes[:8]:
            print("  %s" % l.strip())
        if len(py_changes) > 8:
            print("  …还有 %d 处" % (len(py_changes) - 8))
        print()

    try:
        cnt = count_status_sql()
        print("当前：%d 条 active" % sum(v["active"] for v in cnt.values()))
    except Exception as e:
        print("当前：(读库失败：%s)" % str(e)[:60])

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
