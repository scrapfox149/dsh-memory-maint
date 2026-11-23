# -*- coding: utf-8 -*-
"""插件告警：看运行日志与报错日志。

五思（2026-11-18，第 1 级）
  目的：插件跑过什么、错在哪，能事后查——不能只有当场看屏幕才知道。
  方案：两份日志，都在 state/ 下——
        ① runtime.log   人类可读的运行流水（一行一条：时间|脚本|OK/FAIL|耗时|备注）
        ② errors.jsonl  结构化报错与降级（kind=degraded/exception/anomaly）
        本脚本负责读出来并按时间排序展示；`clear` 需显式 --yes。
  边界：只读日志；`clear` 是唯一写操作且要 --yes；日志缺失时正常返回空；
        保留天数由契约层 KEEP_DAYS 控制（默认 7 天，写日志时自动清理）。
  验证：① 无日志时报"暂无" ② 造记录后能读出 ③ errors 与 runtime 分开展示
  退路：删掉本模块不影响其他功能。

用法：
  python memory-alert.py              # 报错 + 最近运行各若干条
  python memory-alert.py --errors     # 只看报错
  python memory-alert.py --runtime    # 只看运行
  python memory-alert.py --since 1d   # 只看最近一天
  python memory-alert.py --clear-errors --yes   # 清空报错日志
"""
import argparse
import datetime
import json
import os
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
# 向上找到含 state/ 或 py-core/ 的那层（不写死层数）
ROOT = HERE
for _ in range(6):
    if os.path.isdir(os.path.join(ROOT, "py-core")):
        break
    ROOT = os.path.dirname(ROOT)
# 日志目录：优先环境变量（插件装进 node_modules 时由 Node 层指到工作区，
# 否则这里算出来的是副本目录）——2026-11-18 第三次修这个坑
STATE = os.environ.get("DSH_MEMORY_LOG_DIR") or os.path.join(ROOT, "state")
RUNTIME = os.path.join(STATE, "runtime.log")
ERRORS = os.path.join(STATE, "errors.jsonl")

KIND_LABEL = {
    "degraded": "降级（缺列补 None）",
    "exception": "异常",
    "anomaly": "数据异常",
}


def parse_since(s):
    if not s:
        return 0
    unit, num = s[-1], s[:-1]
    try:
        n = float(num)
    except ValueError:
        return 0
    mult = {"m": 60e3, "h": 3600e3, "d": 86400e3}.get(unit)
    return int(datetime.datetime.now().timestamp() * 1000 - n * mult) if mult else 0


def fmt(ms):
    try:
        return datetime.datetime.fromtimestamp(ms / 1000).strftime("%m-%d %H:%M:%S")
    except Exception:
        return "?"


def read_errors(since=0):
    if not os.path.exists(ERRORS):
        return []
    out = []
    with open(ERRORS, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                rec = {"kind": "unknown", "raw": line[:120], "time": 0}
            if (rec.get("time") or 0) >= since:
                out.append(rec)
    out.sort(key=lambda r: r.get("time") or 0)
    return out


def read_runtime(since=0, limit=15):
    if not os.path.exists(RUNTIME):
        return []
    lines = []
    with open(RUNTIME, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            try:
                ms = int(datetime.datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
            except Exception:
                ms = 0
            if since and ms < since:
                continue
            lines.append(line)
    return lines[-limit:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--errors", action="store_true", help="只看报错")
    ap.add_argument("--runtime", action="store_true", help="只看运行")
    ap.add_argument("--since", default="", help="最近，如 1d / 12h")
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--clear-errors", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    if args.clear_errors:
        if not args.yes:
            print("清空报错日志需要 --yes（报错是排查依据，不轻易清）")
            return 1
        if os.path.exists(ERRORS):
            os.remove(ERRORS)
            print("已清空 %s" % ERRORS)
        else:
            print("本来就没有报错日志")
        return 0

    since = parse_since(args.since)
    show_runtime = not args.errors
    show_errors = not args.runtime

    print("=== 插件日志（state/）===\n")

    if show_errors:
        errs = read_errors(since)
        if not errs:
            print("【报错】暂无")
        else:
            print("【报错】%d 条" % len(errs))
            kinds = {}
            for e in errs:
                kinds[e.get("kind", "?")] = kinds.get(e.get("kind", "?"), 0) + 1
            for k, v in sorted(kinds.items(), key=lambda x: -x[1]):
                print("  %-22s %3d" % (KIND_LABEL.get(k, k), v))
            for e in errs[-args.limit:]:
                kind = e.get("kind", "?")
                print("  [%s] %-20s ← %s" % (fmt(e.get("time") or 0),
                                              KIND_LABEL.get(kind, kind), e.get("script", "?")))
                if kind == "degraded":
                    print("         表 %s 缺列 %s（已补 None）" % (e.get("table", "?"), e.get("missing", "?")))
                elif kind == "exception":
                    print("         %s" % (e.get("error", ""))[:110])
                elif kind == "anomaly":
                    print("         %s" % (e.get("detail", ""))[:110])
                else:
                    print("         %s" % str(e.get("raw", ""))[:110])

    if show_runtime:
        runs = read_runtime(since, args.limit)
        print("\n【运行】最近 %d 条" % len(runs) if runs else "\n【运行】暂无")
        for line in runs:
            print("  " + line)

    print("\n（runtime.log / errors.jsonl 保留 7 天，写日志时自动清理；"
          "清空报错用 --clear-errors --yes）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
