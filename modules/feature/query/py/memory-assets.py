# -*- coding: utf-8 -*-
"""项目资产清单：这个项目现在有什么（文件 + 记忆）。

五思（2026-11-25 新建 = 第 1 级）
  目的：用户提出「项目记忆检索」——开工时自动列出项目已有的文件/资产，
        收工时提醒「变了什么、该总结了」。现在**开工时要自己想去哪找**，
        四问第一条「说明书在哪」也靠记忆。
        明确不做：不做「自动注入」（那是 meow-memory 那种宿主级钩子，插件没有），
        只做 `start` 时摆出来。
  方案：项目名 → config.json 的 `assets.<项目>` 给的目录列表（相对工作区或绝对路径）：
        ①扫目录里的文件（排除 .git/__pycache__/node_modules/.local/tmp/state）
        ②列记忆库里 project 字段指向该项目的条目（按层统计 + 最近几条）
        没配目录的项目**只列记忆**，并提示怎么配。
  边界：只读；目录不存在时跳过并标注；文件过多截断（默认 10，--limit 可调）；
        项目不存在时列可用项目名；config.json 坏了当没配。
  验证：文件数与 `Get-ChildItem` 对数；记忆条数与 `memory-project` 对数；
        `--json` 能 json.loads；空项目不崩。
  退路：独立脚本，删掉 + 从 module.json 去掉一行即可。
"""
import io
import json
import os
import sys

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_here = os.path.dirname(os.path.abspath(__file__))
for _up in range(1, 5):
    _pc = os.path.join(_here, *([".."] * _up), "py-core")
    if os.path.isdir(_pc):
        sys.path.insert(0, _pc)
        break
from mem_db import load  # noqa: E402
from paths import workspace_root  # noqa: E402

# 插件根：modules/feature/query/py → 往上 4 层
PLUGIN_ROOT = os.path.abspath(os.path.join(_here, "..", "..", "..", ".."))
TIERS = ("project", "fact", "lesson", "topic", "rules", "user", "soul")
TIER_CN = {"project": "项目", "fact": "事实", "lesson": "教训", "topic": "话题",
           "rules": "规则", "user": "用户", "soul": "自身"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".local", "tmp", "state", ".venv"}


def load_cfg():
    p = os.path.join(PLUGIN_ROOT, "config.json")
    try:
        return json.load(io.open(p, encoding="utf-8-sig"))
    except Exception:
        return {}


