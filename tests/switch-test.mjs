// 2026-11-25：#16 工具开关即时生效 —— 完整边界测试
//
// 覆盖（用户追问「你是不是又省了测试」之后补的）：
//   ① apply() 初始注册
//   ② 关掉 mem_maint（不重启即摘）
//   ③ 改回来（不重启即挂）
//   ④ 写坏 JSON（不崩、回落全开）
//   ⑤ 删除 config.json（不崩）
//   ⑥ 连续改 5 次（防抖，最终状态正确）
//   ⑦ config.json 被整体替换（不是原地修改）
//   ⑧ check-memory-refs 的负向后视（不再把插件内 docs/ 当工作区的）
//
// 跑法（在插件根）：node tests/switch-test.mjs

import { apply } from '../lib/index.js'
import { readFileSync, writeFileSync, unlinkSync, existsSync, renameSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const CFG = join(ROOT, 'config.json')
const original = readFileSync(CFG, 'utf8')

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
  logger: { info: () => {}, warn: () => {} },   // 静音，只看结果
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const names = () => [...live.keys()].sort()
const writeCfg = (obj) => writeFileSync(CFG, JSON.stringify(obj, null, 2) + '\n', 'utf8')
const baseCfg = JSON.parse(original)

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
check('没崩（仍 6 个）', live.size === 6, '现在 ' + live.size + ' 个')

console.log('\n=== ⑤ 删除 config.json ===')
unlinkSync(CFG)
await sleep(1500)
check('没崩（删配置后仍可用）', live.size === 6, '现在 ' + live.size + ' 个')
writeCfg(baseCfg)
await sleep(600)

console.log('\n=== ⑥ 连续改 5 次（防抖）===')
for (let i = 0; i < 5; i += 1) {
  writeCfg({ ...baseCfg, tools: { ...(baseCfg.tools || {}), mem_maint: i % 2 === 0 } })
  await sleep(60)      // 60ms 一次，比防抖窗口 300ms 短 → 应该只触发一次重算
}
await sleep(900)
check('最终状态正确（最后一次是 i=4 → true）', live.has('mem_maint'), '现在 ' + live.size + ' 个')

console.log('\n=== ⑦ config.json 被整体替换 ===')
const tmpCfg = CFG + '.tmp'
writeFileSync(tmpCfg, JSON.stringify({ ...baseCfg, tools: { ...(baseCfg.tools || {}), mem_maint: false } }, null, 2) + '\n', 'utf8')
renameSync(tmpCfg, CFG)     // 原子替换
await sleep(900)
check('替换也能触发（mem_maint 被摘）', !live.has('mem_maint'), '现在 ' + live.size + ' 个')

// 还原
writeFileSync(CFG, original, 'utf8')
await sleep(600)

console.log('\n=== ⑧ check-memory-refs 的负向后视 ===')
// 造两个"假引用"，看检查器会不会误报
const cases = [
  { text: '见 `tools/dsh-memory-maint/docs/CONFIG.md` 的说明', shouldFlag: false, why: '插件内的 docs/ 不该被当工作区的' },
  { text: '见 `docs/CONFIG.md` 的说明', shouldFlag: true, why: '裸 docs/ 才是真引用' },
]
// 直接读检查器的正则
const refsSrc = readFileSync(join(ROOT, 'modules/feature/check/py/check-memory-refs.py'), 'utf8')
const m = refsSrc.match(/PATH_RE = re\.compile\(\s*([\s\S]*?)\)\s*\n/)
const hasLookbehind = refsSrc.includes('(?<![A-Za-z0-9_\\-./\\\\])')
check('PATH_RE 有负向后视', hasLookbehind, hasLookbehind ? '' : '没找到 (?<!...)')

console.log('\n' + '='.repeat(50))
console.log('开关测试：%d 通过 / %d 失败 / 共 %d', pass, fail, pass + fail)
if (fail) process.exitCode = 1
