// 智巡园区静态数据（源自省赛 demo/world/park.py，坐标一致）
// 坐标系：原点左上，x 向右（东），y 向下（南），单位米；世界 60m × 40m

export const WORLD = { w: 60, h: 40 }

export const ROADS = [
  { x: 0, y: 18.5, w: 60, h: 3 },   // 横向主干道
  { x: 28.5, y: 0, w: 3, h: 40 },   // 纵向主干道
  { x: 0, y: 0, w: 60, h: 2 },      // 外环上
  { x: 0, y: 38, w: 60, h: 2 },     // 外环下
  { x: 0, y: 0, w: 2, h: 40 },      // 外环左
  { x: 58, y: 0, w: 2, h: 40 },     // 外环右
]

export const LAWNS = [
  { id: 'lawn-nw', rect: [14, 4, 12, 12] },
  { id: 'lawn-ne', rect: [33, 4, 14, 12] },
  { id: 'lawn-sw', rect: [4, 24, 12, 12] },
  { id: 'lawn-se', rect: [33, 23, 8, 8] },
]

export const POND = { x: 43, y: 25, w: 13, h: 11 }
export const BUILDINGS = [
  { x: 4, y: 4, w: 8, h: 6 },
  { x: 4, y: 30, w: 8, h: 5 },
]

export const BINS = [
  { id: 'bin-1', x: 27.5, y: 17.5 }, { id: 'bin-2', x: 33.0, y: 17.5 },
  { id: 'bin-3', x: 5.0, y: 23.0 },  { id: 'bin-4', x: 32.5, y: 24.0 },
  { id: 'bin-5', x: 52.0, y: 23.0 }, { id: 'bin-6', x: 55.5, y: 36.5 },
]

export const BENCHES = [
  { id: 'bench-1', x: 20.0, y: 16.5 }, { id: 'bench-2', x: 40.0, y: 16.5 },
  { id: 'bench-3', x: 10.0, y: 23.5 }, { id: 'bench-4', x: 36.0, y: 16.5 },
]

export const ZONES = [
  { id: 'zone-a', name: '西北分区', rect: [2, 2, 26.5, 16.5] },
  { id: 'zone-b', name: '东北分区', rect: [31.5, 2, 24.5, 16.5] },
  { id: 'zone-c', name: '西南分区', rect: [2, 21.5, 26.5, 14.5] },
  { id: 'zone-d', name: '东南分区', rect: [31.5, 21.5, 24.5, 14.5] },
]

export const DOCK = { x: 30, y: 20 }

// seed=2026 异常真值（省赛闭环验证数据）
export const ANOMALIES = [
  { type: 'litter', x: 5.68, y: 21.12, near: 'bin-3', label: '垃圾分类违规' },
  { type: 'cigarette', x: 8.67, y: 23.86, near: 'bench-3', label: '未熄烟头' },
  { type: 'dry', x: 7.02, y: 25.25, w: 5.54, h: 2.74, near: 'lawn-sw', label: '植被缺水' },
]

// zone-c 巡逻路线（吸附后，源自 park.py patrol_route）
export const ROUTE_ZONE_C = [
  [30.0, 20.0], [3.5, 23.0], [27.0, 23.0], [27.0, 34.5], [3.0, 36.5],
  [7.0, 26.5], [23.5, 26.5], [23.5, 31.0], [7.0, 28.0], [30.0, 20.0],
]

// 识别结果（省赛第四轮闭环 + 无人机复核实测数据）
export const FINDINGS = [
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
]

// 无人机俯拍复核帧（供证据弹窗第二张图）
export const DRONE_FRAME = { ref: '/frames/drone.jpg', title: '无人机俯拍复核帧（8 米高度）' }

// 各分区巡查点位（定点详查/环视检查用）：{ placeId, x, y, check: 检查项, label: 通俗名 }
export const ZONE_POINTS = {
  'zone-a': [
    { placeId: 'bin-1', x: 27.5, y: 17.5, check: '垃圾分类', label: '1 号垃圾桶' },
    { placeId: 'bench-1', x: 20.0, y: 16.5, check: '烟头', label: '1 号长椅' },
    { placeId: 'lawn-nw', x: 20.0, y: 10.0, check: '植被缺水', label: '西北草坪' },
  ],
  'zone-b': [
    { placeId: 'bin-2', x: 33.0, y: 17.5, check: '垃圾分类', label: '2 号垃圾桶' },
    { placeId: 'bench-2', x: 40.0, y: 16.5, check: '烟头', label: '2 号长椅' },
    { placeId: 'lawn-ne', x: 40.0, y: 10.0, check: '植被缺水', label: '东北草坪' },
  ],
  'zone-c': [
    { placeId: 'bin-3', x: 5.0, y: 23.0, check: '垃圾分类', label: '3 号垃圾桶' },
    { placeId: 'bench-3', x: 10.0, y: 23.5, check: '烟头', label: '3 号长椅' },
    { placeId: 'lawn-sw', x: 10.0, y: 30.0, check: '植被缺水', label: '西南草坪' },
  ],
  'zone-d': [
    { placeId: 'bin-5', x: 52.0, y: 23.0, check: '垃圾分类', label: '5 号垃圾桶' },
    { placeId: 'bin-6', x: 55.5, y: 36.5, check: '垃圾分类', label: '6 号垃圾桶' },
    { placeId: 'lawn-se', x: 37.0, y: 27.0, check: '植被缺水', label: '东南草坪' },
  ],
}

