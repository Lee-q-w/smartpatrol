// ============================================================
// SimAdapter —— 仿真数据源适配器
// ------------------------------------------------------------
// 职责：接收 UI 命令（patrol/recheck/...），驱动当前场景推演，
// 产出遥测事件（位姿/电量/异常/命令日志/报告）。
//
// 场景化：巡逻路线/设备点位/异常真值全部来自 Scene JSON，
// 换场地 = 换场景，推演逻辑零改动。
//
// 任务形态：
//   巡逻范围 zoneIds：单分区 / 多分区 / 全园（按点选顺序排队）
//   巡查方式 mode：
//     quick  快速巡逻 —— 沿规划路线连续巡查（原有模式）
//     point  定点详查 —— 逐个点位停靠检查
//     sweep  环视检查 —— 到点后原地转四朝向各拍一张
//   重点复查 recheck：{anomalyId} 单点 或 {all:true} 全部，无人机中途可出动
// ============================================================
import { CommandType, EventType } from '../core/protocol.js'
import { PARK_SCENE } from '../scenes/park.js'
import {
  buildMission, getPointAnomalyMap, anomaliesByZone, findAnomalyIndexByType,
} from '../scenes/sceneSchema.js'

// 工单流转文案（未处理→处理中→已处理，可退回/重开）
export const HANDLE_TEXT = {
  pending: '退回未处理', processing: '开始处理', resolved: '完成处理',
}

export class SimAdapter {
  constructor(options = {}) {
    this.speed = options.speed ?? 1          // 播放倍速
    this.scene = options.scene ?? PARK_SCENE // 当前巡检场景
    this.listeners = new Set()
    this.running = false
    this.entities = new Map()
    this.anomalies = []
    this.tickHandle = null
    this._missionToken = 0                   // 任务令牌：新任务/停止时递增，作废旧执行链
    this._recheckBusy = false                // 无人机是否正在执行复核
    this._initEntities()
  }

  _initEntities() {
    this.entities.set('patrol-agv-01', {
      id: 'patrol-agv-01', type: 'agv', name: '巡逻 AGV',
      pose: { x: this.scene.dock.x, y: this.scene.dock.y, yaw: 0 }, battery: 96,
      status: 'idle', zone: this.scene.zones[0]?.id ?? '',
    })
    this.entities.set('drone-01', {
      id: 'drone-01', type: 'drone', name: '复核无人机',
      pose: { x: this.scene.dock.x, y: this.scene.dock.y, yaw: 0 }, battery: 100,
      status: 'idle', active: false,
    })
    this.entities.set('env-01', {
      id: 'env-01', type: 'sensor', name: '环境传感器',
      pose: { x: this.scene.dock.x + 0.5, y: this.scene.dock.y + 2, yaw: 0 }, battery: 100, status: 'idle',
    })
  }

  _emit(type, payload) {
    const ev = { type, payload, ts: performance.now() }
    for (const cb of this.listeners) cb(ev)
  }

  async start() {
    this.running = true
    this._emit(EventType.STATUS, { entityId: 'patrol-agv-01', status: 'idle' })
    this._emit(EventType.COMMAND_LOG, { text: `仿真引擎就绪（${this.scene.name} · SimAdapter）` })
  }

  stop() {
    this.running = false
    this._missionToken++
    if (this.tickHandle) { clearInterval(this.tickHandle); this.tickHandle = null }
    this._stopAnimations()
  }

  onEvent(cb) {
    this.listeners.add(cb)
    return () => this.listeners.delete(cb)
  }

  snapshot() { return this.entities }

  // ---------- 命令入口 ----------
  dispatch(cmd) {
    switch (cmd.type) {
      case CommandType.PATROL: return this._patrol(cmd)
      case CommandType.RECHECK: return this._recheck(cmd)
      case CommandType.HANDLE: return this._handle(cmd)
      case CommandType.RETURN_DOCK: return this._returnDock(cmd)
      case CommandType.GOTO: return this._goto(cmd)
      case CommandType.REPORT: return this._report(cmd)
      case 'inject-anomaly': return this._injectAnomaly(cmd)
      default: this._emit(EventType.COMMAND_LOG, { text: `未知命令 ${cmd.type}` })
    }
  }

