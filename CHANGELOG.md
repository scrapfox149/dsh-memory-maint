# 变更日志

本插件自 2026-11-23 起纳入 Git 版本管理。此前的改动只记在记忆库与 AGENTS.md 里，
下面按时间顺序补录，**不保证完整**——只列有据可查的部分。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

---

## [未发布]

### 新增

- **`mem_query hotfiles`** —— 哪些文件改得最勤（`git log` 统计，最近 N 天）
  - `--days N`（默认 30）/ `--top N`（默认 10）/ `--json`
  - **工作区本身不是 git 仓库时会往下找子仓库**（实测：本机仓库在 `tools/dsh-memory-maint`）
  - 没有 git → 明说「统计不了」并指向 `assets`（不猜、不崩）
- **`mem_check start --full`** —— 强制展开完整四问五思（不想等"检测到改动"时用）

### 修复

- **`check-agents` 加 `tools/*.ps1` 的 BOM + 语法校验**（issue #19）：32 项 → **38 项**
- **README 的 `docs/DEVELOPING.md` 链接指向根目录**（文件在 `docs/` 里，点了 404）

### 改进

- **`start` 的「今天在不在动东西」判据从「git」换成三级判断**：
  ```
  ① 有 last-start → 看「上次开工以来」改过的（最准）
  ② 首次（无记录） → 回落最近 24 小时
  ③ 有 git 时再叠 git status（未提交的也算"正在改"）
  ```
  **为什么换**：用户提「别人不一定是跟我们一样通过 git 来控制项目，就例如我们自己的激光靶解析项目就没有」。
  原来的 24h 固定窗口会漏判（昨天下午改的、今天上午看就超了）；改用「上次开工以来」才对。
  **没 git 的项目（激光靶那种）只靠 mtime 也能正确判断。**
- **`since` 减 1 秒容差**——防止「和上次 start 同一秒改的文件」被漏掉

---

## [0.4.4] - 2026-11-26

### 新增

- **`mem_query file` 补上查询入口**（issue #12 完成）：`mem.py file <词> [--top N] [--json]`
  - 之前它的 `__main__` 只有硬编码自测，`mem.py file README` **会忽略 README**——用户跑一次会以为插件坏了
  - 自测挪到 `--selftest`；没有 `memory-export/` 时只搜 `docs/` 并提示（`--json` 下不打印，避免污染）
- **`mem_query diag`** —— 出 BUG 时打一份**脱敏**诊断包（版本/环境/最近错误/配置），
  拖进 GitHub issue 当附件即可。token/密码 → `***`，本机路径只留最后两段
- **`.github/ISSUE_TEMPLATE/`** —— bug / feature 模板，bug 模板第一段就要求跑 `diag`
- **测试从 6 层加到 12 层**：只读性 35 / 数字正确性 7 / 设计一致性 14 / 组合 20 /
  不规范输入 26 / 输出质量 35 / bug 修复复现 13 / json 覆盖 8

### 修复（今晚抓到并修好的 5 个真 bug，全是"新装用户才会遇到"的）

1. **`dump` 在新装环境直接崩** —— `workspace/tmp/` 不存在时 `FileNotFoundError`，现在先建目录
2. **`people --json` 的 counts 少一组** —— 写死 4 个组名，和 `groups` 的实际 key 对不上（差 1），改成按实际 key 生成
3. **首次配置提醒在「轻路」永远看不到** —— 提醒写在 `heavy=True` 分支里，轻路提前 return，移到两条路都经过的位置
4. **`git status` 失败被当成「没有改动」** —— 只捕异常不查退出码，不在 git 仓库里时误走轻路；现在读不到就保守走重路
5. **`file` 在新装环境崩** —— `os.listdir(memory-export)` 没检查目录存在

### 改进

