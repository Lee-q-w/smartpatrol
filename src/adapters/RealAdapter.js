// ============================================================
// RealAdapter —— 真机数据源适配器
// ------------------------------------------------------------
// 职责：WebSocket 连接真实/模拟设备（server/sim_device.py），
//   下发命令（goto/patrol/capture/...）、接收遥测（位姿/电量/状态），
//   设备摄像头帧自动送 AI 识别中心识别，异常进入地图/报告/证据系统。
//
// 协议：JSON over WebSocket，详见 docs/device-protocol.md
//   平台→设备  { t:'cmd', id, type:'hello|goto|turn|patrol|capture|return|stop', args }
//   设备→平台  { t:'hello|telemetry|frame|ack|event', ... }
//
// 设计要点：
//   1. 坐标与 Scene 一致（世界坐标·米·原点左上·x 东 y 南），
//      真实设备位姿直接投影到数字孪生地图 —— 虚实同图。
//   2. 巡逻任务的检查点由场景运行时推导（buildMission），
//      平台算好点位下发给设备；设备只需实现
//      移动/转向/拍照三类原语，三种巡查方式（quick/point/sweep）
//      由「平台下发检查点 + 设备端执行模式」组合完成。
//   3. 拍照帧 → AI 识别（多模态模型）→ 确认态异常，
//      与 AI 识别中心回填共用同一套数据结构（source: 'real-ai'）。
//   4. 连接状态通过自定义事件 'real' 广播：{state, text?, device?}
//      state: offline | connecting | connected | error
// ============================================================
import { CommandType, EventType } from '../core/protocol.js'
import { PARK_SCENE } from '../scenes/park.js'
import { buildMission } from '../scenes/sceneSchema.js'

const MODE_NAME = { quick: '快速巡逻', point: '定点详查', sweep: '环视检查' }

// 工单流转文案
const HANDLE_FLOW = { pending: '已退回待处理', processing: '已派单，开始处理', resolved: '已处置完成' }

export class RealAdapter {
  constructor(options = {}) {
    this.scene = options.scene ?? PARK_SCENE
    this.url = options.url ?? 'ws://127.0.0.1:9601'
    this.aiUrl = options.aiUrl ?? 'http://127.0.0.1:8788'  // AI 识别中心后端
    this.speed = 1   // 兼容 App.vue 倍速 watch（真机不吃倍速，无副作用）
    this.listeners = new Set()
    this.entities = new Map()
    this.anomalies = []          // 真机 AI 识别出的异常（全部为确认态）
    this.ws = null
    this.connState = 'offline'   // offline | connecting | connected | error
    this.device = null           // 设备自报信息 {id,name,model,...}
    this._cmdSeq = 0
    this._frameSeq = 0
    this._lastFrameB64 = ''      // 最近一帧（证据引用用）
    this._initEntities()
  }

  _initEntities() {
    this.entities.set('patrol-agv-01', {
      id: 'patrol-agv-01', type: 'agv', name: '巡逻 AGV（真机）',
      pose: { x: this.scene.dock.x, y: this.scene.dock.y, yaw: 0 }, battery: 96,
      status: 'offline', zone: '',
    })
  }

  _emit(type, payload) {
    const ev = { type, payload, ts: performance.now() }
    for (const cb of this.listeners) cb(ev)
  }

  _log(text) { this._emit(EventType.COMMAND_LOG, { text }) }

  // ---------- 生命周期 ----------
  async start() {
    this._emit(EventType.STATUS, { entityId: 'patrol-agv-01', status: 'offline' })
    this._log('真机模式就绪：请在「设备连接」面板连接设备（模拟设备见 docs/device-protocol.md）')
  }

  stop() { this.disconnect() }

  onEvent(cb) {
    this.listeners.add(cb)
    return () => this.listeners.delete(cb)
  }

  snapshot() { return this.entities }

  /** 连接设备（UI 面板触发；可传新地址覆盖默认） */
  connect(url) {
    if (url) this.url = url
    if (this.ws) { try { this.ws.onclose = null; this.ws.close() } catch { /* 忽略旧连接清理 */ } }
    this._setConn('connecting', `正在连接 ${this.url} …`)
    let ws
    try { ws = new WebSocket(this.url) } catch (e) {
      this._setConn('error', `地址无效：${e.message}`); return
    }
    this.ws = ws
    ws.onopen = () => { this._send('hello', {}) }
    ws.onmessage = (ev) => {
      let m
      try { m = JSON.parse(ev.data) } catch { return }
      try { this._handleDeviceMsg(m) } catch (e) { this._log(`设备消息处理出错：${e.message}`) }
    }
    ws.onclose = () => {
      if (this.ws !== ws) return   // 已被新连接取代
      this.device = null
      this._setConn('offline', '连接已断开')
      this._log('⚠️ 与设备断开连接')
    }
    ws.onerror = () => {
      if (this.ws !== ws) return
      this._setConn('error', `连接失败：${this.url}（请确认设备服务已启动）`)
    }
  }

