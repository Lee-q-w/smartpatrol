// ============================================================
// useMcpBridge —— MCP 桥接（组合式 API · TypeScript 版）
// ------------------------------------------------------------
// 职责：让标准 MCP 客户端（Claude/Cursor/TeleAgent，经 server/mcp_server.py）
// 能查询平台状态、指挥巡检作业。两条通道：
//   1. 状态上报：watch 平台状态 → debounce POST /api/state（+5s 心跳保活）
//   2. 指令执行：EventSource 订阅 /api/mcp/events → 复用 Agent 动作链执行
// 说明：后端离线时静默降级（不报错不重试风暴），AI 核心能力不受影响。
// ============================================================
import { onBeforeUnmount, watch, type WatchSource } from 'vue'

/** Agent 动作（与 AI 助手/手动操作同一动作链，字段按动作类型而异） */
export interface AgentAction {
  type: string
  args?: Record<string, unknown>
}

/** MCP 指令帧（后端 /api/mcp/events 推送） */
interface McpCommandFrame {
  type?: string
  args?: Record<string, unknown>
}

export interface McpBridgeOptions {
  /** 平台状态快照（上报给 MCP Server 查询） */
  source: (() => Record<string, unknown>) & { watchTargets?: WatchSource | WatchSource[] }
  /** 指令执行器（复用前端动作链） */
  actionExecutor: (action: AgentAction) => void
}

export function useMcpBridge({ source, actionExecutor }: McpBridgeOptions): void {
  const API = 'http://127.0.0.1:8788'

  // ---------- 指令通道（SSE）----------
  let es: EventSource | null = null
  let esRetry: ReturnType<typeof setTimeout> | null = null

  function handleCmd(ev: MessageEvent<string>): void {
    try {
      const { type, args } = JSON.parse(ev.data) as McpCommandFrame
      if (!type || type === 'hello') return
      actionExecutor({ type, args }) // 与 AI 助手/手动操作同一动作链
    } catch {
      /* 忽略坏帧 */
    }
  }

  function connectCmd(): void {
    try {
      es = new EventSource(`${API}/api/mcp/events`)
      es.onmessage = handleCmd
      es.onerror = () => {
        // 后端未启动/中断：12s 后重连（EventSource 自身也会重试，双保险节流）
        if (es) {
          es.close()
          es = null
        }
        if (esRetry) clearTimeout(esRetry)
        esRetry = setTimeout(connectCmd, 12000)
      }
    } catch {
      /* 环境不支持 SSE：跳过 */
    }
  }

  // ---------- 状态上报（debounce + 心跳）----------
  let timer: ReturnType<typeof setTimeout> | null = null
  let heartbeat: ReturnType<typeof setInterval> | null = null
  let sending = false

  async function pushSnapshot(): Promise<void> {
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
    } catch {
      /* 后端离线：静默 */
    } finally {
      sending = false
    }
  }

  function schedule(): void {
    if (timer) clearTimeout(timer)
    timer = setTimeout(pushSnapshot, 800) // 变更密集时合并上报
  }

  connectCmd()
  void pushSnapshot()
  heartbeat = setInterval(pushSnapshot, 5000) // 即便无状态变化也保活

  if (source.watchTargets) {
    watch(source.watchTargets, schedule, { deep: true })
  }

  onBeforeUnmount(() => {
    if (timer) clearTimeout(timer)
    if (heartbeat) clearInterval(heartbeat)
    if (esRetry) clearTimeout(esRetry)
    if (es) es.close()
  })
}