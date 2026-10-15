// ============================================================
// 智慧园区场景（源自省赛 demo/world/park.py，坐标一致）
// 世界 60m × 40m，原点左上，x 向东 y 向南
// 含省赛 seed=2026 真实异常真值与证据帧
// ============================================================
import { ANOMALY_TYPE_META } from './sceneSchema.js'

export const PARK_SCENE = {
  id: 'park',
  name: '智慧园区',
  desc: '户外园区巡检 · 含省赛真实异常真值与证据照片',
  world: { w: 60, h: 40 },
  bg: { color: '#f0f4ee' },

  // 装饰层（仅渲染用，不参与巡检逻辑）
  decor: {
    roads: [
      { x: 0, y: 18.5, w: 60, h: 3 },   // 横向主干道
      { x: 28.5, y: 0, w: 3, h: 40 },   // 纵向主干道
      { x: 0, y: 0, w: 60, h: 2 },      // 外环上
      { x: 0, y: 38, w: 60, h: 2 },     // 外环下
      { x: 0, y: 0, w: 2, h: 40 },      // 外环左
      { x: 58, y: 0, w: 2, h: 40 },     // 外环右
    ],
    areas: [
      { id: 'lawn-nw', color: '#6bcf7f', rect: [14, 4, 12, 12] },
      { id: 'lawn-ne', color: '#6bcf7f', rect: [33, 4, 14, 12] },
      { id: 'lawn-sw', color: '#6bcf7f', rect: [4, 24, 12, 12] },
      { id: 'lawn-se', color: '#6bcf7f', rect: [33, 23, 8, 8] },
      { id: 'pond', color: '#7fb8f0', rect: [43, 25, 13, 11], water: true },
    ],
    rects: [
      { x: 4, y: 4, w: 8, h: 6 },       // 北侧建筑
      { x: 4, y: 30, w: 8, h: 5 },      // 南侧建筑
    ],
  },

  // 巡逻分区
  zones: [
    { id: 'zone-a', name: '西北分区', rect: [2, 2, 26.5, 16.5] },
    { id: 'zone-b', name: '东北分区', rect: [31.5, 2, 24.5, 16.5] },
    { id: 'zone-c', name: '西南分区', rect: [2, 21.5, 26.5, 14.5] },
    { id: 'zone-d', name: '东南分区', rect: [31.5, 21.5, 24.5, 14.5] },
  ],

  // 设备点位（检查点由「分区 ∩ 设备」运行时推导）
  devices: [
    { id: 'bin-1', kind: 'bin', x: 27.5, y: 17.5, label: '1 号垃圾桶' },
    { id: 'bin-2', kind: 'bin', x: 33.0, y: 17.5, label: '2 号垃圾桶' },
    { id: 'bin-3', kind: 'bin', x: 5.0, y: 23.0, label: '3 号垃圾桶' },
    { id: 'bin-4', kind: 'bin', x: 32.5, y: 24.0, label: '4 号垃圾桶' },
    { id: 'bin-5', kind: 'bin', x: 52.0, y: 23.0, label: '5 号垃圾桶' },
    { id: 'bin-6', kind: 'bin', x: 55.5, y: 36.5, label: '6 号垃圾桶' },
    { id: 'bench-1', kind: 'bench', x: 20.0, y: 16.5, label: '1 号长椅' },
    { id: 'bench-2', kind: 'bench', x: 40.0, y: 16.5, label: '2 号长椅' },
    { id: 'bench-3', kind: 'bench', x: 10.0, y: 23.5, label: '3 号长椅' },
    { id: 'bench-4', kind: 'bench', x: 36.0, y: 16.5, label: '4 号长椅' },
    { id: 'lawn-nw', kind: 'lawn', x: 20.0, y: 10.0, label: '西北草坪' },
    { id: 'lawn-ne', kind: 'lawn', x: 40.0, y: 10.0, label: '东北草坪' },
    { id: 'lawn-sw', kind: 'lawn', x: 10.0, y: 30.0, label: '西南草坪' },
    { id: 'lawn-se', kind: 'lawn', x: 37.0, y: 27.0, label: '东南草坪' },
  ],

  // 巡逻路线（吸附后，源自 park.py patrol_route）
  routes: {
    'zone-a': [[30.0, 20.0], [3.0, 11.5], [27.0, 3.5], [27.0, 17.0], [3.5, 17.0], [3.0, 11.5], [23.5, 7.0], [23.5, 13.5], [7.0, 13.5], [30.0, 20.0]],
    'zone-b': [[30.0, 20.0], [33.0, 3.5], [54.5, 3.5], [54.5, 17.0], [33.0, 17.0], [36.5, 7.0], [51.0, 7.0], [51.0, 13.5], [36.5, 13.5], [30.0, 20.0]],
    'zone-c': [[30.0, 20.0], [3.5, 23.0], [27.0, 23.0], [27.0, 34.5], [3.0, 36.5], [7.0, 26.5], [23.5, 26.5], [23.5, 31.0], [7.0, 28.0], [30.0, 20.0]],
    'zone-d': [[30.0, 20.0], [33.0, 23.0], [54.5, 23.0], [57.0, 23.5], [33.0, 34.5], [36.5, 26.5], [51.0, 23.0], [57.0, 23.5], [36.5, 31.0], [30.0, 20.0]],
  },

  dock: { x: 30, y: 20 },

  // 可识别异常类型（本场景）
  anomalyTypes: [
    ANOMALY_TYPE_META.cigarette,
    ANOMALY_TYPE_META.dry,
    ANOMALY_TYPE_META.litter,
  ],

  // 异常真值（seed=2026，near 指向设备 id）
  anomalies: [
    { type: 'litter', x: 5.68, y: 21.12, near: 'bin-3', label: '垃圾分类违规' },
    { type: 'cigarette', x: 8.67, y: 23.86, near: 'bench-3', label: '未熄烟头' },
    { type: 'dry', x: 7.02, y: 25.25, w: 5.54, h: 2.74, near: 'lawn-sw', label: '植被缺水' },
  ],

  // 演示证据包（省赛第四轮闭环 + 无人机复核实测；type 与 anomalies 对应）
  findings: [
    { type: 'cigarette', label: '未熄烟头', place: 'bench-3 长椅旁', conf: 0.98, level: 'high',
      evidence: '橙色亮点 2 处（长椅步道边缘 + 步道中段），无人机俯拍复核确认',
      frameRef: '/frames/cigarette.jpg', frameTitle: 'AGV 近景检查帧（bench-3）',
      frameDesc: '拍照时巡逻车位于长椅东南侧，画面中长椅旁步道上可见两处橙红色亮点。' },
    { type: 'dry', label: '植被缺水', place: 'lawn-sw 草坪', conf: 0.95, level: 'high',
      evidence: '草坪内黄褐斑驳斑块（占 1/4-1/3），轮廓不规则、边缘渐变，复核确认',
      frameRef: '/frames/dry.jpg', frameTitle: 'AGV 近景检查帧（bench-3 方向）',
      frameDesc: '画面左侧草坪内部出现成片黄褐色斑块，与周围饱和绿色形成对比。' },
    { type: 'litter', label: '垃圾分类违规', place: 'bin-3 桶旁', conf: 0.90, level: 'medium',
      evidence: '桶旁橙/黄/绿杂色散落小块，俯拍复核确认',
      frameRef: '/frames/litter.jpg', frameTitle: 'AGV 近景检查帧（bin-3）',
      frameDesc: '垃圾桶位旁地面散落橙、黄、绿多色小块，非单一件落物。' },
  ],
}