  disconnect() {
    if (this.ws) { try { this.ws.close() } catch { /* 已关闭 */ } this.ws = null }
    this.device = null
    this._setConn('offline', '设备未连接')
  }

  _setConn(state, text) {
    this.connState = state
    this._emit('real', { state, text, device: this.device })
  }

  _send(type, args) {
    if (!this.ws || this.ws.readyState !== 1) return null
    const id = `r-${++this._cmdSeq}`
    this.ws.send(JSON.stringify({ t: 'cmd', id, type, args: args ?? {} }))
    return id
  }

  // ---------- 设备消息 → 协议事件 ----------
  _handleDeviceMsg(m) {
    switch (m.t) {
      case 'hello': {
        this.device = m.device ?? { id: 'unknown', name: '未知设备' }
        this._setConn('connected', `已连接：${this.device.name}`)
        this._log(`✅ 设备上线：${this.device.name}（${(this.device.capabilities ?? []).join(' / ') || '标准能力'}）`)
        break
      }
      case 'telemetry': {
        const eid = 'patrol-agv-01'   // 设备移动底盘统一映射为平台 AGV 实体
        const ent = this.entities.get(eid)
        if (m.k === 'pose' && m.pose) {
          if (ent) ent.pose = { x: m.pose.x, y: m.pose.y, yaw: m.pose.yaw }
          this._emit(EventType.POSE, { entityId: eid, pose: ent?.pose ?? m.pose })
        } else if (m.k === 'battery') {
          if (ent) ent.battery = m.value
          this._emit(EventType.BATTERY, { entityId: eid, value: m.value })
        } else if (m.k === 'status') {
          if (ent) ent.status = m.status
          this._emit(EventType.STATUS, { entityId: eid, status: m.status })
        }
        break
      }
      case 'frame': this._onFrame(m).catch(e => this._log(`⚠️ ${e.message}`)); break
      case 'ack':
        if (m.ok === false) this._log(`设备拒绝命令：${m.text ?? '未知原因'}`)
        break
      case 'event': {
        if (m.k === 'arrive') this._log(m.text ?? `到达检查点`)
        else if (m.k === 'patrol-done') this._finishPatrol(m.text)
        else if (m.k === 'notice') this._log(m.text ?? '')
        break
      }
      default: break
    }
  }

  // ---------- 命令入口 ----------
  dispatch(cmd) {
    const online = this.ws && this.ws.readyState === 1
    if (!online && cmd.type !== CommandType.REPORT) {
      this._log('设备未连接：请先在「设备连接」面板连接后再下发命令')
      return
    }
    switch (cmd.type) {
      case CommandType.PATROL: return this._patrol(cmd)
      case CommandType.GOTO: {
        const t = cmd.args?.target
        this._log(`巡逻车前往 (${(t?.x ?? 0).toFixed(1)}, ${(t?.y ?? 0).toFixed(1)})`)
        return this._send('goto', { x: t?.x, y: t?.y })
      }
      case CommandType.TURN:
        this._log(`巡逻车转向 ${cmd.args?.yawDeg ?? 0}°`)
        return this._send('turn', { yawDeg: cmd.args?.yawDeg })
      case CommandType.CAPTURE:
        this._log('📸 手动拍照，画面将送 AI 识别…')
        return this._send('capture', {})
      case CommandType.RETURN_DOCK:
        this._log('巡逻车返回停靠点')
        return this._send('return', { x: this.scene.dock.x, y: this.scene.dock.y })
      case CommandType.STOP:
        return this._stopTask()
      case CommandType.RECHECK:
        this._log('真机识别结果由 AI 直接确认，无需无人机复核')
        return
      case CommandType.HANDLE: return this._handle(cmd)
      case CommandType.REPORT: return this._report()
      default: this._log(`未知命令 ${cmd.type}`)
    }
  }

