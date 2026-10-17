<template>
  <div class="app" :data-theme="theme">
    <SplashScreen v-if="splashShown" @done="splashShown = false" />
    <header class="header">
      <div class="logo">🛰 智巡 <span>SmartPatrol</span></div>
      <div class="subtitle">虚实结合的园区智能巡检平台</div>
      <div class="header-right">
        <el-radio-group v-model="dsMode" size="small" @change="onModeChange">
          <el-radio-button value="sim">仿真模式</el-radio-button>
          <el-radio-button value="replay">回放模式</el-radio-button>
          <el-radio-button value="real" title="连接真机或模拟设备后自动巡检">真机</el-radio-button>
        </el-radio-group>
        <el-button circle size="small" @click="toggleTheme" :title="theme === 'dark' ? '切浅色' : '切深色'">
          {{ theme === 'dark' ? '☀' : '🌙' }}
        </el-button>
      </div>
    </header>

    <!-- 导航：功能入口已收敛至首页大模块卡，非首页仅保留返回入口（大屏自带退出按钮） -->
    <nav class="view-nav" v-if="view !== 'home' && view !== 'screen'">
      <button class="back-home" @click="view = 'home'">🏠 返回首页</button>
    </nav>

    <!-- 视图：首页（开屏后落地，平台全貌 + 模块入口） -->
    <HomeView
      v-if="view === 'home'"
      :scene-name="currentScene.name"
      :scene-count="sceneList.length"
      :stats="homeStats"
      :battery="devices.agv.battery"
      :phase="phase"
      :recent-logs="homeRecentLogs"
      :model-configured="modelConfigured"
      @enter="onHomeEnter"
      @quick-patrol="onQuickPatrol"
    />

    <!-- 视图：值守大屏（值班室全屏模式） -->
    <div v-if="view === 'screen'" class="screen-view">
      <header class="screen-top">
        <div class="screen-brand">🛰 智巡 <span>SmartPatrol 值守大屏</span></div>
        <div class="screen-meta">
          <span class="chip">📍 {{ currentScene.name }}</span>
          <span class="chip">{{ modeName }}</span>
          <span class="chip clock">{{ clockText }}</span>
        </div>
        <div class="screen-stats">
          <div class="stat warn" :class="{ alert: handleStats.pending > 0 }"><b>{{ handleStats.pending }}</b><span>待处理</span></div>
          <div class="stat proc"><b>{{ handleStats.processing }}</b><span>处理中</span></div>
          <div class="stat done"><b>{{ handleStats.resolved }}</b><span>已处置</span></div>
          <div class="stat total"><b>{{ anomalies.length }}</b><span>累计异常</span></div>
        </div>
        <button class="screen-exit" @click="exitScreen">⤢ 退出大屏</button>
      </header>
      <div class="screen-map">
        <ParkMap
          :scene="currentScene" :night="true" :agv="devices.agv" :drone="devices.drone"
          :route-progress="routeShown" :route="plannedRoute" :anomalies="anomalies"
          :show-anomalies="anomalies.length > 0" :drone-target="droneTarget"
          :base-width="1400" @anomaly-click="openEvidence" />
        <div class="screen-side">
          <div class="panel-block">
            <div class="pb-title">任务状态</div>
            <div class="pb-body"><span class="phase-dot" :class="phase"></span>{{ phaseLabel }}<template v-if="!isReplay"> · {{ scopeText }}</template></div>
            <div class="pb-body sub">🔋 巡逻车电量 {{ devices.agv.battery }}%</div>
          </div>
          <div class="panel-block grow">
            <div class="pb-title">实时情报</div>
            <div class="pb-body feed">
              <div v-for="(l, i) in recentLogs" :key="l.ts + '-' + i" class="feed-line" :class="feedTone(l.text)">{{ l.text }}</div>
              <div v-if="!recentLogs.length" class="feed-empty">等待情报…</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 视图：AI 识别中心 -->
    <AICenter v-if="view === 'ai'" :scene="currentScene" @fill-anomaly="onFillAnomaly" />

    <!-- 视图：地图工作台 -->
    <MapWorkbench v-if="view === 'workbench'" @saved="onSceneSaved" />

    <!-- 视图：实时巡检 -->
    <main class="main" v-if="view === 'patrol'">
      <!-- 左：地图 -->
      <section class="map-panel">
        <ParkMap
          :scene="currentScene"
          :night="theme === 'dark'"
          :agv="devices.agv"
          :drone="devices.drone"
          :route-progress="routeShown"
          :route="plannedRoute"
          :anomalies="anomalies"
          :show-anomalies="anomalies.length > 0"
          :drone-target="droneTarget"
          :base-width="1400"
          @anomaly-click="openEvidence"
        />
      </section>

      <!-- 右：控制 / 命令流 / 报告 -->
      <aside class="side">
        <el-card class="ctrl-card">
          <template #header><b>巡逻控制</b></template>
          <template v-if="!isReplay">
            <!-- 真机连接面板（仅真机模式显示） -->
            <div v-if="isReal" class="conn-panel">
              <div class="conn-head">
                <span class="conn-dot" :class="realInfo.state"></span>
                <b>{{ realInfo.text || '设备未连接' }}</b>
                <span v-if="realInfo.device" class="conn-dev">🤖 {{ realInfo.device.name }}</span>
              </div>
              <div class="conn-row">
                <el-input v-model="deviceUrl" size="small" :disabled="realInfo.state === 'connected'"
                  placeholder="ws://127.0.0.1:9601" />
                <el-button v-if="realInfo.state !== 'connected'" size="small" type="primary"
                  :loading="realInfo.state === 'connecting'" @click="connectDevice">连接设备</el-button>
                <el-button v-else size="small" @click="disconnectDevice">断开</el-button>
              </div>
              <div class="mode-tip">没设备？在 server 目录运行 <code>uv run sim_device.py</code> 启动模拟真机（协议见 docs/device-protocol.md）</div>
            </div>
            <div class="zone-row">
              <span class="zone-label">巡检场景</span>
              <el-select :model-value="currentScene.id" :disabled="!missionIdle" style="flex:1" @change="changeScene">
                <el-option v-for="s in sceneList" :key="s.id" :value="s.id" :label="s.name" :title="s.desc" />
              </el-select>
            </div>
            <div class="zone-row" style="margin-top: 10px">
              <span class="zone-label">巡逻范围</span>
              <div class="zone-tags" :class="{ disabled: !missionIdle }">
                <el-check-tag :checked="allZones" @change="toggleAll">全园</el-check-tag>
                <el-check-tag
                  v-for="z in zoneList" :key="z.id"
                  :checked="zoneIds.includes(z.id)"
                  @change="toggleZone(z.id)"
                >{{ z.name }}</el-check-tag>
              </div>
            </div>
            <div class="zone-row" style="margin-top: 10px">
              <span class="zone-label">巡查方式</span>
              <el-radio-group v-model="patrolMode" size="small" :disabled="!missionIdle">
                <el-radio-button v-for="(m, k) in PATROL_MODES" :key="k" :value="k">{{ m.label }}</el-radio-button>
              </el-radio-group>
            </div>
            <div class="mode-tip">{{ modeDesc }}</div>
            <el-button :type="startBtn.type" size="large" style="width:100%; margin-top: 10px"
              :disabled="startBtn.disabled" @click="startPatrol">
              {{ startBtn.text }}
            </el-button>
            <el-button style="width:100%; margin-top: 8px" :disabled="recheckBtn.disabled" @click="recheckAll">
              {{ recheckBtn.text }}
            </el-button>
          </template>
          <template v-else>
            <!-- 回放播放器 -->
            <div class="player-row">
              <el-button :type="replayPlaying ? 'warning' : 'primary'" size="large" style="flex:1" @click="toggleReplay">
                {{ replayBtnText }}
              </el-button>
              <el-button size="large" :disabled="replayInfo.state === 'ready'" @click="stopReplay">⏹ 停止</el-button>
            </div>
            <el-slider :model-value="replayT" :max="replayDuration" :step="0.1" :show-tooltip="false"
              :disabled="replayInfo.state === 'ready'" style="margin:14px 0 0" @change="seekReplay" />
            <div class="status-line" style="margin-top:6px">
              <span>回放进度 {{ replayT.toFixed(1) }}s / {{ Math.round(replayDuration) }}s</span>
              <span>倍速 {{ speed }}x</span>
            </div>
            <div class="mode-tip">可暂停、拖动进度条跳转 · 省赛真实记录（园区西南分区闭环）</div>
          </template>
          <el-slider v-if="!isReal" v-model="speed" :min="0.5" :max="4" :step="0.5" style="margin:18px 0 6px" />
          <div class="status-line">
            <span class="battery">电量 {{ devices.agv.battery }}%</span>
            <span>{{ isReplay ? '回放倍速' : '速度' }} {{ speed }}x</span>
          </div>
          <div class="mode-tip">
            <span class="phase-dot" :class="phase"></span>
            任务状态：<b>{{ phaseLabel }}</b><template v-if="!isReplay"> · 范围：{{ scopeText }}</template>
          </div>
          <div class="mode-tip">当前数据源：<b>{{ modeName }}</b></div>
          <div class="mode-tip" v-if="isReal">真机模式：异常由 AI 识别摄像头画面产生，点击报告可查看实拍证据</div>
          <div class="mode-tip" v-else-if="!isReplay">提示：真值异常位于 {{ truthZonesText }}，其余分区巡逻将报告“未发现异常”</div>
        </el-card>

        <el-card class="log-card">
          <template #header><b>命令流</b><span class="log-count">{{ cmdLog.length }}</span></template>
          <div class="cmd-stream">
            <div v-for="(l, i) in cmdLog.slice().reverse()" :key="l.ts + '-' + i" class="log-line">
              <span class="log-ts">{{ fmtTs(l.ts) }}</span>
              <span class="log-text">{{ l.text }}</span>
            </div>
            <div v-if="!cmdLog.length" class="log-empty">等待命令…</div>
          </div>
        </el-card>

        <el-card class="report-card">
          <template #header>
            <b>巡检报告</b>
            <span v-if="report" class="ok-badge">✓ 已生成</span>
            <el-button v-if="anomalies.length || report" size="small" type="primary" plain
              style="margin-left:10px" :loading="exporting" @click="exportReport">📄 导出 PDF</el-button>
          </template>
          <el-empty v-if="report && report.length === 0" description="本轮巡逻未发现异常" :image-size="60" />
          <el-empty v-else-if="!anomalies.length" description="等待巡逻发现异常…（点击地图标记可看证据照片）" :image-size="60" />
          <template v-else>
            <div v-if="anomalies.length" class="ticket-stats">
              <span class="ts-item warning">待处理 {{ handleStats.pending }}</span>
              <span class="ts-item primary">处理中 {{ handleStats.processing }}</span>
              <span class="ts-item success">已处理 {{ handleStats.resolved }}</span>
            </div>
            <div v-for="a in anomalies" :key="a.id" class="finding clickable" :style="{ borderLeftColor: typeColor(a.type) }" @click="openEvidence(a)">
              <div class="f-head">
                <span class="f-icon">{{ typeIcon(a.type) }}</span>
                <b>{{ a.label }}</b>
                <el-tag size="small" :type="a.stage === 'confirmed' ? 'danger' : 'info'">
                  {{ a.stage === 'confirmed' ? '已复核' : a.stage === 'rechecking' ? '复核中' : '初判' }} {{ Math.round(a.confidence * 100) }}%
                </el-tag>
              </div>
              <div class="f-place">📍 {{ a.near }} <span class="view-evi">查看证据照片 →</span></div>
              <div class="f-evi">{{ a.evidence }}</div>
              <div class="f-foot" @click.stop>
                <el-tag size="small" :type="ticketTagType(a)" effect="light" round>
                  📋 {{ ticketLabel(a) }}
                </el-tag>
                <el-button size="small" text type="primary" :disabled="isReplay" @click="handleTicket(a)">
                  {{ ticketBtnText(a) }}
                </el-button>
              </div>
            </div>
          </template>
        </el-card>
      </aside>
    </main>

    <footer class="footer">
      仿真验证多机协同算法 · 回放溯源真实执行 · 真机接入实时巡检 —— 生态 · 科技 · 人本
    </footer>

    <!-- AI 巡检助手（自然语言驱动平台；首页/巡检页可见） -->
    <AIAssistant v-if="view === 'patrol' || view === 'home'" :context="assistantContext" @action="onAssistantAction" />
  </div>
  <EvidenceDialog ref="eviDialogRef" :anomaly="activeAnomaly" />
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElButton, ElCard, ElMessage, ElTag, ElSlider, ElEmpty, ElRadioGroup, ElRadioButton, ElCheckTag, ElSelect, ElOption } from 'element-plus'
import ParkMap from './ParkMap.vue'
import EvidenceDialog from './EvidenceDialog.vue'
import MapWorkbench from './MapWorkbench.vue'
import AICenter from './AICenter.vue'
import AIAssistant from './AIAssistant.vue'
import HomeView from './HomeView.vue'
import SplashScreen from './SplashScreen.vue'
import { useDataSource, DataSourceMode } from './composables/useDataSource.js'
import { PATROL_MODES } from './parkData.js'
import { DRONE_FRAME } from './parkData.js'
const DRONE_FRAME_REF = DRONE_FRAME.ref   // 无人机俯拍复核帧（省赛实录，仅园区）
import { allScenes, anomalyMeta, buildMission, anomaliesByZone } from './scenes/index.js'
import { PARK_SCENE } from './scenes/park.js'

