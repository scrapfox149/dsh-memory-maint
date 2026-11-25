# 开发与维护规则（docs/DEVELOPING.md）

> 这是 `dsh-memory-maint` 的开发/更新规范。**每次改这个插件前后，照这里逐条对一遍。**
> 最后更新：2026-11-18

---

## 一、架构（三层六模块）

```
dsh-memory-maint/
├── lib/index.js              控制层：只认 module.json，不含业务逻辑
├── modules/
│   ├── feature/              逻辑层（业务）
│   │   ├── check/    mem_check   11 命令
│   │   ├── maint/    mem_maint    8 命令
│   │   └── query/    mem_query    5 命令
│   ├── observe/              观察层（监控）
│   │   ├── alert/    mem_alert    2 命令
│   │   └── status/   mem_status   1 命令
│   └── backup/               救生层
│       └── rescue/   mem_backup   2 命令
├── py-core/mem_db.py         基础层：契约层（唯一读库入口）
├── state/                    日志（runtime.log / errors.jsonl，7 天过期）
├── tests/test-mem-plugin.py        冒烟测试
├── docs/DEVELOPING.md             本文件
└── README.md                 使用说明
```

**层间规矩**：
- 控制层**不许** import 业务逻辑，只读 `module.json`
- 逻辑层**不许**依赖观察层
- 观察层可以依赖基础层
- 基础层谁都能用，它不依赖任何人

---

## 二、加东西怎么做（都不用改代码）

### 加一个命令（到现有模块）
1. 把 `xxx.py` 放进 `modules/<层>/<模块>/py/`
2. `module.json` 的 `commands` 加一行：`"新动作": "py/xxx.py"`
3. 跑冒烟：`python tests/test-mem-plugin.py`

**`skipIf`：命令自己声明「什么环境下不该跑」**（2026-11-24）

有些脚本只在**有本机环境**时才成立（比如 `check-agents` 检查计划任务、`weight2` 读前置快照）。
CI 上跑它们必然失败，但**那不是脚本坏了**。让模块自己声明，而不是写死在测试里：

```json
"agents":  { "script": "py/check-agents.py",         "skipIf": "ci" },
"weight2": { "script": "py/memory-weight-check2.py", "skipIf": "ci" }
```

- **`"ci"`** → 环境变量 `CI` 存在时（GitHub Actions 默认设）跳过
- 冒烟测试读这个字段并**打印跳过原因**（不静默）
- **只影响自动化**（冒烟/CI）；`mem.py` 手动调用**不跳**——你说要跑就跑
- 以后加新脚本要跳过时**只改 `module.json`**，不用动测试代码
- 带 `skipIf` 的命令用**对象写法**（`{"script": ..., "skipIf": ...}`），和 `mem_alert clear` 那种带 args 的格式一致

### 加一个模块
1. 建 `modules/<层>/<新模块>/py/`
2. 写 `module.json`：
   ```json
   {
     "tool": "mem_xxx",
     "description": "...",
     "commands": {
       "do": "py/do.py",
       "带参数的": { "script": "py/do.py", "args": ["--flag", "value"] }
     }
   }
   ```

   **`commands` 支持两种写法**（2026-11-18）：
   - 字符串 = 纯脚本路径
   - 对象 = `{"script": 路径, "args": [预设参数]}` —— 用来区分"同一脚本不同动作"
     （例：`mem_alert` 的 `list` 和 `clear` 指向同一个 `memory-alert.py`，
     靠预设参数 `["--clear-errors","--yes"]` 区分）

   用户调用时传的 `args` 会**追加在预设参数后面**。
3. 脚本放进 `py/`
4. 跑冒烟

### 加一个层
1. 建 `modules/<新层>/<模块>/py/`（**注意：必须是"层/模块/py"三层**，漏了模块层会被自检当成模块）
2. 同上写 `module.json`
3. 跑冒烟

