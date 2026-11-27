<template>
  <div class="app" :data-theme="theme">
    <SplashScreen v-if="splashShown" @done="splashShown = false" />
    <header class="header">
      <div class="logo">🛰 智巡 <span>SmartPatrol</span></div>
      <div class="subtitle">虚实结合的园区智能巡检平台</div>
      <div class="header-right">
        <el-popover placement="bottom-end" :width="280" trigger="click">
          <template #reference>
            <button class="weather-badge" :class="weather">
              {{ WEATHER_MODES[weather].icon }} {{ WEATHER_MODES[weather].label }}
              <span class="wb-arrow">▾</span>
            </button>
          </template>
          <div class="wb-pop">
            <p class="wb-pop-title">作业环境</p>
            <div class="wb-pop-row">
              <button v-for="(w, k) in WEATHER_MODES" :key="k" class="wb-opt" :class="{ active: weather === k }" @click="weather = k">
                <span>{{ w.icon }} {{ w.label }}</span>
                <em v-if="weather === k">当前</em>
              </button>
            </div>
            <p class="wb-pop-tip">{{ weather === 'clear' ? '正常作业：全类型判定，无人机按需复核。' : weatherHint }}</p>
          </div>
        </el-popover>
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
      :weather="weather"
      :last-report="homeLastReport"
      @enter="onHomeEnter"
      @quick-patrol="onQuickPatrol"
      @re-export="exportReport"
    />

    <!-- 视图：值守大屏（值班室全屏模式） -->
    <div v-if="view === 'screen'" class="screen-view">
      <header class="screen-top">
        <div class="screen-brand">🛰 智巡 <span>SmartPatrol 值守大屏</span></div>
        <div class="screen-meta">
          <span class="chip">📍 {{ currentScene.name }}</span>
          <span class="chip">{{ modeName }}</span>
          <span class="chip weather" :class="weather">{{ WEATHER_MODES[weather].icon }} {{ WEATHER_MODES[weather].label }}</span>
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
          :scene="currentScene" :night="true" :agv="devices.agv" :agv2="devices.agv2" :drone="devices.drone"
          :route-progress="routeShown" :route="plannedRoutes.length ? null : plannedRoute" :routes="plannedRoutes" :anomalies="anomalies"
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
          :agv2="devices.agv2"
          :drone="devices.drone"
          :route-progress="routeShown"
          :route="plannedRoutes.length ? null : plannedRoute"
          :routes="plannedRoutes"
          :hotspots="hotspots"
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
            <div class="zone-row" style="margin-top: 10px">
              <span class="zone-label">车队编组</span>
              <div class="fleet-row">
                <el-switch v-model="fleetMode" size="small" active-text="双车协同" :disabled="!missionIdle || isReal || isReplay" />
                <span class="fleet-hint">{{ fleetMode ? '两台车按分区并行，任务自动对半分' : '单台车执行全部任务' }}</span>
              </div>
            </div>
            <div class="zone-row" style="margin-top: 10px">
              <span class="zone-label">热点优先</span>
              <div class="fleet-row">
                <el-switch v-model="hotspotFirst" size="small" :disabled="!missionIdle || isReal || isReplay" />
                <span class="fleet-hint">{{ hotspotHint }}</span>
              </div>
            </div>
            <div class="zone-row" style="margin-top: 10px">
              <span class="zone-label">作业环境</span>
              <el-radio-group v-model="weather" size="small">
                <el-radio-button v-for="(w, k) in WEATHER_MODES" :key="k" :value="k">{{ w.icon }} {{ w.label }}</el-radio-button>
              </el-radio-group>
            </div>
            <div v-if="weather !== 'clear'" class="weather-tip">{{ weatherHint }}</div>
            <div class="ctrl-btn-row">
              <el-button :type="startBtn.type" size="large" style="flex: 1.6"
                :disabled="startBtn.disabled" @click="startPatrol">
                {{ startBtn.text }}
              </el-button>
              <el-button size="large" style="flex: 1" :disabled="recheckBtn.disabled" @click="recheckAll">
                {{ recheckBtn.text }}
              </el-button>
            </div>
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
          <el-collapse class="ctrl-more">
            <el-collapse-item name="more" title="更多设置与说明">
              <el-slider v-if="!isReal" v-model="speed" :min="0.5" :max="4" :step="0.5" style="margin: 2px 0 0" />
              <div class="mode-tip" v-if="!isReplay">{{ modeDesc }}</div>
              <div class="mode-tip">当前数据源：<b>{{ modeName }}</b></div>
              <div class="mode-tip" v-if="!isReal && !isReplay">提示：真值异常位于 {{ truthZonesText }}，其余分区巡逻将报告“未发现异常”</div>
            </el-collapse-item>
          </el-collapse>
          <div class="ctrl-status">
            <span class="phase-dot" :class="phase"></span>
            <b>{{ phaseLabel }}</b>
            <template v-if="!isReplay"><span class="cs-sep">·</span><span>{{ scopeText }}</span></template>
            <span class="cs-sep">·</span>
            <span class="battery">
              电量 {{ devices.agv.battery }}%<template v-if="devices.agv2.enabled"> · 2号 {{ devices.agv2.battery }}%</template>
            </span>
            <span class="cs-sep">·</span>
            <span>{{ isReplay ? '回放倍速' : '速度' }} {{ speed }}x</span>
          </div>
          <div class="mode-tip" v-if="isReal">真机模式：异常由 AI 识别摄像头画面产生，点击报告可查看实拍证据</div>
        </el-card>

        <el-card class="log-card" :class="{ collapsed: !logOpen }">
          <template #header>
            <el-switch v-model="logOpen" size="small" class="log-switch" @click.stop />
            <b class="log-title" @click="logOpen = !logOpen">命令流</b>
            <span class="log-count">{{ cmdLog.length }}</span>
            <span v-if="!logOpen && latestLog" class="log-latest" @click="logOpen = true">
              {{ cmdKind(latestLog.text).icon }} {{ latestLog.text }}
            </span>
          </template>
          <div v-show="logOpen" class="cmd-stream">
            <div v-for="(l, i) in cmdTimeline" :key="l.ts + '-' + i" class="log-line" :class="[cmdKind(l.text).cls, { 'round-start': l.round }]">
              <span class="log-ts">{{ fmtTs(l.ts) }}</span>
              <span class="log-ic" :title="cmdKind(l.text).label">{{ cmdKind(l.text).icon }}</span>
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
            <!-- 摘要条：进度 + 关键数字（异常数 / 已复核 / 已处置），清单可展开 -->
            <div class="rep-summary" @click="listOpen = !listOpen" role="button" :aria-expanded="listOpen">
              <div class="rs-bar">
                <div class="rs-fill" :style="{ width: repProgress }"></div>
              </div>
              <div class="rs-nums">
                <span>发现 <b>{{ anomalies.length }}</b></span>
                <span>已复核 <b>{{ confirmedCount }}</b></span>
                <span>已处置 <b>{{ handleStats.resolved }}</b></span>
                <span class="rs-toggle">{{ listOpen ? '收起清单 ▴' : `展开 ${anomalies.length} 处 ▾` }}</span>
              </div>
            </div>
            <div v-show="listOpen" class="finding-list">
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
import { useMcpBridge } from './composables/useMcpBridge'
import { PATROL_MODES } from './parkData.js'
import { archiveRound, computeHotspots, seedDemoHistoryIfEmpty, historyRecords } from './composables/useHotspots'
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
// 车队编组：双车协同（分区对半分，两台车并行巡逻）
const fleetMode = ref(false)
// 热点优先：按历史工单热度重排定点详查顺序（地图叠加热力层）
const hotspotFirst = ref(false)
const roundNo = ref(1)
// 点位坐标（取当前场景异常真值点位；换场景自动失效）
const hotspotPoints = computed(() => (currentScene.value.anomalies ?? [])
  .filter(a => a.near)
  .map(a => {
    const dev = currentScene.value.devices.find(d => d.id === a.near)
    // 与工单记录的 near 同源：优先取场景证据包的地点描述（如「bin-3 桶旁」）
    const f = (currentScene.value.findings ?? []).find(x => x.type === a.type)
    const near = f?.place ?? dev?.label ?? a.near
    const x = dev ? dev.x : a.x + (a.w ?? 0) / 2
    const y = dev ? dev.y : a.y + (a.h ?? 0) / 2
    return { near, x, y }
  }))
