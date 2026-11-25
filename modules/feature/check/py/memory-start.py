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
    "showAssets": True,          # 2026-11-25：开工时列项目资产
    "checklist": "start-checklist.md",
}

# 内置默认（没有 checklist 文件时用）。和 start-checklist.md 的内容保持一致。
# 2026-11-24：用户说「start 应该开放自己改，因为在我们这是五思，在其他人那里可能会是别的规则」——
# 四问/五思是**这一套**，不是硬规则。所以改成读文件，别人换一套写法即可。
DEFAULT_CHECKLIST = """## 四问（每次必过，答不上来先别动手）

① 说明书在哪？    grep -l "<关键词>" DEVELOPING.md README.md
② 功能做过没？    mem.py list | grep <关键词>
③ 工具够不够？    看上面清单里有没有现成的
④ 记忆怎么说？    memory_search "<关键词>"

## 五思（造工具类必上；删/移/批量/不可逆按硬条件；短操作可省）

目的 / 方案 / 边界 / 验证 / 退路
⚠ ④验证要写实测数字，不是「应该对得上」；新脚本自带 --selftest
"""


def load_checklist(cfg):
    """读清单文件；没有就用内置默认。返回 (文本, 来源说明)。

    文件里 `>` 开头的行是**写给人看的说明**，不打印（想留备注就用它）。
    """
    name = cfg.get("checklist") or "start-checklist.md"
    path = os.path.join(ROOT, name)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                lines = [l.rstrip("\n") for l in f]
            # 去掉 `>` 说明行和纯空行
            kept = [l for l in lines if not l.lstrip().startswith(">")]
            text = "\n".join(kept).strip()
            # 连续多个空行压成一个
            while "\n\n\n" in text:
                text = text.replace("\n\n\n", "\n\n")
            return text, name
        except Exception:
            pass
    return DEFAULT_CHECKLIST.strip(), "内置默认"


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


def _workspace():
    """工作区根（用于判断"这里有没有在改东西"）。

    2026-11-25：原来 git 命令用的是 cwd=ROOT（**插件根**），
    但注释写的是"工作区"——插件根在工作区里时，看到的是整个仓库的改动；
    插件装在 profile（不是 git 仓库）时，git 直接报错。**两种情况下"轻路"都触发不到。**
    """
    try:
        from paths import workspace_root
        return workspace_root()
    except Exception:
        return ROOT