### 脚本写法的硬要求
- **必须**有 `py-core` 向上查找引导（否则直接跑会 import 失败）：
  ```python
  _here = os.path.dirname(os.path.abspath(__file__))
  for _up in range(1, 5):
      _pc = os.path.join(_here, *([".."] * _up), "py-core")
      if os.path.isdir(_pc):
          sys.path.insert(0, _pc)
          break
  ```
- **读库必须走契约层**：`from mem_db import load, fetch`，不许自己 `sqlite3.connect`
  - **唯一例外**：`backup/rescue` 的 export/restore —— **有意自包含**，它们不能在插件坏掉时还依赖契约层
  - 数条目用 `count_status_sql()`（SQL 直数）、取条目用 `fetch()`、要全部属性用 `load()`。**别再自己 connect**
- **`except` 不许裸 `continue`**——必须 `report_exception()` 留痕（否则静默丢数据）
- **只读**：所有脚本默认 `mode=ro`，不许写记忆库

---

## 三、改东西后必须做什么

### 最小检查（改一个脚本）
```bash
python tests/test-mem-plugin.py          # 冒烟：35 项必须全绿
```

### 中等检查（改 module.json / 加命令）
```bash
python tests/test-mem-plugin.py          # 冒烟
python tools/mem.py list           # 确认分组与命令列表
python modules/observe/status/py/memory-status.py   # 自检（mem_status 不在 CLI 分组里）
```

### 完整检查（改架构 / 加层 / 动 lib/index.js）
```bash
python tests/test-mem-plugin.py          # ① 冒烟
python tools/mem.py list           # ② CLI 分组能发现
python modules/observe/status/py/memory-status.py   # ③ 自检
# ④ Node 工具注册（用 node 模拟 apply）
# ⑤ 外部调用链：backup-memory.ps1 等能否跑通
```

> **铁律：一个入口通不算通，五个入口全通才算。**
> 2026-11-18 就栽在这里：自检和冒烟都正常，但 `mem_backup` 根本没注册上（`LAYERS` 硬编码）。

### 上线前
```bash
python tools/backup-memory.ps1     # 备份链路
python tools/mem.py check          # 全局体检 11 项零异常
```

---

## 四、测试清单

| 类型 | 命令 | 通过标准 |
|---|---|---|
| **冒烟** | `python tests/test-mem-plugin.py` | 35/35，无 Traceback |
| **空库** | `python tests/test-mem-plugin.py --db tmp/plugin-lab/empty.db` | 35/35 |
| **缺列库** | 造一个删了列的库再跑 | 28/28 且 `errors.jsonl` 有降级记录 |
| **与旧版对比** | archive 里的原始版 vs 现在，同库跑 | 输出逐行一致 |
| **参数** | `--db` / `--days` / `--top` / 非法值 | 生效 + 非法值报错 |
| **只读** | 跑完看活库 mtime | 没变 |
| **带参调用** | 每个工具用 `execute({action, args})` 带一次参数 | 参数真的传到了脚本（不是跑默认动作） |
| **时间类函数** | **造「N 天前」的数据**（不用等真实时间） | 算出的值与手算一致（如半衰期 N 天 → 0.5） |

**沙箱**：`tmp/plugin-lab/`（`empty.db` + `plugin/` 副本），用 `DSH_MEMORY_DB` 切库。

---

## 五、日志与告警

| 文件 | 谁写 | 内容 |
|---|---|---|
| `state/runtime.log` | `mem.py`、`lib/index.js` | 运行流水（时间/脚本/OK-FAIL/耗时） |
| `state/errors.jsonl` | `mem_db.report_*` | 降级 / 异常 / 数据异常 |

**规则**：
- 写日志**全部包 try/except 静默**——不能因为记日志把正事搞崩
- 运行日志**7 天自动过期**（写日志时顺手清，不依赖计划任务）
- **报错日志不自动清**（排查依据），要 `mem_alert --clear-errors --yes`
- 跨进程只能靠**文件**传递（脚本是独立进程）

---

## 六、救生圈规则（backup 层）

**判据**：**「如果插件整个坏了，这个脚本还应不应该能用？」**
- 应该 → 自包含，并归档
- 无所谓 → 正常进插件

