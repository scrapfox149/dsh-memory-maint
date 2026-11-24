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

_here = os.path.dirname(os.path.abspath(__file__))
# 2026-11-24：测试脚本移到 tests/ 了，所以从这里往上找插件根（含 py-core 的那层）。
# 放在根目录或 tests/ 都能跑。
ROOT = _here
for _ in range(3):
    if os.path.isdir(os.path.join(ROOT, "py-core")):
        break
    ROOT = os.path.dirname(ROOT)

PY = sys.executable
def discover():
    """分层扫描 modules/<层>/<模块>/py/*.py —— 加模块不用改本文件"""
    out = []
    mod_root = os.path.join(ROOT, "modules")
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


def load_skip_map():
    """从各 module.json 读 `skipIf` 声明：{脚本名: 条件}。

    2026-11-24：原来是在本文件里硬编码 CI_ONLY_SKIP 字典——
    那等于"测试脚本替模块决定什么时候不该跑"。
    现在由**模块自己声明**（module.json 里 `{"script": ..., "skipIf": "ci"}`），
    加新脚本要跳过时只改 module.json，不用动测试。
    """
    import json
    out = {}
    mod_root = os.path.join(ROOT, "modules")
    if not os.path.isdir(mod_root):
        return out
    for layer in sorted(os.listdir(mod_root)):
        layer_dir = os.path.join(mod_root, layer)
        if not os.path.isdir(layer_dir):
            continue
        for mod in sorted(os.listdir(layer_dir)):
            mf = os.path.join(layer_dir, mod, "module.json")
            if not os.path.isfile(mf):
                continue
            try:
                with open(mf, encoding="utf-8") as f:
                    m = json.load(f)
            except Exception:
                continue
            for spec in (m.get("commands") or {}).values():
                if isinstance(spec, dict) and spec.get("skipIf"):
                    script = os.path.basename(str(spec.get("script", "")))
                    if script:
                        out[script] = str(spec["skipIf"])
    return out


SKIP_MAP = load_skip_map()
SKIP_REASONS = {
    "ci": "CI 环境（没有本机设施）",
    "no-network": "无网络环境",
}


def skip_hit(script):
    """这个脚本在当前环境该跳过吗？返回原因字符串或 None。"""
    cond = SKIP_MAP.get(script)
    if not cond:
        return None
    if cond == "ci" and os.environ.get("CI"):
        return SKIP_REASONS["ci"]
    return None


# 有些脚本不带参数会返回非 0（提示用法），冒烟时补上安全参数
NEEDS_ARGS = {
    "memory-restore.py": ["--verify"],   # 演练模式，不碰活库
}


def run_one(layer, mod, script, db=None):
    path = os.path.join(ROOT, "modules", layer, mod, "py", script)
    if not os.path.exists(path):
        return False, "脚本不存在"
    # CI 上跳过「必须有本机环境才有意义」的脚本（跳过也要说清原因，别静默）
    # 模块自己声明了 skipIf 且当前环境命中 → 跳过（跳过也打印原因，别静默）
    why_skip = skip_hit(script)
    if why_skip:
        return True, "跳过：" + why_skip
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.path.join(ROOT, "py-core") + (
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


def load_selftest_whitelist():
    """读 config.json 的 selftest.legacy —— 那批是老脚本，已做过完整测试，不强制 --selftest。

    2026-11-24（B 方案，用户定）：**清单外的脚本必须自带 --selftest**，否则冒烟失败。
    判据不是"新不新"（没法可靠判断），而是"在不在白名单里"——加新脚本忘了写 selftest，
    冒烟就会红，这是**让规则有后果**。
    """
    import json
    path = os.path.join(ROOT, "config.json")
    if not os.path.isfile(path):
        return None          # 没配置就不检查（不因缺配置让冒烟红）
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        legacy = (cfg.get("selftest") or {}).get("legacy")
        return set(legacy) if isinstance(legacy, list) else None
    except Exception:
        return None


SELFTEST_LEGACY = load_selftest_whitelist()


def run_selftest(layer, mod, script):
    """跑一个脚本的 --selftest。返回 (ok, why)。

    ⚠ **不能只看退出码**：不认 --selftest 参数的脚本会直接跑主流程、返回 0，
    被误判成"自测通过"（2026-11-24 用假脚本实测到）。必须验输出里**真有自测结果**。
    """
    path = os.path.join(ROOT, "modules", layer, mod, "py", script)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = os.path.join(ROOT, "py-core")
    try:
        r = subprocess.run([PY, path, "--selftest"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120, env=env)
    except subprocess.TimeoutExpired:
        return False, "--selftest 超时"
    out = (r.stdout or "") + (r.stderr or "")
    if not ("自测" in out or "selftest" in out.lower()):
        return False, "不认 --selftest（没输出自测结果）"
    if r.returncode != 0:
        tail = out.strip().split("\n")[-1][:70]
        return False, "--selftest 失败: " + tail
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

    # B 方案：白名单外的脚本必须自带 --selftest
    if SELFTEST_LEGACY is not None:
        extra = [(l, m, s) for l, m, s in CHECKS if s not in SELFTEST_LEGACY]
        if extra:
            print("\n--- 新脚本的 --selftest 检查（白名单外 %d 个）---" % len(extra))
            for layer, mod, script in extra:
                ok, why = run_selftest(layer, mod, script)
                mark = "✅" if ok else "❌"
                print("  %s %-8s %-10s %s%s" % (mark, layer[:7], mod, script,
                                                ("  ← " + why) if why else ""))
                if ok:
                    passed += 1
                else:
                    failed += 1
                    fails.append((layer, mod, script, why or "缺 --selftest"))
            print("\n（白名单在 config.json 的 selftest.legacy；老脚本已做过完整测试，不强制）")

    # 总数要用 passed+failed，不能用 len(CHECKS)——
    # 白名单外的脚本会被检查两次（主流程 + --selftest），len(CHECKS) 会少于实际执行次数，
    # 出现「35 通过 / 2 失败 / 共 36」这种对不上的账（2026-11-24 实测）
    print("\n结果: %d 通过 / %d 失败 / 共 %d" % (passed, failed, passed + failed))
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
