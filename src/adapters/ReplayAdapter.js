// ============================================================
// ReplayAdapter —— 历史回放数据源适配器（播放器内核）
// ------------------------------------------------------------
// 数据源：省赛 AGH trace 第四轮闭环（2026-10-11 园区实录）压缩时间轴
// 能力：播放 / 暂停 / 继续 / 停止 / 拖动进度（seek 瞬时重建 t 时刻状态）
// 事件：progress（进度 0-1）+ replay（{state, t, duration} 播放器状态）
// 叙事：异常按 detected → rechecking → confirmed 推进，无人机复核后返航
// ============================================================
import { CommandType, EventType } from '../core/protocol.js'
import { PARK_SCENE } from '../scenes/park.js'

const ANOMS = PARK_SCENE.anomalies
const FINDINGS = PARK_SCENE.findings

// 回放脚本：{ t: 秒, type, payload }
// 文案原则：观众友好——讲"做了什么/看到了什么/得出什么"，专业细节放括号
const REPLAY_SCRIPT = [
  { t: 0,    type: 'cmdlog', payload: { text: '▶ 开始重放：省赛真实巡逻记录（2026-10-11 园区实录）' } },
  { t: 0.3,  type: 'phase',  payload: { phase: 'patrol' } },
  { t: 0.5,  type: 'cmdlog', payload: { text: '收到巡逻任务，规划 5 项检查：垃圾、缺水、烟头' } },
  { t: 1.0,  type: 'pose',   payload: { entityId: 'patrol-agv-01', pose: { x: 5.14, y: 23.04, yaw: 196 } } },
  { t: 1.0,  type: 'battery', payload: { value: 96 } },
  { t: 1.0,  type: 'cmdlog', payload: { text: '巡逻车出发，前往 3 号垃圾桶（实录行驶 32 秒，回放已压缩）' } },
  { t: 3.0,  type: 'cmdlog', payload: { text: '📸 到达垃圾桶，拍下第一张检查照片' } },
  { t: 3.3,  type: 'anomaly', payload: { key: 'litter' } },
  { t: 5.0,  type: 'pose',   payload: { entityId: 'patrol-agv-01', pose: { x: 9.86, y: 23.47, yaw: 11 } } },
  { t: 5.0,  type: 'battery', payload: { value: 92 } },
  { t: 5.0,  type: 'cmdlog', payload: { text: '继续前往 3 号长椅（实录行驶 10 秒）' } },
  { t: 6.5,  type: 'cmdlog', payload: { text: '📸 到达长椅，拍下第二张检查照片（这张画面里同时有三处异常）' } },
  { t: 6.8,  type: 'anomaly', payload: { key: 'cigarette' } },
  { t: 7.3,  type: 'anomaly', payload: { key: 'dry' } },
  { t: 8.0,  type: 'phase',  payload: { phase: 'recheck' } },
  { t: 8.5,  type: 'pose',   payload: { entityId: 'drone-01', pose: { x: 11.53, y: 23.23, yaw: 170 } } },
  { t: 8.5,  type: 'drone',  payload: { active: true } },
  { t: 8.5,  type: 'cmdlog', payload: { text: '无人机起飞，前往长椅上空复查（实录 9 秒到达，悬停 8 米高度）' } },
  { t: 9.0,  type: 'anomaly-stage', payload: { key: 'litter', stage: 'rechecking' } },
  { t: 9.2,  type: 'anomaly-stage', payload: { key: 'cigarette', stage: 'rechecking' } },
  { t: 9.4,  type: 'anomaly-stage', payload: { key: 'dry', stage: 'rechecking' } },
  { t: 10.0, type: 'cmdlog', payload: { text: '📸 无人机拍下俯视复查照片，与地面照片交叉确认' } },
  { t: 10.5, type: 'anomaly-stage', payload: { key: 'litter', stage: 'confirmed' } },
  { t: 10.8, type: 'anomaly-stage', payload: { key: 'cigarette', stage: 'confirmed' } },
  { t: 11.1, type: 'anomaly-stage', payload: { key: 'dry', stage: 'confirmed' } },
  { t: 11.5, type: 'report', payload: { findings: FINDINGS } },
  { t: 11.6, type: 'phase',  payload: { phase: 'report' } },
  { t: 12.0, type: 'cmdlog', payload: { text: '✅ 巡逻完成，报告已生成：共发现 3 处异常，全部经无人机复核确认' } },
  { t: 13.0, type: 'pose',   payload: { entityId: 'drone-01', pose: { x: PARK_SCENE.dock.x, y: PARK_SCENE.dock.y, yaw: 0 } } },
  { t: 14.0, type: 'drone',  payload: { active: false } },
  { t: 14.0, type: 'cmdlog', payload: { text: '🚁 无人机已返航降落，回放结束' } },
]

