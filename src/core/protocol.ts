// ============================================================
// 智巡 SmartPatrol —— 统一设备数据协议 v1.1（TypeScript 版）
// ------------------------------------------------------------
// 目标：前端界面与数据源完全解耦。
//   仿真(Sim) / 历史回放(Replay) / 真机(Real) 三种数据源
//   都实现同一套协议，界面零改动。
//
// 设计原则：
//   1. 所有坐标使用世界坐标系（米，原点左上，x 向东 y 向南）
//   2. 时间统一用 performance.now() 毫秒 + 逻辑时间两种：仿真用
//      自推进时钟，回放用录制时间轴
//   3. 命令与遥测分离：UI 发命令 → Adapter 执行 → 产生遥测事件
// ============================================================

export interface Pose {
  x: number
  y: number
  yaw: number
}

export interface Rect {
  w: number
  h: number
}

export type EntityKind = 'agv' | 'drone' | 'sensor' | 'anomaly'

export const EntityType = {
  AGV: 'agv', // 巡逻 AGV
  DRONE: 'drone', // 复核无人机
  SENSOR: 'sensor', // 环境传感器（固定）
  ANOMALY: 'anomaly', // 异常（识别产物）
} as const

export type DeviceStatus = 'idle' | 'moving' | 'working' | 'offline'

export interface DeviceState {
  /** 如 'patrol-agv-01' */
  id: string
  type: EntityKind
  /** 显示名 */
  name: string
  /** 位置与朝向（度） */
  pose: Pose
  /** 0-100 */
  battery: number
  status: DeviceStatus
  /** 当前所在分区 id */
  zone?: string
  /** 无人机是否起飞 */
  active?: boolean
}

export type AnomalyKind = 'cigarette' | 'dry' | 'litter'
export type AnomalyStage = 'detected' | 'rechecking' | 'confirmed'
export type HandleStatus = 'pending' | 'processing' | 'resolved'

export interface AnomalyHandle {
  status: HandleStatus
  note?: string
  at?: number
}

export interface AnomalyState {
  /** 如 'anomaly-cig-1' */
  id: string
  type: AnomalyKind
  label: string
  /** 世界坐标 */
  pos: { x: number; y: number }
  /** 面状异常（缺水斑块） */
  rect?: Rect
  /** 0-1 */
  confidence: number
  stage: AnomalyStage
  evidence: string
  /** 证据帧引用（图片路径或帧 id） */
  frameRef?: string
  /** 邻近点位 */
  near: string
  /** 工单状态：未处理(pending)→处理中(processing)→已处理(resolved) */
  handle?: AnomalyHandle
}

export type CommandKind =
  | 'goto'
  | 'turn'
  | 'patrol'
  | 'capture'
  | 'recheck'
  | 'handle'
  | 'report'
  | 'return'
  | 'play'
  | 'pause'
  | 'stop'
  | 'seek'

export const CommandType = {
  GOTO: 'goto', // {target: {x,y} | placeId}
  TURN: 'turn', // {yawDeg}
  PATROL: 'patrol', // {zoneIds: string[], mode: 'quick'|'point'|'sweep'}
  CAPTURE: 'capture', // {} —— 拍照取帧
  RECHECK: 'recheck', // {anomalyId} 单点 或 {all:true} 全部待复核 —— 无人机复核
  HANDLE: 'handle', // {anomalyId, to: 'processing'|'resolved'|'pending', note?}
  REPORT: 'report', // {} —— 汇总报告
  RETURN_DOCK: 'return', // 回停靠点
  // —— 回放控制（ReplayAdapter 实现）——
  PLAY: 'play',
  PAUSE: 'pause',
  STOP: 'stop',
  SEEK: 'seek', // {t} 拖动到指定秒（瞬时重建该时刻状态）
} as const

export type PatrolMode = 'quick' | 'point' | 'sweep'
export type CommandStatus = 'issued' | 'executing' | 'done' | 'failed'

export interface Command {
  id: string
  type: CommandKind
  args: Record<string, unknown>
  /** 发出时间戳 */
  issuedAt: number
  status: CommandStatus
  /** 执行摘要（命令流显示用） */
  execLog?: string
}

export type TelemetryEventKind =
  | 'pose'
  | 'battery'
  | 'status'
  | 'anomaly'
  | 'cmdlog'
  | 'phase'
  | 'report'
  | 'drone'

export const EventType = {
  POSE: 'pose', // 位姿更新 {entityId, pose}
  BATTERY: 'battery', // 电量 {entityId, value}
  STATUS: 'status', // 状态变化 {entityId, status}
  ANOMALY: 'anomaly', // 异常发现/更新 {anomaly}
  COMMAND_LOG: 'cmdlog', // 命令执行日志 {text}
  PHASE: 'phase', // 任务阶段 {phase}
  REPORT: 'report', // 报告生成 {findings}
  DRONE_DEPLOY: 'drone', // 无人机起降 {active, target}
} as const

export interface TelemetryEvent<T = Record<string, unknown>> {
  type: TelemetryEventKind | string
  payload: T
  ts: number
}

export type TelemetryHandler = (ev: TelemetryEvent) => void

/** 数据源适配器必须实现的接口：SimAdapter / ReplayAdapter / RealAdapter */
export abstract class DataSourceAdapter {
  /** 启动数据源 */
  async start(): Promise<void> {
    throw new Error('not implemented')
  }
  /** 停止并释放资源 */
  stop(): void {
    throw new Error('not implemented')
  }
  /** 下发命令 */
  dispatch(_cmd: Command): void {
    throw new Error('not implemented')
  }
  /** 订阅遥测事件，返回取消订阅函数 */
  onEvent(_cb: TelemetryHandler): () => void {
    throw new Error('not implemented')
  }
  /** 当前实体快照 */
  snapshot(): Map<string, DeviceState | AnomalyState> {
    throw new Error('not implemented')
  }
}

// ---------- 分区/点位（静态地图数据各数据源共享） ----------
export const PATROL_ZONE_IDS: readonly string[] = ['zone-a', 'zone-b', 'zone-c', 'zone-d']