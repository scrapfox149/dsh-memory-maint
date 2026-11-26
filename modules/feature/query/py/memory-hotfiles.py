#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""哪些文件改得最勤（按 git log 统计），用来判断"这个项目的主战场在哪"。

五思：
  目的：用户提「这样还能直接看哪些文件上一次用的多，改的勤，也能告诉你哪些是常用的」——
        项目待久了哪些是核心文件，靠记忆不可靠，git log 是硬数据。
  方案：`git log --since=N天 --name-only --pretty=format:` → 数每个文件出现几次。
        **只统计 .py/.md/.json/.js 等文本文件**（排除图片、二进制），按次数倒序。
  边界：① 不是 git 仓库 → 明说「没有 git，统计不了」（不猜）
        ② 没有历史 → 明说「N 天内没有提交」
        ③ 只读，不改任何东西
  验证：① 在插件仓库跑，应列出 memory-start.py 等高频文件
        ② 非 git 目录跑，应给提示而不是崩
        ③ --days 越界（0/负数/超大）应被夹到合理范围并说明
  退路：纯读 git log，不写文件，随时可重跑。

用法：
  python memory-hotfiles.py [--days N] [--top N] [--json]
"""
import io
import json
import os
import subprocess
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_here, "..", "..", "..", "..", "py-core")))
from paths import workspace_root  # noqa: E402

# 只统计这些后缀（代码/文档），不统计图片、二进制、锁文件
KEEP = (".py", ".md", ".json", ".js", ".yml", ".yaml", ".ps1", ".txt", ".css", ".html")


def _args():
    """先滤 flag，再取位置参数（踩过的坑：不滤会把开关当参数）。"""
    days, top, want_json = 30, 10, False
    raw = sys.argv[1:]
    want_json = "--json" in raw
    rest = []
    i = 0
    while i < len(raw):
        a = raw[i]
        if a == "--json":
            i += 1
            continue
        if a in ("--days", "--top") and i + 1 < len(raw):
            try:
                v = int(raw[i + 1])
            except ValueError:
                print("（%s 后面要跟数字，给的是 %r，忽略）" % (a, raw[i + 1]))
                i += 2
                continue
            if a == "--days":
                days = v
            else:
                top = v
            i += 2
            continue
        rest.append(a)
        i += 1
    # 夹范围并说明
    if days < 1:
        print("（--days %d 超出范围 1-3650，按 1 算）" % days)
        days = 1
    elif days > 3650:
        print("（--days %d 超出范围 1-3650，按 3650 算）" % days)
        days = 3650
    if top < 1:
        print("（--top %d 超出范围 1-200，按 1 算）" % top)
        top = 1
    elif top > 200:
        print("（--top %d 超出范围 1-200，按 200 算）" % top)
        top = 200
    return days, top, want_json


def is_git_repo(path):
    """这个目录（或它的祖先）是不是 git 仓库。"""
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=path,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=20)
        return r.returncode == 0, (r.stdout or "").strip()
    except Exception:
        return False, ""


def find_repos(ws, max_depth=3):
    """找 ws 及其下 max_depth 层内的 git 仓库根。

    2026-11-26（实测发现）：**工作区本身常常不是 git 仓库**，
    真正的仓库在子目录里（例如 `tools/dsh-memory-maint`）。
    所以不能只看工作区根，要往下找。
    """
    roots = []
    # ① 工作区自己是不是
    ok, top = is_git_repo(ws)
    if ok:
        return [top], True
    # ② 往下一层层找
    try:
        entries = sorted(os.listdir(ws))
    except OSError:
        return [], False
    for name in entries:
        sub = os.path.join(ws, name)
        if not os.path.isdir(sub) or name.startswith(".") or name in ("node_modules", "tmp"):
            continue
        # 只看两层：ws/x 和 ws/x/y
        if os.path.isdir(os.path.join(sub, ".git")):
            roots.append(sub)
            continue
        if max_depth >= 2:
            try:
                for name2 in sorted(os.listdir(sub)):
                    sub2 = os.path.join(sub, name2)
                    if (os.path.isdir(sub2) and not name2.startswith(".")
                            and os.path.isdir(os.path.join(sub2, ".git"))):
                        roots.append(sub2)
            except OSError:
                pass
    return roots, False


def hot_files(root, days, top):
    """跑 git log，返回 [(文件名, 次数)] 按次数倒序。"""
    cmd = ["git", "log", "--since=%d days ago" % days, "--name-only", "--pretty=format:"]
    try:
        r = subprocess.run(cmd, cwd=root, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
    except Exception as e:
        return None, str(e)[:80]
    if r.returncode != 0:
        return None, (r.stderr or "").strip().splitlines()[-1:] or ["git log 失败"]
    counts = {}
    for line in (r.stdout or "").splitlines():
        f = line.strip()
        if not f or not f.lower().endswith(KEEP):
            continue
        counts[f] = counts.get(f, 0) + 1
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return items[:top], None


def main():
    if "--selftest" in sys.argv:
        return selftest()

    days, top, want_json = _args()
    ws = workspace_root()
    roots, ws_is_git = find_repos(ws)

    if not roots:
        msg = "工作区里找不到 git 仓库，统计不了：%s" % ws
        if want_json:
            print(json.dumps({"workspace": ws, "repos": [], "items": [],
                              "note": msg}, ensure_ascii=False))
            return 0
        print("=== 改得最勤的文件 ===")
        print()
        print("⚠ " + msg)
        print("  （子目录里也没有 .git；没有 git 也能用 `mem.py assets <项目>` 看文件清单）")
        print()
        print("结论：找不到 git 仓库，统计不了")
        return 0

    # 跑每个仓库，合并（文件名带上仓库前缀，免得两个仓库里的同名文件混在一起）
    allitems = {}
    used = []
    for root in roots[:5]:          # 最多看 5 个仓库，防扫描太慢
        items, err = hot_files(root, days, top)
        if items is None:
            print("（%s：%s，跳过）" % (os.path.relpath(root, ws), err))
            continue
        used.append(os.path.relpath(root, ws))
        prefix = "" if (ws_is_git or len(roots) == 1) else os.path.relpath(root, ws) + "/"
        for f, n in items:
            allitems[prefix + f] = allitems.get(prefix + f, 0) + n
    merged = sorted(allitems.items(), key=lambda kv: (-kv[1], kv[0]))[:top]

    if want_json:
        print(json.dumps({"workspace": ws, "days": days, "repos": used,
                          "items": [{"file": f, "commits": n} for f, n in merged],
                          "note": "次数 = 这个文件在多少次提交里出现过"},
                         ensure_ascii=False, indent=2))
        return 0

    print("=== 改得最勤的文件（最近 %d 天）===" % days)
    if len(used) > 1 or not ws_is_git:
        print("（扫了 %d 个仓库：%s）" % (len(used), "、".join(used)))
    print()
    if not merged:
        print("（这 %d 天内没有提交）" % days)
        print()
        print("结论：最近没有提交记录")
        return 0
    width = max(len(f) for f, _ in merged)
    for f, n in merged:
        bar = "█" * min(n, 30)
        print("  %-*s  %3d 次  %s" % (width, f, n, bar))
    print()
    print("（次数 = 这个文件在多少次提交里出现过；只统计代码/文档，不统计图片）")
    total = sum(n for _, n in merged)
    print("结论：前 %d 个文件共出现在 %d 次提交里" % (len(merged), total))
    return 0


def selftest():
    """自测：只验纯函数，不动真实仓库。"""
    ok, bad = 0, 0

    def chk(name, cond, detail=""):
        nonlocal ok, bad
        if cond:
            ok += 1
            print("  ✅ %s%s" % (name, ("  → " + detail) if detail else ""))
        else:
            bad += 1
            print("  ❌ %s%s" % (name, ("  → " + detail) if detail else ""))

    chk("KEEP 含 .py", ".py" in KEEP)
    chk("KEEP 不含 .png", ".png" not in KEEP)

    # 滤 flag：不能把 --json 当参数
    sys.argv = ["x", "--json", "--days", "7", "--top", "3"]
    d, t, j = _args()
    chk("_args 滤掉 --json", j is True)
    chk("_args 读到 --days 7", d == 7, str(d))
    chk("_args 读到 --top 3", t == 3, str(t))

    # 越界夹取（会打印提示，但返回值对就行）
    sys.argv = ["x", "--days", "0", "--top", "0"]
    d2, t2, _ = _args()
    chk("--days 0 夹到 1", d2 == 1, str(d2))
    chk("--top 0 夹到 1", t2 == 1, str(t2))

    # 非 git 目录识别
    import tempfile
    tmp = tempfile.mkdtemp(prefix="hot-")
    isg, _ = is_git_repo(tmp)
    chk("非 git 目录识别为 False", isg is False)
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("memory-hotfiles 自测：%d 通过 / %d 失败 / 共 %d" % (ok, bad, ok + bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
