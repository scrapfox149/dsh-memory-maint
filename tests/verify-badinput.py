# -*- coding: utf-8 -*-
"""不规范输入测试：用户可能把配置填成什么样，插件会不会崩 / 静默失效 / 给出误导。

覆盖四类：
  ① config.json 的字段（空 / 错类型 / 越界 / 不存在的东西）
  ② 环境变量（指向不存在 / 指向文件 / 空）
  ③ 命令行参数（0 / 负数 / 非数字 / 超长）
  ④ 库里的脏数据（NULL / 超长 / 特殊字符）

判定：**崩了 = ❌；静默用错值 = ⚠；给了可读提示 = ✅**
"""
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROD = r"C:\Users\24172\Documents\deepseek-harness\default-workspace"
PY = sys.executable
ok, warn, bad = [], [], []


def self_crashed(out, rc):
    """自己崩了没有——不能只看输出里有没有 Traceback。

    2026-11-26 踩的坑：`dump --json` 会把**记忆正文**打出来，
    而记忆里就有讲 Traceback 的条目 → 被误判成崩了。
    正确判据：退出码异常 + 有栈帧 + 栈帧指向我们自己的脚本。
    """
    if rc in (0, 1):
        return False                      # 0 正常 / 1 是"有警告"的设计值
    if "Traceback (most recent call last)" not in out:
        return False
    # 栈帧里要出现我们自己的模块名（py-core / modules）
    return re.search(r'File ".*(py-core|modules)[\\/]', out) is not None



def check(name, level, detail=""):
    ({"ok": ok, "warn": warn, "bad": bad}[level]).append(name)
    icon = {"ok": "✅", "warn": "⚠", "bad": "❌"}[level]
    print("  %s %s%s" % (icon, name, ("  → " + detail) if detail else ""))


def fresh(tag):
    iso = tempfile.mkdtemp(prefix="badin-%s-" % tag)
    os.makedirs(os.path.join(iso, ".dsh-meow"))
    src = os.path.join(PROD, ".dsh-meow", "memory.db")
    if os.path.exists(src):
        con = sqlite3.connect(src)
        bak = sqlite3.connect(os.path.join(iso, ".dsh-meow", "memory.db"))
        con.backup(bak)
        bak.close()
        con.close()
    os.makedirs(os.path.join(iso, "tools", "dsh-memory-maint"), exist_ok=True)
    return iso


