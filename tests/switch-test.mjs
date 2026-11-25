// 2026-11-25：#16 工具开关即时生效 —— 完整边界测试
//
// 覆盖：
//   ① apply() 初始注册
//   ② 关掉 mem_maint（不重启即摘）
//   ③ 改回来（不重启即挂）
//   ④ 写坏 JSON（不崩、回落全开）
//   ⑤ 删除 config.json（不崩）
//   ⑥ 连续改 5 次（只按 mtime 判，最终状态正确）
//   ⑦ config.json 被整体替换（rename）
//   ⑧ check-memory-refs 的负向后视（不再把插件内 docs/ 当工作区的）
//   ⑨ 自己写的 tool-sync.log 每次变化都留一行（宿主 logger 有去重，靠不住）
//
// 跑法（在插件根）：node tests/switch-test.mjs
//
// 注意：必须把 DSH_MEMORY_LOG_DIR 指到临时目录 —— 插件会往那里写 tool-sync.log，
// 不隔离就会污染生产 .local/state（2026-11-24 踩过测试污染日志的坑）。
// 因为常量在模块加载时算，所以要**先设环境变量再动态 import**。

import { readFileSync, writeFileSync, unlinkSync, existsSync, renameSync, mkdtempSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { tmpdir } from 'node:os'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const CFG = join(ROOT, 'config.json')
const original = readFileSync(CFG, 'utf8')

// 隔离日志目录（必须在 import 之前设）
const stateDir = join(mkdtempSync(join(tmpdir(), 'switch-test-')), 'state')
process.env.DSH_MEMORY_LOG_DIR = stateDir

const { apply } = await import('../lib/index.js')

let pass = 0
let fail = 0
function check(name, ok, detail = '') {
  if (ok) { pass += 1; console.log('  ✅ ' + name + (detail ? '  → ' + detail : '')) }
  else { fail += 1; console.log('  ❌ ' + name + (detail ? '  → ' + detail : '')) }
}

const live = new Map()
const ctx = {
  tools: {
    register(tool) {
      live.set(tool.name, tool)
      return () => live.delete(tool.name)
    },
  },
  logger: { info: () => {}, warn: () => {} },
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const names = () => [...live.keys()].sort()
const writeCfg = (obj) => writeFileSync(CFG, JSON.stringify(obj, null, 2) + '\n', 'utf8')
// 2026-11-25：显式给全 6 个工具都开，不依赖生产 config.json 的内容
// （mem_backup 从这版起**默认关闭**，不写 true 的话它会少注册一个）
const baseCfg = { ...JSON.parse(original) }
baseCfg.tools = { ...(baseCfg.tools || {}), mem_backup: true }
const syncLog = join(stateDir, 'tool-sync.log')
const syncLines = () => (existsSync(syncLog) ? readFileSync(syncLog, 'utf8').trim().split('\n').filter(Boolean) : [])

console.log('=== ① apply() ===')
apply(ctx)
check('注册 6 个工具', live.size === 6, names().join(','))

console.log('\n=== ② 关掉 mem_maint ===')
writeCfg({ ...baseCfg, tools: { ...(baseCfg.tools || {}), mem_maint: false } })
await sleep(1500)
check('mem_maint 被摘掉', !live.has('mem_maint'), '现在 ' + live.size + ' 个')

console.log('\n=== ③ 改回来 ===')
writeCfg(baseCfg)
await sleep(1500)
check('mem_maint 回来了', live.has('mem_maint'), '现在 ' + live.size + ' 个')

console.log('\n=== ④ 写坏 JSON ===')
writeFileSync(CFG, '{ 这不是 JSON', 'utf8')
await sleep(1500)
// 配置读不到 → 用内置默认 → mem_backup 默认关，所以是 5 个（不是 6）
check('没崩（坏配置回落默认，mem_backup 默认关 → 5 个）', live.size === 5,
      '现在 ' + live.size + ' 个')

console.log('\n=== ⑤ 删除 config.json ===')
unlinkSync(CFG)
await sleep(1500)
check('没崩（删配置后回落默认 → 5 个）', live.size === 5,
      '现在 ' + live.size + ' 个')
writeCfg(baseCfg)
await sleep(1200)

console.log('\n=== ⑥ 连续改 5 次 ===')
for (let i = 0; i < 5; i += 1) {
  writeCfg({ ...baseCfg, tools: { ...(baseCfg.tools || {}), mem_maint: i % 2 === 0 } })
  await sleep(60)
}
await sleep(1500)
check('最终状态正确（最后一次 i=4 → true）', live.has('mem_maint'), '现在 ' + live.size + ' 个')

console.log('\n=== ⑦ config.json 被整体替换 ===')
const tmpCfg = CFG + '.tmp'
writeFileSync(tmpCfg, JSON.stringify({ ...baseCfg, tools: { ...(baseCfg.tools || {}), mem_maint: false } }, null, 2) + '\n', 'utf8')
renameSync(tmpCfg, CFG)
await sleep(1500)
check('替换也能触发（mem_maint 被摘）', !live.has('mem_maint'), '现在 ' + live.size + ' 个')

// 还原
writeFileSync(CFG, original, 'utf8')
await sleep(1500)

console.log('\n=== ⑧ check-memory-refs 的负向后视 ===')
const refsSrc = readFileSync(join(ROOT, 'modules/feature/check/py/check-memory-refs.py'), 'utf8')
const hasLookbehind = refsSrc.includes('(?<![A-Za-z0-9_\\-./\\\\])')
check('PATH_RE 有负向后视', hasLookbehind, hasLookbehind ? '' : '没找到 (?<!...)')

console.log('\n=== ⑩ 不配 mem_backup 时它不注册（默认关）===')
{
  const noBackup = { ...baseCfg }
  noBackup.tools = { mem_check: true, mem_maint: true, mem_query: true,
                     mem_alert: true, mem_status: true }   // 故意不写 mem_backup
  writeCfg(noBackup)
  await sleep(1500)
  check('mem_backup 默认不注册', !live.has('mem_backup'), '现在 ' + live.size + ' 个')
  check('其他 5 个仍在', live.size === 5, '现在 ' + live.size + ' 个')
  writeCfg(baseCfg)
  await sleep(1500)
  check('显式配 true 后重新注册', live.has('mem_backup'), '现在 ' + live.size + ' 个')
}

console.log('\n=== ⑨ 自己写的 tool-sync.log ===')
const lines = syncLines()
check('日志文件写出来了', lines.length > 0, '路径 ' + syncLog)
// ①⑤⑥⑦ 等改动都会留一行；至少应该有 4 次以上
check('每次变化都有行（≥5 行）', lines.length >= 5, '共 ' + lines.length + ' 行')
const hasPlus = lines.some((l) => /\+[1-9]/.test(l))
check('记录里有「+N」（重新注册过）', hasPlus, lines.find((l) => /\+[1-9]/.test(l)) || '')
if (lines.length) console.log('  最后一行: ' + lines[lines.length - 1])

console.log('\n' + '='.repeat(50))
console.log('开关测试：%d 通过 / %d 失败 / 共 %d', pass, fail, pass + fail)
if (fail) process.exitCode = 1
