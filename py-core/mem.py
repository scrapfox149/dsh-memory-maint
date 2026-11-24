# -*- coding: utf-8 -*-
"""记忆维护统一入口（转发器）。不重写逻辑，只把子命令转发给现有脚本。

五思（2026-11-17 初版，2026-11-24 改造 = 第 1 级）
  目的：脚本三十多个，靠 ls 才想得全；给一个入口降低"要记住的名字数"。
        而且 CLI 名字（mem.py check audit）和 MCP 工具名（mem_check）不一致，
        两套要记，容易混。
  方案：**转发而不是重写**——调 subprocess 跑原脚本，原脚本一行不改、随时能退回直跑。
        **分组和命令从各 module.json 读**，不再硬编码第二份（2026-11-24 改）：
        原来 GROUPS 是手抄的，已经落后——module.json 里 mem_check 有 13 个命令，
        GROUPS 只抄了 8 个（daily/promises/weight2 都没）。一份数据两处维护必然走样。
        **也支持直接写动作名**：`mem.py daily` 等价于 `mem.py check daily`。
  边界：① 只转发，不复制逻辑 ② 找不到脚本时报清楚缺哪个 ③ 保留原脚本退出码
        ④ 动作名跨组重名时**报歧义并列出候选**，不瞎猜
  验证：① `mem.py list` 能列出 module.json 里的全部命令
        ② `mem.py check refs` 与直接跑 check-memory-refs.py 输出一致
        ③ `mem.py daily`（不带组名）能找到 ④ 传错名字提示可用项而不是崩
  退路：删掉本文件即可，原脚本全部可用。

用法：
  python mem.py list                  # 看所有组和命令
  python mem.py check                 # 全量体检（order 里那几项依次跑）
  python mem.py check refs            # 只跑文件引用检查
  python mem.py refs                  # 同上，不用记分组
  python mem.py daily                 # 日常体检
  python mem.py maint dedup           # 去重扫描
  python mem.py expand "备份"          # 关系展开
"""
import json
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


def load_groups():
    """从 modules/<层>/<模块>/module.json 读分组。

    组的名字取 `tool` 去掉 `mem_` 前缀：mem_check → check、mem_maint → maint。
    这样加模块/加命令只改 module.json，本文件不用动。
    """
    groups = {}
    mod_root = HERE.parent / "modules"
    if not mod_root.is_dir():
        return groups
    for layer in sorted(mod_root.iterdir()):
        if not layer.is_dir():
            continue
        for mod in sorted(layer.iterdir()):
            mf = mod / "module.json"
            if not mf.is_file():
                continue
            try:
                m = json.loads(mf.read_text(encoding="utf-8"))
            except Exception:
                continue
            tool = str(m.get("tool") or "")
            gname = tool[4:] if tool.startswith("mem_") else (tool or mod.name)
            cmds = {}
            for k, v in (m.get("commands") or {}).items():
                rel = v.get("script") if isinstance(v, dict) else v
                # module.json 里的路径是**相对模块目录**（py/xxx.py），
                # 这里就地拼成完整路径——早期版本直接 HERE/rel 会全部"缺少脚本"
                cmds[k] = str(mod / rel) if rel else None
            groups[gname] = {
                "desc": str(m.get("description") or ""),
                "cmds": cmds,
                "order": list(m.get("order") or []),
                "layer": layer.name,
                "module": mod.name,
            }
    return groups


def find_command(groups, name):
    """按动作名跨组查找。返回 (组名, 脚本) 或 (None, 候选列表)。

    重名时不猜——报歧义让人指一下。
    """
    hits = [(g, info["cmds"][name]) for g, info in groups.items() if name in info["cmds"]]
    if len(hits) == 1:
        return hits[0][0], hits[0][1]
    return None, [g for g, _ in hits]


def run(script, extra=None):
    # script 现在已是完整路径（load_groups 里拼好的）
    path = Path(script) if script else None
    if path is None or not path.exists():
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


def show_list(groups):
    print("记忆维护统一入口\n")
    for g, info in groups.items():
        print("【%s】%s" % (g, info["desc"]))
        for k, v in info["cmds"].items():
            print("   mem.py %-6s %-10s → %s" % (g, k, v))
        print()
    print("也可以直接用动作名：mem.py daily / mem.py refs / mem.py dedup")
    print()
    print("备份/恢复保持独立：backup-memory.ps1 / backup-meow.py / backup-watchdog.py /")
    print("                    memory-export.py / memory-restore.py")
    return 0


def main():
    args = sys.argv[1:]
    groups = load_groups()

    if not args or args[0] in ("list", "-h", "--help"):
        return show_list(groups)

    first = args[0]

    # ① 正规写法：mem.py <组> [命令] [参数...]
    if first in groups:
        info = groups[first]
        sub = args[1] if len(args) > 1 else None
        if sub is None:
            if not info["order"]:
                print("【%s】的可用命令：%s" % (first, " / ".join(info["cmds"])))
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
            print("未知命令：%s（【%s】可用：%s）" % (sub, first, " / ".join(info["cmds"])))
            return 1
        return run(info["cmds"][sub], args[2:])

    # ② 便捷写法：mem.py <动作名> —— 跨组找，不用记分组
    g, script_or_cands = find_command(groups, first)
    if g:
        return run(script_or_cands, args[1:])

    cands = script_or_cands
    if cands:
        print("命令「%s」在多个组里都有：%s" % (first, " / ".join(cands)))
        print("请写明分组，例如：mem.py %s %s" % (cands[0], first))
        return 1

    all_cmds = sorted({k for info in groups.values() for k in info["cmds"]})
    print("未知命令或分组：%s" % first)
    print("可用分组：%s" % " / ".join(groups))
    print("可用动作：%s" % " / ".join(all_cmds))
    return 1


if __name__ == "__main__":
    sys.exit(main())