const hotspots = computed(() => computeHotspots(hotspotPoints.value, 8))
// 热点地点描述 → 设备 id（适配器按 placeId 排序检查点）
const hotspotIds = computed(() => hotspots.value
  .map(h => hotspotPoints.value.find(p => p.near === h.near))
  .filter(Boolean)
  .map(p => (currentScene.value.anomalies ?? []).find(a => {
    const dev = currentScene.value.devices.find(d => d.id === a.near)
    const f = (currentScene.value.findings ?? []).find(x => x.type === a.type)
    return (f?.place ?? dev?.label ?? a.near) === p.near
  })?.near)
  .filter(Boolean))
const demoHotspot = ref(false)   // 是否仍在使用初始示例历史（界面如实标注）
const hotspotHint = computed(() => {
  if (!hotspots.value.length) return '暂无历史工单，跑两轮巡检后自动生成热点'
  const top = hotspots.value.slice(0, 3).map(h => `${h.near}×${h.count}`).join('、')
  const tag = demoHotspot.value ? '（含示例数据）' : ''
  return `历史高频点位：${top}${tag}${hotspotFirst.value ? '（本轮优先检查）' : ''}`
})
// 作业环境（雨天自适应：影响助手策略、无人机复核与报告标注）
const weather = ref('clear')
const WEATHER_MODES = {
  clear: { label: '晴', icon: '☀', hint: '' },
  rain: { label: '小雨', icon: '🌦', hint: '小雨：烟头只查雨棚连廊等遮蔽处，不判植被缺水，绿地积水按积水内涝判' },
  storm: { label: '大雨', icon: '🌧', hint: '大雨：无人机复核暂停；判积水内涝、通道占用、排水口堵塞，不判缺水与烟头' },
}
const weatherHint = computed(() => WEATHER_MODES[weather.value]?.hint ?? '')
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

