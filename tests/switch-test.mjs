// 2026-11-25：验证 #16「改配置不重启就生效」
//
// mock 一个最小 ctx（只实现 apply 用到的 tools.register / logger），
// 然后：
//   ① apply 一次 → 看初始注册了几个
//   ② 改 config.json 的 tools.mem_maint = false → 等 500ms → 看它有没有被摘掉
//   ③ 改回 true → 等 500ms → 看它有没有回来
//   ④ 写坏 JSON → 看会不会崩
//
// 跑法（在插件根）：node lib/switch-test.mjs

import { apply } from '../lib/index.js'
import { readFileSync, writeFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const CFG = join(ROOT, 'config.json')
const original = readFileSync(CFG, 'utf8')

const live = new Map()
const ctx = {
  tools: {
    register(tool) {
      live.set(tool.name, tool)
      return () => live.delete(tool.name)
    },
  },
  logger: {
    info: (m) => console.log('  [info]', m),
    warn: (m) => console.log('  [warn]', m),
  },
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const names = () => [...live.keys()].sort()

console.log('=== ① apply() ===')
apply(ctx)
const initial = names()
console.log('  已注册: ' + initial.length + ' 个: ' + initial.join(', '))

console.log('\n=== ② 关掉 mem_maint（不重启）===')
const cfg = JSON.parse(original)
cfg.tools = { ...(cfg.tools || {}), mem_maint: false }
writeFileSync(CFG, JSON.stringify(cfg, null, 2) + '\n', 'utf8')
await sleep(800)
console.log('  现在: ' + names().length + ' 个' + (live.has('mem_maint') ? '（mem_maint 还在 ❌）' : '（mem_maint 已摘掉 ✅）'))

console.log('\n=== ③ 改回来 ===')
const cfg2 = JSON.parse(original)
writeFileSync(CFG, JSON.stringify(cfg2, null, 2) + '\n', 'utf8')
await sleep(800)
console.log('  现在: ' + names().length + ' 个' + (live.has('mem_maint') ? '（mem_maint 回来了 ✅）' : '（没回来 ❌）'))

console.log('\n=== ④ 写坏 JSON（不应该崩）===')
writeFileSync(CFG, '{ 这不是 JSON', 'utf8')
await sleep(800)
console.log('  进程还活着，工具数: ' + names().length)

// 还原
writeFileSync(CFG, original, 'utf8')
await sleep(300)
console.log('\n=== 已还原 config.json ===')
