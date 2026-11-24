# -*- coding: utf-8 -*-
"""工作区路径解析 —— 不再硬编码 C:\\Users\\...\\default-workspace。

五思：
① 目的：让插件在别人的机器上也能跑。原来 25 处写死 `C:\\Users\\24172\\...`，
       换台机器全部失效，是「可移植性 3/10」的主因。
② 方案：环境变量优先 → 向上找标志物 → 报错（不猜）。三级兜底，每级都可诊断。
③ 边界：只负责"算路径"，不碰业务逻辑；不做文件操作；找不到就抛异常，
       不返回一个看起来像对的错误路径（那比崩更糟）。
④ 验证：冒烟 30/30；另需单独验证"从不同 cwd 调用都能算对"。
⑤ 退路：git 有历史，改坏了可回滚。

优先级：
  1. 环境变量 DSH_MEMORY_WORKSPACE
  2. 从 start（默认本文件所在目录）向上最多 8 层，找含标志物的目录
  3. 都失败 → RuntimeError

标志物选两样（**不能用 `py-core`**——它就在插件目录里，从插件内部向上找必然先命中自己，
算出来的是插件目录而不是工作区根，2026-11-24 实测踩到）：
  - .dsh-meow/   （记忆库数据目录，只在工作区根）
  - AGENTS.md    （工作区备忘，只在工作区根）

注意：memory-export.py / memory-restore.py 是**故意自包含**的救生圈，
不 import 本模块——它们内联同一套逻辑，改这里时**要同步改那两处**。
"""

import os

# 环境变量名（与 mem_db.py 的 DSH_MEMORY_DB 同一家族）
ENV_WORKSPACE = "DSH_MEMORY_WORKSPACE"

# 工作区的标志物：**只认「装着库的」 `.dsh-meow`**（含 memory.db）。
# 走过的弯路（2026-11-24 实测）：
#   ① `.dsh-meow` 目录 → 命中 `~/.dsh-meow`（meow-memory 的**全局状态目录**，不是工作区）
#   ② `AGENTS.md` → 命中 `~/.dsh/AGENTS.md`（**全局约定**，也不是工作区）
# 只有「有 memory.db 的 .dsh-meow」才唯一标识一个记忆工作区。
_MARKERS = (os.path.join(".dsh-meow", "memory.db"),)
_MAX_UP = 8


def workspace_root(start=None):
    """算出工作区根目录。找不到抛 RuntimeError，不返回可疑值。"""
    env = os.environ.get(ENV_WORKSPACE)
    if env:
        if os.path.isdir(env):
            return os.path.abspath(env)
        raise RuntimeError(
            "%s 指向的目录不存在：%s" % (ENV_WORKSPACE, env))

    here = os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))
    for _ in range(_MAX_UP):
        for m in _MARKERS:
            if os.path.exists(os.path.join(here, m)):
                return here
        parent = os.path.dirname(here)
        if parent == here:      # 到盘根了
            break
        here = parent

    raise RuntimeError(
        "找不到工作区根：从 %s 向上 %d 层都没遇到 %s 中的任何一个。\n"
        "设一个环境变量就能跳过查找：%s=<你的工作区路径>"
        % (start or os.getcwd(), _MAX_UP, " / ".join(_MARKERS), ENV_WORKSPACE))


def sub(*parts):
    """工作区下的子路径，如 sub('docs', 'memory-index.md')。"""
    return os.path.join(workspace_root(), *parts)


# ── 常用固定位置（原来各脚本里各写一遍的那些） ──────────────────────────
def db_path():
    """记忆库路径：DSH_MEMORY_DB 优先（与 mem_db.py 一致），否则 .dsh-meow/memory.db。"""
    return os.environ.get("DSH_MEMORY_DB") or sub(".dsh-meow", "memory.db")


def export_dir():
    return os.environ.get("DSH_MEMORY_EXPORT") or sub("memory-export")


if __name__ == "__main__":
    # 自测：从不同 cwd 打印算出来的根
    print("cwd            =", os.getcwd())
    try:
        print("workspace_root =", workspace_root())
        print("db_path        =", db_path())
        print("export_dir     =", export_dir())
    except RuntimeError as e:
        print("失败：", e)