**要求**：
1. **自包含**：不 import `mem_db`、不 import 任何插件模块；路径走"环境变量 > 内建默认"
2. **告警内联**：连报警都要自己写 `errors.jsonl`（不能 import）
3. **随备份归档**：`backup-memory.ps1` 每次把脚本复制到 `archive/tools/`（两处归档）
4. **灾难演练过**：只从归档取脚本 + `memory-export/` 的纯文本 → 能重建整库

---

## 七、踩过的坑（别再踩）

| # | 坑 | 防法 |
|---|---|---|
| 1 | **CRLF** 让字符串替换静默失败（症状：代码看着对、行为不对） | 改 Windows 上的 .py/.ps1 一律 `newline=""` 读 + `[ \t\r]*$` 匹配；改完**跑一次验行为** |
| 2 | **`except: continue` + 查询缺列 = 静默丢数据** | 不许裸 continue；`fetch()` 缺列会补 NULL + 上报 |
| 3 | **移文件不查调用方** → 备份链路静默断 | 移之前 `grep -rn "旧文件名" tools/ *.ps1 *.md` |
| 4 | **`try{}catch{}` 是静默失败高发区** | 至少要 `Say` 一句，别让失败无声 |
| 5 | **正则把 `, fetch` 加到注释后面** → 等于没导入 | 改 import 时确认新内容在 `#` 之前 |
| 6 | **注释里写 `*/`** 会提前结束注释块 | 注释里避免 `*/` |
| 7 | **路径写死相对层数**（`HERE/../../..`） | 改成"向上找标志物"（找 `py-core/` 或 `state/`） |
| 8 | **层名硬编码**（`LAYERS = ['feature','observe']`） | 一律自动扫描 `modules/*/` |
| 9 | **`backup/py/` 少一层** → 被当成模块 | 结构必须是"层/模块/py" |
| 10 | **改完只看"跑通了"不看数字** | 与旧版对比输出，**数字必须一致**（不一致要能解释） |
| 11 | **用假 ctx 测插件**（`{tools:{register}}`） | 假对象里 `tools` 永远在 → **测不出缺 `inject`**。装完必须看宿主日志 |
| 12 | **返回值带 `undefined`** | 宿主报 `value is not lossless JSON`。可选字段要么给值、要么整键不给 |
| 13 | **降级上报不去重** | 一次运行写 20+ 条，跑几次几百条，**真异常被挤出视野**。必须 24h 去重 |
| 15 | **只测「工具能注册 + 无参默认动作」** | 漏掉 `args` 从工具参数 → Node → 命令行的拼接。`restore` 是唯一必须带参的脚本，正好撞在缺口上。**每个工具至少做一次带 args 的真实调用** |
| 14 | **改横切概念靠「我记得」找实现点** | 日志目录改了 **4 次**才全：`mem_db._STATE_DIR` / Node 传的环境变量 / Node 的 `logRun` / **`memory-alert.py` 自己的 `STATE`**。**先 `grep -rn` 列清单，改完再数一遍** |

---

## 八、上线前检查清单

- [ ] `python tests/test-mem-plugin.py` → 35/35
- [ ] `python modules/observe/status/py/memory-status.py` → 一切正常
- [ ] `python tools/mem.py check` → 11 项零异常
- [ ] `python check-memory-refs.py` → 不存在的 0
- [ ] `backup-memory.ps1` → 救生圈同步 4 个 + 产物 mtime 刷新
- [ ] 全局搜一遍旧路径：改过的文件名有没有残留引用
- [ ] **核对文档数字**：README / DEVELOPING 里写的「N 模块 / N 脚本 / N 工具 / N 命令」是否还准？
      （2026-11-18 实测：README 写"三个工具"时实际已是 6 个，命令数也全错）
- [ ] `docs/memory-maintenance-log.md` 记一笔

---

## 九、现状（2026-11-18 上线后）

