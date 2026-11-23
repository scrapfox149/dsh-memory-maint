# -*- coding: utf-8 -*-
"""AGENTS.md 一致性检查：核对文档里声明的关键设施是否真的存在且参数正确。

背景：2026-11-09 发现备份任务能"看起来正常"却 9 天没跑——文档写的和现实脱节。
这个脚本只做只读检查，输出通过的项和问题项。
"""
import os
import re
import sys
_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break
import xml.etree.ElementTree as ET

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WS = r"C:\Users\24172\Documents\deepseek-harness\default-workspace"
TASKS_DIR = r"C:\Windows\System32\Tasks"
ARCHIVES = [r"E:\DSH\memory\archive", r"D:\FISH-BACKUP_鱼的记忆_勿删"]
SNAPSHOT_DIR = r"E:\DSH\memory\snapshots"
HISTORY_DIR = r"E:\DSH\memory\archive\meow\history"

ok = []
bad = []


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
    "proxy-control.py",
    "AGENTS.md",
]:
    p = os.path.join(WS, rel)
    check("文件 %s 存在" % rel, os.path.exists(p))

# 3) 归档与快照目录
for d in ARCHIVES:
    check("归档 %s 存在" % d, os.path.isdir(d))
check("快照目录存在", os.path.isdir(SNAPSHOT_DIR))
check("记忆历史版本目录存在", os.path.isdir(HISTORY_DIR))
check("备份日志存在", os.path.exists(r"E:\DSH\memory\backup.log"))

# 4) AGENTS.md 提到的关键路径是否都在文档里（存在性反查：文件在、文档也提到）
agents = os.path.join(WS, "AGENTS.md")
if os.path.exists(agents):
    text = open(agents, encoding="utf-8", errors="replace").read()
    for key in ["DSH-FishMemoryBackup", "E:\\DSH\\memory\\archive", "D:\\FISH-BACKUP", "--disable-dynamic-vram"]:
        check("AGENTS.md 提到 %s" % key, key in text)
else:
    bad.append("AGENTS.md 不存在")

# 输出
print("=== 通过 %d 项 ===" % len(ok))
for k in ok:
    print("  [OK] " + k)
if bad:
    print("=== 问题 %d 项 ===" % len(bad))
    for k in bad:
        print("  [!!] " + k)
    sys.exit(1)
print("全部一致。")