// —— 巡检报告卡：摘要 + 可展开清单 ——
const listOpen = ref(false)   // 异常清单默认折叠（摘要优先，细节按需展开）
const confirmedCount = computed(() => anomalies.value.filter(a => a.stage === 'confirmed').length)
const repProgress = computed(() => {
  if (!anomalies.value.length) return '0%'
  // 处置完成度：已处置 / 总数（进度条填充）
  return Math.round((handleStats.value.resolved / anomalies.value.length) * 100) + '%'
})

// —— AI 巡检助手：平台运行状态上报（供意图解析） ——
const assistantContext = computed(() => ({
  sceneId: currentScene.value.id, sceneName: currentScene.value.name,
  scenes: sceneList.value.map(s => ({ id: s.id, name: s.name })),
  zones: zoneList.value,
  mode: dsMode.value, phase: phase.value, patrolMode: patrolMode.value,
  weather: weather.value, weatherLabel: WEATHER_MODES[weather.value].label,
  fleet: { enabled: fleetMode.value, cars: devices.agv2.enabled ? 2 : 1, battery2: Math.round(devices.agv2.battery) },
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
      else zoneIds.value = zoneList.value.map(z => z.id)   // 助手未指定分区 = 全部分区（与提示词语义一致）
      if (args.mode && PATROL_MODES[args.mode]) patrolMode.value = args.mode
      // 助手明确要求双车协同时，自动打开编组开关（分区不足时补齐为全园）
      if (args.fleet === 2) {
        fleetMode.value = true
        if (zoneIds.value.length < 2) zoneIds.value = zoneList.value.map(z => z.id)
      }
      if (args.hotspot) hotspotFirst.value = true
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
    } else if (type === 'workorder') {
      // MCP/助手工单流转：指定异常的处置状态（pending → processing → resolved）
      const a = anomalies.value.find(x => x.id === args.anomalyId)
      if (!a) { ElMessage.warning(`未找到异常 ${args.anomalyId}`); return }
      if (!['pending', 'processing', 'resolved'].includes(args.to)) { ElMessage.warning(`非法状态 ${args.to}`); return }
      dispatch('handle', { anomalyId: a.id, to: args.to })
    }
  } catch (e) {
    ElMessage.error('助手动作执行失败：' + (e.message ?? e))
  }
}