- **6 模块 / 30 脚本 / 6 工具 / 31 命令 / 4085 行**
- 冒烟 **30/30**、全量 **38/38**（含极端）、自检正常、引用失效 0
- `py-core` 四个公共模块：`mem_db`（数据）/ `decay`（衰减）/ `text`（分词）/ `out`（呈现）
- **✅ 已装进 desktop profile**，宿主日志确认 `6/6 个模块已注册`
- 装的位置：`~/.dsh/profiles/desktop/node_modules/dsh-memory-maint/`（正拷贝）
- 日志：`state/runtime.log` + `state/errors.jsonl`（7 天过期，降级 24h 去重）

---

## 十、性能（2026-11-18 实测）

**契约层不是性能瓶颈**：`fetch()` 与裸 SQL 只差 **1.04x**。

| 操作 | 400 条 | 5000 条 |
|---|---|---|
| `fetch('lesson', 2列)` | 2.2 ms | 11.1 ms |
| 同量裸 SQL | 2.0 ms | 10.7 ms |
| `count_status_sql()`（SQL 直数） | 2.3 ms | **7.9 ms** |
| `count_by_status()`（全量 load 再数） | 5.6 ms | **33.5 ms** |
| `load()` 全量七层 | 5.2 ms | 32.8 ms |

**三条用法**：
- **要几列** → `fetch(tier, cols)` ✅ 最省
- **要数量** → `count_status_sql()` ✅ 比 `count_by_status()` **快 4 倍**
- **要全部属性** → `load()`，但注意它**线性增长**（5000 条约 33 ms）

**什么时候该优化**（现在不用做）：
- 库涨到 **5 万条**以上，`load()` 可能到 300 ms+，那时考虑给 `fetch` 加连接复用或批量接口
- 现在 400 条，全部毫秒级，**不提前优化**

---

## 十一、安装与同步（2026-11-18 上线）

### 装在哪

插件装在 **`~/.dsh/profiles/desktop/node_modules/dsh-memory-maint`**（**正拷贝**，不是软链——插件要能独立存在）。

profile 的 `package.json` 有两处登记：
```json
"dependencies": { "dsh-memory-maint": "0.1.0" },
"dsh": { "profile": { "bundles": [ ..., "dsh-memory-maint" ] } }
```

### 改完代码必须同步

### 同步到 profile（宿主读的那份）

插件装在 `~/.dsh/profiles/desktop/node_modules/dsh-memory-maint` ——
**它是副本，不是链接**（pnpm 的 `file:` 协议），**改完工作区代码不会自动同步**。

```powershell
# 改动少时手动同步（把 sources 换成实际路径）
Copy-Item lib\index.js "$env:USERPROFILE\.dsh\profiles\desktop\node_modules\dsh-memory-maint\lib\index.js" -Force
```

**同步范围**：`lib/ modules/ py-core/ cordis.patch.yml package.json config.json
start-checklist.md README.md CHANGELOG.md LICENSE docs/`

**不同步**：`tests/`（测试不进安装包）、`state/`（运行日志，两边各管各的）、`tmp/`

**⚠ 生效差异（重要）**：
- **Python 脚本**（`modules/` `py-core/`）—— **立即生效**（每次子进程重读）
- **`lib/index.js`** —— **必须重启宿主**（Node 侧在模块加载时读一次）

### 上线/重装步骤

1. **同步到 profile**：按上面那段（手动 Copy-Item，或 `robocopy` 整个目录）
2. **确认 profile 的 `package.json`**：`dependencies` 里是 `file:./node_modules/dsh-memory-maint`，
   `dsh.profile.bundles` 里含它
   - ⚠ **别手改 `bundles`**：`dshm` 会按插件的 `userDisabled` 状态重写，手加的条目会被悄悄移除
   - 要启用/停用，用 `dshm_toggle(pkg, enabled: true/false)`（返回 `applied:live` 即热生效）
3. **重启宿主**（`dshm_restart` 对 desktop 无效，只能人工重启）
4. **重启后验证**：
   - `mem_status`：6 个工具 / 35 个脚本 / 记忆库可读
   - `mem_check daily`：4 行 + 「结论：」
   - `mem_check start`：能读到清单
5. **如果只有 Python 改动**（没动 `lib/`）→ **不用重启**，同步后立即生效

