# -*- coding: utf-8 -*-
"""记忆维护统一入口（转发器）。不重写逻辑，只把子命令转发给现有脚本。

五思（2026-11-17，改造 = 第 1 级）
  目的：tools/ 里记忆相关脚本已有 29 个，靠 ls 才想得全；给一个入口降低"要记住的名字数"。
  方案：**转发而不是重写**——mem.py <组> <命令> 调 subprocess 跑原脚本。
       这样原脚本一行不改、记忆里的路径引用不失效、随时能退回直跑。
  边界：① 只转发，不复制逻辑（避免两份实现走样）② 备份/恢复类不做组内自动执行
        ③ 找不到脚本时报清楚缺哪个 ④ 转发失败要保留原脚本的退出码
  验证：① mem.py list 能列全  ② mem.py check refs 与直接跑 check-memory-refs.py 输出一致
        ③ 传错子命令 → 提示可用项而不是崩
  退路：删掉本文件即可，原脚本全部可用。

用法：
  python mem.py list                  # 看所有组和命令
  python mem.py check                 # 全量体检（8 项依次跑）
  python mem.py check refs            # 只跑文件引用检查
  python mem.py maint dedup           # 去重扫描
  python mem.py query expand "备份"    # 关系展开
"""
import subprocess
import sys
from pathlib import Path

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
PY = sys.executable

GROUPS = {
    "check": {
        "desc": "体检（只读）：写作规则、健康、引用、一致性、权重、来源、归档",
        "cmds": {
            "audit": "memory-audit.py",
            "health": "memory-health.py",
            "refs": "check-memory-refs.py",
            "agents": "check-agents.py",
            "agentsmem": "check-agents-memory.py",
            "signal": "memory-signal-check.py",
            "source": "memory-source-check.py",
            "archive": "memory-archive-check.py",
        },
        "order": ["agents", "agentsmem", "refs", "audit", "health", "signal", "source", "archive"],
    },
    "maint": {
        "desc": "维护（只读筛查）：去重、衰减、变更、全局整理、索引、时间线、图谱",
        "cmds": {
            "dedup": "memory-dedup.py",
            "decay": "memory-decay.py",
            "changelog": "memory-changelog.py",
            "dream": "memory-global-dream.py",
            "index": "memory-index.py",
            "timeline": "memory-timeline.py",
            "map": "memory-map.py",
        },
        "order": [],
    },
    "query": {
        "desc": "查询：关系展开、多跳、全文、导出当前",
        "cmds": {
            "expand": "memory-expand.py",
            "hipporag": "memory-hipporag.py",
            "file": "memory-file-search.py",
            "dump": "memory-dump-active.py",
        },
        "order": [],
    },
}


def run(script, extra=None):
    path = HERE / script
    if not path.exists():
        print("  ✗ 缺少脚本: %s" % script)
        return 127
    cmd = [PY, str(path)] + (extra or [])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (r.stdout or "").strip()
        if out:
            print(out)
        if r.stderr and r.returncode != 0:
            print("  [stderr] %s" % (r.stderr or "").strip()[:300])
        return r.returncode
    except Exception as e:
        print("  ✗ 执行失败 %s: %s" % (script, e))
        return 1


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("list", "-h", "--help"):
        print("记忆维护统一入口\n")
        for g, info in GROUPS.items():
            print("【%s】%s" % (g, info["desc"]))
            for k, v in info["cmds"].items():
                print("   mem.py %-6s %-10s → %s" % (g, k, v))
            print()
        print("备份/恢复保持独立：backup-memory.ps1 / backup-meow.py / backup-watchdog.py /")
        print("                    memory-export.py / memory-restore.py")
        return 0

    group = args[0]
    if group not in GROUPS:
        print("未知分组：%s（可用：%s）" % (group, " / ".join(GROUPS)))
        return 1

    info = GROUPS[group]
    sub = args[1] if len(args) > 1 else None

    if sub is None:
        if not info["order"]:
            print("【%s】的可用命令：%s" % (group, " / ".join(info["cmds"])))
            return 0
        print("=" * 60)
        print("全量体检：%d 项" % len(info["order"]))
        print("=" * 60)
        bad = 0
        for k in info["order"]:
            print("\n----- %s (%s) -----" % (k, info["cmds"][k]))
            if run(info["cmds"][k]) != 0:
                bad += 1
        print("\n" + "=" * 60)
        print("完成：%d 项，其中 %d 项返回非 0" % (len(info["order"]), bad))
        return 0 if bad == 0 else 1

    if sub not in info["cmds"]:
        print("未知命令：%s（可用：%s）" % (sub, " / ".join(info["cmds"])))
        return 1
    return run(info["cmds"][sub], args[2:])


if __name__ == "__main__":
    sys.exit(main())