const {
  mode, devices, anomalies, cmdLog, phase, report, patrolProgress, recheckBusy, replayInfo, realInfo,
  scene: currentScene, setScene, switchMode, dispatch, isReplay, isReal, adapter,
} = useDataSource()

const API = 'http://127.0.0.1:8788'
const exporting = ref(false)

const theme = ref('light')
const splashShown = ref(true)   // 开屏页（2.4s 自动进入，可点击跳过）
const speed = ref(1)
const dsMode = ref('sim')
const droneTarget = ref(null)
const view = ref('home')   // 主导航：首页 / 实时巡检 / 地图工作台 / AI 识别中心 / 值守大屏（开屏后落首页）
const zoneIds = ref(['zone-c'])   // 巡逻范围：可多选/全园，保持点选顺序
const patrolMode = ref('quick')  // 巡查方式：quick / point / sweep
const eviDialogRef = ref(null)
const activeAnomaly = ref(null)

// —— 场景（平台化：任意场地可建图） ——
const sceneList = ref(allScenes())

async function changeScene(id) {
  const s = sceneList.value.find(x => x.id === id)
  if (!s || !missionIdle.value || s.id === currentScene.value.id) return
  zoneIds.value = [s.zones[0]?.id].filter(Boolean)   // 切场景重置为第一个分区
  await setScene(s)
}