### 回滚

```powershell
copy tmp\profile-backup-20261118\package.json.bak "$env:USERPROFILE\.dsh\profiles\desktop\package.json"
```
再删 `node_modules/dsh-memory-maint` 即可。

---

## 十二、宿主接口契约（2026-11-18 踩两次坑总结）

> 这一节是**上线当天连挂两次**换来的。改 `lib/index.js` 前必读。

### 必须导出 `inject`，否则 `ctx.tools` 取不到

```js
export const inject = ['tools'];   // 缺这行 → "cannot get property tools without inject"
export function apply(ctx) { ... }
```

`ctx.logger` 是**内置**的，不用声明（meow-memory 用 52 次但 inject 里没有）。
其余宿主能力（`ctx.settings` / `ctx.on` / `ctx.effect`）用之前先确认要不要声明。

### 返回值必须是「无损 JSON」

宿主会检查 `JSON.stringify` 结果，**`undefined` 不是合法 JSON**：

```js
// ❌ 会报 "value is not lossless JSON"
return { ok: r.ok, output: r.out, error: r.ok ? undefined : r.err };

// ✅ 可选字段：要么给值、要么整个键不出现
const result = { ok: !!r.ok, action, output: String(r.out || "") };
if (!r.ok && r.err) result.error = String(r.err);
return result;
```

### 形状对照

| 场景 | 返回 |
|---|---|
| 成功 | `{ ok: true, action, output }` |
| 失败 | `{ ok: false, action, error }` |
| `output.render()` | `[{ type: 'text', text }]` |

### 上线前必须这样验（不靠重启）

```js
const mod = await import('file://.../lib/index.js');
const regs = [];
mod.apply({ tools: { register: t => regs.push(t) }, logger: { info(){}, warn(){} } });
// ① 注册数对
// ② 每个工具 execute 成功路径：JSON.stringify 合法、键里没有 undefined
// ③ 每个工具 execute 失败路径（传个不存在的 action）
// ④ 每个工具 output.render() 返回 [{type, text}]
```

**⚠️ 但仍有一类测不出来**：`inject` 缺失在假 ctx 里永远正常（假 ctx 的 `tools` 总在）。
**所以装完必须看宿主日志**：
```bash
grep "dsh-memory-maint" ~/.dsh/logs/desktop-next.log | tail -3
# 要看到 6/6 个模块已注册
```

### 降级/告警要限流

`report_degraded` 已加 **24 小时去重**（同一 `脚本+表+缺列` 只记一次）。
**原因**：`map-export`/`dump-active` 这类全字段脚本每层都缺列，一次运行写 20+ 条，跑几次积几百条，**真异常被挤出视野**。

**以后加新的上报时**：
- 「每次都会发生、本身不是问题」的（缺列、降级、缓存未命中）→ **必须去重/限流**
- 「偶发的真异常」→ 每次都记

### 改「横切概念」先 grep 找全（2026-11-18 踩 4 次的教训）

**横切概念** = 同一个值/路径/策略散落在多个文件里：日志目录、缓存目录、配置路径、超时时间、重试次数。

**事故**：把日志目录从「跟 `__file__` 算」改成「统一工作区」，以为两处，**实际四处**，改了 4 次才通：

| # | 实现点 | 漏了的后果 |
|---|---|---|
| 1 | `py-core/mem_db.py` 的 `_STATE_DIR` | Python 写的日志还在副本 |
| 2 | `lib/index.js` 给子进程传的 `DSH_MEMORY_LOG_DIR` | 子进程读不到 |
| 3 | `lib/index.js` 自己的 `logRun()` | Node 写运行流水还在副本 |
| 4 | **`modules/observe/alert/py/memory-alert.py` 的 `STATE`** | 读日志的脚本读空目录 → 显示「没有报错」 |

**第 4 个最隐蔽**：它**读日志**，自己算目录、**不 import mem_db**，所以前三个都对了它也还是错的。

**规矩**：