// —— MCP 桥接：状态上报 + 指令执行（Claude/Cursor/TeleAgent 等标准 MCP 客户端指挥平台） ——
useMcpBridge({
  // 平台快照（与内置助手上下文同源，额外补 id/坐标/证据等 MCP 查询所需字段）
  source: () => ({
    scene: { id: currentScene.value.id, name: currentScene.value.name },
  mode: dsMode.value, phase: phase.value, patrolMode: patrolMode.value,
  weather: weather.value, weatherLabel: WEATHER_MODES[weather.value].label,
    battery: Math.round(devices.agv.battery),
    fleet: { enabled: !!devices.agv2.enabled, battery2: Math.round(devices.agv2.battery),
             pos2: { x: +devices.agv2.x.toFixed(1), y: +devices.agv2.y.toFixed(1) } },
    position: { x: +devices.agv.x.toFixed(1), y: +devices.agv.y.toFixed(1) },
    agvStatus: devices.agv.status,
    zones: zoneList.value,
    anomalies: anomalies.value.map(a => ({
      id: a.id, type: a.type, label: a.label, near: a.near,
      zoneName: zoneList.value.find(z => z.id === a.zone)?.name,
      confidence: a.confidence, stage: a.stage,
      handleStatus: a.handle?.status ?? 'pending', evidence: a.evidence,
    })),
    stats: handleStats.value, reportGenerated: !!report.value,
  }),
  watchTargets: [dsMode, phase, patrolMode, weather, fleetMode, anomalies, devices, report],
  actionExecutor: onAssistantAction,   // 与 AI 助手同一套动作链（含 workorder）
})
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
  if (weather.value === 'storm') return { disabled: true, text: '🌧 大雨暂停无人机复核，转人工确认' }
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