  // 异常工单流转：未处理 pending → 处理中 processing → 已处理 resolved（可退回/重开）
  _handle(cmd) {
    const { anomalyId, to, note } = cmd.args ?? {}
    const a = this.anomalies.find(x => x.id === anomalyId)
    if (!a) {
      this._emit(EventType.COMMAND_LOG, { text: '未找到该异常工单' })
      return
    }
    if (!['pending', 'processing', 'resolved'].includes(to)) return
    a.handle = { status: to, note: note ?? a.handle?.note, at: Date.now() }
    this._emit(EventType.ANOMALY, { anomaly: a })
    const flow = { pending: '已退回待处理', processing: '已派单，开始处理', resolved: '已处置完成' }[to]
    this._emit(EventType.COMMAND_LOG, { text: `📋 工单更新：${a.label}（${a.near}）${flow}${note ? ' · ' + note : ''}` })
    this._emit(EventType.REPORT, { findings: this._findingsWithInjected() })
  }

  // AI 识别中心回填：注入真图识别的异常（直接进入报告与证据系统）
  _injectAnomaly(cmd) {
    const a = cmd.args?.anomaly
    if (!a?.type) return
    if (this.anomalies.some(x => x.type === a.type && x.source === 'ai')) {
      this._emit(EventType.COMMAND_LOG, { text: `该类型真图异常已存在（${a.label}），不重复注入` })
      return
    }
    const nearDev = this.scene.devices.find(d => a.nearDevId === d.id)
    const pos = a.pos ?? nearDev?.pos ?? { x: this.scene.dock.x + (Math.random() * 6 - 3), y: this.scene.dock.y + (Math.random() * 4 - 2) }
    const anomaly = {
      id: `anomaly-ai-${a.type}-${Date.now() % 100000}`, type: a.type, label: a.label,
      pos, confidence: a.confidence ?? 0.9, stage: 'confirmed',
      evidence: a.evidence, near: a.near ?? nearDev?.label ?? '人工标注',
      source: 'ai', frameRef: a.frameRef, frameTitle: a.frameTitle, frameDesc: a.frameDesc,
      handle: { status: 'pending', at: Date.now() },   // 新异常工单：未处理
    }
    this.anomalies.push(anomaly)
    this._emit(EventType.ANOMALY, { anomaly })
    this._emit(EventType.COMMAND_LOG, {
      text: `🤖 AI 识别中心回填：${a.label}（把握程度 ${Math.round((a.confidence ?? 0.9) * 100)}%）已进入异常库与报告`,
    })
    // 同步进报告（真图识别已是模型确认结果，无需再复核）
    this._emit(EventType.REPORT, { findings: this._findingsWithInjected() })
  }

  // 报告 = 场景演示证据包 + 注入的真图异常（去重按 type）
  _findingsWithInjected() {
    const base = (this.scene.findings ?? []).filter(f => !this.anomalies.some(a => a.source === 'ai' && a.type === f.type))
    const injected = this.anomalies
      .filter(a => a.source === 'ai')
      .map(a => ({
        type: a.type, label: a.label, place: a.near, conf: a.confidence, level: a.confidence >= 0.9 ? 'high' : 'medium',
        evidence: a.evidence, frameRef: a.frameRef, frameTitle: a.frameTitle, frameDesc: a.frameDesc,
        handle: a.handle,
      }))
    return [...base, ...injected]
  }

  _zoneName(id) {
    return this.scene.zones.find(z => z.id === id)?.name ?? id
  }

