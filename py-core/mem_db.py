# -*- coding: utf-8 -*-
"""记忆库读取契约层（唯一入口）。所有维护脚本都该通过它读库，不要各自写 SQL。

五思（2026-11-17，第 1 级）
  目的：原先 29 个脚本各自写死表名与列名，插件一旦改 schema 就同时全坏，且报
        "no such column" 很难一眼定位。集中到一处后，schema 变了只改这个文件。
  方案：① 集中定义 TIERS 与"已知字段"  ② 用 PRAGMA table_info 动态探测实际列，
        缺列自动跳过并补默认值（兼容插件改版）  ③ load() 返回规范化 dict，
        脚本取自己需要的字段，不关心列在不在。
  边界：① **只读**（默认 mode=ro，不会写库）② 不改变任何调用方的输出格式
        ③ 找不到表/缺列时优雅降级，不抛  ④ 写操作不在这里（仍走 memory_* 工具）
  验证：① 改造一个脚本后与改造前输出逐字对比  ② 造缺列的测试库，确认不崩
        ③ mem.py check 全量回归
  退路：本文件是新增的；调用方改回直连 SQL 即可，原脚本存 tools/archive/。

用法：
    from mem_db import load, DB

    for it in load(tiers=["lesson"], status="active"):
        it["tier"], it["id"], it["content"], it["importance"]
"""
from paths import workspace_root  # noqa: E402
import json
import os
import sqlite3
import sys

# 库路径：先读环境变量（沙箱/测试用），否则用活库
DB = (os.environ.get("DSH_MEMORY_DB")
      or os.path.join(workspace_root(), ".dsh-meow/memory.db"))
TIERS = ["soul", "user", "rules", "project", "topic", "fact", "lesson"]

# 已知字段及其默认值（缺少时补这个值，避免调用方拿到 None 崩掉）
KNOWN = {
    "id": "",
    "title": "",
    "content": "",
    "importance": 1,
    "keywords": "[]",
    "status": "active",
    "project": "",
    "subcategory": "",
    "goal": "",
    "source_session": "",
    "created_at": 0,
    "updated_at": 0,
    "last_accessed_at": 0,
    "hit_count": 0,
    "corrected": 0,
}


def connect(db=None):
    """只读连接。db 为 None 时用活库。

    2026-11-18 加：**验证能真的读**——之前库文件损坏时，sqlite3.connect 本身
    不报错，等到第一次查询才抛 DatabaseError，而某些脚本会把它当"没数据"静默
    返回空（假阴性）。现在连上就探一次，坏库立刻抛并上报。
    """
    path = db or DB
    if not os.path.exists(path):
        raise FileNotFoundError("记忆库不存在: %s" % path)
    # 2026-11-26：**路径是目录**时 sqlite 只抛 `unable to open database file`（技术错误，
    # 用户看不懂）。DSH_MEMORY_DB 填错是很容易发生的，给一句人话。
    if os.path.isdir(path):
        raise RuntimeError(
            "记忆库路径指向的是一个**目录**，不是文件：%s\n"
            "  → 应该是 …\\.dsh-meow\\memory.db 这种文件路径" % path)
    con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        con.execute("select 1").fetchone()
    except sqlite3.DatabaseError as exc:
        con.close()
        report_exception("mem_db.connect",
                         "记忆库无法读取（可能损坏或不是 SQLite）：%s | %s" % (path, exc))
        raise RuntimeError("记忆库损坏或不是 SQLite 文件: %s" % path) from exc
    return con


def actual_columns(con, tier):
    """探测某层实际存在的列（插件改版时这里会自动少返回）"""
    try:
        return [r[1] for r in con.execute('PRAGMA table_info("%s")' % tier)]
    except sqlite3.Error:
        return []