const DURATION = REPLAY_SCRIPT[REPLAY_SCRIPT.length - 1].t

export class ReplayAdapter {
  constructor(options = {}) {
    this.speed = options.speed ?? 1
    this.listeners = new Set()
    this.running = false
    this.entities = new Map()
    this.anomalies = []
    this.playT = 0
    this.stepIdx = 0
    this.timer = null
    this._paused = false
    this.state = 'ready'          // ready | playing | paused | done
    this._initEntities()
  }

  // 地图回放路线：dock → 各 AGV 位姿目标（供 ParkMap 画已走路径）
  get replayRoute() {
    const pts = [[PARK_SCENE.dock.x, PARK_SCENE.dock.y]]
    for (const s of REPLAY_SCRIPT) {
      if (s.type === 'pose' && s.payload.entityId === 'patrol-agv-01') {
        pts.push([s.payload.pose.x, s.payload.pose.y])
      }
    }
    return pts
  }

  get duration() { return DURATION }

  _initEntities() {
    this.entities.set('patrol-agv-01', {
      id: 'patrol-agv-01', type: 'agv', name: '巡逻 AGV',
      pose: { x: PARK_SCENE.dock.x, y: PARK_SCENE.dock.y, yaw: 0 },
      battery: 96, status: 'idle', zone: 'zone-c',
    })
    this.entities.set('drone-01', {
      id: 'drone-01', type: 'drone', name: '复核无人机',
      pose: { x: PARK_SCENE.dock.x, y: PARK_SCENE.dock.y, yaw: 0 },
      battery: 100, status: 'idle', active: false,
    })
  }

  _emit(type, payload) {
    for (const cb of this.listeners) cb({ type, payload, ts: performance.now() })
  }

  _emitReplay() {
    this._emit('replay', { state: this.state, t: this.playT, duration: DURATION })
  }

  async start() {
    this.running = true
    this._emit(EventType.COMMAND_LOG, { text: '回放模式就绪：省赛真实巡逻记录（可暂停 / 拖动进度条跳转）' })
    this._emitReplay()
  }

  stop() {
    this.running = false
    this._clearTimer()
    this._clearTweens()
  }

  onEvent(cb) { this.listeners.add(cb); return () => this.listeners.delete(cb) }
  snapshot() { return this.entities }

  // ---------- 播放器命令 ----------
  dispatch(cmd) {
    switch (cmd.type) {
      case 'play': case CommandType.PATROL: return this._play()
      case 'pause': return this._pause()
      case 'stop': return this._stop()
      case 'seek': return this._seek(cmd.args?.t ?? 0)
      case CommandType.HANDLE:
        this._emit(EventType.COMMAND_LOG, { text: '回放为历史实录，工单状态不可修改；请切到仿真/真机模式处置' })
        return
      default: this._emit(EventType.COMMAND_LOG, { text: `回放模式暂不支持命令 ${cmd.type}` })
    }
  }