  // ---------- 巡逻任务（多分区 + 三种巡查方式） ----------
  async _patrol(cmd) {
    const args = cmd.args ?? {}
    const zoneIds = args.zoneIds?.length ? [...args.zoneIds] : (args.zoneId ? [args.zoneId] : [])
    const mode = ['quick', 'point', 'sweep'].includes(args.mode) ? args.mode : 'quick'

    this._cancelMission()
    this.anomalies = []               // 多轮巡逻：清空上一轮异常（UI 侧由 phase=patrol 同步重置）
    this.mission = buildMission(this.scene, zoneIds, mode)
    const token = this._missionToken

    // 回停靠点满电出发（每轮任务从 dock 起算）
    const agv = this.entities.get('patrol-agv-01')
    agv.battery = 96
    this.batteryBase = 96
    this._emit(EventType.BATTERY, { entityId: 'patrol-agv-01', value: 96 })

    const scope = zoneIds.length === this.scene.zones.length ? '全园' : zoneIds.map(z => this._zoneName(z)).join('、')
    const modeName = { quick: '快速巡逻', point: '定点详查', sweep: '环视检查' }[mode]
    this._emit(EventType.PHASE, { phase: 'patrol' })

    // 上一轮结束后若车不在停靠点（定点/环视任务终点），先开回停靠点再出发
    if (Math.hypot(agv.pose.x - this.scene.dock.x, agv.pose.y - this.scene.dock.y) >= 1) {
      this._emit(EventType.COMMAND_LOG, { text: '巡逻车先返回停靠点补给，再开始本轮任务' })
      await this._flyTo(agv, { x: this.scene.dock.x, y: this.scene.dock.y })
      if (token !== this._missionToken || !this.running) return
    }

    if (mode === 'quick') {
      this._emit(EventType.COMMAND_LOG, {
        text: `收到${modeName}任务，规划${scope}路线（共 ${this.mission.route.length - 1} 个检查点）`,
      })
      this._runQuick(token)
    } else {
      this._emit(EventType.COMMAND_LOG, {
        text: `收到${modeName}任务，将停靠 ${this.mission.points.length} 个检查点：${scope}`,
      })
      this._runStopAndCheck(token, mode)
    }
  }

  // 取消当前任务：作废执行链、停 tick、收回无人机
  _cancelMission() {
    this._missionToken++
    if (this.tickHandle) { clearInterval(this.tickHandle); this.tickHandle = null }
    const drone = this.entities.get('drone-01')
    drone.active = false; drone.status = 'idle'
    drone.pose = { x: this.scene.dock.x, y: this.scene.dock.y, yaw: drone.pose.yaw }
    this._emit(EventType.DRONE_DEPLOY, { active: false })
  }

  // ---- quick：沿线连续巡查（弧长推进，车速恒定） ----
  _runQuick(token) {
    const agv = this.entities.get('patrol-agv-01')
    agv.status = 'moving'
    this._emit(EventType.STATUS, { entityId: 'patrol-agv-01', status: 'moving' })

    const m = this.mission
    // 有真值异常的分区 → 在该分区的局部进度上均匀布点发现
    const byZone = anomaliesByZone(this.scene)
    const zonePlans = (m.zoneRanges ?? [])
      .map(r => ({ range: r, indices: byZone[r.zoneId] ?? [] }))
      .filter(p => p.indices.length)
      .map(p => ({
        range: p.range,
        thresholds: p.indices.map((_, i) => (i + 1) / (p.indices.length + 1)),
        indices: p.indices,
        fired: p.indices.map(() => false),
      }))

    this.progress = 0

    this.tickHandle = setInterval(() => {
      if (!this.running || token !== this._missionToken) {
        clearInterval(this.tickHandle); this.tickHandle = null; return
      }
      // 每 tick 前进 0.4m × 倍速（车速恒定）
      this.progress = Math.min(1, this.progress + (0.4 * this.speed) / m.total)
      const p = this._routePointAt(m.route, this.progress)
      const p2 = this._routePointAt(m.route, Math.min(1, this.progress + 0.01))
      agv.pose = { x: p[0], y: p[1], yaw: Math.atan2(p2[1] - p[1], p2[0] - p[0]) * 180 / Math.PI }
      agv.zone = this._zoneOf(p[0], p[1])
      agv.battery = Math.max(45, Math.round(this.batteryBase - this.progress * 40))
      this._emit(EventType.POSE, { entityId: 'patrol-agv-01', pose: agv.pose })
      this._emit(EventType.BATTERY, { entityId: 'patrol-agv-01', value: agv.battery })
      this._emit('progress', { value: this.progress })

      // 异常发现：按各分区的局部进度均匀触发
      for (const plan of zonePlans) {
        if (plan.range.len <= 0) continue
        const local = Math.max(0, Math.min(1, (this.progress * m.total - plan.range.start) / plan.range.len))
        plan.thresholds.forEach((th, i) => {
          if (local >= th && !plan.fired[i]) {
            plan.fired[i] = true
            this._discover(plan.indices[i])
          }
        })
      }

      if (this.progress >= 1) {
        clearInterval(this.tickHandle); this.tickHandle = null
        this._finishMission(token)
      }
    }, 40)
  }