// zone-c 点位 → 异常映射（真实真值：bench-3 烟头 / bin-3 垃圾 / lawn-sw 缺水）
export const POINT_ANOMALY = {
  'bin-3': 'litter', 'bench-3': 'cigarette', 'lawn-sw': 'dry',
}

export const PATROL_MODES = {
  quick: { label: '快速巡逻', desc: '沿规划路线连续巡查，速度快' },
  point: { label: '定点详查', desc: '逐个点位停靠检查：垃圾桶查分类、长椅查烟头、草坪查缺水' },
  sweep: { label: '环视检查', desc: '到点后原地转向四个方向各拍一张，覆盖更全' },
}
export const ROUTES = {
  'zone-a': [[30.0, 20.0], [3.0, 11.5], [27.0, 3.5], [27.0, 17.0], [3.5, 17.0], [3.0, 11.5], [23.5, 7.0], [23.5, 13.5], [7.0, 13.5], [30.0, 20.0]],
  'zone-b': [[30.0, 20.0], [33.0, 3.5], [54.5, 3.5], [54.5, 17.0], [33.0, 17.0], [36.5, 7.0], [51.0, 7.0], [51.0, 13.5], [36.5, 13.5], [30.0, 20.0]],
  'zone-c': ROUTE_ZONE_C,
  'zone-d': [[30.0, 20.0], [33.0, 23.0], [54.5, 23.0], [57.0, 23.5], [33.0, 34.5], [36.5, 26.5], [51.0, 23.0], [57.0, 23.5], [36.5, 31.0], [30.0, 20.0]],
}

export const TYPE_META = {
  cigarette: { label: '未熄烟头', color: '#ff4d3d', icon: '⚠' },
  dry: { label: '植被缺水', color: '#e6a23c', icon: '🌿' },
  litter: { label: '垃圾分类违规', color: '#8e44ad', icon: '🗑' },
}

// ============================================================
// buildMission —— 任务规划（UI 画规划线 & SimAdapter 推演共用）
// zoneIds：巡逻范围（单分区/多分区/全园，保持点选顺序）
// mode：quick 沿线快速 / point 定点详查 / sweep 环视检查
// 返回 { mode, zones, route, total, zoneRanges?, points? }
//   route：规划折线（世界坐标），地图按弧长截断绘制
//   zoneRanges：quick 模式下每分区在折线上的弧长区间（供异常阈值按局部进度触发）
//   points：point/sweep 模式的停靠检查点序列
// ============================================================
export function buildMission(zoneIds, mode = 'quick') {
  const zones = zoneIds?.length ? [...zoneIds] : ['zone-c']

  if (mode === 'quick') {
    // 拼接各分区路线（相邻重复点去重，弧长连续）
    const route = []
    const segZone = []
    for (const z of zones) {
      const r = ROUTES[z] ?? ROUTES['zone-c']
      for (const p of r) {
        const last = route[route.length - 1]
        if (last && Math.hypot(last[0] - p[0], last[1] - p[1]) < 1e-6) continue
        route.push([p[0], p[1]])
        segZone.push(z)
      }
    }
    const cum = [0]
    for (let i = 1; i < route.length; i++) {
      cum.push(cum[i - 1] + Math.hypot(route[i][0] - route[i - 1][0], route[i][1] - route[i - 1][1]))
    }
    const zoneRanges = []
    for (const z of zones) {
      const first = segZone.indexOf(z)
      if (first < 0) continue
      let end = first
      while (end + 1 < segZone.length && segZone[end + 1] === z) end++
      zoneRanges.push({ zoneId: z, start: cum[first], end: cum[end], len: cum[end] - cum[first] })
    }
    return { mode, zones, route, total: cum[cum.length - 1], zoneRanges }
  }

  // point / sweep：停靠点 → 停靠点连线
  const points = zones.flatMap(z => (ZONE_POINTS[z] ?? []).map(p => ({ ...p, zone: z })))
  const route = [[DOCK.x, DOCK.y], ...points.map(p => [p.x, p.y])]
  const cum = [0]
  for (let i = 1; i < route.length; i++) {
    cum.push(cum[i - 1] + Math.hypot(route[i][0] - route[i - 1][0], route[i][1] - route[i - 1][1]))
  }
  return { mode, zones, points, route, total: cum[cum.length - 1] }
}