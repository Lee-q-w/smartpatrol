<!-- AIAssistant.vue —— AI 巡检助手「小巡」（右下角悬浮球 + 对话面板）
     职责：普通话下指令即执行——对话经后端 /api/agent/chat 由大模型做意图解析，
     返回结构化 actions（动作白名单：patrol / switch_scene / switch_mode /
     export_report / mark_resolved / recheck），emit('action') 上抛给 App 执行；
     后端不可用时自动降级本地规则引擎（离线优先，演示永不掉线），
     首次降级会引导配置模型 Key。 -->
<template>
  <div class="assistant">
    <transition name="pop">
      <div v-if="open" class="panel">
        <div class="panel-head">
          <span class="bot-avatar">🤖</span>
          <div class="bot-title">
            <b>小巡 · AI 助手</b>
            <span class="bot-sub" :class="engine">{{ engine === 'rule' ? '离线规则模式' : '大模型驱动' }}</span>
          </div>
          <button class="close-btn" @click="open = false">✕</button>
        </div>
        <div class="msg-list" ref="listRef">
          <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
            <div class="bubble">{{ m.text }}</div>
          </div>
          <div v-if="busy" class="msg ai"><div class="bubble typing">小巡思考中…</div></div>
        </div>
        <div class="chips">
          <button v-for="c in chips" :key="c" :disabled="busy" @click="send(c)">{{ c }}</button>
        </div>
        <div class="input-row">
          <el-input v-model="input" :placeholder="busy ? '小巡正在回复…' : '试试：全面体检一下'" :disabled="busy"
            @keyup.enter="send()" />
          <el-button type="primary" :loading="busy" @click="send()">发送</el-button>
        </div>
      </div>
    </transition>
    <button class="fab" :class="{ active: open }" @click="toggle" title="AI 巡检助手">
      <span class="fab-icon">{{ open ? '✕' : '🤖' }}</span>
      <span v-if="!open" class="fab-tip">问我就能操作</span>
    </button>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { ElButton, ElInput } from 'element-plus'

const props = defineProps({
  context: { type: Object, required: true },   // 平台运行状态（场景/分区/模式/异常摘要）
})
const emit = defineEmits(['action'])

const API = 'http://127.0.0.1:8788'

const open = ref(false)
const input = ref('')
const busy = ref(false)
const engine = ref('ai')                        // ai 大模型 / rule 离线规则
const messages = ref([])
const listRef = ref(null)

const MODE_NAME = { quick: '快速巡逻', point: '定点详查', sweep: '环视检查' }
const chips = computed(() => {
  const list = ['全面体检一下', '现在有什么异常']
  if (props.context.anomalies?.some(a => (a.handleStatus ?? 'pending') !== 'resolved')) list.push('全部标记已处理')
  list.push('导出报告')
  return list
})

function toggle() {
  open.value = !open.value
  if (open.value && !messages.value.length) {
    messages.value = [{
      role: 'ai',
      text: '你好，我是小巡 🤖 用一句话指挥平台就行，比如「帮我详查西南分区」「现在有什么异常」「导出报告」。',
    }]
  }
}

async function scrollToBottom() {
  await nextTick()
  if (listRef.value) listRef.value.scrollTop = listRef.value.scrollHeight
}