- **`backup.targets` 加三道保护**：去重 / 拒绝把工作区当备份目标（会自己同步自己）/ 只配一个时恢复文档写「未配置第二副本」
- **`--limit` 越界会说明**：「（--limit -3 超出范围 1-200，按 1 算）」，不再静默夹
- **`DSH_MEMORY_DB` 指向目录时给可读提示**，不再是 `sqlite3.OperationalError: unable to open database file`
- **`help` 加了 `file` 的意图**（「文档里提到过某个说法」）
- **`assets` 不再把 `.tgz`/`.log` 这类构建产物当"项目资产"**
- **README 去重去旧**（「六个工具」重复出现两次、架构里的动作数 13/8/5 → 16/7/8）

---

## 已知问题（未修，记着）

### 1. `file` 的检索质量偏「概念中心」

**现象**：`mem.py file 备份怎么恢复` 第一条命中的是「多跳局限」，最相关的 `memory-restore` 不在前列。

**原因**：`file` 用 bigram 重叠 × IDF × 长度归一（BM25 风格），会偏向**被很多条目共享的词**（概念中心）。
和 `hipporag` 同一个毛病（那条教训：PPR 偏向概念中心，具体操作类问题该用 `memory_search`）。

**可能的方向**（未定）：对"操作类"查询加权、或提高 `docs/` 文档的权重（用户想找的往往是文档不是记忆条目）。

### 2. `start` 在本机会永远走「重路」

**现象**：`=== 开工前 ===` 永远显示「🔧 读不到 git 状态，保守处理」，每天都展开完整四问五思。

**原因**：本机工作区**不是 git 仓库** → `git status` 失败 → 保守走重路（**这是正确行为**），
但对"想每天只看一句话"的人来说偏啰嗦。**设计上没毛病，是使用体验问题。**

---

## [0.4.3] - 2026-11-25

> 首次强提醒过时了——它还在说「工具开关改了要重启宿主」，而这版早就即时生效了。

### 修复

- **`check-agents` 加 `tools/*.ps1` 的 BOM + 语法校验**（issue #19）：
  前 3 字节必须是 `EF BB BF`、`Parser::ParseFile()` 零错误，任一不满足就报红并指名。
  平台分支（只在 Windows 跑）。现 **38 项**。
- （上面那 5 个：dump / people / 提醒位置 / git status / file）

### 改进

- **首次 `start` 的强提醒**（只提一次的那段）：
  - 「六段配置」→ **七段**（补 `assets.<项目>`）
  - 去掉「⚠ 要重启宿主」，改成「**改完即时生效，不用重启**」
  - 补一句「`mem_backup` 默认关闭 + 备份到哪只有你知道 + **要不要现在设置**」
  - 补一句「`assets` 没配就只列记忆」
- **`start` 里的项目资产段**：读配置原来只看插件根那个 `config.json`，
  而 0.4.1 起配置在**工作区** → 改成**工作区优先、插件根兜底**（和 `lib/index.js` 一致）。
  不修的话：配了 `assets` 也不显示项目资产。

### 给别人用的三条保证（这次专门核过）

| 项 | 做法 |
|---|---|
| **不污染别人的记忆系统** | 读写都走 `DSH_MEMORY_WORKSPACE`（宿主传的值）；`backup.targets` 默认**空**；`config.json` 不进包 |
| **名字是通用默认** | `config.example.json` 和代码默认都是 `DeepSeek`；只有我们自己的 `config.json` 才写「鱼」 |
| **备份默认关** | 不配 `tools.mem_backup: true` 就不注册；首次提醒里明说并询问 |

### 回归
冒烟 37 / 单元 30 / 新功能 20 / `memory-start` 自测 8 —— 全绿。仍是 **prerelease**（还有功能没补全）。

---

## [0.4.2] - 2026-11-25

> 安装后行为验收里抓出来的一个真 bug。

### 修复

- **轮询盯错了配置文件**：`configPath()` 原来只在启动时算一次。如果启动时工作区还没有
  `config.json`（新装就是这样），它盯的是插件根那个**不存在**的路径——
  用户后来在工作区建了配置，**轮询根本不认**，改了不生效、日志也不响。
  现在**每次轮询重新算路径**，路径本身变了也算一次变化。

### 新增（验收）

