# -*- coding: utf-8 -*-
"""插件自检：报当前状态 + 有没有毛病。

五思（2026-11-18，第 1 级）
  目的：插件应该能自己回答"我现在是什么状态、有没有报错"，而不是只能靠外部
        test-mem-plugin.py 跑一遍才知道。
  方案：轻量检查——① 扫描 modules/ 看模块与脚本清单 ② 用 compile() 验语法
        （**不执行**，所以快）③ 检查 py-core 契约层在不在 ④ 检查库路径与条目统计
        ⑤ 检查最近备份时间 ⑥ 汇总已知问题
  边界：只读；**3 秒内返回**；不做全命令实跑（那是 test-mem-plugin.py 的活）；
        不改任何数据。
  验证：① 正常报完整状态 ② 故意弄坏一个 .py，必须在这里报出语法错误
        ③ 库不存在时要说明白而不是崩
  退路：独立模块，删掉不影响任何现有功能。

用法：
  python memory-status.py          # 人类可读
  python memory-status.py --json   # 给程序用
"""
import datetime
import json
import os
import sqlite3
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
# 向上找到含 py-core 的那层（不写死层数，将来目录再深也不会错）
ROOT = HERE
for _ in range(6):
    if os.path.isdir(os.path.join(ROOT, "py-core")):
        break
    ROOT = os.path.dirname(ROOT)
MODULES = os.path.join(ROOT, "modules")
PY_CORE = os.path.join(ROOT, "py-core")

# 让契约层可导入
if PY_CORE not in sys.path:
    sys.path.insert(0, PY_CORE)

KNOWN_ISSUES = [
    "26 个脚本全部走契约层（load/fetch/count_status_sql）；只有 backup/rescue 的 export/restore 有意自包含",
    "保命工具 export/restore 已并入 backup 层（自包含），并由备份脚本同步到两处 archive/tools/，插件坏了也能独立执行",
    "已装进 desktop profile，6 个工具已注册；**改完工作区代码要同步到 profile**"
    "（`~/.dsh/profiles/desktop/node_modules/dsh-memory-maint`），"
    "`lib/index.js` 的改动要重启宿主才生效",
]


def check_modules():
    """分层扫描 modules/<层>/<模块>/module.json + 验脚本语法"""
    mods = []
    if not os.path.isdir(MODULES):
        return mods
    for layer in sorted(os.listdir(MODULES)):
        layer_dir = os.path.join(MODULES, layer)
        if not os.path.isdir(layer_dir):
            continue
        for name in sorted(os.listdir(layer_dir)):
            d = os.path.join(layer_dir, name)
            if not os.path.isdir(d):
                continue
            mf = os.path.join(d, "module.json")
            ok_manifest, tool, cmd_count = False, "", 0
            if os.path.exists(mf):
                try:
                    meta = json.load(open(mf, encoding="utf-8"))
                    tool = meta.get("tool", "")
                    cmd_count = len(meta.get("commands", {}))
                    ok_manifest = bool(tool)
                except Exception:
                    ok_manifest = False
            scripts, bad = [], []
            pd = os.path.join(d, "py")
            if os.path.isdir(pd):
                for f in sorted(os.listdir(pd)):
                    if not f.endswith(".py"):
                        continue
                    scripts.append(f)
                    fp = os.path.join(pd, f)
                    try:
                        compile(open(fp, encoding="utf-8").read(), fp, "exec")
                    except SyntaxError as e:
                        bad.append("%s 第 %s 行: %s" % (f, e.lineno, e.msg))
                    except Exception as e:
                        bad.append("%s: %s" % (f, e))
            mods.append({"name": name, "layer": layer, "manifest_ok": ok_manifest,
                         "tool": tool, "commands": cmd_count,
                         "scripts": scripts, "bad": bad})
    return mods