// 双车协同：按与适配器一致的奇偶拆分，为每台车各画一条路线（避免两车偏离同一条线）
const plannedRoutes = computed(() => {
  if (isReplay.value || !fleetMode.value || zoneIds.value.length < 2) return []
  const even = zoneIds.value.filter((_, i) => i % 2 === 0)
  const odd = zoneIds.value.filter((_, i) => i % 2 === 1)
  return [
    { points: buildMission(currentScene.value, even, patrolMode.value).route, color: '#1f8fff' },
    { points: buildMission(currentScene.value, odd, patrolMode.value).route, color: '#17b98c' },
  ]
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

// 命令流卡片收纳：默认展开；新任务开始时自动展开（过程可追溯），空闲可收起只留最新一条
const logOpen = ref(true)
const latestLog = computed(() => cmdLog.value[cmdLog.value.length - 1] ?? null)
watch(phase, v => {
  if (v === 'patrol') logOpen.value = true   // 新一轮任务开始 → 自动展开
})

// 时间线视图：倒序展示时标记「组首」（正序视角中的新一轮任务），配合缩进形成视觉归组
// round=false → 组首（新一轮任务开头，正序视角），round=true → 同轮内
const cmdTimeline = computed(() => {
  const list = cmdLog.value.slice(-60).reverse()
  // 先在正序上计算每行是否属于某轮
  const inRound = new Array(list.length).fill(false)
  let open = false
  for (let j = list.length - 1; j >= 0; j--) {
    if (isRoundStart(list[j].text)) { open = true; inRound[j] = true }
    else if (open && /本轮.*完成|生成巡检报告|返回停靠点/.test(list[j].text)) { inRound[j] = true; open = false }
    else inRound[j] = open
  }
  // 倒序视角：非组首 → 缩进
  return list.map((l, i) => ({ ...l, round: inRound[i] }))
})

// 情报行语义染色（告警/确认/完成/工单一目了然）
function feedTone(text) {
  if (/发现|疑似|⚠/.test(text)) return 'tone-warn'
  if (/确认|复核/.test(text)) return 'tone-danger'
  if (/报告|完成|✅/.test(text)) return 'tone-done'
  if (/工单/.test(text)) return 'tone-ticket'
  return ''
}

// —— 命令流时间线：按阶段分类（图标 + 色系），一轮任务内缩进归组 ——
const CMD_KINDS = [
  { re: /(收到|规划).*(任务|路线)|前往|返回停靠点|已到达|补给/, icon: '🚗', cls: 'k-move', label: '行车' },
  { re: /停靠.*检查|环视拍照|拍照识别|检查完成/, icon: '🔍', cls: 'k-check', label: '识别' },
  { re: /发现|疑似|⚠|待复核|无人机.*(复查|复核|飞往)/, icon: '🚁', cls: 'k-recheck', label: '复核' },
  { re: /工单更新|标记处置|派单/, icon: '🧾', cls: 'k-ticket', label: '工单' },
  { re: /报告|生成巡检|本轮.*完成/, icon: '📄', cls: 'k-report', label: '报告' },
  { re: /雨|天气|🌧|🌦/, icon: '🌧', cls: 'k-weather', label: '环境' },
  { re: /就绪|充电|电量/, icon: '⚙', cls: 'k-sys', label: '系统' },
]
function cmdKind(text) {
  for (const k of CMD_KINDS) if (k.re.test(text)) return k
  return { icon: '•', cls: 'k-misc', label: '其他' }
}
// 一轮任务的边界：以「收到…任务」行开启新组
function isRoundStart(text) {
  return /收到.*(任务|指令)/.test(text) && !/充电|补给/.test(text)
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

// —— 首页：上次报告快捷卡（闭环归档：发现→处置→报告→可再取） ——
const lastExport = ref(null)   // { ts, count, scene }
function rememberExport(n) {
  lastExport.value = { ts: Date.now(), count: n, scene: currentScene.value.name }
}
const homeLastReport = computed(() => {
  if (!lastExport.value) return null
  const d = new Date(lastExport.value.ts)
  const pad = n => String(n).padStart(2, '0')
  return {
    time: `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`,
    count: lastExport.value.count,
    scene: lastExport.value.scene,
  }
})

// 模型配置状态（首页徽标与问候条用；保存配置后刷新页面同步）
const modelConfigured = ref(false)
onMounted(async () => {
  // 热点历史：首次使用写入 3 条示例（标注为演示数据），保证热力图开箱可见
  demoHotspot.value = seedDemoHistoryIfEmpty([
    { near: 'bin-3 桶旁', type: 'litter', label: '垃圾分类违规', round: 1 },
    { near: 'bin-3 桶旁', type: 'litter', label: '垃圾分类违规', round: 2 },
    { near: 'bin-3 桶旁', type: 'litter', label: '垃圾分类违规', round: 3 },
    { near: 'bench-3 长椅旁', type: 'cigarette', label: '未熄烟头', round: 2 },
    { near: 'bench-3 长椅旁', type: 'cigarette', label: '未熄烟头', round: 3 },
    { near: 'lawn-sw 草坪', type: 'dry', label: '植被缺水', round: 3 },
  ])
  roundNo.value = (historyRecords().reduce((m, r) => Math.max(m, r.round ?? 0), 0) || 0) + 1
  try {
    const r = await fetch(`${API}/api/config/model`, { signal: AbortSignal.timeout(3000) })
    if (r.ok) modelConfigured.value = !!(await r.json()).configured
  } catch { /* 后端离线按未配置处理 */ }
})

// 每轮出报告后归档工单（供热点统计；同轮同点位去重）
watch(phase, (v) => {
  if (v !== 'report') return
  const items = anomalies.value.map(a => ({ near: a.near, type: a.type, label: a.label }))
  if (!items.length) return
  archiveRound(items, roundNo.value)
  roundNo.value += 1
  demoHotspot.value = false   // 已有真实工单入库，不再标注示例
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
  if (!missionIdle.value) return
  dispatch('patrol', {
    zoneIds: zoneIds.value, mode: patrolMode.value,
    fleet: fleetMode.value && !isReplay.value && !isReal.value ? 2 : 1,
    // 热点优先：把历史高频点位（映射为设备 id）传给适配器，定点详查会先查热点
    hotspots: hotspotFirst.value ? hotspotIds.value : undefined,
  })
  // 雨天作业：把降级策略写进命令流，让过程可追溯（也便于报告与答辩说明）
  if (weather.value === 'storm') {
    cmdLog.value.push({ ts: Date.now(), text: '🌧 大雨模式：不判缺水与烟头，重点看积水内涝/通道占用/排水口堵塞，无人机复核暂停' })
  } else if (weather.value === 'rain') {
    cmdLog.value.push({ ts: Date.now(), text: '🌦 小雨模式：烟头只查雨棚连廊等遮蔽处，绿地积水按积水内涝判' })
  }
}

function recheckAll() {
  if (weather.value === 'storm') {
    ElMessage.warning('大雨天气无人机无法起飞，请改人工确认或等雨停再复核')
    return
  }
  dispatch('recheck', { all: true })
}

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
      weather: WEATHER_MODES[weather.value].label,
      weatherNote: weather.value === 'clear' ? '' : WEATHER_MODES[weather.value].hint,
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
    rememberExport(findings.length)
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
.main { display: flex; gap: 18px; align-items: flex-start; min-height: calc(100vh - 238px); }
.map-panel { flex: 1 1 auto; min-width: 0; height: calc(100vh - 238px); position: sticky; top: 14px; padding: 14px; border-radius: 12px; background: #fff; box-shadow: 0 2px 12px rgba(0,0,0,0.08), inset 0 0 0 1px rgba(31,45,61,0.04); display: flex; align-items: center; justify-content: center; }
/* contain 自适应：画布在容器内等比最大化（max-width/max-height + auto），点击坐标已做缩放补偿 */
.map-panel :deep(.park-map-wrap) { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
.map-panel :deep(canvas) { max-width: 100%; max-height: 100%; width: auto; height: auto; }
.side { width: 460px; flex: none; display: flex; flex-direction: column; gap: 16px; }
/* 侧栏多板块均匀分布：控制卡自然高，命令流与报告卡弹性瓜分剩余高度 */
.ctrl-card { flex: none; }
/* 命令流/报告卡自然高度：内容多时页面整体拉长，卡内不再滚动 */
.log-card { flex: none; display: flex; flex-direction: column; }
.log-card :deep(.el-card__body) { flex: none; display: flex; flex-direction: column; overflow: visible; }
.report-card { flex: none; display: flex; flex-direction: column; }
.report-card :deep(.el-card__body) { flex: none; overflow: visible; }
.status-line { display: flex; justify-content: space-between; margin-top: 10px; color: #909399; font-size: 13px; }
.battery { color: #67c23a; font-weight: 600; }
.mode-tip { margin-top: 8px; font-size: 12px; color: #909399; }
.fleet-row { display: flex; align-items: center; gap: 10px; flex: 1; }
.fleet-row .fleet-hint { font-size: 11.5px; color: #909399; line-height: 1.4; }
.weather-tip {
  margin-top: 8px; padding: 7px 10px; border-radius: 8px; font-size: 12px; line-height: 1.5;
  color: #b26a00; background: #fdf6ec; border: 1px solid #f5dab1;
}
/* 顶栏环境徽章（全局开关：天气约束影响助手/报告/复核） */
.weather-badge {
  display: inline-flex; align-items: center; gap: 5px; cursor: pointer;
  border: 1px solid #dcdfe6; background: #fff; color: #606266;
  border-radius: 14px; padding: 5px 12px; font-size: 12.5px; line-height: 1; font-family: inherit;
  transition: all .18s;
}
.weather-badge:hover { border-color: #409eff; color: #409eff; }
.weather-badge .wb-arrow { font-size: 10px; color: #909399; }
.weather-badge.rain { color: #b26a00; border-color: #f0d9b8; background: #fdf6ec; }
.weather-badge.storm { color: #8a5300; border-color: #e7c88f; background: #fbeed6; }
.wb-pop-title { margin: 0 0 8px; font-size: 13px; font-weight: 600; color: #1f2d3d; }
.wb-pop-row { display: flex; gap: 6px; }
.wb-opt {
  flex: 1; display: flex; align-items: center; justify-content: space-between; gap: 4px;
  border: 1px solid #dcdfe6; background: #fff; border-radius: 8px; padding: 7px 8px;
  font-size: 12.5px; color: #606266; cursor: pointer; font-family: inherit;
}
.wb-opt.active { border-color: #409eff; color: #1f6ac0; background: #ecf5ff; }
.wb-opt em { font-style: normal; font-size: 10px; color: #909399; }
.wb-opt.active em { color: #1f6ac0; }
.wb-pop-tip { margin: 8px 0 0; font-size: 11.5px; line-height: 1.6; color: #b26a00; background: #fdf6ec; border-radius: 6px; padding: 6px 8px; }
/* 大屏环境 chip */
.screen-meta .chip.weather { color: #e6b062; }
.screen-meta .chip.weather.rain { color: #e6b062; }
.screen-meta .chip.weather.storm { color: #f0b25a; background: rgba(240,178,90,.14); }
/* 控制卡精简（评委反馈）：开始/复检并排，次要信息折叠收纳，状态合并一行 */
.ctrl-btn-row { display: flex; gap: 8px; margin-top: 10px; }
.ctrl-btn-row .el-button { margin: 0; flex: 1; white-space: normal; height: auto; min-height: 40px; padding-top: 7px; padding-bottom: 7px; }
.ctrl-more { margin-top: 10px; --el-collapse-header-height: 30px; border-top: none; border-bottom: none; }
.ctrl-more :deep(.el-collapse-item__header) { font-size: 12px; color: #909399; background: transparent; border-bottom: 1px dashed #ebeef5; }
.ctrl-more :deep(.el-collapse-item__wrap) { background: transparent; border-bottom: none; }
.ctrl-more :deep(.el-collapse-item__content) { padding-bottom: 6px; }
.ctrl-status { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 6px; margin-top: 10px; color: #909399; font-size: 13px; }
.ctrl-status b { color: #606266; }
.cs-sep { color: #dcdfe6; }
.log-count { margin-left: 8px; color: #909399; font-size: 12px; }
.cmd-stream { flex: none; font-size: 12px; }
/* 命令流收纳（折叠）：卡片压到单行高度，最新指令以摘要形式显示在标题行 */
.log-card.collapsed { --el-card-padding: 0; }
.log-card.collapsed :deep(.el-card__body) { display: none; }
.log-card :deep(.el-card__header) { display: flex; align-items: center; gap: 8px; padding: 10px 14px; }
.log-card .log-switch { margin-right: 2px; }
.log-card .log-title { cursor: pointer; user-select: none; }
.log-latest {
  flex: 1; min-width: 0; margin-left: 2px; font-size: 12px; font-weight: normal; color: #909399;
  cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.log-latest:hover { color: #606266; }
.log-line { display: flex; gap: 8px; padding: 3px 0; border-bottom: 1px dashed #f0f0f0; animation: fade-in .3s; }
.log-line.round-start { margin-top: 5px; border-top: 1px solid #ebeef5; padding-top: 6px; }
.log-line:not(.round-start) { padding-left: 10px; border-left: 2px solid #f4f6f9; margin-left: 6px; }
.log-ts { color: #c0c4cc; flex: none; }
.log-ic { flex: none; font-size: 11px; width: 16px; text-align: center; filter: grayscale(.15); }
.log-line.k-move .log-ic { filter: none; }
.log-line.k-check .log-text { color: #7a4d00; }
.log-line.k-recheck .log-text { color: #6b4fa0; }
.log-line.k-ticket .log-text { color: #2f6b3a; }
.log-line.k-report .log-text { color: #1f6ac0; font-weight: 500; }
.log-line.k-weather .log-text { color: #b26a00; background: #fdf6ec; border-radius: 4px; padding: 0 4px; }
.log-line.k-sys .log-text { color: #909399; }
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
/* 报告卡摘要条（默认折叠清单） */
.rep-summary { cursor: pointer; border: 1px solid #e4e9f0; border-radius: 8px; padding: 10px 12px; margin-bottom: 10px; background: #fafcfe; transition: border-color .18s; user-select: none; }
.rep-summary:hover { border-color: #409eff; }
.rs-bar { height: 6px; border-radius: 4px; background: #eef2f6; overflow: hidden; margin-bottom: 8px; }
.rs-fill { height: 100%; border-radius: 4px; background: linear-gradient(90deg, #67c23a, #4aa8e0); transition: width .4s; }
.rs-nums { display: flex; align-items: center; gap: 14px; font-size: 12px; color: #909399; }
.rs-nums b { color: #1f2d3d; font-size: 14px; margin-left: 2px; }
.rs-nums .rs-toggle { margin-left: auto; color: #409eff; white-space: nowrap; font-size: 12px; }
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
.app[data-theme='dark'] .ctrl-more :deep(.el-collapse-item__header) { color: #8fb0d0; border-bottom-color: #1d3350; }
.app[data-theme='dark'] .ctrl-status b { color: #cfe0f5; }
.app[data-theme='dark'] .cs-sep { color: #2c4a6b; }

/* ---------- 窄窗口降级：单列（地图在上，控制区在下） ---------- */
@media (max-width: 1180px) {
  .main { flex-direction: column; min-height: 0; }
  .side { width: auto; }
  .map-panel { position: static; height: auto; }
  .map-panel :deep(canvas) { max-height: none; }
  .log-card, .report-card { flex: none; }
  .log-card :deep(.el-card__body), .report-card :deep(.el-card__body) { flex: none; overflow: visible; }
  .cmd-stream { max-height: 220px; }
}
</style>
