# -*- coding: utf-8 -*-
"""导出诊断包：把这个插件的运行环境、最近错误、配置（脱敏）打成一份可提交的文本。

**为什么有它**（2026-11-26 用户问）：
「假如我们是新用户…出了 BUG 能不能向开发者提交日志方便修复 BUG？」
——之前答案是"不能"：`errors.jsonl` 有，但用户不知道它在哪、该交哪几条、
交上来还带着本机路径要我自己去猜。

设计原则：
  ①**一次命令，出一个文件**——用户把它贴给开发者就行，不用指导他找路径
  ②**脱敏**——不打印 token / 密码；本机路径只保留最后两段（能定位插件、不暴露用户名）
  ③**给开发者看的顺序**：版本 → 环境 → 症状 → 错误 → 配置 →（可选）库健康
  ④**只读**，不改任何东西

用法：
  mem.py diag                 # 打印到屏幕
  mem.py diag --out 文件名     # 写到文件
  mem.py diag --json          # 结构化（给程序用）
"""
import io
import json
import os
import platform
import re
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_here = os.path.dirname(os.path.abspath(__file__))
# 层级：py → status → observe → modules → 插件根（**4 层**，不是 3）
sys.path.insert(0, os.path.abspath(os.path.join(_here, "..", "..", "..", "..", "py-core")))

try:
    import paths
except Exception:
    paths = None

ROOT = os.path.abspath(os.path.join(_here, "..", "..", "..", ".."))

# 敏感键：出现就替换成 ***
SECRET_KEYS = ("token", "password", "passwd", "secret", "key", "cookie", "auth")
# 本机路径里要保留的段数（能看出是"工作区/插件目录"，但看不到用户名）
KEEP_TAIL = 2


def _mask_path(s):
    """把路径压成 …\\最后两段，既能看到结构又不暴露用户名。"""
    if not isinstance(s, str):
        return s
    # Windows 绝对路径
    m = re.findall(r"[A-Za-z]:\\[^\s\"',]+", s)
    for full in m:
        parts = full.split("\\")
        tail = "\\".join(parts[-KEEP_TAIL:]) if len(parts) > KEEP_TAIL else full
        s = s.replace(full, "…\\" + tail)
    return s


def _mask_obj(o):
    if isinstance(o, dict):
        return {k: ("***" if any(t in k.lower() for t in SECRET_KEYS) else _mask_obj(v))
                for k, v in o.items()}
    if isinstance(o, list):
        return [_mask_obj(x) for x in o]
    if isinstance(o, str):
        return _mask_path(o)
    return o


def _plugin_version():
    try:
        d = json.load(io.open(os.path.join(ROOT, "package.json"), encoding="utf-8-sig"))
        return d.get("version"), d.get("name")
    except Exception:
        return "?", "?"


def _config_path():
    """和 lib/index.js 的 configPath() 一致：工作区优先，插件根兜底。"""
    try:
        ws = paths.workspace_root() if paths else None
    except Exception:
        ws = None
    cands = []
    if ws:
        cands.append(os.path.join(ws, "tools", "dsh-memory-maint", "config.json"))
    cands.append(os.path.join(ROOT, "config.json"))
    for c in cands:
        if os.path.exists(c):
            return c
    return None


def _state_dir():
    env = os.environ.get("DSH_MEMORY_LOG_DIR")
    if env:
        return env
    try:
        from paths import workspace_root
        return os.path.join(workspace_root(), "tools", "dsh-memory-maint", ".local", "state")
    except Exception:
        return None


def _tail_lines(p, n):
    if not p or not os.path.exists(p):
        return []
    try:
        lines = io.open(p, encoding="utf-8", errors="replace").read().splitlines()
        return lines[-n:]
    except Exception:
        return []


def collect():
    """收集一份诊断数据（dict）。"""
    ver, name = _plugin_version()
    st = _state_dir()
    cfg_p = _config_path()

    cfg = None
    if cfg_p:
        try:
            cfg = _mask_obj(json.load(io.open(cfg_p, encoding="utf-8-sig")))
        except Exception as e:
            cfg = {"（配置读不出来）": _mask_path(str(e)[:200])}

    # 库（只读基本信息，不读内容）
    db_info = {}
    try:
        from paths import workspace_root
        dbp = os.path.join(workspace_root(), ".dsh-meow", "memory.db")
        db_info["path"] = _mask_path(dbp)
        db_info["exists"] = os.path.exists(dbp)
        if db_info["exists"]:
            db_info["size_kb"] = round(os.path.getsize(dbp) / 1024, 1)
    except Exception as e:
        db_info["error"] = _mask_path(str(e)[:200])

    # 模块/脚本
    mods = []
    mdir = os.path.join(ROOT, "modules")
    if os.path.isdir(mdir):
        for layer in sorted(os.listdir(mdir)):
            ld = os.path.join(mdir, layer)
            if not os.path.isdir(ld) or layer.startswith("_"):
                continue
            for mod in sorted(os.listdir(ld)):
                if os.path.isdir(os.path.join(ld, mod)):
                    mods.append("%s/%s" % (layer, mod))

    errs = _tail_lines(os.path.join(st, "errors.jsonl") if st else None, 12)
    runlog = _tail_lines(os.path.join(st, "runtime.log") if st else None, 12)
    synclog = _tail_lines(os.path.join(st, "tool-sync.log") if st else None, 8)

    return {
        "插件": {"name": name, "version": ver},
        "环境": {
            "OS": platform.platform(),
            "Python": sys.version.split()[0],
            "工作区": _mask_path(str(paths.workspace_root()) if paths else "?"),
            "state 目录": _mask_path(st or "（没有）"),
            "配置文件": _mask_path(cfg_p or "（没有，用内置默认）"),
        },
        "模块": mods,
        "记忆库": db_info,
        "最近的错误（errors.jsonl）": [_mask_path(x) for x in errs],
        "最近运行流水（runtime.log）": [_mask_path(x) for x in runlog],
        "工具开关流水（tool-sync.log）": [_mask_path(x) for x in synclog],
        "配置（已脱敏）": cfg,
    }


