// ============================================================
// 室内仓库场景 —— 多设备类型示例场景
// 世界 40m × 30m；演示"任意场地可建图"：非户外、无无人机也能巡检
// 异常真值为演示数据，证据照片待真图识别接入后采集补充
// ============================================================
import { ANOMALY_TYPE_META } from './sceneSchema.js'

export const WAREHOUSE_SCENE = {
  id: 'warehouse',
  name: '室内仓库',
  desc: '室内仓储巡检 · 多设备类型（货架/消防栓/安全出口）',
  world: { w: 40, h: 30 },
  bg: { color: '#eceff3' },

  decor: {
    roads: [
      { x: 0, y: 12, w: 40, h: 4 },     // 中央主通道
      { x: 30, y: 0, w: 1.5, h: 30 },   // 月台分隔线通道
    ],
    areas: [
      { id: 'dock-in', color: '#dfe9f5', rect: [31.5, 2, 7, 11] },   // 收货月台
      { id: 'dock-out', color: '#fdf0dd', rect: [31.5, 16, 7, 11] }, // 发货月台
    ],
    rects: [  // 货架排（装饰）
      { x: 2, y: 2, w: 8, h: 9 }, { x: 12, y: 2, w: 8, h: 9 }, { x: 22, y: 2, w: 8, h: 9 },
      { x: 2, y: 19, w: 8, h: 9 }, { x: 12, y: 19, w: 8, h: 9 }, { x: 22, y: 19, w: 8, h: 9 },
    ],
  },

  zones: [
    { id: 'zone-a', name: 'A 存储区', rect: [1, 1, 30, 11] },
    { id: 'zone-b', name: 'B 存储区', rect: [1, 16, 30, 13] },
    { id: 'zone-c', name: '收货月台', rect: [31, 1, 8, 13] },
    { id: 'zone-d', name: '发货月台', rect: [31, 15, 8, 14] },
  ],

  devices: [
    { id: 'shelf-a1', kind: 'shelf', x: 6.0, y: 6.5, label: 'A1 货架' },
    { id: 'shelf-a2', kind: 'shelf', x: 16.0, y: 6.5, label: 'A2 货架' },
    { id: 'shelf-a3', kind: 'shelf', x: 26.0, y: 6.5, label: 'A3 货架' },
    { id: 'shelf-b1', kind: 'shelf', x: 6.0, y: 23.5, label: 'B1 货架' },
    { id: 'shelf-b2', kind: 'shelf', x: 16.0, y: 23.5, label: 'B2 货架' },
    { id: 'shelf-b3', kind: 'shelf', x: 26.0, y: 23.5, label: 'B3 货架' },
    { id: 'hydrant-a', kind: 'hydrant', x: 1.5, y: 10.8, label: 'A 区消防栓' },
    { id: 'hydrant-b', kind: 'hydrant', x: 1.5, y: 17.8, label: 'B 区消防栓' },
    { id: 'exit-1', kind: 'exit', x: 29.5, y: 5.8, label: 'A 区安全出口' },
    { id: 'exit-2', kind: 'exit', x: 29.5, y: 22.5, label: 'B 区安全出口' },
  ],

  routes: {
    'zone-a': [[35, 27], [33, 14], [6, 10.8], [6, 4], [16, 4], [26, 4], [29.5, 5.8], [16, 10.8], [16, 14], [33, 14], [35, 27]],
    'zone-b': [[35, 27], [33, 15.5], [29.5, 22.5], [26, 23.5], [16, 26], [6, 23.5], [1.5, 17.8], [6, 19], [16, 17.5], [33, 15.5], [35, 27]],
    'zone-c': [[35, 27], [33, 20], [35, 12], [35, 4], [33, 6], [35, 12], [35, 20], [35, 27]],
    'zone-d': [[35, 27], [37, 20], [33, 18], [37, 25], [35, 27]],
  },

  dock: { x: 35, y: 27 },   // AGV 停靠点（车库，右下角；所有分区路线以此为起终点）

  // 仓库场景的巡检重点：货物堆放与通道占用（对应下方 anomalies 真值类型）
  anomalyTypes: [
    ANOMALY_TYPE_META.goods,
    ANOMALY_TYPE_META.blocked,
  ],

  // 异常真值（仿真引擎按此注入）：坐标为世界坐标，near 关联设备/点位 id
  anomalies: [
    { type: 'goods', x: 14, y: 21, w: 3, h: 2, near: 'shelf-b2', label: '货物堆放违规' },
    { type: 'blocked', x: 28.2, y: 22.5, near: 'exit-2', label: '安全出口占用' },
  ],

  // 演示证据（无照片帧，待真图识别接入后采集补充）
  // findings：复核确认后的证据记录（报告卡/证据弹窗展示）；与 anomalies 真值一一对应
  findings: [
    { type: 'goods', label: '货物堆放违规', place: 'B2 货架旁', conf: 0.93, level: 'high',
      evidence: '通道内货物越线堆放，占用消防间距，复核确认',
      frameRef: '', frameTitle: '', frameDesc: '' },
    { type: 'blocked', label: '安全出口占用', place: 'B 区安全出口', conf: 0.88, level: 'high',
      evidence: '安全出口前堆放托盘货物，疏散通道受阻，复核确认',
      frameRef: '', frameTitle: '', frameDesc: '' },
  ],
}