// 地图工作台保存场景后：刷新选择器列表
function onSceneSaved() {
  sceneList.value = allScenes()
}

// AI 识别中心回填：注入真图识别异常到当前仿真数据源
function onFillAnomaly(a) {
  if (isReplay.value) {
    ElMessage.warning('回放模式为历史实录，不可回填；请切到仿真模式后再试')
    return
  }
  dispatch('inject-anomaly', { anomaly: a })
}

const modeName = computed(() => ({ sim: '仿真引擎（seed=2026）', replay: '历史回放（省赛真实记录）', real: '真机（AI 识别实时画面）' }[dsMode.value]))

// —— 真机连接 ——
const deviceUrl = ref('ws://127.0.0.1:9601')
const deviceOnline = computed(() => realInfo.value.state === 'connected')
function connectDevice() { adapter.value?.connect(deviceUrl.value.trim()) }
function disconnectDevice() { adapter.value?.disconnect() }

// 可发起/可调整新任务的状态：空闲，或上一轮已出报告
const missionIdle = computed(() => phase.value === 'idle' || phase.value === 'report')

const zoneList = computed(() => currentScene.value.zones.map(z => ({ id: z.id, name: z.name })))
const allZones = computed(() => zoneIds.value.length === zoneList.value.length)
const modeDesc = computed(() => PATROL_MODES[patrolMode.value]?.desc ?? '')
const pendingRecheck = computed(() => anomalies.value.filter(a => a.stage !== 'confirmed'))

// —— 异常工单：未处理→处理中→已处理（发现→处置闭环） ——
const handleStats = computed(() => {
  const s = { pending: 0, processing: 0, resolved: 0 }
  for (const a of anomalies.value) s[a.handle?.status ?? 'pending']++
  return s
})

