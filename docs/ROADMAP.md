# ROADMAP · 待办与下一步

> **这个文件是施工图，权威入口是 GitHub issue**（状态可查、可关闭、有编号）。
> **这个文件是待办的单一来源。** 记忆库里的 todo 会散落、会过期，这里集中一份方便查。
> 完成一项就划掉并在 `CHANGELOG.md` 记一句；不要留着"已完成还挂着"。

---

## 一、等设置页面一起做（B 方案 UI）

**背景**：`config.json` 已经有六段可配置（`agent` / `start` / `selftest` / `backup` / `paths` / `tools`），
但**用户看不见它们**，而且**部分配置要重启才生效**。

- [ ] **[#15](https://github.com/scrapfox149/dsh-memory-maint/issues/15)** **首次安装说明界面**
  第一次装插件时弹一次，**给"安装了插件的 AI"看**（不只是用户）——
  让 AI 知道"有这些可配置项"，从而**主动告诉用户**。
  *用户原话：「写一个第一次安装插件会弹出的说明界面，来让安装了插件的AI看见，让它告诉用户有这些可配置」*

- [x] ~~**[#16](https://github.com/scrapfox149/dsh-memory-maint/issues/16)** 模块启用要即时生效~~ ✅ 2026-11-25（disposer + 1 秒轮询 + 自写流水）
- [x] ~~ **设置页面本身**~~ ✅ 2026-11-25
  机制：`client.inject: ['settings']` + `lib/client.js`，把 `config.json` 的六段做成表单。
  *说明界面和设置页面是同一套 UI 机制，先做设置页，说明界面顺势就有。*

**验收标准**：改任何配置 → **不用重启** → 下一次工具调用就生效。

---

## 二、查询能力增强（[#8–#13](https://github.com/scrapfox149/dsh-memory-maint/issues?q=is%3Aissue)）

| # | 动作 | 说明 | 依赖 |
|---|---|---|---|
| [8](https://github.com/scrapfox149/dsh-memory-maint/issues/8) | **`history`** | 记忆的变更史（谁改的、什么时候、改了哪） | 数据源 `editHistory_infoFrom` 里的 `reflect-update-<session>-turnRange(a,b)` |
| [9](https://github.com/scrapfox149/dsh-memory-maint/issues/9) | **`conflict`** | 矛盾候选（同项目、关键词重叠高、内容相反） | 只筛不判，交人复核 |
| [10](https://github.com/scrapfox149/dsh-memory-maint/issues/10) | **`recall`** | 按时间窗口召回（"上周我记了什么"） | — |
| [11](https://github.com/scrapfox149/dsh-memory-maint/issues/11) | **`stale`** | 重要但久未更新（`importance>=3` 且 `updated_at` 很旧） | 和 `decay` 区分：decay 看"是否该退场"，stale 看"是否该更新" |
| [12](https://github.com/scrapfox149/dsh-memory-maint/issues/12) | **`--json`** | 给所有查询动作加结构化输出 | 目前只有 `mem.py list --json` |
| [13](https://github.com/scrapfox149/dsh-memory-maint/issues/13) | **`project` 子类过滤** | `--decisions` / `--quotes` / `--todo` | `project` 层本来就有 `subcategory` 列 |

---

## 三、长期（低优先级，等条件出现再做）

- [ ] **#14 多库支持**
  现在写死一份 `memory.db`。**等第二个记忆库真的出现再做**——
  现在只做检测（`mem_status` 里报"当前库路径"），**不预先抽象 `Backend` 接口**（抽象了没人用就是负担）。

---

## 四、已完成

### 2026-11-25

- **#16 模块启用即时生效** —— `ctx.tools.register()` 返回的 disposer + 1 秒轮询 `config.json`；
  宿主 logger 会去重，所以自己写一份 `tool-sync.log`
- **#13 `project` 按子类过滤** —— `--decisions` / `--quotes` / `--todo`（可组合）
- **`mem_query assets`** —— 项目资产清单（新命令，不在原 issue 里）
- **`--json` 6 个动作**（#12 已做 7/8，差 `file`，等能力下沉时一起）

### 2026-11-24

- ✅ **6 个工具 / 35 个动作**（删了 `mapexport`，`help` 里分常用/低频）
- ✅ **六段可配置**：`agent` / `start` / `selftest` / `backup` / `paths` / `tools`
- ✅ **恢复文档模板化**（`{{AGENT_NAME}}` / `{{ARCHIVE}}` / `{{BACKUP}}` 等占位符，备份时渲染）
- ✅ **测试 35/35 + 42/42**（15 组极限场景）
- ✅ **修 6 个真 bug**：路径标志物 / 环境变量未传 / 往上找是死路 / `mem.py` 丢 `args` / 测试污染日志 / 有警告被记 FAIL

---

## 五、怎么用这个文件

- **加待办**：写进对应小节，**一句说清"要做什么 + 为什么"**
- **做完了**：划掉 → 在 `CHANGELOG.md` 记一句 → 从记忆库把对应 todo 标 `stale`
- **优先级**：这个文件的顺序就是优先级顺序