  // ---------- 巡逻任务：平台推导检查点 → 下发设备执行 ----------
  _patrol(cmd) {
    const args = cmd.args ?? {}
    const zoneIds = args.zoneIds?.length ? [...args.zoneIds] : (args.zoneId ? [args.zoneId] : [])
    const mode = ['quick', 'point', 'sweep'].includes(args.mode) ? args.mode : 'quick'
    const m = buildMission(this.scene, zoneIds, mode)

    let checkpoints
    if (mode === 'quick') {
      checkpoints = this._quickCheckpoints(m.route)
    } else {
      checkpoints = (m.points ?? []).map(p => ({ placeId: p.placeId, label: p.label, x: p.x, y: p.y, zone: p.zone }))
    }
    if (!checkpoints.length) {
      this._log('所选范围内没有检查点，请调整巡逻范围')
      return
    }

    this.anomalies = []   // 新任务：清空上一轮异常
    this._emit(EventType.PHASE, { phase: 'patrol' })
    const scope = zoneIds.length === this.scene.zones.length ? '全园' : zoneIds.map(z => this._zoneName(z)).join('、')
    if (mode === 'quick') {
      this._log(`收到${MODE_NAME[mode]}任务，已规划${scope}路线（${checkpoints.length} 个拍照检查点），下发真机执行`)
    } else {
      this._log(`收到${MODE_NAME[mode]}任务，将停靠 ${checkpoints.length} 个检查点：${scope}，下发真机执行`)
    }
    this._send('patrol', { mode, checkpoints, dock: this.scene.dock })
  }

  // quick 模式：沿路线每 5m 抽一个拍照检查点（+终点）
  _quickCheckpoints(route) {
    if (!route?.length) return []
    const STEP = 5
    const pts = [{ x: route[0][0], y: route[0][1], label: '出发点' }]
    let acc = 0, next = STEP
    for (let i = 1; i < route.length; i++) {
      const [x0, y0] = route[i - 1], [x1, y1] = route[i]
      const seg = Math.hypot(x1 - x0, y1 - y0)
      while (acc + seg >= next) {
        const k = (next - acc) / seg
        pts.push({ x: x0 + (x1 - x0) * k, y: y0 + (y1 - y0) * k, label: `途经点 ${pts.length}` })
        next += STEP
      }
      acc += seg
    }
    const last = route[route.length - 1]
    const lastPt = pts[pts.length - 1]
    if (Math.hypot(last[0] - lastPt.x, last[1] - lastPt.y) > 0.5) {
      pts.push({ x: last[0], y: last[1], label: '路线终点' })
    }
    return pts
  }

  _zoneName(id) { return this.scene.zones.find(z => z.id === id)?.name ?? id }

  // ---------- 拍照帧 → AI 识别 ----------
  async _onFrame(m) {
    const pose = m.pose ?? { x: 0, y: 0, yaw: 0 }
    this._emit(EventType.POSE, { entityId: 'patrol-agv-01', pose })
    this._frameSeq++
    this._lastFrameB64 = String(m.image ?? '')   // 暂存最近帧，供证据引用
    const label = m.label ?? `第 ${this._frameSeq} 帧`
    this._log(`📸 ${label} 已拍摄，送 AI 识别…`)
    if (!this._lastFrameB64) { this._log('⚠️ 收到空帧，跳过识别'); return }

    const res = await this._callAI(this._lastFrameB64)
    if (res.found && res.type) {
      this._addRealAnomaly(res, pose, label)
    } else {
      this._log(`🤖 AI 识别 ${label}：未发现异常`)
    }
  }

  async _callAI(b64) {
    let blob
    try { blob = await (await fetch(`data:image/jpeg;base64,${b64}`)).blob() } catch { throw new Error('帧数据解码失败') }
    const fd = new FormData()
    fd.append('file', blob, 'frame.jpg')
    let r
    try { r = await fetch(`${this.aiUrl}/api/recognize`, { method: 'POST', body: fd, signal: AbortSignal.timeout(90000) }) }
    catch { throw new Error(`AI 识别服务不可达（${this.aiUrl}），请先启动后端`) }
    let body = null
    try { body = await r.json() } catch { /* 非 JSON 响应 */ }
    if (!r.ok) throw new Error(body?.detail ?? `AI 服务返回 ${r.status}`)
    return body
  }