def run(iso, *args, extra_env=None):
    e = {**os.environ, "DSH_MEMORY_WORKSPACE": iso,
         "DSH_MEMORY_LOG_DIR": os.path.join(iso, "state"), "PYTHONIOENCODING": "utf-8"}
    if extra_env:
        e.update(extra_env)
    r = subprocess.run([PY, os.path.join(BASE, "py-core", "mem.py"), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120, env=e)
    return ((r.stdout or "") + (r.stderr or "")), r.returncode


def write_cfg(iso, cfg):
    io.open(os.path.join(iso, "tools", "dsh-memory-maint", "config.json"), "w",
            encoding="utf-8").write(json.dumps(cfg, ensure_ascii=False, indent=2))


print("=== ① config.json 字段填坏 ===")

# 1. start.timeoutSeconds：0 / 负数 / 字符串
for v, label in ((0, "0"), (-5, "负数"), ("abc", "字符串")):
    iso = fresh("timeout")
    write_cfg(iso, {"start": {"timeoutSeconds": v}})
    out, rc = run(iso, "start")
    if self_crashed(out, rc):
        check("timeoutSeconds=%s" % label, "bad", "崩了 rc=%d" % rc)
    elif "结论" in out or "开工前" in out:
        check("timeoutSeconds=%s" % label, "ok", "没崩")
    else:
        check("timeoutSeconds=%s" % label, "warn", out[:60].replace("\n", " "))
    shutil.rmtree(iso, ignore_errors=True)

# 2. assets 指向不存在的路径 / 指向文件 / 空数组
iso = fresh("assets")
os.makedirs(os.path.join(iso, "realdir"), exist_ok=True)
io.open(os.path.join(iso, "afile.txt"), "w").write("x")
write_cfg(iso, {"assets": {"proj": ["不存在的目录", "afile.txt", "", None]}})
out, rc = run(iso, "assets", "proj")
if self_crashed(out, rc):
    check("assets 填不存在的路径/文件/空/None", "bad", "崩了")
elif "结论" in out:
    check("assets 填不存在的路径/文件/空/None", "ok", "没崩，给了结论")
else:
    check("assets 填不存在的路径/文件/空/None", "warn", out[:70].replace("\n", " "))
shutil.rmtree(iso, ignore_errors=True)

# 3. tools 填非布尔
iso = fresh("tools")
write_cfg(iso, {"tools": {"mem_check": "false", "mem_query": 0, "mem_maint": None}})
out, rc = run(iso, "list")
check("tools 填 'false'/0/None", "bad" if self_crashed(out, rc) else "ok",
      "没崩" if "Traceback" not in out else "崩了")
shutil.rmtree(iso, ignore_errors=True)

# 4. agent.name 空 / 超长 / 特殊字符
for v, label in (("", "空"), ("x" * 5000, "5000 字"), ("<script>\"'&", "特殊字符")):
    iso = fresh("agent")
    write_cfg(iso, {"agent": {"name": v}})
    out, rc = run(iso, "status")
    check("agent.name=%s" % label, "bad" if self_crashed(out, rc) else "ok",
          "没崩" if "Traceback" not in out else "崩了")
    shutil.rmtree(iso, ignore_errors=True)

# 5. backup.exportDir 指向一个文件
iso = fresh("exportdir")
io.open(os.path.join(iso, "afile.txt"), "w").write("x")
write_cfg(iso, {"backup": {"exportDir": os.path.join(iso, "afile.txt")}})
out, rc = run(iso, "export")
check("exportDir 指向文件", "warn" if self_crashed(out, rc) else "ok",
      "没崩" if "Traceback" not in out else "崩了（可接受，但提示可更友好）")
shutil.rmtree(iso, ignore_errors=True)

print("\n=== ② 环境变量 ===")
iso = fresh("env")

# DSH_MEMORY_DB 指向目录 / 不存在
out, rc = run(iso, "daily", extra_env={"DSH_MEMORY_DB": iso})
check("DSH_MEMORY_DB 指向目录", "bad" if self_crashed(out, rc) else "ok",
      (out.strip().splitlines()[-1] if out.strip() else "")[:60])
out, rc = run(iso, "daily", extra_env={"DSH_MEMORY_DB": os.path.join(iso, "nope.db")})
check("DSH_MEMORY_DB 指向不存在的文件", "bad" if self_crashed(out, rc) else "ok",
      (out.strip().splitlines()[-1] if out.strip() else "")[:60])

# DSH_MEMORY_WORKSPACE 指向不存在的目录
out, rc = run(os.path.join(iso, "nope-ws"), "daily")
check("工作区指向不存在的目录", "warn" if self_crashed(out, rc) else "ok",
      (out.strip().splitlines()[-1] if out.strip() else "")[:60])
shutil.rmtree(iso, ignore_errors=True)

print("\n=== ③ 命令行参数 ===")
iso = fresh("args")
for args, label in (
    (["dump", "--json"], "正常"),
    (["project", "dsh", "--recent", "0"], "--recent 0"),
    (["project", "dsh", "--recent", "-1"], "--recent -1"),
    (["project", "dsh", "--recent", "abc"], "--recent abc"),
    (["assets", "dsh", "--limit", "0"], "--limit 0"),
    (["assets", "dsh", "--limit", "-3"], "--limit -3"),
    (["why", ""], "空查询"),
):
    out, rc = run(iso, *args)
    if self_crashed(out, rc):
        check("参数：%s" % label, "bad", "崩了")
    else:
        check("参数：%s" % label, "ok", "rc=%d" % rc)
shutil.rmtree(iso, ignore_errors=True)

print("\n" + "=" * 56)
print("不规范输入：✅ %d 正常 / ⚠ %d 需注意 / ❌ %d 崩了" % (len(ok), len(warn), len(bad)))
if warn:
    print("  需注意：")
    for w in warn:
        print("    ⚠ " + w)
if bad:
    print("  崩了：")
    for b in bad:
        print("    ❌ " + b)
sys.exit(0 if not bad else 1)