// —— AI 巡检助手：平台运行状态上报（供意图解析） ——
const assistantContext = computed(() => ({
  sceneId: currentScene.value.id, sceneName: currentScene.value.name,
  scenes: sceneList.value.map(s => ({ id: s.id, name: s.name })),
  zones: zoneList.value,
  mode: dsMode.value, phase: phase.value, patrolMode: patrolMode.value,
  anomalies: anomalies.value.map(a => ({
    label: a.label, near: a.near, stage: a.stage,
    handleStatus: a.handle?.status ?? 'pending', confidence: a.confidence,
  })),
}))

// 助手动作执行器：AI 决定的动作落到平台（与手动操作同一套命令链）
async function onAssistantAction(a) {
  const { type, args = {} } = a
  try {
    if (type === 'patrol') {
      if (!missionIdle.value) { ElMessage.warning('当前任务进行中，稍候再试'); return }
      if (args.zoneIds?.length) zoneIds.value = [...args.zoneIds]
      if (args.mode && PATROL_MODES[args.mode]) patrolMode.value = args.mode
      startPatrol()
    } else if (type === 'switch_mode') {
      if (args.mode && ['sim', 'replay', 'real'].includes(args.mode) && args.mode !== dsMode.value) {
        dsMode.value = args.mode
        await onModeChange(args.mode)
      }
    } else if (type === 'switch_scene') {
      if (args.sceneId && args.sceneId !== currentScene.value.id) await changeScene(args.sceneId)
    } else if (type === 'export_report') {
      if (!anomalies.value.length && !report.value) { ElMessage.warning('还没有巡检结果，先巡逻一轮吧'); return }
      exportReport()
    } else if (type === 'mark_resolved') {
      const targets = anomalies.value.filter(x => (x.handle?.status ?? 'pending') !== 'resolved')
      if (!targets.length) { ElMessage.info('没有待处理的异常'); return }
      targets.forEach(x => dispatch('handle', { anomalyId: x.id, to: 'resolved' }))
    } else if (type === 'recheck') {
      recheckAll()
    }
  } catch (e) {
    ElMessage.error('助手动作执行失败：' + (e.message ?? e))
  }
}
const ticketLabel = a => ({ pending: '未处理', processing: '处理中', resolved: '已处理' }[a.handle?.status ?? 'pending'] ?? '未处理')
const ticketTagType = a => ({ pending: 'warning', processing: 'primary', resolved: 'success' }[a.handle?.status ?? 'pending'] ?? 'warning')
const ticketBtnText = a => ({ pending: '派单处理 →', processing: '完成处置 →', resolved: '重新打开' }[a.handle?.status ?? 'pending'] ?? '派单处理 →')
function handleTicket(a) {
  if (isReplay.value) return
  const to = { pending: 'processing', processing: 'resolved', resolved: 'pending' }[a.handle?.status ?? 'pending']
  dispatch('handle', { anomalyId: a.id, to })
}

// —— 回放播放器 ——
const replayPlaying = computed(() => replayInfo.value.state === 'playing')
const replayT = computed(() => replayInfo.value.t ?? 0)
const replayDuration = computed(() => replayInfo.value.duration || 14)
const replayBtnText = computed(() => ({
  ready: '▶ 播放真实巡逻记录',
  playing: '⏸ 暂停回放',
  paused: '▶ 继续回放',
  done: '↻ 重新播放',
}[replayInfo.value.state] ?? '▶ 播放真实巡逻记录'))
function toggleReplay() { dispatch(replayPlaying.value ? 'pause' : 'play', {}) }
function stopReplay() { dispatch('stop', {}) }
function seekReplay(v) { dispatch('seek', { t: v }) }

// 本场景预置真值异常所在的分区（提示文案用）
const truthZonesText = computed(() => {
  const byZone = anomaliesByZone(currentScene.value)
  const names = Object.keys(byZone).filter(k => k)
    .map(k => currentScene.value.zones.find(z => z.id === k)?.name ?? k)
  return names.length ? names.join('、') : '无（本场景未预置真值，可演示空报告）'
})

// —— 按钮状态与文案（让用户明白“为什么不能点 / 系统在做什么”） ——
const PHASE_LABEL = { idle: '待命', patrol: '巡逻中', detect: '识别异常中', recheck: '无人机复核中', report: '已完成' }
const phaseLabel = computed(() => PHASE_LABEL[phase.value] ?? '待命')

const scopeText = computed(() => {
  if (isReplay.value) return '西南分区（真实回放）'
  return zoneIds.value.length === zoneList.value.length ? '全园' : zoneIds.value.map(id => zoneList.value.find(z => z.id === id)?.name ?? id).join('、')
})

// 开始/停止按钮：
//   真机未连接 → 禁用提示先连接；真机任务中 → 急停可点；
//   空闲/已出报告 → 发起任务；仿真任务中 → 禁用展示进行中阶段
const startBtn = computed(() => {
  if (isReal.value && !deviceOnline.value) return { type: 'default', disabled: true, text: '🔌 请先连接设备' }
  if (missionIdle.value) return { type: 'primary', disabled: false, text: `▶ 开始${PATROL_MODES[patrolMode.value].label}` }
  if (isReal.value) return { type: 'danger', disabled: false, text: '⏹ 停止任务（急停）' }
  return { type: 'default', disabled: true, text: `⏳ ${phaseLabel.value}…` }
})

// 重点复查按钮：按 忙 / 无异常 / 已全复核 / 有待复核 四态给文案（真机模式无无人机复核）
const recheckBtn = computed(() => {
  if (isReal.value) return { disabled: true, text: '🚁 真机模式由 AI 直接确认，无需复核' }
  if (recheckBusy.value) return { disabled: true, text: '⏳ 无人机复核中…' }
  if (!anomalies.value.length) return { disabled: true, text: '🚁 重点复查（发现异常后可点）' }
  if (!pendingRecheck.value.length) return { disabled: true, text: '✅ 异常已全部复核' }
  return { disabled: false, text: `🚁 重点复查（${pendingRecheck.value.length} 处待复核）` }
})