```bash
# 改之前：列出所有点
grep -rn "state\|STATE_DIR\|runtime.log\|errors.jsonl" lib/ py-core/ modules/

# 改之后：再数一次，处数对不上就是还有漏的
```

**「我记得这里也用了」是最不可靠的索引，只有 grep 算数。**

---

### 改了代码怎么生效

```powershell
# 1) 同步到 profile（那边是副本，不是链接）
robocopy tools\dsh-memory-maint "$env:USERPROFILE\.dsh\profiles\desktop\node_modules\dsh-memory-maint" /E /XD .git __pycache__ state tmp /XF *.pyc
```

**生效差异**：
- **Python 脚本** → **不用重启**（每次调用都是新子进程，重读文件）
- **`lib/index.js`** → **必须重启宿主**（模块加载时读一次）

---

## 十三、文档同步（2026-11-18 用户要求）

> 用户原话：「**这种说明文件本就应该及时同步最新变化**」

### 什么时候要改文档

| 改了什么 | 要动哪份文档 |
|---|---|
| 加/删/改脚本、模块、命令 | **README 的工具表** + **DEVELOPING 第九章现状** |
| 改架构（加层、改结构） | **两份的目录树** |
| 加新坑 | **DEVELOPING 第七章坑清单** |
| 改安装/同步方式 | **DEVELOPING 第十一、十二章** |
| 任何"数字"（模块数/脚本数/命令数） | **两份都要核对** |

### 数字不要靠记，靠查

```bash
python tools/dsh-memory-maint/modules/observe/status/py/memory-status.py
# 或者用工具：mem_status(action="status")
```

**它报的模块/脚本/命令数才是准的**。手写的数字最容易过时。

### 为什么单独列一章

**2026-11-18 的真实教训**：插件从 5 模块 22 脚本一路改到 6 模块 28 脚本 29 命令，
中途**没人回头改文档**，导致 README 里写着「注册的**三个**工具」、命令数 9/7/4——
**全都错**，而且看起来还很专业，很容易让人（包括我自己）信以为真。

**文档过时比没有文档更危险**——没有文档会去查代码，过时的文档会让人按错的来。

## 发版流程（2026-11-25 定，栽过两次）

**用户原话**：「放在那提醒你以后发版应该是**做完所有确认，测试之后再决定**，而不是**顺手就做掉**」。

### 五步，缺一步都不叫"可以发"

**① 测四层**
```powershell
cd tests
python test-mem-plugin.py      # 冒烟（能跑）
python test-units.py           # 单元
python test-newfeat.py         # 新功能边界
python test-full.py            # 全量极端场景
node switch-test.mjs           # 工具开关
# 以下三个在插件根跑：
python tests/verify-readonly.py   # 不碰用户数据（sha256 不变）
python tests/verify-numbers.py    # 算得对（输出数字 vs 查库）
python tests/verify-design.py     # 像设计（行为符合设计意图）
```

**② 测升级链**（这条最容易漏，也最致命）
```
装旧版 → 改配置（agent.name / backup.targets）→ 升新版 → 配置还在吗？
```
**2026-11-25 的 0.4.0 就是漏了这步**：`config.json` 在包里，升级把它覆盖了。

**③ 验安装后行为**
干净环境装包，验 14 条：工具数（`mem_backup` 默认关 → 5 个）、没有 `config.json`、有 `config.example.json`、`status` / `assets` / `--json` / `start` / `daily` 各命令正常。

**④ 打包验包**
```powershell
node <dsН>/node/bin/node.exe <dsН>/pnpm/bin/pnpm.cjs pack
tar -tzf dsh-memory-maint-X.Y.Z.tgz | ...
```
必须：**无 `__pycache__` / 无 `tests/` / 无 `config.json` / 有 `config.example.json`**。

**⑤ 问用户「发吗」**

**这一步不能省，也不能用"我修完了"代替。**

### 判据
**「我这是'改完了'，还是'可以发了'？」** —— 前者只是第一步，中间隔着上面五步 + 一次用户点头。

### 为什么这条老是违反
发版流程太熟（bump → pack → tag → Release，一条脚本跑完）→ **顺手就做了**。
**熟 → 快 → 跳过判断**。对策：**发版脚本开头先打印"已问过用户吗？"**，别靠记性。