def git_changes():
    """看工作区里有没有未提交改动，按类型分开数。

    2026-11-24：用户提「普通小项目小事没必要动这套规则，问题是怎么让它被需要时出现」。
    不能靠"我自己判断今天算不算大事"（那又是自觉），要看**可观测的信号**：
    工作区里有没有真在被改的脚本 / 文档。
    """
    try:
        r = subprocess.run(["git", "status", "--porcelain"], cwd=_workspace(),
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
        r = subprocess.run(["git", "log", "--oneline", "-1"], cwd=_workspace(),
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
    check("DEFAULTS 六个键齐全", set(DEFAULTS) == {
        "expandOnPyChanges", "expandOnDocsOnly", "timeoutSeconds", "showTodoCount",
        "showAssets", "checklist"})

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


# ── 「可配置」强提醒只做一次（用户 2026-11-24：这个文件应该是只主动强提醒一次，后面都作为说明文件存在）──
def _state_dir():
    """和 lib 那边一致的 state 目录：DSH_MEMORY_LOG_DIR 优先，否则工作区/tools/插件/state。"""
    env = os.environ.get("DSH_MEMORY_LOG_DIR")
    if env:
        return env
    try:
        from paths import workspace_root
        return os.path.join(workspace_root(), "tools", "dsh-memory-maint", ".local", "state")
    except Exception:
        return None


def _tip_marker():
    d = _state_dir()
    return os.path.join(d, "config-tipped") if d else None


def is_first_time_config_tip():
    """还没提过 → True。拿不到 state 目录就返回 False（宁可不提，也别每次都刷屏）。"""
    p = _tip_marker()
    if not p:
        return False
    return not os.path.exists(p)


def mark_config_tipped():
    p = _tip_marker()
    if not p:
        return
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("1\n")
    except Exception:
        pass


def assets_summary():
    """列出配了目录的项目：文件数 + 记忆条数。

    2026-11-25：用户提「项目记忆检索」——开工时要知道这个项目已有什么。
    **不重复实现扫描逻辑**：调 `mem.py assets <项目> --json` 拿数字（合并入口，不合并脚本）。
    失败就整段不打印——`start` 是每天跑的，不能因为一个项目目录没了就报错。
    """
    # 2026-11-25：配置从 0.4.1 起放**工作区**（升级不丢），不是插件根。
    # 和 lib/index.js 的 configPath() 保持一致：工作区优先，插件根兜底。
    try:
        import json as _json
        from paths import workspace_root
        cand = [
            os.path.join(workspace_root(), "tools", "dsh-memory-maint", "config.json"),
            os.path.join(ROOT, "config.json"),
        ]
        raw = {}
        for _p in cand:
            if os.path.exists(_p):
                with open(_p, encoding="utf-8-sig") as f:
                    raw = _json.load(f)
                break
    except Exception:
        return []            # 配置读不到就当没配，不影响 start
    dirs = raw.get("assets") or {}
    names = [k for k in dirs if not k.startswith("_")]
    if not names:
        return []
    script = os.path.abspath(os.path.join(_here, "..", "..", "query", "py", "memory-assets.py"))
    if not os.path.exists(script):
        return []
    out = []
    for name in names:
        try:
            r = subprocess.run([sys.executable, script, name, "--json"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=30)
            d = _json.loads(r.stdout)
            out.append((name, d["files"]["total"], d["memories"]["total"]))
        except Exception:
            continue    # 这个项目跳过，不影响别的
    return out


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

    # 2026-11-24：**看见了也要主动提**（用户原话：「看见了也要主动提，告诉用户这些可配置，功能可以关闭」）。
    # 但用户又说「**这个文件应该是只主动强提醒一次，后面都作为说明文件存在**」——
    # 所以：第一次（state/config-told 不存在）强提醒一次；之后完全不提（help / CONFIG.md 还在）。
    if is_first_time_config_tip():
        print()
        print("=== 可配置（这是第一次提醒，之后不再主动提）===")
        print()
        print("这个插件有七段配置，**不用改代码**（改完即时生效，不用重启）：")
        print("  agent.name       AI 的名字          默认 DeepSeek")
        print("  tools.<工具名>   工具开关           false = 关掉（1 秒内生效）")
        print("  assets.<项目>    项目资产扫哪些目录   没配就只列记忆")
        print("  backup.targets   备份放哪几处        ⚠ 见下，默认关")
        print("  backup.exportDir 导出去向           默认 workspace/memory-export")
        print("  start.checklist  开工清单           可换成用户自己的规则")
        print("  paths.*          本机设施路径         没配就跳过")
        print()
        print("⚠ **备份默认是关的**（tools.mem_backup = false）")
        print("  mem_backup 用来导出/恢复记忆，但**备份到哪只有你自己知道**，")
        print("  所以默认不注册它——不配的话它跑起来什么也不做，反而像坏了。")
        print("  要开：config.json 里 tools.mem_backup = true，并配好 backup.targets")
        print("        （建议两处、不同物理盘）。")
        print("  **要现在设置吗？** 让 AI 带你看 CONFIG.md 的 backup 段，或直接说路径。")
        print()
        print("  用户问「能不能改 / 能不能关」→ 照上面答；细节看 CONFIG.md。")
        print("  随时能重看：mem_check help（有「可以改的」一节）")
        mark_config_tipped()


    # 2026-11-25：项目资产（只列配了目录的项目；明细走 mem.py assets <项目>）
    if CFG.get("showAssets", True):
        _assets = assets_summary()
        if _assets:
            print("项目资产：")
            for _name, _nf, _nm in _assets:
                print("  %s：%d 个文件 / %d 条记忆" % (_name, _nf, _nm))
            print("  （明细：mem.py assets <项目>）")
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
    checklist, src = load_checklist(CFG)
    print(checklist)
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