// 地图规划线：仿真与推演共用 buildMission；回放用实录路线（dock→垃圾桶→长椅）
const plannedRoute = computed(() => {
  if (isReplay.value) return adapter.value?.replayRoute ?? []
  return buildMission(currentScene.value, zoneIds.value, patrolMode.value).route
})

function toggleZone(id) {
  if (!missionIdle.value) return
  const i = zoneIds.value.indexOf(id)
  if (i >= 0) {
    if (zoneIds.value.length === 1) return   // 至少保留一个分区
    zoneIds.value.splice(i, 1)
  } else {
    zoneIds.value.push(id)
  }
}

function toggleAll() {
  if (!missionIdle.value) return
  zoneIds.value = allZones.value ? [zoneList.value[0].id] : zoneList.value.map(z => z.id)
}

function toggleTheme() { theme.value = theme.value === 'dark' ? 'light' : 'dark' }

async function onModeChange(m) {
  // 回放为园区实录：切回放前先回到园区场景，避免地图与数据错位
  if (m === 'replay' && currentScene.value.id !== 'park') {
    await setScene(PARK_SCENE)
  }
  switchMode(m)
}

// —— 值守大屏（值班室全屏模式） ——
const clockText = ref('')
let clockTimer = null
onMounted(() => {
  const pad = n => String(n).padStart(2, '0')
  clockTimer = setInterval(() => {
    const d = new Date()
    clockText.value = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  }, 1000)
})
onBeforeUnmount(() => { if (clockTimer) clearInterval(clockTimer) })

const recentLogs = computed(() => cmdLog.value.slice(-14).reverse())

// 情报行语义染色（告警/确认/完成/工单一目了然）
function feedTone(text) {
  if (/发现|疑似|⚠/.test(text)) return 'tone-warn'
  if (/确认|复核/.test(text)) return 'tone-danger'
  if (/报告|完成|✅/.test(text)) return 'tone-done'
  if (/工单/.test(text)) return 'tone-ticket'
  return ''
}

async function enterScreen() {
  try { await document.documentElement.requestFullscreen() } catch { /* 拒绝全屏时仍显示大屏布局 */ }
}
function exitScreen() {
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {})
  view.value = 'home'
}
watch(view, v => {
  if (v === 'screen') enterScreen()
  else if (document.fullscreenElement) document.exitFullscreen().catch(() => {})
})

// —— 首页：状态概览与模块入口 ——
const homeStats = computed(() => ({
  pending: handleStats.value.pending,
  processing: handleStats.value.processing,
  resolved: handleStats.value.resolved,
  total: anomalies.value.length,
}))
const homeRecentLogs = computed(() => cmdLog.value.slice(-3).reverse().map(l => l.text))

// 模型配置状态（首页徽标与问候条用；保存配置后刷新页面同步）
const modelConfigured = ref(false)
onMounted(async () => {
  try {
    const r = await fetch(`${API}/api/config/model`, { signal: AbortSignal.timeout(3000) })
    if (r.ok) modelConfigured.value = !!(await r.json()).configured
  } catch { /* 后端离线按未配置处理 */ }
})

function onHomeEnter(v) {
  view.value = v
}

// 首页一键全面体检：全园快速巡逻（切到实时巡检看过程）
function onQuickPatrol() {
  view.value = 'patrol'
  if (!missionIdle.value) { ElMessage.info('当前任务进行中，先看实时巡检'); return }
  zoneIds.value = zoneList.value.map(z => z.id)
  patrolMode.value = 'quick'
  startPatrol()
}

function startPatrol() {
  // 真机模式任务进行中：按钮变急停（安全优先，真机必须可随时停）
  if (isReal.value && !missionIdle.value) { dispatch('stop', {}); return }
  dispatch('patrol', { zoneIds: zoneIds.value, mode: patrolMode.value })
}

function recheckAll() { dispatch('recheck', { all: true }) }

function openEvidence(a) {
  // 弹窗需要照片与帧说明：异常自带元数据优先（真机帧 / AI 注入），无照片时弹窗显示占位
  const f = currentScene.value.findings?.find(x => x.type === a.type)
  activeAnomaly.value = {
    ...a,
    frameRef: a.frameRef ?? f?.frameRef,
    frameTitle: a.frameTitle ?? f?.frameTitle,
    frameDesc: a.frameDesc ?? f?.frameDesc,
  }
  eviDialogRef.value?.open()
}

watch(speed, (v) => {
  if (adapter.value) adapter.value.speed = v
})

const routeShown = computed(() => patrolProgress.value || 0)