---


---

## 十四、测试三条硬标准（用户 2026-11-19 定）

改任何工具（不只是插件）都按这三条：

### ① 好用度归鱼定

> 用户原话：「我的工具需要让我认为满意，好用，但是**鱼的工具好用标准和程度应该由鱼自己定**」

→ **可以按自己"用起来顺不顺手"主动重构**，不必等用户提需求；但**改完要给前后对比数据**（如 `signal` 42 条 → 16 条），让用户能验证判断是否成立。

### ② 改完必须全量测试

**各种情况 + 极端情况 + 不会遇见和极少遇见的情况都应尽量包含。**

不要只测"正常路径"：
- 正常 → 空库 → 缺列 → 库损坏 → 特殊字符 → 超长 → 极端参数 → 并发/重复
- 工具层：无参调用 + **带参调用** + 失败路径

### ③ 没条件就造，再辅以长期观察

**没有测试条件或缺失测试数据时，自己造测试数据。**

例：`memory-decay` 本是"要等时间流逝"的——造「最后访问是 N 天前」的数据后，**公式部分当场验完**（5/5），只剩"阈值合不合理"留给 2027-05-17 长期观察。

**"能跑"不算通过。** 覆盖常见/极端/罕见，缺数据自己造。

## 十五、输出格式约定（`py-core/out.py`，2026-11-19）

**新脚本请用它**，老脚本不强制改（各自有合理设计）。

```python
from out import title, section, item, action, ok, warn, bad, kv

print(title("日常体检（memory.db）"))
print(section("今天该做的"))
print(item("过期约定 2 条"))
print(action("跑 mem_check promises 看详情"))
print(ok("文件引用 36 个全部有效"))
```

| 元素 | 写法 | 用途 |
|---|---|---|
| 一级标题 | `=== 标题 ===` | 每个工具输出用一次 |
| 二级分区 | `-- 分区名 --` | 分区之间 |
| 条目 | `  · 内容` | 普通列表项 |
| 动作 | `     → 具体命令` | **下一步该干什么**（最重要） |
| 状态 | `  ✅ / ⚠ / ❌ 内容` | 通过/警告/失败 |

**为什么不做成 `modules/observe/output/` 独立层**：它不是"一个模块"，是"每个脚本都会用到的渲染约定"——放 `py-core`（和 `mem_db.py` 并列：一个管数据格式，一个管呈现格式）。

**为什么老脚本不改**：统计后发现真正的"标题不一致"只有 2 个分区标题（`【报错】`），而 `[X]` / `[剩 179 天]` / `[lesson]` 这些是**有意义的条目前缀**，统一成 `·` 反而丢失信息。

## 十六、基础层四个公共模块（2026-11-19）

`py-core/` 里三个「同一逻辑只有一份」的公共模块（外加契约层本身，共四个）：

| 文件 | 管什么 | 谁在用 |
|---|---|---|
| **`mem_db.py`** | **数据**：连库、探列、缺列补 NULL、状态计数、写日志 | 28 个脚本 |
| **`decay.py`** | **衰减**：半衰期、`decay_of`、`days_since`（`max(0)` 已写死） | expand / hipporag / decay |
| **`text.py`** | **分词**：`bigrams` / `jaccard` / `kw_set` | dedup / file-search / hipporag |
| **`out.py`** | **呈现**：title / section / item / action / ok / warn / bad | 新脚本 |

**铁律：同一个量化概念只允许一份实现。**
- 衰减 → 只准用 `decay.decay_of`，**不要在脚本里自己写 `0.5 ** (days/hl)`**
- 分词 → 只准用 `text.bigrams`
- 反例（2026-11-19 两次 bug）：`decay` 用 `exp` 而另两个用 `0.5**`；`decay` 漏了 `max(0)` → 未来时间算出 4.4。**根源都是"同一逻辑多份"**。

**验证方式**：改完存基线（`tmp/baseline/`），改后逐行 diff，**必须完全一致**。

