// ============================================================
// useMcpBridge —— MCP 桥接（组合式 API）
// ------------------------------------------------------------
// 职责：让标准 MCP 客户端（Claude/Cursor/TeleAgent，经 server/mcp_server.py）
// 能查询平台状态、指挥巡检作业。两条通道：
//   1. 状态上报：watch 平台状态 → debounce POST /api/state（+5s 心跳保活）
//   2. 指令执行：EventSource 订阅 /api/mcp/events → 复用 Agent 动作链执行
// 说明：后端离线时静默降级（不报错不重试风暴），AI 核心能力不受影响。
// ============================================================
import { onBeforeUnmount, watch } from 'vue'

export function useMcpBridge({ source, actionExecutor }) {
  const API = 'http://127.0.0.1:8788'

  // ---------- 指令通道（SSE）----------
  let es = null
  let esRetry = null

  function handleCmd(ev) {
    try {
      const { type, args } = JSON.parse(ev.data)
      if (!type || type === 'hello') return
      actionExecutor({ type, args })   // 与 AI 助手/手动操作同一动作链
    } catch { /* 忽略坏帧 */ }
  }

  function connectCmd() {
    try {
      es = new EventSource(`${API}/api/mcp/events`)
      es.onmessage = handleCmd
      es.onerror = () => {   // 后端未启动/中断：1.2s 后重连（EventSource 自身也会重试，双保险节流）
        if (es) { es.close(); es = null }
        clearTimeout(esRetry)
        esRetry = setTimeout(connectCmd, 12000)
      }
    } catch { /* 环境不支持 SSE：跳过 */ }
  }

  // ---------- 状态上报（debounce + 心跳）----------
  let timer = null
  let heartbeat = null
  let sending = false

  async function pushSnapshot() {
    if (sending) return
    sending = true
    try {
      const snap = source()
      await fetch(`${API}/api/state`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(snap),
        signal: AbortSignal.timeout(4000),
      })
    } catch { /* 后端离线：静默 */ }
    finally { sending = false }
  }

  function schedule() {
    clearTimeout(timer)
    timer = setTimeout(pushSnapshot, 800)   // 变更密集时合并上报
  }

  connectCmd()
  pushSnapshot()
  heartbeat = setInterval(pushSnapshot, 5000)   // 即便无状态变化也保活

  if (source.watchTargets) {
    watch(source.watchTargets, schedule, { deep: true })
  }

  onBeforeUnmount(() => {
    clearTimeout(timer); clearInterval(heartbeat); clearTimeout(esRetry)
    if (es) es.close()
  })
}
