// ============================================================
// useDataSource —— 数据源管理（组合式 API）
// ------------------------------------------------------------
// UI 只面对这个 composable：切换 sim/replay/real 模式、发命令、收遥测。
// 真机模式（real）：RealAdapter 通过 WebSocket 连接设备（server/sim_device.py）。
// ============================================================
import { computed, onBeforeUnmount, reactive, ref, shallowRef } from 'vue'
import { SimAdapter } from '../adapters/SimAdapter.js'
import { ReplayAdapter } from '../adapters/ReplayAdapter.js'
import { RealAdapter } from '../adapters/RealAdapter.js'
import { PARK_SCENE } from '../scenes/park.js'

export const DataSourceMode = { SIM: 'sim', REPLAY: 'replay', REAL: 'real' }

const ADAPTERS = {
  [DataSourceMode.SIM]: (scene) => new SimAdapter({ scene }),
  [DataSourceMode.REPLAY]: () => new ReplayAdapter(),
  [DataSourceMode.REAL]: (scene) => new RealAdapter({ scene }),  // 真机：WebSocket 连接设备
}

export function useDataSource() {
  const mode = ref(DataSourceMode.SIM)
  const adapter = shallowRef(null)
  const cmdCount = ref(0)

  // 遥测状态（响应式镜像）
  const devices = reactive({
    agv: { x: 30, y: 20, yaw: 0, battery: 96, status: 'idle', zone: '' },
    drone: { x: 30, y: 20, yaw: 0, active: false, battery: 100 },
  })
  const anomalies = ref([])
  const cmdLog = ref([])          // 命令日志流（最多保留 60 条）
  const phase = ref('idle')
  const report = ref(null)
  const patrolProgress = ref(0)
  const recheckBusy = ref(false)  // 无人机是否正在执行复核（按钮状态用）
  const replayInfo = ref({ state: 'ready', t: 0, duration: 0 })  // 回放播放器状态
  const realInfo = ref({ state: 'offline', text: '设备未连接', device: null })  // 真机连接状态
  const sceneRef = ref(PARK_SCENE) // 当前巡检场景

  let unsub = null

  function applyEvent(ev) {
    const { type, payload } = ev
    switch (type) {
      case 'pose': {
        if (payload.entityId === 'patrol-agv-01') {
          devices.agv.x = payload.pose.x; devices.agv.y = payload.pose.y; devices.agv.yaw = payload.pose.yaw
        } else if (payload.entityId === 'drone-01') {
          devices.drone.x = payload.pose.x; devices.drone.y = payload.pose.y
        }
        break
      }
      case 'battery': devices.agv.battery = payload.value; break
      case 'status': devices.agv.status = payload.status; break
      case 'anomaly': {
        // 快照克隆：适配器持有原始对象并就地修改，若直接存同一引用，
        // 后续 emit 替换同位置不触发响应式（computed 缓存不失效）——克隆切断共享
        const a = payload.anomaly
        const snap = { ...a, handle: a.handle ? { ...a.handle } : undefined }
        const i = anomalies.value.findIndex(x => x.id === snap.id)
        if (i >= 0) anomalies.value[i] = snap
        else anomalies.value.push(snap)
        break
      }
      case 'cmdlog': {
        cmdLog.value.push({ ts: ev.ts, text: payload.text })
        if (cmdLog.value.length > 60) cmdLog.value.splice(0, cmdLog.value.length - 60)
        cmdCount.value++
        break
      }
      case 'phase':
        phase.value = payload.phase
        // 新任务开始：清空上一轮异常与报告（sim 多轮巡逻 / replay 重放都需要）
        if (payload.phase === 'patrol') {
          anomalies.value = []
          report.value = null
          patrolProgress.value = 0
        }
        break
      case 'report': report.value = payload.findings; break
      case 'drone': devices.drone.active = payload.active; break
      case 'recheckbusy': recheckBusy.value = payload.busy; break
      case 'replay': replayInfo.value = { ...replayInfo.value, ...payload }; break
      case 'real': realInfo.value = { ...realInfo.value, ...payload }; break
      case 'progress': patrolProgress.value = payload.value; break
    }
  }

  async function switchMode(next) {
    if (!ADAPTERS[next]) throw new Error(`数据源模式 ${next} 未实现`)
    // 停旧
    if (adapter.value) { adapter.value.stop(); unsub && unsub() }
    // 重置状态（AGV/无人机归位到当前场景停靠点）
    anomalies.value = []; cmdLog.value = []; report.value = null
    phase.value = 'idle'; patrolProgress.value = 0; recheckBusy.value = false
    replayInfo.value = { state: 'ready', t: 0, duration: 0 }
    realInfo.value = { state: 'offline', text: '设备未连接', device: null }
    const dk = sceneRef.value?.dock ?? { x: 30, y: 20 }
    devices.agv = { x: dk.x, y: dk.y, yaw: 0, battery: 96, status: 'idle', zone: '' }
    devices.drone = { x: dk.x, y: dk.y, yaw: 0, active: false, battery: 100 }
    // 建新（仿真/真机吃当前场景）
    adapter.value = ADAPTERS[next](sceneRef.value)
    unsub = adapter.value.onEvent(applyEvent)
    await adapter.value.start()
    mode.value = next
  }

  /** 切换巡检场景：重建当前模式适配器，巡检状态全部重置 */
  async function setScene(scene) {
    sceneRef.value = scene
    await switchMode(mode.value)
  }

  function dispatch(type, args = {}) {
    if (!adapter.value) return
    const cmd = { id: `ui-${++cmdCount.value}`, type, args, issuedAt: performance.now(), status: 'issued' }
    adapter.value.dispatch(cmd)
    return cmd
  }

  // 进度跟踪：巡逻中由 pose 事件近似（供 UI 显示）——由 SimAdapter 内部推进
  function setProgress(p) { patrolProgress.value = p }

  // 默认启动 sim
  switchMode(DataSourceMode.SIM)

  onBeforeUnmount(() => {
    adapter.value && adapter.value.stop()
    unsub && unsub()
  })

  return {
    mode, adapter, cmdCount, scene: sceneRef,
    devices, anomalies, cmdLog, phase, report, patrolProgress, recheckBusy, replayInfo, realInfo,
    switchMode, setScene, dispatch,
    isSim: computed(() => mode.value === DataSourceMode.SIM),
    isReplay: computed(() => mode.value === DataSourceMode.REPLAY),
    isReal: computed(() => mode.value === DataSourceMode.REAL),
  }
}