// send()：发送一条用户消息。历史窗口取最近 8 条（含本轮）连同平台上下文
// 一起交给模型；非 200 或网络失败一律走本地规则降级
async function send(preset) {
  const text = String(preset ?? input.value).trim()
  if (!text || busy.value) return
  input.value = ''
  messages.value.push({ role: 'user', text })
  scrollToBottom()
  busy.value = true
  // 历史给模型（最近 8 条）
  const history = messages.value.slice(-8).map(m => ({ role: m.role, content: m.text }))
  try {
    const r = await fetch(`${API}/api/agent/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: history, context: props.context }),
      signal: AbortSignal.timeout(45000),
    })
    if (r.ok) {
      const d = await r.json()
      engine.value = 'ai'
      reply(d.reply, d.actions)
    } else {
      fallback(text)
    }
  } catch {
    fallback(text)
  } finally {
    busy.value = false
    scrollToBottom()
  }
}

// 离线规则降级：模型服务不可用时本地关键词解析（离线优先，演示永不掉线）
const fallbackCount = ref(0)
function fallback(text) {
  engine.value = 'rule'
  const d = ruleReply(text, props.context)
  // 首次降级时引导配置大模型（配置后自动切回大模型驱动）
  const hint = fallbackCount.value++ === 0
    ? '\n\n💡 小提示：到「AI 识别中心」→「模型配置」填入你的 API Key，就能解锁大模型对话能力。'
    : ''
  reply(d.reply + hint, d.actions)
}

function reply(text, actions) {
  messages.value.push({ role: 'ai', text })
  for (const a of actions ?? []) emit('action', a)
}

// ---------- 本地规则引擎 ----------
// 意图解析顺序：查询直答 → 场景切换 → 数据源切换 → 巡逻（全面/分区/方式）
// → 报告导出 → 批量处置 → 无人机复核；同一句话可复合命中多个动作
function ruleReply(t, ctx) {
  const actions = []
  const parts = []

  // 查询优先：问异常/情况 直接回答，不触发巡逻
  const isQuery = /异常|问题|情况|结果|怎么样|多少/.test(t) && !/巡|查一查|检查|体检/.test(t)
  if (isQuery) {
    const list = ctx.anomalies ?? []
    if (!list.length) {
      return { reply: '当前没有发现异常，一切正常。要不要来一次全面体检？', actions: [] }
    }
    const pending = list.filter(a => (a.handleStatus ?? 'pending') !== 'resolved')
    const done = list.length - pending.length
    const detail = list.slice(0, 5).map(a => `${a.label}（${a.near}，${{ pending: '未处理', processing: '处理中', resolved: '已处置' }[a.handleStatus ?? 'pending'] ?? '未处理'}）`).join('；')
    return {
      reply: `本轮共发现 ${list.length} 处异常，其中待处理 ${pending.length} 处、已处置 ${done} 处：${detail}。`,
      actions: [],
    }
  }

  // 场景切换
  if (/仓库|室内/.test(t) && ctx.sceneId !== 'warehouse') {
    actions.push({ type: 'switch_scene', args: { sceneId: 'warehouse' } })
    parts.push('已切换到室内仓库场景')
  } else if (/园区|室外/.test(t) && ctx.sceneId !== 'park' && ctx.scenes?.some(s => s.id === 'park')) {
    actions.push({ type: 'switch_scene', args: { sceneId: 'park' } })
    parts.push('已切换到园区场景')
  }

  // 数据源切换
  if (/真机|设备/.test(t)) {
    actions.push({ type: 'switch_mode', args: { mode: 'real' } })
    parts.push('已切换真机模式（连接设备后即可巡逻）')
  } else if (/回放|历史记录/.test(t)) {
    actions.push({ type: 'switch_mode', args: { mode: 'replay' } })
    parts.push('已切换回放模式')
  } else if (/仿真|模拟/.test(t)) {
    actions.push({ type: 'switch_mode', args: { mode: 'sim' } })
    parts.push('已切换仿真模式')
  }

  // 巡逻（全面体检 / 指定分区 / 指定方式）
  let mode = ctx.patrolMode ?? 'quick'
  if (/详查|定点/.test(t)) mode = 'point'
  else if (/环视/.test(t)) mode = 'sweep'
  else if (/快速/.test(t)) mode = 'quick'
  const zone = (ctx.zones ?? []).find(z => z.name && t.includes(z.name.replace(/分区|区域/g, '')) && z.name.replace(/分区|区域/g, '').length >= 2)
  const wantPatrol = /全面|全园|体检|整体|巡一遍|巡查|巡逻|检查/.test(t) || mode !== (ctx.patrolMode ?? 'quick')
  if (wantPatrol && !actions.some(a => a.type === 'switch_mode' || a.type === 'switch_scene')) {
    if (zone) {
      actions.push({ type: 'patrol', args: { zoneIds: [zone.id], mode } })
      parts.push(`马上安排${zone.name}${MODE_NAME[mode]}`)
    } else {
      actions.push({ type: 'patrol', args: { mode } })
      parts.push(`马上安排全园${MODE_NAME[mode]}`)
    }
  }

  // 报告 / 处置 / 复核
  if (/报告|导出|PDF|pdf/.test(t)) {
    actions.push({ type: 'export_report', args: {} })
    parts.push('正在生成 PDF 巡检报告')
  }
  if (/处理完|已处理|标记|解决/.test(t)) {
    actions.push({ type: 'mark_resolved', args: { all: true } })
    parts.push('已标记全部异常处置完成')
  }
  if (/复核|复查/.test(t)) {
    actions.push({ type: 'recheck', args: { all: true } })
    parts.push('已呼叫无人机复核待确认异常')
  }

  if (!actions.length) {
    return {
      reply: '我可以帮你：全面体检、指定分区巡查（如「详查西南分区」）、查异常、标记已处理、导出报告、切换真机/回放/仿真模式。',
      actions: [],
    }
  }
  return { reply: parts.join('，') + '。', actions }
}
</script>

<style scoped>
.assistant { position: fixed; right: 24px; bottom: 24px; z-index: 200; font-size: 13px; }
/* 悬浮球 */
.fab {
  position: relative; width: 54px; height: 54px; border-radius: 50%; border: none; cursor: pointer;
  background: linear-gradient(135deg, #409eff, #2a6aa8); color: #fff; font-size: 24px;
  box-shadow: 0 6px 20px rgba(64, 158, 255, 0.45); transition: transform .2s, box-shadow .2s;
  display: flex; align-items: center; justify-content: center;
}
.fab:hover { transform: translateY(-3px) scale(1.05); box-shadow: 0 10px 26px rgba(64, 158, 255, 0.55); }
.fab.active { background: linear-gradient(135deg, #909399, #606266); font-size: 18px; }
.fab-tip {
  position: absolute; right: 62px; top: 50%; transform: translateY(-50%); white-space: nowrap;
  background: rgba(31, 45, 61, 0.85); color: #fff; padding: 4px 10px; border-radius: 6px; font-size: 12px;
  opacity: 0; transition: opacity .25s; pointer-events: none;
}
.fab:hover .fab-tip { opacity: 1; }
/* 面板 */
.panel {
  position: absolute; right: 0; bottom: 66px; width: 380px; height: 520px;
  background: #fff; border-radius: 14px; box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18);
  display: flex; flex-direction: column; overflow: hidden; border: 1px solid rgba(31, 45, 61, 0.08);
}
.panel-head { display: flex; align-items: center; gap: 10px; padding: 12px 14px; background: linear-gradient(135deg, #ecf5ff, #f4f9ff); border-bottom: 1px solid #ebeef5; }
.bot-avatar { font-size: 26px; }
.bot-title { flex: 1; display: flex; flex-direction: column; }
.bot-title b { color: #1f2d3d; font-size: 14px; }
.bot-sub { font-size: 11px; color: #67c23a; }
.bot-sub.rule { color: #e6a23c; }
.close-btn { border: none; background: none; color: #909399; font-size: 14px; cursor: pointer; padding: 4px 8px; border-radius: 6px; }
.close-btn:hover { background: #f0f2f5; color: #606266; }
.msg-list { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 10px; }
.msg { display: flex; }
.msg.user { justify-content: flex-end; }
.bubble {
  max-width: 82%; padding: 8px 12px; border-radius: 10px; line-height: 1.55; white-space: pre-wrap; word-break: break-all;
}
.msg.ai .bubble { background: #f4f6f9; color: #303133; border-top-left-radius: 2px; }
.msg.user .bubble { background: linear-gradient(135deg, #409eff, #5aadff); color: #fff; border-top-right-radius: 2px; }
.bubble.typing { color: #909399; font-style: italic; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 8px 14px 4px; }
.chips button {
  border: 1px solid #d9ecff; background: #ecf5ff; color: #409eff; border-radius: 12px;
  padding: 3px 10px; font-size: 12px; cursor: pointer; transition: all .15s;
}
.chips button:hover { background: #d9ecff; }
.chips button:disabled { opacity: 0.5; cursor: not-allowed; }
.input-row { display: flex; gap: 8px; padding: 10px 14px 12px; }
.input-row .el-input { flex: 1; }
/* 弹出动画 */
.pop-enter-active, .pop-leave-active { transition: all .25s ease; }
.pop-enter-from, .pop-leave-to { opacity: 0; transform: translateY(12px) scale(.96); }

/* 深色主题 */
:global(.app[data-theme='dark']) .panel { background: #101d2d; border-color: #1d3350; box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5); }
:global(.app[data-theme='dark']) .panel-head { background: linear-gradient(135deg, #12233a, #0e1a29); border-bottom-color: #1d3350; }
:global(.app[data-theme='dark']) .bot-title b { color: #cfe0f5; }
:global(.app[data-theme='dark']) .msg.ai .bubble { background: #14273d; color: #9fb8d4; }
:global(.app[data-theme='dark']) .chips button { background: #14273d; border-color: #1d3350; color: #8fb0d0; }
:global(.app[data-theme='dark']) .chips button:hover { background: #1d3350; }
:global(.app[data-theme='dark']) .close-btn:hover { background: #14273d; color: #9fb8d4; }
</style>