- `tests/` 外补了一份「安装后行为验收」：干净环境装包 → 验 14 条
  （工具数 / 默认配置 / 配置即时生效 / `mem.py` 各命令 / `--json` / `start` 的分段）。
  **干净环境 + 复制一份真库**，验完 **14/14**。

### 这一版为什么还是测试版

还有功能没补全：`#12` 差 `file` 的 `--json`、`#8`–`#11` 四个新查询、`reuse`（经验复用）。
按 2026-11-25 决定：**没补全前一律 prerelease**。

---

## [0.4.1] - 2026-11-25

> **修复一个发版级问题：升级会覆盖用户配置。**
> 0.4.0 已撤回（Release 和 tag 都删了），本版是它的修复版。

### ⚠ 升级前必做（0.3.0 / 0.4.0 用户）

**如果你改过插件目录里的 `config.json`（`agent.name` / `backup.targets` / `paths`），
升级前先把它复制到**：

```
<工作区>/tools/dsh-memory-maint/config.json
```

**为什么**：老版本把 `config.json` 打在包里，升级 = 删旧目录 + 装新包 → **你的配置会被包里的默认值覆盖**（实测：改过的名字变回打包者机器上的名字，备份路径变成别人机器上的路径）。

**从 0.4.1 起不用再手动搬**：配置固定读工作区那份，升级不会碰它。

### 修复

- **`config.json` 不再打进安装包**（`package.json` 的 `files` 去掉它，改放 `config.example.json`）
- **`loadPluginConfig()` 改成「工作区优先」**：
  1. `<工作区>/tools/dsh-memory-maint/config.json`
  2. 插件根 `config.json`（兼容老用户；**并会把它复制到工作区**，只做一次）
  3. 都没有 → 用内置默认值
- **轮询路径同步改动**，否则会出现"改了工作区那份却不生效"这种更迷惑的情况

### 新增

- **`mem_backup` 默认关闭** —— 它是救生工具（导出/恢复），但**别人的备份路径我们不知道**
  （默认 `backup.targets` 为空，跑起来什么也不做）。所以这一版起：**不配 `tools.mem_backup: true` 就不注册它**。
  其他五个工具仍是「不配 = 开」。
  判据：**这个工具默认开，会不会让新用户对着一个"什么都没配"的功能困惑？** 会 → 默认关。
- **`config.example.json`** —— 配置样例（通用默认值，**不含任何本机路径**）。复制成 `config.json` 再改。

### 验证（这次实测了升级链）

```
① pnpm add dsh-memory-maint-0.3.0.tgz
② 把 config.json 的 agent.name 改成「测试用户」，放在工作区
③ pnpm add dsh-memory-maint-0.4.1.tgz
④ 调 apply → 工作区配置还在，agent.name = 测试用户 ✅，注册 6 个工具 ✅
```

三项回归：全量 **42** / 冒烟 **37** / 单元 **30** / 新功能 **20** / 开关 **11** —— 全绿。

---

## [0.4.0] - 2026-11-25

> 这一版的主线是 **「能改的立刻生效」** 和 **「知道项目现在有什么」**。

### 新增

- **`mem_query assets <项目>`** —— 项目资产清单：扫 config.json 里 `assets.<项目>` 配的目录
  + 列库里 `project` 字段指向该项目的记忆。`--json` / `--limit` / `--selftest`。
- **`mem_check start` 里列「项目资产」**（`start.showAssets` 控制）：
  ```
  项目资产：
    dsh：126 个文件 / 239 条记忆
    盾构激光靶：14 个文件 / 30 条记忆
  ```
  实现上调 `assets --json` 拿数字——**扫描逻辑只有一份**（合并入口，不合并脚本）。

### 改进

- **`mem_query` 的 6 个动作支持 `--json`**（`project` / `people` / `dump` / `expand` / `hipporag` / `why`），
  接别的工具不用再解析文本。**文本模式的输出一个字都没变**，`--json` 是凭空多出来的一条路。
