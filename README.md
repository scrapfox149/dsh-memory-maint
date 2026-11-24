# dsh-memory-maint

给 **DSH 记忆库**做维护的一套工具：**体检、去重、衰减、检索、备份**。

> 30 个 Python 脚本 / 3329 行 · 6 个 MCP 工具 / 31 个动作
> 逻辑全在 Python，Node 层只做工具注册与转发。

---

## 为什么做这个

记忆库就是一个 SQLite 文件，跑久了会积出这些问题：

- 同样的内容被记了好几遍
- 该褪色的旧条目还占着检索位
- 记忆里引用的文件路径早就没了
- 重要性标得不对（该 4 的标成 1，或者反过来）
- 有约定带了期限，到点了没人提醒

一条条手动查太慢。所以做成一套**跑一条命令就出结论**的工具。

## 一眼看效果

`mem_check`（不传参数就是日常体检）：

```
=== 日常体检（memory.db）===

今天该做的（1 件，按优先级）：
  🔗 2 个文件引用失效
     → 跑 `mem_check refs` 看是哪些记忆指向了不存在的文件

不用管的：
  · audit 建议修 28 条 —— 都是「偏长」这类，不影响检索
  · 告警里的降级 60 条 —— 缺列补 None，是正常现象
  · signal 26 条 —— 长文没命中信号词表，多数是语义重要但措辞不同

其他：插件自检 模块 6 / 本次无新异常

结论：⚠ 1 件事要做
```

**刻意分成三区**：该做的 / 不用管的 / 其他。
把"提醒"和"问题"分开，避免报警疲劳——**修不好的东西不进日报，否则人会对警告脱敏**。

## 六个工具

| 工具 | 动作数 | 做什么 |
|---|---|---|
| **`mem_check`** | 13 | **日常体检（不传 action 就是它）**、审计、健康、引用检查、约定提醒、规则一致性 |
| `mem_maint` | 8 | 去重、衰减、变更日志、索引、时间线、图谱 |
| `mem_query` | 5 | 关系展开（1 跳）、多跳检索、全文搜索、导出 |
| `mem_alert` | 2 | 看 / 清错误告警 |
| `mem_status` | 1 | 插件自检（模块发现、契约层、库连通） |
| **`mem_backup`** | 2 | **导出 / 恢复（救生圈）** |

忘了动作名就跑 `mem_check(action="help")`。

## 架构

```
lib/index.js          控制层：发现模块 + 注册工具，不含任何业务逻辑
modules/
  feature/            逻辑层
    check/              mem_check   13 动作
    maint/              mem_maint    8 动作
    query/              mem_query    5 动作
  observe/            观察层
    alert/              mem_alert    2 动作
    status/             mem_status   1 动作
  backup/             救生层（有意自包含）
    rescue/             mem_backup   2 动作
py-core/              基础层
  mem_db.py             连库 / 探列 / 缺列补 NULL / 状态计数 / 写日志
  decay.py              衰减公式（max(0) 写死，以后不可能漏）
  text.py               分词 / Jaccard / 关键词集合
  out.py                输出格式（title / section / item / action）
```

**层间规矩**

- 控制层只认 `module.json`，**不知道任何业务逻辑**
- 逻辑层不许依赖观察层
- 基础层谁都能用，它不依赖任何人
- **救生层有意自包含**：不依赖契约层，插件整个坏掉也能跑

## 设计原则

1. **一个职责只有一份实现** —— 衰减公式曾经散落在三个脚本里、三种写法，一天内出过两次不一致；现在收在 `py-core/decay.py`，改一处就够
2. **调用单行道**：Node → Python，Python 不回调
3. **数据通路唯一**：所有库访问走 `py-core/mem_db.py`（`export`/`restore` 例外，见下条）
4. **保命工具不依赖被保对象**：`memory-export` / `memory-restore` 自包含，随备份归档一起存，插件坏了也能从导出重建整个库
5. **检查不能「永久红」**：修不好的问题（比如已归档条目里的旧路径）不进日报

## 状态

- 30 个 Python 脚本 / 3329 行
- 冒烟测试 **30/30**
- 已装进 desktop profile

## 开发

改代码前先读 [`DEVELOPING.md`](./DEVELOPING.md) —— 里面有架构细节、加东西的流程、测试清单，**和十三个踩过的坑**。

版本历史见 [`CHANGELOG.md`](./CHANGELOG.md)。

## 安装

**前置**：先装 [`meow-memory`](https://github.com/Phant0Meow/dsh-meow-memory)——本插件维护的是它的库。

### 1. 登记到 profile

编辑 `~/.dsh/profiles/desktop/package.json`，两处都要加：

```json
{
  "dependencies": {
    "dsh-memory-maint": "file:./node_modules/dsh-memory-maint"
  },
  "dsh": {
    "profile": {
      "bundles": ["dsh-memory-maint"]
    }
  }
}
```

> ⚠️ **必须用 `file:` 协议**。写成版本号（如 `"0.2.0"`）会被当成 registry 包，pnpm 去 npm 上找、
> 找不到，**整个 `pnpm install` 失败**——而且症状看起来像"新插件有问题"，实际是这条埋的雷。

### 2. 让改动生效

| 改了什么 | 怎么生效 |
|---|---|
| Python 脚本（`py-core/`、`modules/`） | **下次调用即生效**（每次都是新进程） |
| `lib/index.js` | **必须重启宿主**（desktop 版只能人工重启） |

### 3. 验证

调 `mem_status`（不传参数），应该看到：

```
模块 6 个 / 脚本 30 个
  ✅ backup   rescue   mem_backup   命令 2 / 脚本 2
  ✅ feature  check    mem_check    命令 13 / 脚本 13
  ...
```

看不到这行就是没装好——**别用"没报错"当装好了**。

## 依赖

- **`meow-memory`**（记忆库本体）—— 本插件的全部工具都读写它管理的那份 SQLite；
  没有它，这套维护工具**没有对象可维护**。两者是「库」与「维护工具」的关系，不是替代关系
- Python 3.10+（默认取宿主运行时自带，可用 `DSH_MEMORY_PYTHON` 覆盖）

## 许可

MIT