def load(tiers=None, status=None, db=None, extra_cols=None):
    """读出规范化记录列表。

    tiers  : 要读的层（默认全部）。不存在的层自动跳过。
    status : "active" / "archived" / "stale" / None(全部)
    extra_cols : 除 KNOWN 之外还想读的列名（存在的才读）
    返回   : [dict]，每项含 tier + KNOWN 里有的字段（缺的取默认值）
    """
    con = connect(db)
    out = []
    try:
        for t in (tiers or TIERS):
            cols = actual_columns(con, t)
            if not cols:
                continue                      # 这一层不存在 → 跳过
            want = [c for c in KNOWN if c in cols]
            if extra_cols:
                want += [c for c in extra_cols if c in cols and c not in want]
            sql = 'select %s from "%s"' % (",".join(want), t)
            for row in con.execute(sql):
                rec = dict(KNOWN)             # 先铺默认值
                rec.update({k: v for k, v in zip(want, row) if v is not None})
                rec["tier"] = t
                if status and rec.get("status") != status:
                    continue
                out.append(rec)
    finally:
        con.close()
    return out


def count_by_status(db=None):
    """各层 active/stale/archived 计数，给体检用"""
    res = {}
    for t in TIERS:
        res[t] = {"active": 0, "stale": 0, "archived": 0}
    for it in load(db=db):
        st = it.get("status") or "active"
        if st in res[it["tier"]]:
            res[it["tier"]][st] += 1
    return res


if __name__ == "__main__":
    rows = load(status="active")
    print("契约层自检：读到 %d 条 active" % len(rows))
    for t, c in count_by_status().items():
        if sum(c.values()):
            print("  %-8s active %3d  stale %3d  archived %3d" % (t, c["active"], c["stale"], c["archived"]))


def count_status_sql(db=None):
    """各层 active/stale/archived 计数——**用 SQL 数，不全量读**。

    2026-11-18 新增：`count_by_status()` 是先 load 全部条目再数，数据量大时浪费；
    自检/体检这类"只想知道有几个"的场景，直接在库里数即可。
    返回结构与 count_by_status() 一致，可直接互换。
    """
    res = {}
    con = connect(db)
    try:
        for t in TIERS:
            res[t] = {"active": 0, "stale": 0, "archived": 0}
            try:
                for st, n in con.execute(
                        'select status, count(*) from "%s" group by status' % t):
                    if st in res[t]:
                        res[t][st] = n
            except sqlite3.Error as exc:
                report_degraded("mem_db.count_status_sql", t, str(exc))
    finally:
        con.close()
    return res


def dream_log(since_ms=0, db=None):
    """读 dream 整理记录（表不存在时返回空表，不崩）"""
    con = connect(db)
    try:
        cols = [r[1] for r in con.execute('PRAGMA table_info(dream_log)')]
        if not cols:
            return []
        want = [c for c in ("run_at", "summary", "changes") if c in cols]
        if "run_at" not in want:
            return []
        out = []
        for row in con.execute('select %s from dream_log order by run_at' % ",".join(want)):
            d = dict(zip(want, row))
            if (d.get("run_at") or 0) >= since_ms:
                out.append(d)
        return out
    except sqlite3.Error:
        return []
    finally:
        con.close()


# ============ 日志体系（2026-11-18）============
# 两份日志：
#   state/runtime.log   人类可读的运行流水（一行一条）
#   state/errors.jsonl  结构化报错/降级（一行一条 JSON）
# 保留 7 天，**写日志时顺手清理**（不依赖计划任务）。

# 日志目录：优先环境变量（插件装在 node_modules 时，由 Node 层指到工作区，
# 避免"工具写副本、命令行写工作区"两份日志）——2026-11-18 实测发现。
_STATE_DIR = (os.environ.get("DSH_MEMORY_LOG_DIR")
              or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".local", "state"))
_RUNTIME = os.path.join(_STATE_DIR, "runtime.log")
_ERRORS = os.path.join(_STATE_DIR, "errors.jsonl")
KEEP_DAYS = int(os.environ.get("DSH_MEMORY_LOG_DAYS", "7"))

_last_prune = [0.0]


def _now_ms():
    return int(__import__("time").time() * 1000)


def _fmt(ms):
    return __import__("datetime").datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def _prune(fname, keep_days=None):
    """删掉超过 keep_days 的行（按行首时间戳判断）。失败静默。"""
    try:
        keep = keep_days or KEEP_DAYS
        if not os.path.exists(fname):
            return 0
        cutoff = _now_ms() - keep * 86400000
        kept, dropped = [], 0
        with open(fname, encoding="utf-8", errors="replace") as f:
            for line in f:
                line_s = line.rstrip("\n")
                if not line_s:
                    continue
                ms = _parse_ts(line_s)
                if ms and ms < cutoff:
                    dropped += 1
                    continue
                kept.append(line_s)
        if dropped:
            with open(fname, "w", encoding="utf-8") as f:
                f.write("\n".join(kept) + ("\n" if kept else ""))
        return dropped
    except Exception:
        return 0


