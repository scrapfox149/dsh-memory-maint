# 变更日志

本插件自 2026-11-23 起纳入 Git 版本管理。此前的改动只记在记忆库与 AGENTS.md 里，
下面按时间顺序补录，**不保证完整**——只列有据可查的部分。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

---

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