def check_core():
    return {
        "py_core": os.path.isdir(PY_CORE),
        "mem_db": os.path.exists(os.path.join(PY_CORE, "mem_db.py")),
    }


def check_db():
    try:
        from mem_db import count_status_sql, DB
    except Exception as e:
        return {"error": "契约层导入失败: %s" % e}
    info = {"path": DB, "exists": os.path.exists(DB)}
    if not info["exists"]:
        return info
    try:
        info["mtime"] = datetime.datetime.fromtimestamp(os.path.getmtime(DB)).strftime("%Y-%m-%d %H:%M")
        info["size_kb"] = round(os.path.getsize(DB) / 1024.0, 1)
        # 契约层用 SQL 数（count_status_sql），不再自己连库
        tiers = count_status_sql(DB)
        info["tiers"] = tiers
        info["total_active"] = sum(v["active"] for v in tiers.values() if v)
    except sqlite3.Error as e:
        info["error"] = str(e)
    return info


def main():
    as_json = "--json" in sys.argv
    mods = check_modules()
    core = check_core()
    db = check_db()

    problems = []
    for m in mods:
        if not m["manifest_ok"]:
            problems.append("模块 %s 的 module.json 缺失或无效" % m["name"])
        for b in m["bad"]:
            problems.append("脚本 %s/%s → %s" % (m["name"], "py", b))
    if not core["mem_db"]:
        problems.append("契约层 py-core/mem_db.py 不存在")
    if not db.get("exists"):
        problems.append("记忆库不存在：%s" % db.get("path"))

    total_scripts = sum(len(m["scripts"]) for m in mods)
    result = {
        "ok": not problems,
        "modules": len(mods),
        "scripts": total_scripts,
        "detail": [{"name": m["name"], "tool": m["tool"], "commands": m["commands"],
                    "scripts": len(m["scripts"]), "bad": len(m["bad"])} for m in mods],
        "core": core,
        "db": db,
        "problems": problems,
        "known_issues": KNOWN_ISSUES,
    }

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not problems else 1

    print("=== dsh-memory-maint 自检 ===\n")
    print("模块 %d 个 / 脚本 %d 个" % (len(mods), total_scripts))
    for m in mods:
        flag = "✅" if (m["manifest_ok"] and not m["bad"]) else "❌"
        print("  %s %-8s %-8s %-12s 命令 %d / 脚本 %d%s"
              % (flag, m["layer"][:8], m["name"], m["tool"] or "(无 tool)", m["commands"], len(m["scripts"]),
                 ("  坏 %d" % len(m["bad"])) if m["bad"] else ""))
        for b in m["bad"]:
            print("       ✗ %s" % b)

    dev_doc = os.path.join(ROOT, "DEVELOPING.md")
    print("\n契约层: %s" % ("✅ py-core/mem_db.py" if all(core.values()) else "❌ 缺文件"))
    print("维护规范: %s" % ("✅ DEVELOPING.md" if os.path.exists(dev_doc) else "⚠ 缺 DEVELOPING.md（改插件前先看它）"))
    if db.get("error"):
        print("记忆库: ❌ %s" % db["error"])
    elif not db.get("exists"):
        print("记忆库: ❌ 不存在 %s" % db.get("path"))
    else:
        print("记忆库: ✅ %s（%s，%s KB，共 %d 条 active）"
              % (db["path"].split("/")[-1], db.get("mtime", "?"),
                 db.get("size_kb", "?"), db.get("total_active", 0)))
        for t, v in (db.get("tiers") or {}).items():
            if v:
                print("    %-8s active %3d  stale %3d  archived %3d" % (t, v["active"], v["stale"], v["archived"]))

    print("\n已知问题（长期）：")
    for i in KNOWN_ISSUES:
        print("  · %s" % i)

    print("\n结论：%s" % ("✅ 一切正常" if not problems else "❌ %d 个问题" % len(problems)))
    if problems:
        for p in problems:
            print("  ✗ %s" % p)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