  // AI 确认的异常 → 异常库 + 报告（真机链路无"初判"阶段，识别即确认）
  _addRealAnomaly(res, pose, frameLabel) {
    const meta = { label: res.label ?? res.type, near: '拍照点' }
    const existing = this.anomalies.find(a => a.type === res.type)
    const pos = {
      x: pose.x + Math.cos((pose.yaw ?? 0) * Math.PI / 180) * 0.8,
      y: pose.y + Math.sin((pose.yaw ?? 0) * Math.PI / 180) * 0.8,
    }
    const nearDev = this._nearestDevice(pos)
    if (nearDev) meta.near = nearDev.label
    if (existing) {
      // 同类异常再次识别：更新证据与置信度，不重复建点
      existing.confidence = Math.max(existing.confidence, res.confidence ?? 0.9)
      existing.evidence = res.evidence ?? existing.evidence
      this._emit(EventType.ANOMALY, { anomaly: existing })
      } else {
        const anomaly = {
          id: `anomaly-real-${res.type}-${this._frameSeq}`, type: res.type, label: meta.label,
          pos, confidence: res.confidence ?? 0.9, stage: 'confirmed',
          evidence: res.evidence ?? '真机画面 AI 识别发现异常', near: meta.near,
          source: 'real-ai',
          // 帧图进证据（异常对象直接持有 dataURL，证据弹窗/导出 PDF 均可用）
          frameRef: `data:image/jpeg;base64,${this._lastFrameB64}`,
          frameTitle: `真机拍摄 · ${frameLabel}`,
          frameDesc: res.evidence ?? '真机摄像头帧，AI 识别确认异常',
          handle: { status: 'pending', at: Date.now() },   // 新异常工单：未处理
        }
        this.anomalies.push(anomaly)
        this._emit(EventType.ANOMALY, { anomaly })
      }
    const a = existing ?? this.anomalies[this.anomalies.length - 1]
    this._log(`🤖 AI 识别确认：${a.near}发现${a.label}（把握程度 ${Math.round(a.confidence * 100)}%），已进入报告`)
    // 识别即确认：同步刷新报告（与 AI 识别中心回填行为一致）
    this._emit(EventType.REPORT, { findings: this._findings() })
  }

  // ---------- 工单流转（真机异常同样可处置） ----------
  _handle(cmd) {
    const { anomalyId, to, note } = cmd.args ?? {}
    const a = this.anomalies.find(x => x.id === anomalyId)
    if (!a) { this._log('未找到该异常工单'); return }
    if (!['pending', 'processing', 'resolved'].includes(to)) return
    a.handle = { status: to, note: note ?? a.handle?.note, at: Date.now() }
    this._emit(EventType.ANOMALY, { anomaly: a })
    this._log(`📋 工单更新：${a.label}（${a.near}）${HANDLE_FLOW[to]}${note ? ' · ' + note : ''}`)
    this._emit(EventType.REPORT, { findings: this._findings() })
  }

  _nearestDevice(pos) {
    let best = null, bd = Infinity
    for (const d of this.scene.devices ?? []) {
      const dist = Math.hypot(d.x - pos.x, d.y - pos.y)
      if (dist < bd) { bd = dist; best = d }
    }
    return bd <= 6 ? best : null
  }

  // ---------- 任务收尾 / 报告 ----------
  _finishPatrol(text) {
    this._log(text ?? '本轮巡逻完成')
    if (!this.anomalies.length) {
      this._log('本轮巡逻未发现异常')
      this._emit(EventType.PHASE, { phase: 'report' })
      this._emit(EventType.REPORT, { findings: [] })
      return
    }
    this._emit(EventType.PHASE, { phase: 'report' })
    this._emit(EventType.COMMAND_LOG, { text: `AI 识别共确认 ${this.anomalies.length} 处异常，生成巡检报告` })
    this._emit(EventType.REPORT, { findings: this._findings() })
  }

  _report() {
    this._emit(EventType.PHASE, { phase: 'report' })
    this._emit(EventType.REPORT, { findings: this._findings() })
  }

  // 真机报告 = AI 识别确认的异常（不使用场景演示证据包——那是仿真的演示数据）
  _findings() {
    return this.anomalies.map(a => ({
      type: a.type, label: a.label, place: a.near, conf: a.confidence,
      level: a.confidence >= 0.9 ? 'high' : 'medium',
      evidence: a.evidence, frameRef: a.frameRef, frameTitle: a.frameTitle, frameDesc: a.frameDesc,
      handle: a.handle,
    }))
  }

  _stopTask() {
    this._send('stop', {})
    this._log('⏹ 已下发急停，任务取消，设备返回待命')
    this._emit(EventType.PHASE, { phase: 'idle' })
    this._emit(EventType.STATUS, { entityId: 'patrol-agv-01', status: 'idle' })
  }
}
