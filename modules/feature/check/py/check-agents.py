# -*- coding: utf-8 -*-
"""AGENTS.md 一致性检查：核对文档里声明的关键设施是否真的存在且参数正确。

背景：2026-11-09 发现备份任务能"看起来正常"却 9 天没跑——文档写的和现实脱节。
这个脚本只做只读检查，输出通过的项和问题项。
"""
import os
import re
import subprocess
import sys
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break
from paths import workspace_root  # noqa: E402
import xml.etree.ElementTree as ET

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import platform

WS = workspace_root()
# 2026-11-24：这个脚本查的是**本机设施**（Windows 计划任务、E:\DSH 归档），
# 在别的平台上"查不到"不是故障，是环境不同。所以按平台分流：
#   Windows → 全查；其它 → 只查 AGENTS.md 的引用一致性，归档类标「跳过」。
IS_WINDOWS = platform.system() == "Windows"
TASKS_DIR = r"C:\Windows\System32\Tasks"


def _load_paths_config():
    """从插件根 config.json 的 paths 段读本机路径。

    2026-11-24：原来这四项写死在代码里（E:\\DSH\\... / D:\\FISH-BACKUP...），
    别人机器上根本没有这些目录——不是"检查失败"，是"没有这个设施"。
    现在：config.json 里配了才查，没配就跳过（不算问题）。
    """
    import json
    try:
        p = os.path.join(WS, "tools", "dsh-memory-maint", "config.json")
        if not os.path.exists(p):
            return {}
        with open(p, encoding="utf-8") as f:
            return (json.load(f).get("paths") or {})
    except Exception:
        return {}


_CFG_PATHS = _load_paths_config()
ARCHIVES = [p for p in (_CFG_PATHS.get("archives") or []) if p]
SNAPSHOT_DIR = _CFG_PATHS.get("snapshotDir") or ""
HISTORY_DIR = _CFG_PATHS.get("historyDir") or ""
BACKUP_LOG = _CFG_PATHS.get("backupLog") or ""

ok = []
bad = []
skipped = []


def check(name, cond, detail=""):
    if cond:
        ok.append(name)
    else:
        bad.append(name + ("：" + detail if detail else ""))


def task_xml(task_name):
    p = os.path.join(TASKS_DIR, task_name)
    if not os.path.exists(p):
        return None
    try:
        return ET.parse(p)
    except Exception:
        return None


def task_arguments(task_name):
    tree = task_xml(task_name)
    if tree is None:
        return None
    for el in tree.iter():
        if el.tag.endswith("Arguments"):
            return (el.text or "").strip()
    return ""


# 1) 计划任务存在 + 参数正确
expected = {
    "DSH-FishMemoryBackup": "backup-memory.ps1",
    "DSH-BackupWatchdog": "backup-watchdog.py",
    "DSH-FxRateSync": "update-fx.py",
    "DSH-ProxyIdleReaper": "proxy-idle-reaper.py",
    "DSH-ProxyGuard": "proxy-guard.py",
}
for name, needle in expected.items():
    args = task_arguments(name)
    check("任务 %s 存在" % name, args is not None, "任务文件不存在")
    if args is not None:
        check("任务 %s 参数含 %s" % (name, needle), needle in args, "实际参数：%r" % args)

# 2) 脚本文件存在
for rel in [
    "tools/backup-memory.ps1",
    "tools/backup-meow.py",
    "tools/backup-watchdog.py",
    "tools/run-ps-silent.py",
    "tools/proxy-guard.py",
    "tools/proxy-idle-reaper.py",
    "tools/update-fx.py",
    "tools/proxy-control.py",      # 2026-11-24 从工作区根移进 tools/
    "tools/proxy-health.py",
    "tools/proxy-nodes.py",
    "tools/probe-core.py",
    "tools/browser-channel.ps1",
    "AGENTS.md",
]:
    p = os.path.join(WS, rel)
    check("文件 %s 存在" % rel, os.path.exists(p))

# 3) 归档与快照目录（**只查 config.json 里配了的**——别人机器上可能没有这些设施）
if IS_WINDOWS:
    if ARCHIVES:
        for d in ARCHIVES:
            check("归档 %s 存在" % d, os.path.isdir(d))
    else:
        skipped.append("归档目录（config.json 的 paths.archives 没配）")
    if SNAPSHOT_DIR:
        check("快照目录存在", os.path.isdir(SNAPSHOT_DIR))
    else:
        skipped.append("快照目录（paths.snapshotDir 没配）")
    if HISTORY_DIR:
        check("记忆历史版本目录存在", os.path.isdir(HISTORY_DIR))
    else:
        skipped.append("记忆历史版本目录（paths.historyDir 没配）")
    if BACKUP_LOG:
        check("备份日志存在", os.path.exists(BACKUP_LOG))
    else:
        skipped.append("备份日志（paths.backupLog 没配）")
