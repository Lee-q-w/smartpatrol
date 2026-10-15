// ============================================================
// 智巡 SmartPatrol —— 统一设备数据协议 v1.0
// ------------------------------------------------------------
// 目标：前端界面与数据源完全解耦。
//   仿真(Sim) / 历史回放(Replay) / 真机(Real, 预留) 三种数据源
//   都实现同一套协议，界面零改动。
//
// 设计原则：
//   1. 所有坐标使用世界坐标系（米，原点左上，x 向东 y 向南）
//   2. 时间统一用 performance.now() 毫秒 + 逻辑时间两种：仿真用
//      自推进时钟，回放用录制时间轴
//   3. 命令与遥测分离：UI 发命令 → Adapter 执行 → 产生遥测事件
// ============================================================

// ---------- 实体（设备与异常的实时状态快照） ----------
export const EntityType = {
  AGV: 'agv',          // 巡逻 AGV
  DRONE: 'drone',      // 复核无人机
  SENSOR: 'sensor',    // 环境传感器（固定）
  ANOMALY: 'anomaly',  // 异常（识别产物）
}

/**
 * @typedef {Object} DeviceState 设备实时状态
 * @property {string} id                如 'patrol-agv-01'
 * @property {string} type              EntityType 之一
 * @property {string} name              显示名
 * @property {{x:number,y:number,yaw:number}} pose 位置与朝向（度）
 * @property {number} battery           0-100
 * @property {'idle'|'moving'|'working'|'offline'} status
 * @property {string} [zone]            当前所在分区 id
 * @property {boolean} [active]         无人机是否起飞
 */

/**
 * @typedef {Object} AnomalyState 异常状态
 * @property {string} id                如 'anomaly-cig-1'
 * @property {'cigarette'|'dry'|'litter'} type
 * @property {string} label
 * @property {{x:number,y:number}} pos  世界坐标
 * @property {{w:number,h:number}} [rect] 面状异常（缺水斑块）
 * @property {number} confidence        0-1
 * @property {'detected'|'rechecking'|'confirmed'} stage
 * @property {string} evidence
 * @property {string} [frameRef]        证据帧引用（图片路径或帧 id）
 * @property {string} near              邻近点位
 * @property {{status:'pending'|'processing'|'resolved', note?:string, at?:number}} [handle]
 *                                      工单状态：未处理(pending)→处理中(processing)→已处理(resolved)
 */

// ---------- 命令（UI → 数据源） ----------
export const CommandType = {
  GOTO: 'goto',            // {target: {x,y} | placeId}
  TURN: 'turn',            // {yawDeg}
  PATROL: 'patrol',        // {zoneIds: string[], mode: 'quick'|'point'|'sweep'}
                           //   zoneIds 巡逻范围（单/多分区/全园，按点选顺序）
                           //   mode 巡查方式：quick 沿线快速 / point 定点详查 / sweep 环视检查
  CAPTURE: 'capture',      // {} —— 拍照取帧
  RECHECK: 'recheck',      // {anomalyId} 单点 或 {all:true} 全部待复核 —— 无人机复核
  HANDLE: 'handle',        // {anomalyId, to: 'processing'|'resolved'|'pending', note?} —— 异常工单流转
                            //   异常发现后的处置闭环：未处理→处理中→已处理（可退回/重开）
  REPORT: 'report',        // {} —— 汇总报告
  RETURN_DOCK: 'return',   // 回停靠点
  // —— 回放控制（ReplayAdapter 实现）——
  PLAY: 'play',            // 播放 / 从暂停继续
  PAUSE: 'pause',          // 暂停
  STOP: 'stop',            // 停止并复位
  SEEK: 'seek',            // {t} 拖动到指定秒（瞬时重建该时刻状态）
}

/**
 * @typedef {Object} Command
 * @property {string} id
 * @property {string} type                CommandType
 * @property {Object} args
 * @property {number} issuedAt            发出时间戳
 * @property {'issued'|'executing'|'done'|'failed'} status
 * @property {string} [execLog]           执行摘要（命令流显示用）
 */

// ---------- 遥测事件（数据源 → UI） ----------
export const EventType = {
  POSE: 'pose',              // 位姿更新 {entityId, pose}
  BATTERY: 'battery',        // 电量 {entityId, value}
  STATUS: 'status',          // 状态变化 {entityId, status}
  ANOMALY: 'anomaly',        // 异常发现/更新 {anomaly}
  COMMAND_LOG: 'cmdlog',     // 命令执行日志 {text}
  PHASE: 'phase',            // 任务阶段 {phase}
  REPORT: 'report',          // 报告生成 {findings}
  DRONE_DEPLOY: 'drone',     // 无人机起降 {active, target}
}

/**
 * 数据源适配器必须实现的接口。
 * 三个实现：SimAdapter / ReplayAdapter /（预留）RealAdapter
 * @interface DataSourceAdapter
 */
export class DataSourceAdapter {
  /** 启动数据源 @returns {Promise<void>} */
  async start() { throw new Error('not implemented') }
  /** 停止并释放资源 */
  stop() { throw new Error('not implemented') }
  /**
   * 下发命令
   * @param {Command} cmd
   */
  dispatch(cmd) { throw new Error('not implemented') }
  /**
   * 订阅遥测事件
   * @param {(ev: {type: string, payload: any, ts: number}) => void} cb
   * @returns {() => void} 取消订阅
   */
  onEvent(cb) { throw new Error('not implemented') }
  /** 当前实体快照 @returns {Map<string, DeviceState|AnomalyState>} */
  snapshot() { throw new Error('not implemented') }
}

// ---------- 分区/点位（静态地图数据各数据源共享） ----------
export const PATROL_ZONE_IDS = ['zone-a', 'zone-b', 'zone-c', 'zone-d']