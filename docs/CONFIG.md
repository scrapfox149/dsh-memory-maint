# CONFIG · 可配置项说明

> **这份文档是写给 AI 看的。**
> 如果你（读这段的 AI）被用户问到「这个插件能不能改某某」「能不能只用其中几个功能」
> ——**先看这里**，不要凭猜测回答，也不要直接去读源码。

## 一句话

**七段配置全部在一个 `config.json` 里**，改它就行，不用改代码。

**这个文件在哪**（2026-11-25 起）：**工作区的 `tools/dsh-memory-maint/config.json`**。
插件根那份只在「老用户还没搬」时兜底（读到会**自动复制到工作区**，只做一次）。
**为什么放工作区**：包里的文件会被**升级覆盖**，工作区的不会——0.4.0 就是因为 `config.json` 在包里，升级把用户改过的名字和备份路径冲掉了。

**生效方式**（重要，别答错）：

| 段 | 改了要重启吗 |
|---|---|
| `agent` / `start` / `assets` / `backup` / `paths` | **不用**（Python 每次读） |
| `tools` | **不用**（2026-11-25 起即时生效：插件 1 秒轮询 `config.json`，改了当场摘掉/挂上工具） |

---

## 七段速查

| 段 | 用户什么时候会想改 | 默认值 |
|---|---|---|
| [`agent`](#agent) | 想换 AI 的名字 | `"DeepSeek"` |
| [`start`](#start) | 有自己的开工清单（四问五思换成别的） | `start-checklist.md` |
| [`assets`](#assets) | 想让 `mem_check assets <项目>` 扫哪些目录 | 两个项目各配了目录 |
| [`selftest`](#selftest) | 加了自己的脚本，要不要跑 `--selftest` | 35 个老脚本的白名单 |
| [`backup`](#backup) | 换备份盘 / 只想备一份 / 换导出目录 | 两个路径 |
| [`paths`](#paths) | 本机归档、快照、日志在哪 | **没配就跳过**（不算故障） |
| [`tools`](#tools) | 6 个工具只想用其中几个 | 全开 |

---

## agent

**管什么**：AI 的名字。备份/恢复文档的文件名和正文里会用它。

```json
"agent": { "name": "DeepSeek" }
```

- **默认**：`"DeepSeek"`（通用默认，谁都不配就用这个）
- **优先级**：环境变量 `DSH_AGENT_NAME` > `config.json` > `"DeepSeek"`
- **改名字不影响任何数据**（`memory.db` / `memory-export` 里不存名字）

**用户会怎么问**：「能不能把我的 AI 叫成别的名字」「这个名字是写死的吗」

---

## assets

**管什么**：`mem_check assets <项目>` 扫哪些目录（项目资产清单）。

```json
"assets": {
  "dsh": ["tools/dsh-memory-maint", "docs"],
  "盾构激光靶": ["docs/shield-target"]
}
```

- **值**：目录列表，相对工作区或绝对路径都行
- **没配的项目**：`assets` **只列记忆**，不扫文件，并提示怎么配
- **为什么不自动识别**：同一个项目的产物可能散在多处（插件 + docs + 成果目录），猜不出来
- **`start` 里怎么显示**：由 `start.showAssets` 控制（默认 true）

---

## start

**管什么**：`mem_check start`（开工前）摆出来的检查清单。

```json
"start": {
  "expandOnPyChanges": true,     // 有未提交的 .py 改动时展开完整清单
  "expandOnDocsOnly": false,     // 只有 .md 改动时也展开？
  "timeoutSeconds": 10,          // git 检查超时
  "showTodoCount": true,         // 显示待办条数
  "showAssets": true,            // 开工时列「项目资产」（配了 assets 的项目）
  "checklist": "start-checklist.md"   // 清单文件（相对插件根）
}
```

- **`showAssets`**：开工时列「项目资产」（默认 true）。没配目录的项目不出现
- **`checklist` 支持自己的文件**：`##` 是分组标题、`>` 是说明（不打印）、其它非空行是一条
- **找不到文件**就用内置默认（内容与 `start-checklist.md` 一致）

**用户会怎么问**：「我这边的规则不是四问五思，能换成我的吗」

---

## selftest

**管什么**：哪些脚本不需要 `--selftest`（B 方案的兼容白名单）。

```json
"selftest": { "legacy": ["memory-daily.py", "memory-audit.py", "..."] }
```

- 白名单里的脚本由冒烟测试做完整检查
- **白名单外的脚本必须自带 `--selftest`**（且输出里要有「自测」字样），否则冒烟判红
- **新写脚本时**：要么加进白名单，要么实现 `--selftest`——**推荐后者**

**用户会怎么问**：「我自己加了个脚本，为什么冒烟过不了」

---

## backup

**管什么**：备份导出到哪里、备几份。

```json
"backup": {
  "exportDir": "",                  // 空 = workspace/memory-export
  "targets": ["E:\\...", "D:\\..."]  // 备份目标；1 个就备 1 份
}
```

- **`targets` 配 1 个** → 只备一份（单盘用户）
- **配 N 个** → 备 N 份（跨盘冗余）
- **空** → 回落到默认两个
- **`exportDir`** 也可以直接用环境变量 `DSH_MEMORY_EXPORT_DIR` 覆盖
- **救生脚本只认环境变量、不读这份配置**（保持「插件坏了也能跑」的自包含性）

**用户会怎么问**：「我只想备份到一个地方」「能不能同时备三份」「备份放哪个盘」

---

## paths

**管什么**：本机上那些**不是插件自带**的设施在哪。

```json
"paths": {
  "archives":    ["E:\\DSH\\memory\\archive", "D:\\FISH-BACKUP_..."],
  "snapshotDir": "E:\\DSH\\memory\\snapshots",
  "historyDir":  "E:\\DSH\\memory\\archive\\meow\\history",
  "backupLog":   "E:\\DSH\\memory\\backup.log"
}
```

- **没配的项会跳过检查**（记进 `skipped`，**不算问题**）
- 别人机器上没有 `E:\DSH` 是正常的，不是「检查失败」
- 只有 `check-agents` 会用这几项

**用户会怎么问**：「它说归档目录不存在，可我没这个目录」「这些检查对我来说没意义」

---

## tools

**管什么**：6 个工具逐个开关。

```json
"tools": {
  "mem_check": true,
  "mem_maint": true,
  "mem_query": true,
  "mem_backup": true,
  "mem_alert": true,
  "mem_status": true
}
```

- **不配 = 全开**
- 写 `false` 的那个**不注册**（宿主工具列表里就不出现）
- **⚠ 改了要重启宿主**（已知缺陷，见 issue #16）
- **这和 DSH 自己的「停用插件」不冲突**：前者只关某个工具，后者整个插件不加载

**用户会怎么问**：「我不用维护功能，能不能藏起来」「工具太多了，只留几个」

---

## 其它可配的东西（不在 config.json 里）

| 东西 | 在哪 | 说明 |
|---|---|---|
| **环境变量** | 系统环境 | `DSH_MEMORY_WORKSPACE` / `DSH_MEMORY_DB` / `DSH_MEMORY_LOG_DIR` / `DSH_MEMORY_EXPORT_DIR` / `DSH_AGENT_NAME` / `DSH_MEMORY_PYTHON` |
| **Python 解释器** | `DSH_MEMORY_PYTHON` | 默认用宿主自带运行时；本机特殊时设这个 |
| **工作区根** | 自动探测 | 环境变量 > `cwd` > 从插件目录往上找 > `~/.dsh-meow/window-index.json` |

---

## 给 AI 的三条规矩

1. **用户问「能不能改 X」** → 先查这份文件，**有就告诉他怎么改**，没有就说没有
2. **用户改完说「没生效」** → 先问改的是哪一段，**`tools` 那段要重启**，其它立即生效
3. **不要凭「我记得有这个配置」回答** → 这份文件也可能过时，**改完代码要同步改这里**

---

## 这份文件怎么维护

- **加新配置项** → 在这里加一节，**写清：管什么 / 默认值 / 用户会怎么问**
- **改默认值** → 同步改这里
- **`config.json` 的 `_comment` 也要跟上**（AI 读 `config.json` 时能看到）