else:
    skipped.append("归档/快照/历史/日志（非 Windows，本机设施不存在）")

# 4) AGENTS.md 提到的关键路径是否都在文档里（存在性反查：文件在、文档也提到）
agents = os.path.join(WS, "AGENTS.md")
if os.path.exists(agents):
    text = open(agents, encoding="utf-8", errors="replace").read()
    for key in ["DSH-FishMemoryBackup", "E:\\DSH\\memory\\archive", "D:\\FISH-BACKUP", "--disable-dynamic-vram"]:
        check("AGENTS.md 提到 %s" % key, key in text)
else:
    bad.append("AGENTS.md 不存在")

# 5) tools/*.ps1 的 UTF-8 BOM + 语法（issue #19）
#
# 背景：2026-11-24 给 backup-memory.ps1 加 agent.name 支持时，文件被存成 UTF-8 **无 BOM**。
# PowerShell 5.1 按 GBK 解析含中文的脚本 → **解析阶段就死**（一行没执行）。
# 而计划任务显示 Ready、LastTaskResult=0x0 → **失败完全静默**：
# backup.log 整整 27 小时没有记录，直到夜间自检才发现。
#
# 判据：① 前 3 字节必须是 EF BB BF ② ParseFile 的 $errs.Count 必须为 0。
# 平台：这条是 PowerShell 5.1 + Windows 的坑；纯 Linux / pwsh 7 不成立，所以按平台分支。
if IS_WINDOWS:
    tools_dir = os.path.join(WS, "tools")
    ps1s = []
    if os.path.isdir(tools_dir):
        ps1s = sorted(f for f in os.listdir(tools_dir) if f.lower().endswith(".ps1"))
    if not ps1s:
        skipped.append("tools/*.ps1（一个都没有）")
    for fn in ps1s:
        fp = os.path.join(tools_dir, fn)
        # ① BOM
        try:
            with open(fp, "rb") as fh:
                head = fh.read(3)
        except OSError:
            head = b""
        check("%s 有 UTF-8 BOM" % fn, head == b"\xef\xbb\xbf",
              "前 3 字节 = %r（应为 b'\\xef\\xbb\\xbf'）" % head)
        # ② 语法（交给 PowerShell 自己的 Parser，比我们猜可靠）
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                 "$e=$null; [System.Management.Automation.Language.Parser]::ParseFile("
                 "'%s',[ref]$null,[ref]$e) | Out-Null; $e.Count" % fp.replace("'", "''")],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
            cnt = (r.stdout or "").strip().splitlines()[-1] if (r.stdout or "").strip() else "?"
            n_err = int(cnt) if cnt.isdigit() else -1
        except Exception as exc:
            n_err = -1
            cnt = str(exc)[:40]
        check("%s 语法无错" % fn, n_err == 0,
              ("%s 个语法错误" % cnt) if n_err != 0 else "")
        # 有错就把第一条错误也列出来（否则只说"有错"没法修）
        if n_err > 0:
            try:
                r2 = subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                     "$e=$null; [System.Management.Automation.Language.Parser]::ParseFile("
                     "'%s',[ref]$null,[ref]$e) | Out-Null; $e[0].Message" % fp.replace("'", "''")],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
                msg = (r2.stdout or "").strip().splitlines()
                if msg:
                    bad.append("%s 首个语法错误：%s" % (fn, msg[-1][:100]))
            except Exception:
                pass
else:
    skipped.append("tools/*.ps1 的 BOM/语法（非 Windows 环境不成立）")

# 输出
print("=== 通过 %d 项 ===" % len(ok))
for k in ok:
    print("  [OK] " + k)
if skipped:
    print("=== 跳过 %d 项（环境不适用，非故障）===" % len(skipped))
    for k in skipped:
        print("  [--] " + k)
if bad:
    print("=== 问题 %d 项 ===" % len(bad))
    for k in bad:
        print("  [!!] " + k)
    print()
    print("结论：⚠ %d 项不一致" % len(bad))
    sys.exit(1)
print("全部一致。")
print()
print("结论：✅ %d 项全部一致（跳过 %d 项）" % (len(ok), len(skipped)))