  // ---- point / sweep：逐点停靠检查 ----
  async _runStopAndCheck(token, mode) {
    const alive = () => this.running && token === this._missionToken
    const agv = this.entities.get('patrol-agv-01')
    agv.status = 'moving'
    this._emit(EventType.STATUS, { entityId: 'patrol-agv-01', status: 'moving' })

    const m = this.mission
    let flown = 0   // 已飞距离（供进度/电量换算）
    this._emit('progress', { value: 0 })

    for (let i = 0; i < m.points.length; i++) {
      if (!alive()) return
      const pt = m.points[i]
      const segLen = Math.hypot(pt.x - agv.pose.x, pt.y - agv.pose.y)
      const flownBase = flown
      await this._flyTo(agv, { x: pt.x, y: pt.y }, {
        onProgress: k => {
          const p = (flownBase + k * segLen) / m.total
          this._emit('progress', { value: p })
          agv.battery = Math.max(45, Math.round(this.batteryBase - p * 40))
          this._emit(EventType.BATTERY, { entityId: 'patrol-agv-01', value: agv.battery })
        },
      })
      if (!alive()) return
      flown += segLen
      agv.zone = pt.zone
      this._emit('progress', { value: Math.min(1, flown / m.total) })

      // 停靠检查
      agv.status = 'working'
      this._emit(EventType.STATUS, { entityId: 'patrol-agv-01', status: 'working' })
      this._emit(EventType.COMMAND_LOG, {
        text: `🛑 停靠${pt.label}（${this._zoneName(pt.zone)}），检查：${pt.check}`,
      })

      if (mode === 'sweep') {
        await this._sweepAt(agv, pt, alive)
      } else {
        await this._wait(900)
        if (!alive()) return
        this._checkAt(pt)
      }
      if (!alive()) return
      agv.status = 'moving'
      this._emit(EventType.STATUS, { entityId: 'patrol-agv-01', status: 'moving' })
    }
    if (!alive()) return
    this._finishMission(token)
  }

  // 停靠点检查：命中真实异常真值则发现，否则报告正常
  _checkAt(pt) {
    const type = getPointAnomalyMap(this.scene)[pt.placeId]
    if (type) {
      const idx = findAnomalyIndexByType(this.scene, type)
      if (idx >= 0 && !this.anomalies.some(a => a.type === type)) {
        this._discover(idx)
        return
      }
    }
    this._emit(EventType.COMMAND_LOG, { text: `✅ ${pt.label}检查完成：${pt.check}无异常` })
  }

  // 环视：原地转四朝向各拍一张（第 2 张命中异常真值则发现）
  async _sweepAt(entity, pt, alive) {
    const dirs = [
      { yaw: 0, name: '东' }, { yaw: 90, name: '南' }, { yaw: 180, name: '西' }, { yaw: 270, name: '北' },
    ]
    for (let k = 0; k < dirs.length; k++) {
      if (!alive()) return
      await this._turnTo(entity, dirs[k].yaw)
      if (!alive()) return
      this._emit(EventType.COMMAND_LOG, { text: `📸 环视拍照 ${k + 1}/4（朝${dirs[k].name}）` })
      await this._wait(500)
      if (!alive()) return
      if (k === 1) this._checkAt(pt)
    }
  }

