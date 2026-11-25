/**
 * dsh-memory-maint — 记忆库维护插件主入口
 *
 * 设计（2026-11-17 定）：
 *   ① 逻辑只有一份，在 Python（modules/xxx/py/ 与 py-core/），本文件不实现任何业务算法
 *   ② 本层只做三件事：发现模块 → 注册工具 → 调 Python 并把 stdout 变成工具结果
 *   ③ 调用是单行道 Node → Python；Python 不回调本层
 *   ④ 数据通路唯一：Python 侧一律走 py-core/mem_db.py 契约层
 *
 * 加新模块 = 在 modules/ 下加一个目录 + module.json，本文件不用改。
 */
import { execFile } from 'node:child_process';
import { readdirSync, readFileSync, writeFileSync, existsSync, appendFileSync, mkdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { homedir } from 'node:os';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..');

/**
 * 找工作区根。
 * 优先级：环境变量 → 向上找「装着库的 .dsh-meow」→ 退回插件目录。
 *
 * 2026-11-24 踩过的两个坑（标志物选错，从 profile 往上找会撞上全局目录）：
 *   - `.dsh-meow` 目录   → 命中 `~/.dsh-meow`（meow-memory 的**全局状态目录**，不是工作区）
 *   - `AGENTS.md`       → 命中 `~/.dsh/AGENTS.md`（**全局约定**，也不是工作区）
 * 只有「有 memory.db 的 .dsh-meow」才唯一标识一个记忆工作区。
 * 另外标志物里**不能有 py-core**——它就在插件目录里，会先命中自己。
 */
/**
 * 从 meow-memory 的 window-index.json 里猜工作区。
 * `~/.dsh-meow/window-index.json` 记录 `sessionId -> workspace`，取出现最多的那个。
 * ⚠ 这是 meow-memory 的文件，格式可能变——所以**只在最后兜底**，并且失败就当没找到。
 */
function workspaceFromWindowIndex() {
  try {
    const p = join(homedir(), '.dsh-meow', 'window-index.json');
    if (!existsSync(p)) return null;
    const m = JSON.parse(readFileSync(p, 'utf8'));
    const counts = new Map();
    for (const ws of Object.values(m)) {
      if (typeof ws !== 'string') continue;
      if (!existsSync(join(ws, '.dsh-meow', 'memory.db'))) continue;   // 只认真装库的
      counts.set(ws, (counts.get(ws) || 0) + 1);
    }
    let best = null, bestN = 0;
    for (const [ws, n] of counts) if (n > bestN) { best = ws; bestN = n; }
    return best;
  } catch (e) {
    return null;
  }
}

function findWorkspace() {
  // ① 环境变量（最快、最明确）
  const env = process.env.DSH_MEMORY_WORKSPACE;
  if (env) return env;

  // ② 宿主进程的 cwd（如果宿主恰好是从工作区启动的）
  try {
    const cwd = process.cwd();
    if (existsSync(join(cwd, '.dsh-meow', 'memory.db'))) return cwd;
  } catch (e) { /* 拿不到就往下走 */ }

  // ③ 从 ROOT 往上找（只认「装着库的 .dsh-meow」）
  let dir = ROOT;
  for (let i = 0; i < 8; i += 1) {
    if (existsSync(join(dir, '.dsh-meow', 'memory.db'))) return dir;
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }

  // ④ meow-memory 的 window-index（最后兜底：它是别人的文件，格式可能变）
  const fromIndex = workspaceFromWindowIndex();
  if (fromIndex) return fromIndex;

  return ROOT;
}
const WORKSPACE = findWorkspace();

// 读插件根的 config.json（2026-11-24：用户提「备份救生部分也要让人可以控制」——
// 我们这边路径是写死的，别人那边没有 memory-export/ 这类目录）。
// 救生脚本**保持自包含**（它们只认环境变量，不读 config.json），
// 所以由这里把配置翻译成环境变量传下去。
/**
 * 配置文件路径 —— **工作区优先，插件根兜底，并做一次性迁移**。
 *
 * 2026-11-25 实测的坑：`config.json` 原来打进包里（`package.json` 的 `files` 有它），
 * 而升级 = 删旧包目录 + 装新包 → **用户改过的 `agent.name` / `backup.targets` / `paths`
 * 会被包里的版本覆盖**（实测：改过的名字变回打包者机器上的名字）。
 * 结论：**配置必须跟着用户走，不能跟着包走**。
 *
 * 老用户（0.4.0 及以前）的配置在插件根，那份会被升级删掉，
 * 所以这里**把它复制到工作区**（只做一次；工作区已有就不动）。
 */
function configPath() {
  const ws = join(WORKSPACE, 'tools', 'dsh-memory-maint', 'config.json');
  if (existsSync(ws)) return ws;
  const inPlugin = join(ROOT, 'config.json');
  if (existsSync(inPlugin)) {
    // 一次性迁移：老配置搬到工作区（失败就算了，照旧读插件根那份）
    try {
      mkdirSync(dirname(ws), { recursive: true });
      writeFileSync(ws, readFileSync(inPlugin, 'utf8'), 'utf8');
      return ws;
    } catch {
      return inPlugin;
    }
  }
  return inPlugin;      // 都没有 → 返回它，loadPluginConfig 会当"没有配置"用默认值
}

function loadPluginConfig() {
  try {
    const p = configPath();
    if (!existsSync(p)) return {};
    return JSON.parse(readFileSync(p, 'utf8'));
  } catch (e) {
    return {};   // 配置坏了就当没有，不影响工具可用
  }
}

// 日志统一写工作区那份（否则工具写 node_modules 副本、命令行写工作区，两份分裂）
const WORKSPACE_STATE = process.env.DSH_MEMORY_LOG_DIR
  || join(WORKSPACE, 'tools', 'dsh-memory-maint', '.local', 'state');
const MODULES_DIR = join(ROOT, 'modules');

// Python：优先环境变量，否则宿主运行时自带的解释器（拼在用户主目录下，不写死用户名）
const PY =
  process.env.DSH_MEMORY_PYTHON ||
  join(homedir(), '.dsh', 'dsh-runtimes', 'dsh-next-primary-runtime', 'dependencies', 'python', 'python.exe');

/** 记一条运行流水到 state/runtime.log（失败静默，不影响主流程） */
function logRun(script, ok, elapsedMs, note = '', extra = '') {
  try {
    const dir = WORKSPACE_STATE;   // 统一写工作区那份（不再用 ROOT/state，那是 node_modules 副本）
    mkdirSync(dir, { recursive: true });
    const d = new Date();
    const pad = n => String(n).padStart(2, '0');
    const ts = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
               `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    const line = `${ts} | ${script.slice(0, 26).padEnd(26)} | ${ok ? 'OK  ' : 'FAIL'} | ` +
                 `${String(Math.round(elapsedMs)).padStart(6)}ms | ${String(note).slice(0, 80)}` +
                 (extra ? ` args=${String(extra).slice(0, 40)}` : '') + '\n';
    appendFileSync(join(dir, 'runtime.log'), line, 'utf8');
  } catch {}
}

/** 跑一个 Python 脚本，返回 {ok, out, err} */
function runPython(scriptPath, args = [], timeoutMs = 180000) {
  return new Promise((resolve) => {
    const start = Date.now();
    // 2026-11-25：**每次跑脚本时重新读配置**，不在模块加载时缓存。
    // 否则改了配置还得重启宿主，和 #16「能改但要重启 = 半个功能」是同一个病。
    const cfg = loadPluginConfig();
    const exportDir = cfg?.backup?.exportDir;
    execFile(
      PY,
      [scriptPath, ...args],
      {
        timeout: timeoutMs,
        encoding: 'utf8',
        maxBuffer: 8 * 1024 * 1024,
        env: {
          ...process.env,
          PYTHONIOENCODING: 'utf-8',
          // py-core 里放契约层 mem_db.py，各模块脚本要能 import 到它
          PYTHONPATH: join(ROOT, 'py-core') + (process.env.PYTHONPATH ? ';' + process.env.PYTHONPATH : ''),
          // 2026-11-24：必须把工作区显式传给 Python。
          // 插件装在 profile 里（~/.dsh/profiles/desktop/node_modules/...），
          // py-core/paths.py 的 workspace_root() 从 __file__ 往上找标志物，
          // 从那里往上会先撞见 ~/.dsh 或 ~/.dsh-meow，算出错误的根，命令直接报「记忆库不存在」。
          DSH_MEMORY_WORKSPACE: WORKSPACE,
          DSH_MEMORY_LOG_DIR: WORKSPACE_STATE,
          // 备份导出目录可配：config.json 的 backup.exportDir（空 = 用默认 workspace/memory-export）。
          // 救生脚本只认这个环境变量，不直接读 config.json——保持"插件坏了也能跑"的自包含性。
          ...(exportDir ? { DSH_MEMORY_EXPORT_DIR: String(exportDir) } : {}),
        },
      },
      (err, stdout, stderr) => {
        const elapsed = Date.now() - start;
        const outText = (stdout || '').trim();
        // 2026-11-24：**「有警告」不等于「跑崩了」**。
        // memory-daily / quality / integrity 这类检查脚本，有该做的事时**故意返回 1**
        // （好让计划任务知道"今天有事"）。但它们会把「结论：」打出来——那才是"跑完了"的信号。
        // 之前只看 err（退出码非 0）就判 FAIL，runtime.log 里全是假的 FAIL。
        const hasConclusion = outText.includes('结论：');
        const reallyFailed = !!err && !hasConclusion;
        const note = reallyFailed
          ? String(err.message || err).slice(0, 80)
          : (hasConclusion && err ? '有警告（退出码非 0，但输出完整）' : '');
        logRun(scriptPath.split(/[\\/]/).pop() || scriptPath,
               !reallyFailed, elapsed, note, (args || []).join(' '));
        resolve({
          ok: !reallyFailed,
          out: outText,
          err: (stderr || '').trim() || (reallyFailed ? String(err.message || err) : ''),
        });
      },
    );
  });
}

/** 分层扫描 modules/<层>/<模块>/module.json —— 加模块不用改本文件 */
// 层名不再硬编码：自动扫描 modules/ 下的子目录（2026-11-18 修）
// 加新层 = 建目录，本文件不用改。注册顺序按目录名排序，feature 恰好在前。
function discoverLayers() {
  if (!existsSync(MODULES_DIR)) return [];
  return readdirSync(MODULES_DIR)
    .filter((d) => {
      const p = join(MODULES_DIR, d);
      try {
        return statSync(p).isDirectory() && d !== '__pycache__';
      } catch {
        return false;
      }
    })
    .sort();
}

function loadModules() {
  if (!existsSync(MODULES_DIR)) return [];
  const out = [];
  for (const layer of discoverLayers()) {
    const base = join(MODULES_DIR, layer);
    if (!existsSync(base)) continue;
    for (const dirName of readdirSync(base)) {
      const mf = join(base, dirName, 'module.json');
      if (!existsSync(mf)) continue;
      try {
        const meta = JSON.parse(readFileSync(mf, 'utf8'));
        out.push({ ...meta, dirName, layer });
      } catch (e) {
        // 单个模块清单坏了不该拖垮其他
      }
    }
  }
  return out;
}

/** 把一个模块变成一个工具定义 */
function buildTool(mod) {
  const actions = Object.keys(mod.commands || {});
  const firstAction = actions[0];
  return {
    name: mod.tool,
    description: `${mod.description}\n可用动作：${actions.join(' / ')}`,
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        action: {
          type: 'string',
          enum: actions,
          description: `要执行的动作，默认 ${firstAction}`,
        },
        args: {
          type: 'array',
          items: { type: 'string' },
          description: '透传给该动作的额外参数（如关键词、--days 30）',
        },
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          ok: { type: 'boolean' },
          action: { type: 'string' },
          output: { type: 'string' },
          error: { type: 'string' },
        },
      },
      render: (_a, v) => {
        const parts = [];
        if (v.error) parts.push(`执行失败：${v.error}`);
        if (v.output) parts.push(v.output);
        return [{ type: 'text', text: parts.join('\n') || '（无输出）' }];
      },
    },
    async execute(args) {
      const action = args?.action || firstAction;
      const cmd = (mod.commands || {})[action];
      if (!cmd) {
        return { ok: false, action, error: `未知动作：${action}` };
      }
      // commands 支持两种写法（2026-11-18）：
      //   "clear": "py/x.py"                         —— 纯脚本路径
      //   "clear": {"script":"py/x.py","args":[...]} —— 带预设参数
      // 后者用来区分"同一脚本不同动作"（如 alert 的 list / clear）
      const script = typeof cmd === 'string' ? cmd : cmd.script;
      const presetArgs = (typeof cmd === 'object' && Array.isArray(cmd.args)) ? cmd.args : [];
      const scriptPath = join(MODULES_DIR, mod.layer || 'feature', mod.dirName, script);
      if (!existsSync(scriptPath)) {
        return { ok: false, action, error: `脚本不存在：${script}` };
      }
      const extraArgs = Array.isArray(args?.args) ? args.args : [];
      const r = await runPython(scriptPath, [...presetArgs, ...extraArgs]);
      // 返回值必须是"无损 JSON"：undefined 会让宿主报
      // "value is not lossless JSON"（2026-11-18 踩过）。用 null 或不带该字段。
      const result = { ok: !!r.ok, action, output: String(r.out || "") };
      if (!r.ok) {
        // 2026-11-19 改：脚本常把「用法提示」打到 stdout 再 exit 1，此时
        // err.message 只是 Node 的 "Command failed: ..."，很唬人。
        // 优先用脚本自己的输出当错误信息。
        const own = String(r.out || "").trim();
        const tail = String(r.err || "").trim();
        if (own && own !== tail) {
          result.error = own;
        } else if (tail) {
          result.error = tail;
        }
      }
      return result;
    },
  };
}

// Cordis 依赖注入：不声明 inject，ctx.tools 取不到（会报
// "cannot get property tools without inject"）。meow-memory 也是 ["tools"]。
export const inject = ['tools'];

/**
 * 工具级开关（config.json 的 `tools` 段）+ **即时生效**。
 *
 * 五思（2026-11-25，按 DEVELOPING.md 的要求）：
 *   ① 目的：改 `config.json` 的 tools 段，**不重启宿主**就生效。
 *      用户原话：「模块是否启用应该即时生效，不是吗？」
 *   ② 方案：`fs.watch` 监听 config.json + `ctx.tools.register()` 返回的 disposer
 *      重新评估——变 false 就调 disposer 摘掉，变 true 就重新注册。
 *   ③ 边界：轮询间隔内多次改（只看 mtime，不会漏）、读到坏 JSON（回落全开）、
 *      文件被删（同上）、disposer 不是函数（判 typeof）、
 *      重复注册（Map 记录，先摘再挂）、轮询起不来（降级成"要重启"，不崩）。
 *   ④ 验证：改 tools.mem_maint=false → 不重启 → 日志出现「-1」且工具消失；
 *      改回 true → 不重启 → 日志「+1」且工具回来；写坏 JSON → 不崩、回落全开。
 *   ⑤ 退路：最坏情况退回"改配置要重启"（旧行为），功能不受影响。
 */
function installToolSwitches(ctx) {
  const mods = loadModules();
  /** toolName -> disposer（register 的返回值；不是函数就存 null） */
  const live = new Map();

  // 2026-11-25 用户定：**默认关闭备份**。
  // `mem_backup` 是救生工具（导出/恢复），但**别人的备份路径我们不知道**
  // （默认 targets 为空 → 跑起来什么也不做）。默认关，等用户配好路径自己开。
  const DEFAULT_OFF = new Set(['mem_backup']);

  /** 按当前配置重算"哪些该在"，返回 {added, removed} */
  function syncTools() {
    const toolsCfg = loadPluginConfig()?.tools || {};
    let added = 0;
    let removed = 0;
    for (const mod of mods) {
      if (!mod.tool) continue;
      // 普通工具：不配 = 开（`!== false`）；DEFAULT_OFF 里的：**配了 true 才开**
      const want = DEFAULT_OFF.has(mod.tool)
        ? toolsCfg[mod.tool] === true
        : toolsCfg[mod.tool] !== false;
      const has = live.has(mod.tool);
      if (want && !has) {
        try {
          const disposer = ctx.tools.register(buildTool(mod));
          live.set(mod.tool, typeof disposer === 'function' ? disposer : null);
          added += 1;
        } catch (e) {
          ctx.logger?.warn?.(`dsh-memory-maint: 注册 ${mod.tool} 失败 ${String(e)}`);
        }
      } else if (!want && has) {
        const disposer = live.get(mod.tool);
        if (typeof disposer === 'function') {
          try { disposer(); } catch { /* 摘不掉就留着，下次再试 */ }
        }
        live.delete(mod.tool);
        removed += 1;
      }
    }
    return { added, removed };
  }

  const first = syncTools();
  const off = mods.filter((m) => m.tool && !live.has(m.tool)).length;
  ctx.logger?.info?.(`dsh-memory-maint: 注册 ${live.size} 个工具` +
    (off ? `，按配置停用 ${off} 个` : ''));

  // 轮询配置文件的 mtime —— **不用 fs.watch**。
  // 2026-11-25 实测：fs.watch 在 Windows 上第一次触发之后就再也不触发了
  // （同一个文件被 truncate + write 几次，只有第一次报 change），
  // 导致"改回 true"那次没有任何日志、工具也没回来。
  // 日志不可靠 = 排障时眼睛是坏的，所以换成 1 秒轮询 mtime：
  // 可靠、可控，代价只是每秒一次 stat（可忽略）。
  //
  // 路径必须与 loadPluginConfig 一致（工作区优先）——
  // 否则"改了工作区那份却不生效"，比不监听更迷惑。
  // 2026-11-25 验收时发现的坑：`configPath()` **会随"用户后来在工作区建了配置"而变**。
  // 原来只在启动时算一次 → 启动时工作区没配置（盯的是插件根那个不存在的路径）
  // → 用户后来在工作区建了 config.json，轮询根本不认。
  // 所以：**每次轮询重新算路径**，路径本身变了也算一次变化。
  let lastPath = configPath();
  let lastMtime = 0;
  try { lastMtime = statSync(lastPath).mtimeMs; } catch { /* 文件不存在就等它出现 */ }
  let pollTimer = null;
  try {
    pollTimer = setInterval(() => {
      const cfgPath = configPath();          // ← 每次重新算（可能从插件根切到工作区）
      let m = 0;
      try { m = statSync(cfgPath).mtimeMs; } catch { m = 0; }   // 被删 → 0，下次出现再比
      if (cfgPath === lastPath && m === lastMtime) return;      // 路径和 mtime 都没变 → 不动
      lastPath = cfgPath;
      lastMtime = m;
      const r = syncTools();
      // ① 自己写一份流水（不动宿主 logger）——
      //    2026-11-25 实测：宿主对**内容完全相同**的日志做去重，写成 `log.repeated {"repeats":N}`，
      //    「改回 true」那次（本该是 +1 -0）就这样消失了，只剩 +0 -1 那几条被合并。
      //    日志不可靠 = 排障时眼睛是坏的（用户原话），所以这份自己管。
      try {
        mkdirSync(WORKSPACE_STATE, { recursive: true });
        const d = new Date();
        const pad = (n) => String(n).padStart(2, '0');
        const ts = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
                   `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
        appendFileSync(join(WORKSPACE_STATE, 'tool-sync.log'),
          `${ts} | mtime=${m} | +${r.added} -${r.removed} | 现在 ${live.size} 个\n`);
      } catch { /* 写不了就只靠宿主日志，不影响功能 */ }
      // ② 宿主日志照打（能看见就行；内容带上 mtime，让每次都是新消息，避开去重）
      ctx.logger?.info?.(`dsh-memory-maint: 配置变了 → 工具同步（+${r.added} -${r.removed}，现在 ${live.size} 个，mtime=${m}）`);
    }, 1000);
    pollTimer.unref?.();    // 不阻止进程退出
  } catch (e) {
    // 起不了轮询就降级：改配置仍需重启（旧行为），但不影响已有工具
    ctx.logger?.warn?.(`dsh-memory-maint: 无法轮询 config.json（${String(e)}），改配置仍需重启`);
  }

  return { first, stop: () => { try { pollTimer && clearInterval(pollTimer); } catch { /* ignore */ } } };
}

export function apply(ctx) {
  const mods = loadModules();
  installToolSwitches(ctx);
  const byLayer = mods.reduce((a, m) => ((a[m.layer] = (a[m.layer] || 0) + 1), a), {});
  ctx.logger?.info?.(`dsh-memory-maint: ${mods.length} 个模块已加载（` + JSON.stringify(byLayer) + '）');
}