  _play() {
    if (this.state === 'playing') return
    if (this.state === 'paused') {
      this._paused = false; this.state = 'playing'
      this._startTimer(); this._emitReplay()
      return
    }
    // ready / done：从头开始（done 先复位）
    if (this.state === 'done') this._resetPlayback()
    if (this.playT === 0 && this.stepIdx === 0) {
      this._emit(EventType.PHASE, { phase: 'patrol' })   // UI 清空上一轮
      this._emit(EventType.COMMAND_LOG, { text: '▶ 开始重放省赛巡逻全程' })
    }
    this._paused = false
    this.state = 'playing'
    this._startTimer()
    this._emitReplay()
  }

  _pause() {
    if (this.state !== 'playing') return
    this._paused = true
    this.state = 'paused'
    this._emitReplay()
    this._emit(EventType.COMMAND_LOG, { text: '⏸ 回放已暂停，可拖动进度条跳转' })
  }

  _stop() {
    this._clearTimer()
    this._clearTweens()
    this._resetPlayback()
    this._paused = false
    this.state = 'ready'
    // 清 UI 状态并复位（patrol 清异常列表，idle 解锁控制）
    this._emit(EventType.PHASE, { phase: 'patrol' })
    this._emit(EventType.PHASE, { phase: 'idle' })
    this._emit('progress', { value: 0 })
    this._emitReplay()
    this._emit(EventType.COMMAND_LOG, { text: '⏹ 回放已停止，可重新播放' })
  }

  // 拖动进度：瞬时重建 t 时刻状态（不播日志，直接落到结果）
  _seek(t) {
    const target = Math.max(0, Math.min(DURATION, Number(t) || 0))
    this._clearTweens()
    this._resetPlayback()
    this.playT = target
    // 清 UI 后按时间轴瞬时重建
    this._emit(EventType.PHASE, { phase: 'patrol' })
    while (this.stepIdx < REPLAY_SCRIPT.length && REPLAY_SCRIPT[this.stepIdx].t <= this.playT) {
      this._execStep(REPLAY_SCRIPT[this.stepIdx], { instant: true })
      this.stepIdx++
    }
    if (this.stepIdx >= REPLAY_SCRIPT.length) this.state = 'done'
    this._emit('progress', { value: this.playT / DURATION })
    this._emitReplay()
    this._emit(EventType.COMMAND_LOG, { text: `⏩ 已跳转到 ${target.toFixed(1)}s（第 ${this.stepIdx}/${REPLAY_SCRIPT.length} 步）` })
  }

  _resetPlayback() {
    this.playT = 0
    this.stepIdx = 0
    this.anomalies = []
    this._initEntities()
  }

  _startTimer() {
    if (this.timer) return
    this.timer = setInterval(() => {
      if (!this.running || this._paused) return
      this.playT = Math.min(DURATION, this.playT + 0.1 * this.speed)
      while (this.stepIdx < REPLAY_SCRIPT.length && REPLAY_SCRIPT[this.stepIdx].t <= this.playT) {
        this._execStep(REPLAY_SCRIPT[this.stepIdx])
        this.stepIdx++
      }
      this._emit('progress', { value: this.playT / DURATION })
      this._emitReplay()
      if (this.stepIdx >= REPLAY_SCRIPT.length && this.playT >= DURATION) {
        this._clearTimer()
        this.state = 'done'
        this._emitReplay()
      }
    }, 100)
  }

  _clearTimer() {
    if (this.timer) { clearInterval(this.timer); this.timer = null }
  }

