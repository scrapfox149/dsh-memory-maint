# dsh-memory-maint

鱼自己的记忆库维护插件。**逻辑只有一份，在 Python；本插件只做工具注册与转发。**

> **改这个插件之前先读 [`DEVELOPING.md`](./DEVELOPING.md)** —— 里面有架构、加东西的流程、测试清单、
> **十三个踩过的坑**、宿主接口契约、安装与同步。本文只做速查。

## 结构（三层六模块，2026-11-18）

```
dsh-memory-maint/
├── lib/index.js          控制层：只做「发现模块 + 注册工具」，不含业务逻辑
├── modules/
│   ├── feature/          逻辑层（业务）
│   │   ├── check/          mem_check   13 命令（daily 默认）
│   │   ├── maint/          mem_maint    8 命令
│   │   └── query/          mem_query    5 命令
│   ├── observe/          观察层（监控）
│   │   ├── alert/          mem_alert    2 命令（看日志）
│   │   └── status/         mem_status   1 命令（自检）
│   └── backup/           救生层
│       └── rescue/         mem_backup   2 命令（export/restore）
├── py-core/              基础层（同一逻辑只有一份）
│   ├── mem_db.py           数据：连库 / 探列 / 缺列补 NULL / 状态计数 / 写日志
│   ├── decay.py            衰减：半衰期 + decay_of（max(0) 已写死）
│   ├── text.py             分词：bigrams / jaccard / kw_set
│   └── out.py              呈现：title / section / item / action / ok / warn / bad
├── state/                日志（runtime.log / errors.jsonl，7 天过期）
├── test-mem-plugin.py    冒烟测试（自动分层发现）
├── DEVELOPING.md         开发/维护规范（改代码前必读）
└── cordis.patch.yml
```

**层与层的规矩**：
- 控制层只认 `module.json`，**不知道任何业务逻辑**
- 逻辑层不许依赖观察层
- 观察层可以依赖基础层
- 基础层谁都能用，它不依赖任何人
- **救生层（backup）有意自包含**：不依赖契约层，插件坏掉也能跑

## 六个工具

> **日常入口**：直接调 `mem_check`（不传 action 就是 `daily`）——输出分「该做的 / 不用管的 / 其他」三区。忘了动作名跑 `mem_check(action="help")`。


| 工具 | 命令数 | 动作 |
|---|---|---|
| `mem_check` | **13** | **daily**（默认，日常体检）/ **help**（动作清单）/ audit / health / refs / agents / agentsmem / signal / source / archive / promises / sample / weight2 |
| `mem_maint` | 8 | dedup / decay / changelog / dream / index / timeline / map / mapexport |
| `mem_query` | 5 | expand / hipporag / file / dump / people |
| `mem_alert` | 2 | list / clear |
| `mem_status` | 1 | status |
| `mem_backup` | 2 | export / restore |

调用示例：`mem_maint(action="dedup", args=["--min-sim", "0.3"])`

## 安装

已装进 `~/.dsh/profiles/desktop/node_modules/dsh-memory-maint/`（**正拷贝**）。
profile 的 `package.json` 两处登记：`dependencies` + `dsh.profile.bundles`。

**改完工作区代码必须同步**：
```bash
python tools/sync-plugin.py          # 工作区 → node_modules
python tools/sync-plugin.py --check  # 只对比
```

- Python 脚本：同步后**下次调用即生效**（每次都是新进程）
- 改了 `lib/index.js`：**必须重启宿主**

## 加东西（都不用改代码）

| 要加什么 | 怎么做 |
|---|---|
| **新命令** | `module.json` 的 `commands` 加一行 |
| **新模块** | 建 `modules/<层>/<模块>/py/` 三件套 + `module.json` |
| **新层** | 建 `modules/<新层>/<模块>/py/` |

结构**必须**是「层/模块/py」三层——漏了模块层会被自检当成模块。

## 设计铁律

1. **一个职责只有一份实现**（算法在 Python 就在 Python）
2. **调用单行道**：Node → Python，Python 不回调节点
3. **数据通路唯一**：Python 侧一律走 `py-core/mem_db.py`（`load` / `fetch` / `count_status_sql`）
4. **边界靠接口不靠语言**：Node 不知道 Python 里怎么算
5. **保命工具不依赖被保对象**（export/restore 自包含，随备份归档）

## 状态

- **6 模块 / 30 脚本 / 6 工具 / 31 命令 / 4085 行**
- 冒烟 **30/30**、全量 **38/38**（含极端）、自检正常、引用失效 0
- ✅ **已装进 desktop profile**，宿主日志确认 `6/6 个模块已注册`

## 依赖

- Python 解释器（默认取宿主运行时自带，可用 `DSH_MEMORY_PYTHON` 覆盖）