def _parse_ts(line):
    """从一行里取时间：JSON 的 time 字段，或行首 'YYYY-MM-DD HH:MM:SS'。"""
    try:
        if line.lstrip().startswith("{"):
            return int(json.loads(line).get("time") or 0)
    except Exception:
        pass
    try:
        return int(__import__("datetime").datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
    except Exception:
        return 0


def prune_logs(keep_days=None):
    """清理两份日志的过期行，返回 (runtime 删了几行, errors 删了几行)"""
    return _prune(_RUNTIME, keep_days), _prune(_ERRORS, keep_days)


def log_run(script, ok, elapsed_ms=0, note="", args=""):
    """记一条运行流水。**失败不抛**——不能因为写日志把正事搞崩。"""
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        # 每 5 分钟最多清理一次，避免每条都扫文件
        import time as _t
        if _t.time() - _last_prune[0] > 300:
            _last_prune[0] = _t.time()
            prune_logs()
        line = "%s | %-26s | %-4s | %6dms | %s%s" % (
            _fmt(_now_ms()), script[:26], "OK" if ok else "FAIL",
            int(elapsed_ms or 0), note[:80], (" args=" + args[:40]) if args else "")
        with open(_RUNTIME, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _append_error(rec):
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        rec.setdefault("time", _now_ms())
        with open(_ERRORS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


# 降级去重窗口：同一个 (脚本, 表, 缺列) 在这个时间内只报一次。
# 为什么需要：map-export / dump-active 这类"全字段导出"的脚本，每层都缺
# 若干列，一次运行就能写 20+ 条降级——不刷屏，就看不见真问题。
DEGRADE_DEDUP_MS = 24 * 3600 * 1000


def report_degraded(script, table, missing, note=""):
    """上报一次降级（某脚本查某表时缺列，已补 None 继续跑）。

    同一组合 24 小时内只记一次，避免刷屏（2026-11-18）。
    """
    try:
        now = _now_ms()
        sig = (str(script), str(table), str(missing))
        if os.path.exists(_ERRORS):
            with open(_ERRORS, encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except Exception:
                        continue
                    if r.get("kind") != "degraded":
                        continue
                    if ((r.get("script"), r.get("table"), r.get("missing")) == sig
                            and now - int(r.get("time") or 0) < DEGRADE_DEDUP_MS):
                        return
    except Exception:
        pass
    _append_error({"kind": "degraded", "script": script, "table": table,
                   "missing": missing, "note": note})


def report_exception(script, error, context=""):
    """上报一次未捕获异常"""
    _append_error({"kind": "exception", "script": script,
                   "error": str(error)[:500], "context": context})


def report_anomaly(script, detail):
    """上报一次数据异常（不是崩溃，但结果可疑）"""
    _append_error({"kind": "anomaly", "script": script, "detail": str(detail)[:500]})


def fetch(tier, cols, status=None, db=None, where=None, params=()):
    """按需取列，缺列自动补 None 并**上报降级**。

    返回**元组列表**（按 cols 顺序），调用方原来的 `for a, b, c in rows:` 不用改。
    """
    if isinstance(cols, str):
        cols = [c.strip() for c in cols.split(",")]
    con = connect(db)
    try:
        real = actual_columns(con, tier)
        if not real:
            return []
        missing = [c for c in cols if c not in real]
        if missing:
            report_degraded(os.path.basename(sys.argv[0]) if sys.argv else "?",
                            tier, ",".join(missing))
        select = ['"%s"' % c if c in real else "NULL as %s" % c for c in cols]
        sql = 'select %s from "%s"' % (",".join(select), tier)
        conds, args = [], list(params)
        if status:
            conds.append("status=?")
            args.append(status)
        if where:
            conds.append("(%s)" % where)
        if conds:
            sql += " where " + " and ".join(conds)
        return [tuple(r) for r in con.execute(sql, args)]
    finally:
        con.close()