- **所有配置项即时生效**：`PLUGIN_CONFIG` 原来是模块加载时读一次，现在每次 `runPython` 重新读——
  `backup.exportDir` 之类改了不用重启宿主。

### 修复

- **`tools` 段改了不用重启宿主**（issue #16）。
  - `ctx.tools.register()` 返回的 **disposer** 之前一直被忽略，现在用它做真开关
  - 1 秒轮询 `config.json` 的 `mtime`（**`fs.watch` 在 Windows 上实测只触发一次**）
  - **自己写一份流水** `$DSH_MEMORY_LOG_DIR/tool-sync.log`——宿主 logger 会对内容相同的日志去重
    （`log.repeated`），"改回 true"那条会被吞掉
  - `tests/switch-test.mjs`（mock ctx，11 项）+ 加进 CI
- **`check-memory-refs` 加了负向后视**：不再把「插件内部的 `docs/CONFIG.md`」误报成工作区的
- **`project` 支持 `--decisions` / `--quotes` / `--todo`** 按子类过滤（可组合）。

### 文档

- `docs/CONFIG.md`：六段 → **七段速查**，新增 `assets` 段，**修正「`tools` 要重启」的过时说明**
- `README`：`mem_query` 7 → 8 个动作
- `mem_check help`：意图清单里加「这个项目已有什么」
- 新增 `docs/design-experience-reuse.md`（经验复用的设计笔记，还没实现）

### 测试

冒烟 **37**（+2）/ 单元 30 / 新功能 **20**（+6）/ 开关 11 —— 全绿。

---

## [0.3.0] - 2026-11-24

> 今天共 58 个提交。这一版的核心变化是**从「补功能」转向「足够好用、需要时想得起来」**。

### 新增

**体检类**
- **`mem_check start`**：开工前把清单摆到眼前，**按需展开**。
  - 有未提交的 `.py` 改动 → 完整清单 + 正在改的脚本
  - 工作区干净 → 一句话「四问可省」
- **`mem_check quality`**：把 `audit` / `signal` / `source` 压成一份可读结果
- **`mem_check integrity`**：把 `refs` / `agents` / `agentsmem` / `archive` 压成一份

**查询类**
- **`mem_query why`**：看查询里哪些词撞上了记忆的关键词（**词面重叠，不是 BM25 分数**）；
  关键词命中不足 3 条时自动补扫正文，`--full` 可强制
- **`mem_query project`**：一个项目的记忆全景（条数 / 各层分布 / 最近更新 / 待办 / 重复嫌疑）

**高级模式**
- **`mem_check daily --advanced`**：把低频动作（`health` / `weight2` / `sample`）的排障信息
  并成一个开关——平时 4 行，排障时加参数
- **有问题时自动提示** `--advanced`（没问题不提——提示本身也是噪音）

### 改进

- **`mem.py` 从 `module.json` 读分组**：原来 `GROUPS` 是手抄的、已经落后
  （13 个 `mem_check` 命令只抄了 8 个，`backup` 组整个没有）
- **支持直接用动作名**：`mem.py daily` == `mem.py check daily`
- **`mem_check` 的体检顺序**挪进 `module.json` 的 `order` 字段
- **`memory-daily` 输出从 7 段压到 4 行**：结论前置，解释挪进 `--verbose`
- **`check-agents` 按平台分流**：非 Windows 上跳过本机设施检查（标「跳过」不标「问题」）
- **`mem.py list --json`**：结构化清单，路径用**相对插件根**（不带 `C:\Users\...`）
- **`help` 分组**：常用动作列全，低频动作单独一行（`health` / `agentsmem` / `source` / `archive` / `sample` / `weight2`）
- **删掉 `mapexport` 命令**：它被 `map` 取代了（`map` 现在快照不存在时自己先导出）

### 可配置

**六段全在插件根的 `config.json`，改配置不用改代码**；每一项的说明见 `docs/CONFIG.md`。

- **`agent.name`** —— AI 的名字。默认 `DeepSeek`（通用），本机覆盖成「鱼」。
  优先级：`DSH_AGENT_NAME` 环境变量 > `config.json` > `DeepSeek`
