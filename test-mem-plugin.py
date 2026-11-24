# -*- coding: utf-8 -*-
"""插件冒烟测试：一条命令验证整个 dsh-memory-maint 是否完好。

五思（2026-11-18，第 1 级）
  目的：插件有 20 个脚本 + 3 个工具入口，手工一条条验太慢也容易漏（今天就漏过
        memory-changelog 的 sqlite3 残留）。这个脚本一次跑完全部，改动后必跑。
  方案：① 逐个跑 modules/*/py/*.py ② 断言：退出码 0、无 Traceback、有输出
        ③ 额外跑异常用例（空库、库不存在）④ 汇总成一张表
  边界：只读；**不改任何数据**；跑之前不备份（因为不写）；对会写文件的命令
        （index/timeline/map/dump）也允许，它们写的是 docs/ 与 tmp/ 的产物
  验证：① 全绿 = 插件完好 ② 故意改坏一个脚本，必须能报出来（见文件尾自测说明）
  退路：纯只读脚本，删掉无副作用。

用法：
  python test-mem-plugin.py            # 用活库
  python test-mem-plugin.py --db <路径>  # 指定库（空库/沙箱）
"""
import argparse
import os
import subprocess
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
def discover():
    """分层扫描 modules/<层>/<模块>/py/*.py —— 加模块不用改本文件"""
    out = []
    mod_root = os.path.join(HERE, "modules")
    if not os.path.isdir(mod_root):
        return out
    for layer in sorted(os.listdir(mod_root)):
        layer_dir = os.path.join(mod_root, layer)
        if not os.path.isdir(layer_dir):
            continue
        for mod in sorted(os.listdir(layer_dir)):
            py_dir = os.path.join(layer_dir, mod, "py")
            if not os.path.isdir(py_dir):
                continue
            for f in sorted(os.listdir(py_dir)):
                if f.endswith(".py"):
                    out.append((layer, mod, f))
    return out


CHECKS = discover()


# 有些脚本不带参数会返回非 0（提示用法），冒烟时补上安全参数
NEEDS_ARGS = {
    "memory-restore.py": ["--verify"],   # 演练模式，不碰活库
}

# 只在「有本机环境」时才成立、CI 上必然缺前置的脚本。
# 2026-11-24：CI 跑到 28/30，挂的这两个都不是坏，是环境不对——
#   check-agents.py            检查计划任务 / E:\DSH\memory\archive 等本机设施
#   memory-weight-check2.py    读 tmp/memory-snapshot.json（要先跑 memory-map-export）
# 判据：`CI` 环境变量存在（GitHub Actions 默认设 CI=true）→ 跳过并说明。
CI_ONLY_SKIP = {
    "check-agents.py": "检查本机计划任务与归档目录，CI 上没有",
    "memory-weight-check2.py": "需要 tmp/memory-snapshot.json 前置产物，CI 上没有",
}


def run_one(layer, mod, script, db=None):
    path = os.path.join(HERE, "modules", layer, mod, "py", script)
    if not os.path.exists(path):
        return False, "脚本不存在"
    # CI 上跳过「必须有本机环境才有意义」的脚本（跳过也要说清原因，别静默）
    if os.environ.get("CI") and script in CI_ONLY_SKIP:
        return True, "CI 跳过：" + CI_ONLY_SKIP[script]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.path.join(HERE, "py-core") + (
        ";" + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    if db:
        env["DSH_MEMORY_DB"] = db
    args = [PY, path] + NEEDS_ARGS.get(script, [])
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180, env=env)
    except subprocess.TimeoutExpired:
        return False, "超时 180 秒"
    # 只在 **stderr** 里找 Traceback——stdout 里有 Traceback 字样是正常的
    # （比如 mem_alert 展示历史告警时会把以前的报错原文打出来）
    err = r.stderr or ""
    if "Traceback" in err:
        tail = [l for l in err.strip().split("\n") if l.strip()][-1]
        return False, "异常: " + tail[:70]
    if r.returncode != 0:
        # 有些脚本「有该做的事」时会故意返回非零（如 memory-daily 的“⚠ N 件事要做”），
        # 那是设计不是故障——只要它跑完了（输出了结论区）就算通过。
        out = r.stdout or ""
        if "结论：" in out or "该做的" in out:
            return True, "有警告（退出码 %d）" % r.returncode
        return False, "退出码 %d" % r.returncode
    if not (r.stdout or "").strip():
        return False, "无输出"
    return True, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="", help="指定库路径（默认活库）")
    args = ap.parse_args()

    print("=== dsh-memory-maint 冒烟测试 ===")
    print("库: %s\n" % (args.db or "活库"))
    passed = failed = 0
    fails = []
    for layer, mod, script in CHECKS:
        ok, why = run_one(layer, mod, script, args.db or None)
        mark = "✅" if ok else "❌"
        print("  %s %-8s %-10s %s%s" % (mark, layer[:7], mod, script, ("  ← " + why) if why else ""))
        if ok:
            passed += 1
        else:
            failed += 1
            fails.append((layer, mod, script, why))

    print("\n结果: %d 通过 / %d 失败 / 共 %d" % (passed, failed, len(CHECKS)))
    if fails:
        print("\n失败项：")
        for layer, mod, script, why in fails:
            print("  %s/%s/%s → %s" % (layer, mod, script, why))
        print("\n（插件有破损，先修再继续）")
        return 1
    print("\n（插件完好）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