function fmtTs(ts) {
  const d = new Date(ts)
  return `${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}
function typeColor(t) { return anomalyMeta(currentScene.value, t).color }
function typeIcon(t) { return anomalyMeta(currentScene.value, t).icon }

// ---------- 巡检报告导出 PDF ----------
// 图片 URL（静态 /frames 或 blob:）→ base64（失败返回 null）
async function imgToB64(url) {
  if (!url) return null
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(5000) })
    if (!r.ok) return null
    const blob = await r.blob()
    return await new Promise(resolve => {
      const fr = new FileReader()
      fr.onload = () => resolve(String(fr.result).split(',')[1] ?? null)
      fr.onerror = () => resolve(null)
      fr.readAsDataURL(blob)
    })
  } catch {
    return null
  }
}

async function exportReport() {
  if (exporting.value) return
  exporting.value = true
  try {
    // findings 以 anomalies 为主（含 AI 注入项）；无 anomalies 时用报告数据
    const list = anomalies.value.length
      ? anomalies.value
      : (report.value ?? []).map((f, i) => ({
          id: `rep-${i}`, type: f.type, label: f.label, near: f.place,
          confidence: f.conf, stage: 'confirmed', evidence: f.evidence,
          source: 'sim', frameRef: f.frameRef, frameTitle: f.frameTitle, frameDesc: f.frameDesc,
        }))
    // 逐条取证据照片（近景 + 无人机复核帧）
    const findings = await Promise.all(list.map(async a => {
      const f = currentScene.value.findings?.find(x => x.type === a.type)
      const frameRef = a.frameRef ?? f?.frameRef
      const [photoB64, droneB64] = await Promise.all([
        imgToB64(frameRef),
        a.source === 'real-ai' ? null   // 真机异常无无人机复核帧（AI 直接确认）
          : a.stage === 'confirmed' ? imgToB64(currentScene.value.droneFrame?.ref ?? DRONE_FRAME_REF) : null,
      ])
      return {
        label: a.label, type: a.type, near: a.near, confidence: a.confidence, stage: a.stage,
        evidence: a.evidence, source: a.source ?? 'sim',
        handle: a.handle,
        photoB64, photoTitle: a.frameTitle ?? f?.frameTitle, photoDesc: a.frameDesc ?? f?.frameDesc,
        droneB64,
      }
    }))
    const body = {
      sceneName: currentScene.value.name,
      scope: isReplay.value ? '西南分区（真实回放）' : scopeText.value,
      mode: isReplay.value ? '回放模式' : PATROL_MODES[patrolMode.value].label,
      source: modeName.value,
      findings,
    }
    const r = await fetch(`${API}/api/report/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(30000),
    })
    if (!r.ok) {
      const err = await r.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${r.status}`)
    }
    // 下载
    const blob = await r.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    const ts = new Date()
    const pad = n => String(n).padStart(2, '0')
    a.download = `smartpatrol-report-${ts.getFullYear()}${pad(ts.getMonth() + 1)}${pad(ts.getDate())}-${pad(ts.getHours())}${pad(ts.getMinutes())}.pdf`
    a.click()
    URL.revokeObjectURL(a.href)
    ElMessage.success(`巡检报告已导出（${findings.length} 处异常）`)
  } catch (e) {
    ElMessage.error('导出失败：' + e.message + '（请确认识别服务已启动）')
  } finally {
    exporting.value = false
  }
}
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; }
html, body, #app { height: 100%; }
</style>

<style scoped>
/* ---------- 浅色主题（默认） ---------- */
.app { padding: 14px 18px 10px; background: linear-gradient(180deg, #f4f7fa 0%, #eef2f5 100%); min-height: 100vh; }
.header { display: flex; align-items: center; gap: 14px; padding: 10px 6px 18px; }
.logo { font-size: 26px; font-weight: 800; color: #1f2d3d; }
.logo span { color: #409eff; font-size: 18px; }
.subtitle { color: #909399; font-size: 13px; flex: 1; }
.header-right { display: flex; gap: 10px; align-items: center; }
.view-nav { padding: 0 6px 14px; }
.back-home {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 18px; border-radius: 8px; border: 1px solid #dcdfe6;
  background: #fff; color: #606266; font-size: 13px; cursor: pointer; transition: all .2s;
}
.back-home:hover { color: #409eff; border-color: #409eff; box-shadow: 0 2px 10px rgba(64,158,255,.15); }
.main { display: flex; gap: 18px; align-items: stretch; min-height: calc(100vh - 238px); }
.map-panel { flex: 1 1 auto; min-width: 0; padding: 14px; border-radius: 12px; background: #fff; box-shadow: 0 2px 12px rgba(0,0,0,0.08), inset 0 0 0 1px rgba(31,45,61,0.04); display: flex; align-items: center; justify-content: center; }
/* contain 自适应：画布在容器内等比最大化（max-width/max-height + auto），点击坐标已做缩放补偿 */
.map-panel :deep(.park-map-wrap) { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
.map-panel :deep(canvas) { max-width: 100%; max-height: 100%; width: auto; height: auto; }
.side { width: 460px; flex: none; display: flex; flex-direction: column; gap: 16px; }
/* 侧栏多板块均匀分布：控制卡自然高，命令流与报告卡弹性瓜分剩余高度 */
.ctrl-card { flex: none; }
.log-card { flex: 1 1 0; display: flex; flex-direction: column; min-height: 150px; }
.log-card :deep(.el-card__body) { flex: 1; display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.report-card { flex: 1.6 1 0; display: flex; flex-direction: column; min-height: 170px; }
.report-card :deep(.el-card__body) { flex: 1; overflow-y: auto; min-height: 0; }
.status-line { display: flex; justify-content: space-between; margin-top: 10px; color: #909399; font-size: 13px; }
.battery { color: #67c23a; font-weight: 600; }
.mode-tip { margin-top: 8px; font-size: 12px; color: #909399; }
.log-count { margin-left: 8px; color: #909399; font-size: 12px; }
.cmd-stream { flex: 1; overflow-y: auto; font-size: 12px; }
.log-line { display: flex; gap: 8px; padding: 3px 0; border-bottom: 1px dashed #f0f0f0; animation: fade-in .3s; }
.log-ts { color: #c0c4cc; flex: none; }
.log-text { color: #606266; }
.log-empty { color: #c0c4cc; text-align: center; padding: 20px 0; }
.ok-badge { margin-left: 10px; color: #67c23a; font-size: 13px; }
.finding { background: #f8fafc; border-left: 4px solid #409eff; border-radius: 6px; padding: 10px 12px; margin-bottom: 10px; animation: fade-in .4s; }
.f-head { display: flex; align-items: center; gap: 8px; }
.f-icon { font-size: 18px; }
.f-place { color: #606266; font-size: 13px; margin: 4px 0 2px; }
.view-evi { color: #409eff; font-size: 12px; }
.finding.clickable { cursor: pointer; }
.finding.clickable:hover { background: #eef5ff; box-shadow: 0 2px 8px rgba(64,158,255,0.15); }
.zone-row { display: flex; align-items: center; gap: 8px; }
.zone-label { font-size: 13px; color: #909399; flex: none; }
.player-row { display: flex; gap: 8px; }
.player-row .el-button { margin: 0; }
.zone-tags { display: flex; flex-wrap: wrap; gap: 6px; flex: 1; }
.zone-tags.disabled { opacity: 0.55; pointer-events: none; }
/* 真机连接面板 */
.conn-panel { border: 1px solid #dcdfe6; border-radius: 8px; padding: 10px 12px 8px; margin-bottom: 12px; background: #f8fafc; }
.conn-head { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #606266; }
.conn-dot { width: 9px; height: 9px; border-radius: 50%; background: #c0c4cc; flex: none; }
.conn-dot.connected { background: #67c23a; box-shadow: 0 0 8px rgba(103,194,58,.8); animation: pulse 1.6s infinite; }
.conn-dot.connecting { background: #e6a23c; animation: pulse 0.8s infinite; }
.conn-dot.error { background: #f56c6c; }
.conn-dev { margin-left: auto; color: #409eff; font-size: 12px; }
.conn-row { display: flex; gap: 8px; margin-top: 8px; }
.conn-row > .el-input { flex: 1; }
.conn-panel code { background: #eef2f5; padding: 1px 5px; border-radius: 4px; font-size: 11px; }
@keyframes pulse { 50% { opacity: 0.45; } }
.phase-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #c0c4cc; margin-right: 6px; }
.phase-dot.patrol { background: #409eff; box-shadow: 0 0 6px rgba(64,158,255,.8); }
.phase-dot.detect { background: #e6a23c; box-shadow: 0 0 6px rgba(230,162,60,.8); }
.phase-dot.recheck { background: #8e44ad; box-shadow: 0 0 6px rgba(142,68,173,.8); }
.phase-dot.report { background: #67c23a; box-shadow: 0 0 6px rgba(103,194,58,.8); }
.f-evi { color: #909399; font-size: 12px; line-height: 1.5; }
.f-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 6px; padding-top: 6px; border-top: 1px dashed #ebeef5; }
.ticket-stats { display: flex; gap: 8px; margin-bottom: 10px; }
.ts-item { font-size: 12px; padding: 2px 10px; border-radius: 10px; font-weight: 600; }
.ts-item.warning { color: #e6a23c; background: #fdf6ec; }
.ts-item.primary { color: #409eff; background: #ecf5ff; }
.ts-item.success { color: #67c23a; background: #f0f9eb; }
.footer { text-align: center; color: #909399; font-size: 12px; padding: 26px 0 10px; }
@keyframes fade-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

/* ---------- 值守大屏（值班室全屏模式） ---------- */
.screen-view {
  position: fixed; inset: 0; z-index: 300; display: flex; flex-direction: column;
  background: radial-gradient(ellipse at 20% 0%, #10233c 0%, #0b1622 45%, #081018 100%);
}
.screen-top { display: flex; align-items: center; gap: 18px; padding: 14px 28px; border-bottom: 1px solid #1d3350; background: rgba(8, 18, 32, 0.92); }
.screen-brand { font-size: 24px; font-weight: 800; color: #e8f0ff; text-shadow: 0 0 18px rgba(64, 158, 255, 0.5); }
.screen-brand span { color: #409eff; font-size: 15px; font-weight: 600; margin-left: 8px; }
.screen-meta { display: flex; gap: 10px; flex: 1; }
.chip { background: #14273d; color: #8fb0d0; border: 1px solid #1d3350; padding: 4px 14px; border-radius: 14px; font-size: 13px; white-space: nowrap; }
.chip.clock { color: #7fd4e8; font-family: Consolas, 'Courier New', monospace; letter-spacing: 1px; }
.screen-stats { display: flex; gap: 14px; }
.stat { display: flex; flex-direction: column; align-items: center; background: #0e1a29; border: 1px solid #1d3350; border-radius: 10px; padding: 6px 18px; min-width: 74px; transition: all .3s; }
.stat b { font-size: 26px; line-height: 1.15; font-family: Consolas, 'Courier New', monospace; }
.stat.warn b { color: #e6a23c; text-shadow: 0 0 12px rgba(230, 162, 60, 0.45); }
.stat.proc b { color: #409eff; text-shadow: 0 0 12px rgba(64, 158, 255, 0.45); }
.stat.done b { color: #67c23a; text-shadow: 0 0 12px rgba(103, 194, 58, 0.45); }
.stat.total b { color: #8fb0d0; }
.stat span { font-size: 11px; color: #5d7a99; letter-spacing: 2px; }
/* 有待处理告警时：警示卡片发光强调（指挥中心告警优先级） */
.stat.warn.alert { border-color: #e6a23c; box-shadow: 0 0 18px rgba(230, 162, 60, 0.35); animation: stat-pulse 1.6s infinite; }
@keyframes stat-pulse { 50% { box-shadow: 0 0 28px rgba(230, 162, 60, 0.55); } }
.screen-exit {
  border: 1px solid #1d3350; background: #14273d; color: #9fb8d4; border-radius: 8px;
  padding: 8px 16px; font-size: 13px; cursor: pointer; transition: all .15s; white-space: nowrap;
}
.screen-exit:hover { background: #1d3350; color: #cfe0f5; }
.screen-map { flex: 1; display: flex; gap: 18px; padding: 18px 28px; overflow: hidden; align-items: center; justify-content: center; }
.screen-map :deep(canvas) { max-width: 100%; max-height: 100%; height: auto; width: auto; border-radius: 10px; box-shadow: 0 0 40px rgba(64, 158, 255, 0.18); }
.screen-side { width: 320px; flex: none; display: flex; flex-direction: column; gap: 14px; align-self: stretch; max-height: 100%; }
.panel-block { background: rgba(14, 26, 41, 0.92); border: 1px solid #1d3350; border-radius: 10px; padding: 12px 16px; }
.panel-block.grow { flex: 1; overflow: hidden; display: flex; flex-direction: column; min-height: 0; }
.pb-title { color: #5d7a99; font-size: 12px; letter-spacing: 3px; margin-bottom: 10px; }
.pb-body { color: #cfe0f5; font-size: 15px; display: flex; align-items: center; gap: 8px; }
.pb-body.sub { color: #67c23a; margin-top: 8px; font-size: 13px; }
.pb-body.feed { display: block; overflow-y: auto; font-size: 12.5px; color: #9fb8d4; }
.pb-body.feed::-webkit-scrollbar { width: 6px; }
.pb-body.feed::-webkit-scrollbar-thumb { background: #1d3350; border-radius: 3px; }
.pb-body.feed::-webkit-scrollbar-track { background: transparent; }
.feed-line { padding: 6px 0; border-bottom: 1px dashed #14273d; line-height: 1.5; animation: fade-in .3s; }
.feed-line.tone-warn { color: #e6a23c; }
.feed-line.tone-danger { color: #ff8c7a; }
.feed-line.tone-done { color: #67c23a; }
.feed-line.tone-ticket { color: #7fd4e8; }
.feed-empty { color: #3a506b; text-align: center; padding: 30px 0; }
.screen-side .phase-dot { margin-right: 0; }

/* ---------- 深色指挥中心主题 ---------- */
.app[data-theme='dark'] { background: radial-gradient(ellipse at 20% 0%, #10233c 0%, #0b1622 45%, #081018 100%); }
.app[data-theme='dark'] .logo { color: #e8f0ff; text-shadow: 0 0 18px rgba(64,158,255,0.5); }
.app[data-theme='dark'] .subtitle { color: #5d7a99; }
.app[data-theme='dark'] .map-panel { background: #0e1a29; box-shadow: 0 0 24px rgba(64,158,255,0.15), inset 0 0 0 1px rgba(64,158,255,0.08); border-radius: 12px; }
.app[data-theme='dark'] :deep(.el-card) { background: linear-gradient(160deg, #12233a 0%, #101d2d 100%); border: 1px solid #1d3350; border-radius: 10px; box-shadow: 0 4px 18px rgba(0,0,0,0.35); }
.app[data-theme='dark'] :deep(.el-card__header) { border-bottom-color: #1d3350; color: #cfe0f5; }
.app[data-theme='dark'] :deep(.el-card__body) { color: #9fb8d4; }
.app[data-theme='dark'] .back-home { background: #101d2d; border-color: #1d3350; color: #8fb0d0; }
.app[data-theme='dark'] .back-home:hover { color: #79bbff; border-color: #409eff; box-shadow: 0 2px 10px rgba(64,158,255,.2); }
.app[data-theme='dark'] .status-line, .app[data-theme='dark'] .mode-tip,
.app[data-theme='dark'] .f-place, .app[data-theme='dark'] .log-text { color: #9fb8d4; }
.app[data-theme='dark'] .f-evi, .app[data-theme='dark'] .log-ts, .app[data-theme='dark'] .log-count { color: #5d7a99; }
.app[data-theme='dark'] .f-foot { border-top-color: #14273d; }
.app[data-theme='dark'] .ts-item.warning { background: rgba(230,162,60,.12); }
.app[data-theme='dark'] .ts-item.primary { background: rgba(64,158,255,.12); }
.app[data-theme='dark'] .ts-item.success { background: rgba(103,194,58,.12); }
.app[data-theme='dark'] .finding { background: #0e1a29; border-radius: 8px; box-shadow: inset 0 0 0 1px rgba(64,158,255,0.07); }
.app[data-theme='dark'] .finding.clickable:hover { background: #14273d; box-shadow: 0 0 16px rgba(64,158,255,0.18); }
.app[data-theme='dark'] .log-line { border-bottom-color: #14273d; }
.app[data-theme='dark'] .log-empty { color: #3a506b; }
.app[data-theme='dark'] .cmd-stream::-webkit-scrollbar { width: 6px; }
.app[data-theme='dark'] .cmd-stream::-webkit-scrollbar-thumb { background: #1d3350; border-radius: 3px; }
.app[data-theme='dark'] .footer { color: #3a506b; }
.app[data-theme='dark'] :deep(.el-check-tag) { background-color: #14273d; color: #9fb8d4; }
.app[data-theme='dark'] :deep(.el-check-tag.is-checked) { background-color: #409eff; color: #fff; }
.app[data-theme='dark'] .conn-panel { background: #0e1a29; border-color: #1d3350; }
.app[data-theme='dark'] .conn-head { color: #cfe0f5; }
.app[data-theme='dark'] .conn-panel code { background: #14273d; color: #8fb0d0; }

/* ---------- 窄窗口降级：单列（地图在上，控制区在下） ---------- */
@media (max-width: 1180px) {
  .main { flex-direction: column; min-height: 0; }
  .side { width: auto; }
  .map-panel :deep(canvas) { max-height: none; }
  .log-card, .report-card { flex: none; }
  .log-card :deep(.el-card__body), .report-card :deep(.el-card__body) { flex: none; overflow: visible; }
  .cmd-stream { max-height: 220px; }
}
</style>