  // ---- 任务收尾：有未复核异常→无人机自动复核→报告；全部已复核→直接出报告；无异常→空报告 ----
  _finishMission(token) {
    const agv = this.entities.get('patrol-agv-01')
    agv.status = 'idle'
    this._emit(EventType.STATUS, { entityId: 'patrol-agv-01', status: 'idle' })
    const unconfirmed = this.anomalies.filter(a => a.stage !== 'confirmed')
    if (!this.anomalies.length) {
      this._emit(EventType.COMMAND_LOG, { text: '本轮巡逻完成，未发现异常' })
      this._emit(EventType.PHASE, { phase: 'report' })
      this._emit(EventType.REPORT, { findings: [] })   // 空报告：UI 显示"未发现异常"
    } else if (!unconfirmed.length) {
      // 巡逻途中手动"重点复查"已全部确认：直接出报告，并回收在外无人机
      this._emit(EventType.COMMAND_LOG, { text: '本轮异常均已复核确认，生成巡检报告' })
      this._emit(EventType.PHASE, { phase: 'report' })
      this._emit(EventType.REPORT, { findings: this.scene.findings ?? [] })
      this._recallDrone(token)
    } else {
      this._emit(EventType.COMMAND_LOG, { text: '本轮巡逻完成，呼叫无人机前来复查' })
      this._emit(EventType.PHASE, { phase: 'recheck' })
      this._autoRecheck(token)
    }
  }

  // 无人机返航回收（飞回停靠点后停用）
  async _recallDrone(token) {
    const alive = () => this.running && token === this._missionToken
    const drone = this.entities.get('drone-01')
    if (!drone.active) return
    await this._flyTo(drone, { x: this.scene.dock.x, y: this.scene.dock.y })
    if (!alive()) return
    drone.active = false; drone.status = 'idle'
    this._emit(EventType.DRONE_DEPLOY, { active: false })
  }

  // ---- 无人机忙闲状态（同步事件，UI 用来渲染按钮状态） ----
  _setRecheckBusy(v) {
    this._recheckBusy = v
    this._emit('recheckbusy', { busy: v })
  }

  // ---- 无人机自动复核（任务收尾） ----
  async _autoRecheck(token) {
    const alive = () => this.running && token === this._missionToken
    // 若手动"重点复查"正在进行，等它结束再接管（避免双链同时驱动无人机）
    while (this._recheckBusy && alive()) await this._wait(300)
    if (!alive()) return
    this._setRecheckBusy(true)
    try {
      const drone = this.entities.get('drone-01')
      const targets = this.anomalies.filter(a => a.stage !== 'confirmed')
      if (!targets.length) {
        this._emit(EventType.PHASE, { phase: 'report' })
        this._emit(EventType.COMMAND_LOG, { text: '所有异常均已复核，生成巡检报告' })
        this._emit(EventType.REPORT, { findings: this.scene.findings ?? [] })
        await this._recallDrone(token)   // 无人机在外则回收
        return
      }
      drone.status = 'working'; drone.active = true
      this._emit(EventType.DRONE_DEPLOY, { active: true })
      await this._wait(600)
      for (const a of targets) {
        if (!alive()) return
        a.stage = 'rechecking'
        this._emit(EventType.ANOMALY, { anomaly: a })
        this._emit(EventType.COMMAND_LOG, { text: `🚁 无人机飞往${a.near}，复查${a.label}` })
        await this._flyTo(drone, a.pos)
        if (!alive()) return
        await this._wait(500)
        if (!alive()) return
        this._confirm(a)
      }
      if (!alive()) return
      this._emit(EventType.PHASE, { phase: 'report' })
      this._emit(EventType.COMMAND_LOG, { text: '复核完成，生成巡检报告' })
      this._emit(EventType.REPORT, { findings: this.scene.findings ?? [] })
      // 无人机返航降落
      await this._recallDrone(token)
    } finally {
      this._setRecheckBusy(false)
    }
  }

