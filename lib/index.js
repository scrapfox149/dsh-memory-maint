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
import { readdirSync, readFileSync, existsSync, appendFileSync, mkdirSync, statSync } from 'node:fs';
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

// 日志统一写工作区那份（否则工具写 node_modules 副本、命令行写工作区，两份分裂）
const WORKSPACE_STATE = process.env.DSH_MEMORY_LOG_DIR
  || join(WORKSPACE, 'tools', 'dsh-memory-maint', 'state');
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
          // 2026-11-24：**必须把工作区显式传给 Python**。
          // 插件装在 profile 里（~/.dsh/profiles/desktop/node_modules/...），
          // py-core/paths.py 的 workspace_root() 从 __file__ 往上找标志物，
          // 从那里往上会先撞见 ~/.dsh 或 ~/.dsh-meow，算出错误的根，命令直接报「记忆库不存在」。
          DSH_MEMORY_WORKSPACE: WORKSPACE,
          DSH_MEMORY_LOG_DIR: WORKSPACE_STATE,
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

export function apply(ctx) {
  const mods = loadModules();
  let registered = 0;
  for (const mod of mods) {
    if (!mod.tool) continue;
    try {
      ctx.tools.register(buildTool(mod));
      registered += 1;
    } catch (e) {
      ctx.logger?.warn?.(`dsh-memory-maint: 注册 ${mod.tool} 失败 ${String(e)}`);
    }
  }
  const byLayer = mods.reduce((a, m) => ((a[m.layer] = (a[m.layer] || 0) + 1), a), {});
  ctx.logger?.info?.(`dsh-memory-maint: ${registered}/${mods.length} 个模块已注册（` + JSON.stringify(byLayer) + '）');
}