  // ---------- 脚本步执行 ----------
  _execStep(step, { instant = false } = {}) {
    const { type, payload } = step
    switch (type) {
      case 'cmdlog':
        if (!instant) this._emit(EventType.COMMAND_LOG, payload)
        return
      case 'phase':
        this._emit(EventType.PHASE, payload)
        return
      case 'battery':
        this._emit(EventType.BATTERY, { entityId: 'patrol-agv-01', value: payload.value })
        return
      case 'report':
        this._emit(EventType.REPORT, payload)
        return
      case 'pose': {
        const e = this.entities.get(payload.entityId)
        if (!e) return
        if (instant) {
          e.pose = { ...payload.pose }
          this._emit(EventType.POSE, { entityId: payload.entityId, pose: e.pose })
        } else {
          this._tween(e, payload.pose, 1.2)
          if (payload.entityId === 'patrol-agv-01') e.status = 'moving'
        }
        return
      }
      case 'drone': {
        const d = this.entities.get('drone-01')
        if (d) { d.active = payload.active; d.status = payload.active ? 'working' : 'idle' }
        this._emit(EventType.DRONE_DEPLOY, { active: payload.active })
        return
      }
      case 'anomaly': {
        const fi = ANOMS.findIndex(a => a.type === payload.key)
        if (fi < 0) return
        const a = ANOMS[fi]
        const f = FINDINGS.find(x => x.type === a.type)
        const anomaly = {
          id: `anomaly-${a.type}-${fi}`, type: a.type, label: f.label,
          pos: { x: a.x + (a.w ?? 0) / 2, y: a.y + (a.h ?? 0) / 2 },
          rect: a.w ? { w: a.w, h: a.h } : undefined,
          confidence: f.conf * 0.75, stage: 'detected', evidence: f.evidence, near: f.place,
        }
        this.anomalies.push(anomaly)
        this._emit(EventType.ANOMALY, { anomaly })
        if (!instant) {
          this._emit(EventType.PHASE, { phase: 'detect' })
          this._emit(EventType.COMMAND_LOG, { text: `🔍 照片识别：发现${f.label}（初步判断，把握程度 ${(anomaly.confidence * 100) | 0}%）` })
        }
        return
      }
      case 'anomaly-stage': {
        const a = this.anomalies.find(x => x.type === payload.key)
        if (!a) return
        a.stage = payload.stage
        if (payload.stage === 'confirmed') {
          const f = FINDINGS.find(x => x.type === a.type)
          a.confidence = f?.conf ?? a.confidence
        }
        this._emit(EventType.ANOMALY, { anomaly: a })
        if (!instant) {
          if (payload.stage === 'rechecking') {
            this._emit(EventType.COMMAND_LOG, { text: `🚁 无人机前往复核：${a.label}` })
          } else {
            this._emit(EventType.COMMAND_LOG, { text: `✅ 复核确认：${a.label}（把握程度 ${(a.confidence * 100) | 0}%）` })
          }
        }
        return
      }
    }
  }

  // ---------- 位姿补间动画（消除回放跳变；暂停时冻结） ----------
  _tween(entity, targetPose, seconds) {
    const entityId = entity.id
    if (this._tweens?.has(entityId)) { clearInterval(this._tweens.get(entityId)) }
    ;(this._tweens ??= new Map())
    const from = { ...entity.pose }
    const to = targetPose
    let t = 0
    const total = Math.max(0.2, seconds / Math.max(0.2, this.speed))
    const handle = setInterval(() => {
      if (!this.running) { clearInterval(handle); this._tweens.delete(entityId); return }
      if (this._paused) return          // 暂停：冻结在当前位置
      t += 0.05
      const k = Math.min(1, t / total)
      const ease = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2  // easeInOutQuad
      const pose = {
        x: from.x + (to.x - from.x) * ease,
        y: from.y + (to.y - from.y) * ease,
        yaw: from.yaw + ((((to.yaw - from.yaw) % 360) + 540) % 360 - 180) * ease,
      }
      entity.pose = pose
      this._emit(EventType.POSE, { entityId, pose })
      if (k >= 1) { clearInterval(handle); this._tweens.delete(entityId) }
    }, 50)
    this._tweens.set(entityId, handle)
  }

  _clearTweens() {
    if (this._tweens) { for (const h of this._tweens.values()) clearInterval(h); this._tweens.clear() }
  }
}
