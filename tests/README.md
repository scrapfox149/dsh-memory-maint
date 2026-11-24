# tests · 测试脚本

> **这些是插件的测试，不是插件本体。** 安装时不会带上它们（`package.json` 的 `files` 不含 `tests/`）。

## 四个脚本

| 脚本 | 管什么 | 什么时候跑 |
|---|---|---|
| **`test-units.py`** | 纯函数数值（`decay` 的衰减、`text` 的分词） | 改算法时 |
| **`test-mem-plugin.py`** | 冒烟：35 个脚本都能跑、不抛 Traceback | **每次改完必跑** |
| **`test-full.py`** | 全量：15 组极限场景（42 断言） | **发版前必跑** |
| `test-make-db.py` | 造一个结构对齐的空库（CI 用） | 不单独跑，CI 里调 |

## 怎么跑

```powershell
cd tests
python test-units.py
python test-mem-plugin.py                    # 用工作区的真库
python test-mem-plugin.py --db tmp/ci.db     # 用指定库
python test-full.py
```

**三个脚本都从自己所在目录往上找插件根**（含 `py-core` 的那层），
所以放在根目录或 `tests/` 都能跑。

## 全量测试覆盖什么（15 组）

```
空库 / 库不存在 / 缺列 / 10 万字内容 / 特殊字符+SQL 注入 /
重复 id / 2000 字查询 / 只读不变(hash+mtime) / 并发 /
WAL / 10 万条(2.9s) / 损坏库 / 只读文件 / junction / 写不进去
```

## 三条约定（踩过坑的）

1. **输出里必须有「结论：」行** —— 冒烟靠它区分「有警告」和「跑崩了」；
   `mem_check daily` / `quality` / `integrity` 有该做的事时**故意返回 1**（好让计划任务知道有事），
   **不能只看退出码判失败**。
2. **测试要写自己的日志目录** —— `test-full.py` 会设 `DSH_MEMORY_LOG_DIR` 到临时目录，
   否则「损坏库」那组会把假异常灌进生产 `state/errors.jsonl`（2026-11-24 发生过一次，249 行）。
3. **断言别写死数量** —— 用「失败数 == 0」，否则加一项测试就全红。

## CI

`.github/workflows/tests.yml`：push / PR 到 `main` 时跑（Windows + Python 3.12）。

**CI 上和本机不同的一件事**：checkout 里既没有 `.dsh-meow/` 也没有 `AGENTS.md`，
所以 `paths.workspace_root()` 会**按设计报错**（不猜路径）——workflow 里显式设了
`DSH_MEMORY_WORKSPACE: ${{ github.workspace }}`，顺便验证环境变量这条路是通的。