- **`start`** —— 开工清单：`expandOnPyChanges` / `expandOnDocsOnly` / `timeoutSeconds` / `showTodoCount` / `checklist`
- **`start-checklist.md`** —— 四问/五思写在文件里（`##` 是分组、`>` 是不打印的说明），可换成自己的规则
- **`selftest.legacy`** —— 35 个老脚本的白名单（它们不需要 `--selftest`）
- **`backup.targets`** —— 备份目标：配 1 个就备一份，配 N 个备 N 份，空则回落默认两个
- **`backup.exportDir`** —— 导出去向，默认 `workspace/memory-export`
- **`paths`** —— 本机设施（归档 / 快照 / 历史 / 日志）。**没配就跳过，不算故障**
- **`tools`** —— 6 个工具逐个开关，不配=全开
- **`skipIf`** —— `module.json` 的 `commands` 可声明「什么环境下不该跑」（目前 `ci`）

**生效方式**：Python 脚本**立即生效**（每次子进程重读）；
`lib/index.js` **要重启宿主**——这是已知缺陷，见 issue #16。

### 工具链

- **B 方案：白名单外的脚本必须自带 `--selftest`**
  - `config.json` 的 `selftest.legacy` 登记 35 个老脚本
  - 冒烟会跑 `--selftest` 并验**输出里有没有「自测」字样**
    （只看退出码会让不认参数的脚本蒙混过关）

### 修复

- **`memory-daily` 漏了「结论：」行** —— 压缩输出时删掉的，有 todo 时冒烟会判失败
- **冒烟结果行的总数** —— 改用 `passed + failed`；原来用 `len(CHECKS)`，白名单外脚本执行两次时账对不上
- **`mem.py` 缺 `import os`** —— 算相对路径时 `NameError` 被 `except Exception` 吞掉，静默退回绝对路径
- **`paths.py` 的 workspace 标志物撞全局目录** —— `.dsh-meow` 命中 `~/.dsh-meow`（meow-memory 的状态目录）、
  `AGENTS.md` 命中 `~/.dsh/AGENTS.md`（全局约定）。**改成只认「装着库的」 `.dsh-meow/memory.db`**
- **`lib/index.js` 没传 `DSH_MEMORY_WORKSPACE`** —— Python 侧从 `__file__` 往上找，算出错误的根
- **`lib` 的 `findWorkspace()` 往上找是死路** —— 插件在 profile、工作区在别处，没有上下级关系。
  改成 `cwd` → 往上找 → `~/.dsh-meow/window-index.json` 三级兜底
- **`mem.py` 丢掉 `module.json` 的 `args`** —— `mem.py clear` 跑成了不带 `--clear-errors` 的脚本，
  **只打印告警、根本没清**
- **测试污染生产日志** —— 「损坏库」那组把 342 条假异常写进了 `state/errors.jsonl`；
  改成写自己的临时目录
- **「有警告」被记 FAIL** —— `daily` / `quality` / `integrity` 有 todo 时故意返回 1，
  但 `lib` 只看退出码。改成**只要 stdout 里有「结论：」就算跑完了**
- **`audit` 只看前 40 条** —— 74 条建议里后面的看不见，加 `--all`

### 文档

- **新增 `docs/CONFIG.md`**（写给 AI 的可配置项说明）：六段的默认值、生效方式、用户会怎么问。
  `mem_check help` 里也加了摘要 —— **AI 第一次运行就能知道有这些可配置**，不用读源码、不用猜。
- **新增 `docs/ROADMAP.md`**：施工图；**权威入口是 GitHub issue #8~#16**（状态可查、可关闭）。
- **新增 `tests/README.md`**：四个测试脚本各管什么、怎么跑、三条约定（结论行 / 自己的日志目录 / 不写死数量）。
- **README 写清与 `meow-memory` 的分工**：它管「记忆怎么活」，本插件管「记忆健不健康」。
- **`AGENTS.md` 加 §6.0 日常入口**：`mem.py daily` 这一层，不用记脚本路径。
- **文档归位**：`CONFIG.md` / `DEVELOPING.md` / `ROADMAP.md` 移进 `docs/`（插件根 12 文件 → 9）。