def render_text(d):
    out = []
    out.append("=== dsh-memory-maint 诊断包 ===")
    out.append("（把这份内容贴给插件开发者，或在 issues 里附上；已自动脱敏）")
    out.append("")
    for section in ("插件", "环境", "记忆库"):
        out.append("## " + section)
        for k, v in d[section].items():
            out.append("  %-14s %s" % (k, v))
        out.append("")
    out.append("## 模块（%d 个）" % len(d["模块"]))
    out.append("  " + " · ".join(d["模块"]))
    out.append("")
    for sec in ("最近的错误（errors.jsonl）", "最近运行流水（runtime.log）",
                "工具开关流水（tool-sync.log）"):
        lines = d[sec]
        out.append("## %s（%d 条）" % (sec, len(lines)))
        if not lines:
            out.append("  （没有记录）")
        for line in lines:
            out.append("  | " + line[:300])
        out.append("")
    out.append("## 配置（已脱敏）")
    out.append(json.dumps(d["配置（已脱敏）"], ensure_ascii=False, indent=2))
    out.append("")
    out.append("=== 诊断包结束 ===")
    return "\n".join(out)


def selftest():
    """只验脱敏逻辑和渲染，不依赖真实环境。"""
    passed, failed = [], []

    def check(name, cond, detail=""):
        (passed if cond else failed).append(name + ((" " + detail) if detail and not cond else ""))

    # ① 路径脱敏
    masked = _mask_path(r"C:\Users\hidden\User\Documents\ws\tools\x")
    check("路径脱敏保留最后两段", "tools\\x" in masked and "hidden" not in masked, masked)

    # ② 敏感键
    m = _mask_obj({"token": "abc123", "apiKey": "xyz", "nested": {"password": "p"}})
    check("token 被脱敏", m["token"] == "***")
    check("apiKey 被脱敏（含 key）", m["apiKey"] == "***")
    check("嵌套里的 password 也被脱敏", m["nested"]["password"] == "***")

    # ③ 普通字段保留
    m2 = _mask_obj({"agent": {"name": "DeepSeek"}})
    check("普通字段不动", m2["agent"]["name"] == "DeepSeek")

    # ④ 渲染
    fake = {"插件": {"version": "0.0.0"}, "环境": {"OS": "t"}, "记忆库": {"exists": False},
            "模块": ["feature/a"], "最近的错误（errors.jsonl）": ["x"],
            "最近运行流水（runtime.log）": [], "工具开关流水（tool-sync.log）": [],
            "配置（已脱敏）": {}}
    txt = render_text(fake)
    check("渲染出标题", "诊断包" in txt)
    check("渲染出结束行", "诊断包结束" in txt)
    check("空 list 显示『没有记录』", "（没有记录）" in txt)

    total = len(passed) + len(failed)
    print("memory-diag 自测：%d 通过 / %d 失败 / 共 %d" % (len(passed), len(failed), total))
    for f in failed:
        print("  ❌ %s" % f)
    return 0 if not failed else 1


def main():
    if "--selftest" in sys.argv:
        return selftest()

    args = sys.argv[1:]
    as_json = "--json" in args
    out_path = None
    if "--out" in args:
        i = args.index("--out")
        if i + 1 < len(args):
            out_path = args[i + 1]

    d = collect()
    text = json.dumps(d, ensure_ascii=False, indent=2) if as_json else render_text(d)

    if out_path:
        io.open(out_path, "w", encoding="utf-8", newline="\n").write(text + "\n")
        print("诊断包已写到：%s" % out_path)
        print("（把整个文件贴给开发者，或作为 issue 附件；已自动脱敏）")
        print("结论：✅ 诊断包已生成")
    else:
        print(text)
        if not as_json:
            print()
            print("结论：✅ 诊断包已输出（用 --out 文件名 可以存成文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