  // ---- 重点复查（手动）：{anomalyId} 单点 或 {all:true} 全部待复核 ----
  async _recheck(cmd) {
    if (this._recheckBusy) {
      this._emit(EventType.COMMAND_LOG, { text: '无人机正在执行复核任务，请稍候' })
      return
    }
    const args = cmd.args ?? {}
    const targets = args.all
      ? this.anomalies.filter(a => a.stage !== 'confirmed')
      : this.anomalies.filter(a => a.id === args.anomalyId && a.stage !== 'confirmed')
    if (!targets.length) {
      this._emit(EventType.COMMAND_LOG, {
        text: args.all ? '所有异常均已复核确认，无需重复复查' : '未找到待复核的异常',
      })
      return
    }
    const token = this._missionToken   // 跟随当前任务：新任务/停止时自动作废
    const alive = () => this.running && token === this._missionToken
    this._setRecheckBusy(true)
    try {
      const drone = this.entities.get('drone-01')
      drone.active = true; drone.status = 'working'
      this._emit(EventType.DRONE_DEPLOY, { active: true, target: targets[0].pos })
      this._emit(EventType.COMMAND_LOG, {
        text: `🚁 收到重点复查指令，出动无人机（${targets.length} 处待复核）`,
      })
      for (const a of targets) {
        if (!alive()) return
        a.stage = 'rechecking'
        this._emit(EventType.ANOMALY, { anomaly: a })
        this._emit(EventType.COMMAND_LOG, { text: `🚁 无人机飞往${a.near}，复查${a.label}` })
        await this._flyTo(drone, a.pos)
        if (!alive()) return
        await this._wait(400)
        if (!alive()) return
        this._confirm(a)
      }
      // 复核完返航（若自动流程未在跑则收回无人机）
      await this._flyTo(drone, { x: this.scene.dock.x, y: this.scene.dock.y })
      if (!alive()) return
      if (!this.tickHandle) {
        drone.active = false; drone.status = 'idle'
        this._emit(EventType.DRONE_DEPLOY, { active: false })
      } else {
        // 任务仍在跑：留给收尾流程回收，但飞回停靠点待命
        drone.status = 'idle'
      }
    } finally {
      this._setRecheckBusy(false)
    }
  }

  // ---- 发现异常（初判）----
  _discover(ai) {
    const a = this.scene.anomalies?.[ai]
    if (!a) return
    // 证据：优先取场景演示证据包（type 关联），否则生成仿真推演证据
    const f = (this.scene.findings ?? []).find(x => x.type === a.type)
    const nearLabel = f?.place ?? this.scene.devices.find(d => d.id === a.near)?.label ?? a.near
    const hasRect = !!a.w
    this.anomalies.push({
      id: `anomaly-${a.type}-${ai}`, type: a.type, label: f?.label ?? a.label,
      pos: { x: a.x + (a.w ?? 0) / 2, y: a.y + (a.h ?? 0) / 2 },
      rect: hasRect ? { w: a.w, h: a.h } : undefined,
      confidence: (f?.conf ?? 0.9) * 0.75,  // 初判置信度（复核前）
      stage: 'detected', evidence: f?.evidence ?? '仿真推演发现疑似异常，等待复核确认', near: nearLabel,
      handle: { status: 'pending', at: Date.now() },   // 新异常工单：未处理
    })
    this._emit(EventType.ANOMALY, { anomaly: this.anomalies[this.anomalies.length - 1] })
    this._emit(EventType.PHASE, { phase: 'detect' })
    this._emit(EventType.COMMAND_LOG, { text: `📸 拍照识别：发现${f?.label ?? a.label}（初步判断，等待复核）` })
  }

  _confirm(a) {
    a.stage = 'confirmed'
    const f = (this.scene.findings ?? []).find(x => x.type === a.type)
    a.confidence = f?.conf ?? a.confidence
    this._emit(EventType.ANOMALY, { anomaly: a })
    this._emit(EventType.COMMAND_LOG, {
      text: `✅ 复核确认：${a.label}（把握程度 ${(a.confidence * 100) | 0}%）`,
    })
  }

  // ---------- 其他命令 ----------
  async _goto(cmd) {
    const agv = this.entities.get('patrol-agv-01')
    const t = cmd.args?.target ?? { x: this.scene.dock.x, y: this.scene.dock.y }
    this._emit(EventType.COMMAND_LOG, { text: `巡逻车前往 (${t.x.toFixed(1)}, ${t.y.toFixed(1)})` })
    await this._flyTo(agv, t)
    this._emit(EventType.COMMAND_LOG, { text: '已到达目的地' })
  }