def projects_of(row):
    raw = (row.get("project") or "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.replace("，", ",").split(",") if p.strip()]


def scan_files(dirs, ws, limit):
    """扫目录里的文件，返回 [{path, size, mtime}]（按 mtime 倒序，截 limit 条）+ 总数"""
    out = []
    for d in dirs:
        base = d if os.path.isabs(d) else os.path.join(ws, d)
        if not os.path.isdir(base):
            out.append({"path": d, "missing": True})
            continue
        for root, subdirs, files in os.walk(base):
            subdirs[:] = [s for s in subdirs if s not in SKIP_DIRS]
            for fn in files:
                if fn.endswith((".pyc", ".pyo")):
                    continue
                fp = os.path.join(root, fn)
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                out.append({"path": os.path.relpath(fp, ws), "size": st.st_size,
                            "mtime": int(st.st_mtime)})
    real = [x for x in out if not x.get("missing")]
    missing = [x for x in out if x.get("missing")]
    real.sort(key=lambda x: -x["mtime"])
    return real[:limit], len(real), missing


def human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.1f%s" % (n, unit) if unit != "B" else "%dB" % n
        n /= 1024.0


def selftest():
    """边界自测（B 方案）：不碰真库、不写文件，只测纯函数与容错。"""
    passed, failed = [], []

    def check(name, ok, detail=""):
        (passed if ok else failed).append(name)
        print("  %s %s%s" % ("✅" if ok else "❌", name, ("  → " + detail) if detail else ""))

    # ① projects_of：逗号/中文逗号/空
    check("projects_of 拆多项目", projects_of({"project": "dsh, 盾构激光靶"}) == ["dsh", "盾构激光靶"])
    check("projects_of 处理中文逗号", projects_of({"project": "a，b"}) == ["a", "b"])
    check("projects_of 空字段返回空", projects_of({"project": ""}) == [])

    # ② human_size
    check("human_size 字节", human_size(512) == "512B")
    check("human_size KB", human_size(2048) == "2.0KB")

    # ③ scan_files：目录不存在时要标 missing，不崩
    files, n, missing = scan_files(["__nosuchdir__"], os.getcwd(), 5)
    check("目录不存在标 missing", len(missing) == 1 and n == 0, "missing=%d" % len(missing))

    # ④ load_cfg 在 config.json 坏掉时返回 {}
    check("load_cfg 返回 dict", isinstance(load_cfg(), dict))

    total = len(passed) + len(failed)
    print("\nmemory-assets 自测：%d 通过 / %d 失败 / 共 %d"
          % (len(passed), len(failed), total))
    return 0 if not failed else 1


def main():
    if "--selftest" in sys.argv:
        return selftest()

    args = list(sys.argv[1:])
    if not args:
        cfg = load_cfg()
        names = sorted(k for k in (cfg.get("assets") or {}) if not k.startswith("_"))
        print("用法：mem.py assets <项目名> [--limit N] [--json]")
        print()
        if names:
            print("已配置目录的项目：")
            for n in names:
                dirs = cfg["assets"][n]
                print("  %-16s %s" % (n, ", ".join(dirs) if isinstance(dirs, list) else dirs))
        print()
        print("（在 config.json 的 assets 段里给项目配目录，就能扫文件；不配只列记忆）")
        return 0

    want_json = "--json" in args
    if want_json:
        args = [a for a in args if a != "--json"]

    limit = 10
    if "--limit" in args:
        i = args.index("--limit")
        try:
            limit = max(1, min(200, int(args[i + 1])))
            del args[i:i + 1 + 1]
        except Exception:
            print("--limit 需要一个数字")
            return 1

    if not args:
        print("用法：mem.py assets <项目名> [--limit N] [--json]")
        return 1
    want = args[0]

    ws = workspace_root()
    cfg = load_cfg()
    dirs = (cfg.get("assets") or {}).get(want) or []

    files, n_files, missing = scan_files(dirs, ws, limit) if dirs else ([], 0, [])

    # 记忆：project 字段指向该项目
    rows = []
    for tier in TIERS:
        for r in load([tier]):
            if r.get("status") not in (None, "active"):
                continue
            if want in projects_of(r):
                rows.append((tier, r))

    by_tier = {}
    for tier, _r in rows:
        by_tier[tier] = by_tier.get(tier, 0) + 1

    if want_json:
        print(json.dumps({
            "project": want,
            "dirs": dirs,
            "files": {"total": n_files, "missing_dirs": [m["path"] for m in missing],
                      "recent": files},
            "memories": {
                "total": len(rows),
                "by_tier": by_tier,
                "recent": [{"id": r.get("id"), "tier": t,
                            "subcategory": r.get("subcategory") or "",
                            "content": r.get("content") or "",
                            "updated_at": r.get("updated_at") or r.get("created_at")}
                           for t, r in sorted(rows,
                                              key=lambda tr: tr[1].get("updated_at")
                                              or tr[1].get("created_at") or 0,
                                              reverse=True)[:limit]],
            },
        }, ensure_ascii=False, indent=1))
        return 0

    print("=== 项目：%s 的资产 ===" % want)
    print()

    if dirs:
        print("文件：%d 个（扫 %d 个目录，列出最近改动的 %d 个）"
              % (n_files, len(dirs), min(limit, len(files))))
        for f in files:
            d = int(f["mtime"])
            import time as _t
            print("  %s  %7s  %s" % (_t.strftime("%m-%d %H:%M", _t.localtime(d)),
                                     human_size(f["size"]), f["path"]))
        if missing:
            print("  ⚠ 目录不存在：%s" % ", ".join(m["path"] for m in missing))
        print()
    else:
        print("文件：没配目录（在 config.json 的 assets.%s 里加目录就能扫）" % want)
        print()

    print("记忆：%d 条" % len(rows))
    if by_tier:
        parts = ["%s %d" % (TIER_CN.get(t, t), n)
                 for t, n in sorted(by_tier.items(), key=lambda x: -x[1])]
        print("  分布：" + " / ".join(parts))
    print()

    if rows:
        print("最近改动的 %d 条：" % min(5, len(rows)))
        for t, r in sorted(rows, key=lambda tr: tr[1].get("updated_at")
                           or tr[1].get("created_at") or 0, reverse=True)[:5]:
            c = (r.get("content") or "").replace("\n", " ")[:56]
            print("  [%s] %s" % (TIER_CN.get(t, t), c))
        print()

    print("结论：%s 有 %d 个文件、%d 条记忆%s" % (
        want, n_files, len(rows),
        "" if dirs else "（未配目录）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