## [0.2.0] - 2026-11-23

### 修复

- **`check-memory-refs` 的永久假红**：原来把记忆正文里的**模板占位符**当成真引用
  （`tools/xxx.py`、`docs/<名字>.md` 这类），报了永远修不好。现在跳过 `xxx` / `*` / `<` 的项。
  修完：46 个引用、**0 个失效**。
- **三条记忆里的 `proxy-control.py` 路径写错**（记成了 `tools/` 下，实际在工作区根目录）：
  已改正措辞。其中一条本身就是在讲"别写成 tools 下的路径"，改成了不出现完整路径的描述。

### 说明

- 「归档条目的旧路径不再报警」这条其实 **2026-11-19 就改好了**（`load(status="active")`），
  只是 CHANGELOG 待办忘了勾——本次一并确认。

---

## [0.1.0] - 2026-11-23

首次纳入版本管理（Git）。功能与架构是此前陆续建成的，此次作为一个基线版本。

### 功能

**记忆库维护**
- 去重（`memory-dedup`）、衰减（`memory-decay`）、变更日志（`memory-changelog`）
- 体检（`memory-health`）、审计（`memory-audit`）、日报（`memory-daily`）

**救生圈（不依赖插件即可运行）**
- `memory-export`：把整个记忆库导出为格式无关的 Markdown + JSON
- `memory-restore`：从导出重建库（`--verify` 演练，拒绝覆盖活库）
- 两者自包含，插件坏掉时从归档拷出来照样能跑

**索引与图谱**
- `memory-index`（按 project/层分组，一条一行）
- `memory-timeline`（按天）、`memory-map`（topic 为枢纽）、`memory-map-export`（全量快照）

**检查类**
- `check-agents`（28 项：本文件声明的任务/路径是否真实存在）
- `check-memory-refs`（扫记忆里引用的 `tools/ docs/ art/` 路径是否存在）
- `check-agents-memory`（AGENTS 规则 ↔ 记忆库对照）
- `memory-signal-check`（importance 越级）、`memory-source-check`（提到他人但没标来源）
- `memory-weight-check2`、`memory-promises`（带期限的约定）、`memory-archive-check`

**检索类**
- `memory-expand`（1 跳关系展开）、`memory-hipporag`（多跳 PageRank）
- `memory-file-search`（直接检索源文件）

### 架构

- **Python 自包含**在 `py-core/` + `modules/`；`lib/index.js` 只做工具注册与转发
- **契约层** `py-core/mem_db.py` 统一库访问，其他脚本不得直连 SQLite（`export`/`restore` 除外，见「救生圈」）
- `py-core/decay.py`、`py-core/text.py` 收拢此前散落多处的重复逻辑（衰减公式曾 3 处不一致）
- `modules/` 分 **feature**（check/maint/query）/**observe**（status/alert）/**backup**（rescue）三层

### 工程约定

- 脚本路径不写死相对层数，**向上找标志物**（`py-core/` 存在即项目根）
- 计划任务用 `pythonw.exe` 启动，避免每次弹窗
- 改工具后必须**全量测试**：正常 + 异常 + 边界，缺数据的自己造

---

## 待办（下次动这个插件时）

- [x] ~~检查类工具「会不会一直红」的自检~~ ✅ 2026-11-23（见 0.2.0）
- [ ] **注入相关度门槛**：在 `meow-memory` 那边（不是本插件）的 `keywordHitScore` 只判 `raw > 0`，
      一个泛词命中就注入。本插件帮不上，记在这里以免混淆。
- [ ] **关键词质量**：本插件不生成关键词（`memory_remember` 走宿主侧），质量取决于调用者怎么写。
- [ ] **两条「本机环境」记忆内容重复**：`0mwta8rgx` 与 `0mwta90vs` 都是"五条环境要点"，
      择一保留、另一条归档。