  async _returnDock() {
    const agv = this.entities.get('patrol-agv-01')
    this._emit(EventType.COMMAND_LOG, { text: '巡逻车返回停靠点充电' })
    await this._flyTo(agv, { x: this.scene.dock.x, y: this.scene.dock.y })
    agv.status = 'idle'
    this._emit(EventType.STATUS, { entityId: 'patrol-agv-01', status: 'idle' })
  }

  _report() {
    this._emit(EventType.PHASE, { phase: 'report' })
    this._emit(EventType.REPORT, { findings: this._findingsWithInjected() })
  }

  // ---------- 工具 ----------
  _zoneOf(x, y) {
    for (const z of this.scene.zones) {
      const [zx, zy, zw, zh] = z.rect
      if (x >= zx && x <= zx + zw && y >= zy && y <= zy + zh) return z.id
    }
    return ''
  }

  // 弧长参数化：progress ∈ [0,1] → 折线上的点
  _routePointAt(route, progress) {
    const pts = route
    if (progress <= 0) return pts[0]
    let total = 0; const segs = []
    for (let i = 1; i < pts.length; i++) {
      const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
      segs.push(d); total += d
    }
    const target = total * Math.min(1, progress)
    let acc = 0
    for (let i = 1; i < pts.length; i++) {
      const d = segs[i - 1]
      if (d > 0 && acc + d >= target) {
        const t = (target - acc) / d
        return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * t, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * t]
      }
      acc += d
    }
    return pts[pts.length - 1]
  }

  // 等待（受倍速影响）
  _wait(ms) {
    return new Promise(resolve => {
      setTimeout(resolve, Math.max(60, ms / Math.max(0.5, this.speed)))
    })
  }

  // 平滑飞行到目标（车速恒定；onProgress 返回该段进度 0→1）
  _flyTo(entity, target, { onProgress } = {}) {
    return new Promise(resolve => {
      const sx = entity.pose.x, sy = entity.pose.y
      const dist = Math.hypot(target.x - sx, target.y - sy)
      if (dist < 0.05) { onProgress?.(1); resolve(); return }
      const yaw = Math.atan2(target.y - sy, target.x - sx) * 180 / Math.PI
      entity.pose = { ...entity.pose, yaw }
      let moved = 0
      const handle = setInterval(() => {
        if (!this.running) { clearInterval(handle); this._animHandles?.delete(handle); resolve(); return }
        moved = Math.min(dist, moved + 0.4 * this.speed)
        const k = moved / dist
        entity.pose = { yaw, x: sx + (target.x - sx) * k, y: sy + (target.y - sy) * k }
        this._emit(EventType.POSE, { entityId: entity.id, pose: entity.pose })
        onProgress?.(k)
        if (k >= 1) { clearInterval(handle); this._animHandles?.delete(handle); resolve() }
      }, 30)
      ;(this._animHandles ??= new Set()).add(handle)
    })
  }

  // 原地平滑转向（最短角路径）
  _turnTo(entity, targetYaw) {
    return new Promise(resolve => {
      const from = entity.pose.yaw
      const delta = ((((targetYaw - from) % 360) + 540) % 360) - 180
      const dur = Math.max(300, Math.abs(delta) * 4) / Math.max(0.5, this.speed)
      const t0 = performance.now()
      const handle = setInterval(() => {
        if (!this.running) { clearInterval(handle); this._animHandles?.delete(handle); resolve(); return }
        const k = Math.min(1, (performance.now() - t0) / dur)
        const ease = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2   // easeInOutQuad
        entity.pose = { ...entity.pose, yaw: from + delta * ease }
        this._emit(EventType.POSE, { entityId: entity.id, pose: entity.pose })
        if (k >= 1) { clearInterval(handle); this._animHandles?.delete(handle); resolve() }
      }, 30)
      ;(this._animHandles ??= new Set()).add(handle)
    })
  }

  // 停止时无需强杀动画句柄：各动画循环在下一 tick 检测 running=false 后
  // 自行 clearInterval 并 resolve，等待中的执行链靠 alive() 检查退出。
  // （若在此处直接 clearInterval，Promise 将永远不 resolve，执行链悬挂）
  _stopAnimations() { /* 动画循环自行清理 */ }
}
