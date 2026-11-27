// ============================================================
// Scene —— 通用场景数据结构 v1（TypeScript 版）
// ------------------------------------------------------------
// 一个 Scene = 一块场地（室内/室外均可）+ 设备点位 + 巡逻路线
//            + 可识别异常类型 + 演示真值（可选）
// 设计目标：
//   1. 场地不再写死：换场地 = 换 Scene JSON，零代码改动
//   2. 仿真器(SimAdapter) / 真机适配器 / 地图编辑器吃同一份 Scene
//   3. 检查点不单独维护：由「分区 ∩ 设备点位」运行时推导
//   4. 异常真值通过 near 指向设备 id，自动建立"点位→异常"映射
// ============================================================

import type { PatrolMode } from '../core/protocol'

export interface AnomalyTypeMeta {
  type?: string
  label: string
  color: string
  icon: string
}

export interface DeviceKind {
  id: string
  name: string
  color: string
  /** square 方块 / bar 宽条 / circle 圆点 */
  shape: 'square' | 'bar' | 'circle'
  check: string
}

/** [x, y, w, h] 世界坐标（米） */
export type Rect4 = [number, number, number, number]
/** [x, y] 世界坐标（米） */
export type Point2 = [number, number]

export interface SceneZone {
  id: string
  name: string
  rect: Rect4
}

export interface SceneDevice {
  id: string
  kind: string
  x: number
  y: number
  label: string
}

export interface SceneAnomaly {
  type: string
  x: number
  y: number
  w?: number
  h?: number
  near?: string
  label?: string
}

export interface SceneFinding {
  type: string
  label: string
  place: string
  conf: number
  level: string
  evidence: string
  frameRef?: string
  frameTitle?: string
  frameDesc?: string
}

export interface Scene {
  id: string
  name: string
  desc?: string
  world: { w: number; h: number }
  bg?: Record<string, unknown>
  decor?: Record<string, unknown>
  zones: SceneZone[]
  devices: SceneDevice[]
  routes: Record<string, Point2[]>
  dock: { x: number; y: number }
  anomalyTypes?: AnomalyTypeMeta[]
  deviceKinds?: DeviceKind[]
  anomalies?: SceneAnomaly[]
  findings?: SceneFinding[]
}

export interface ZonePoint {
  placeId: string
  x: number
  y: number
  zone: string
  check: string
  label: string
}

export interface ZoneRange {
  zoneId: string
  start: number
  end: number
  len: number
}

export interface Mission {
  mode: PatrolMode
  zones: string[]
  route: Point2[]
  total: number
  zoneRanges?: ZoneRange[]
  points?: ZonePoint[]
}

// ---------- 全局异常类型元数据（场景可用 anomalyTypes 覆盖/扩展） ----------
export const ANOMALY_TYPE_META: Record<string, AnomalyTypeMeta> = {
  cigarette: { label: '未熄烟头', color: '#ff4d3d', icon: '⚠' },
  dry: { label: '植被缺水', color: '#e6a23c', icon: '🌿' },
  litter: { label: '垃圾分类违规', color: '#8e44ad', icon: '🗑' },
  blocked: { label: '通道占用', color: '#e74c3c', icon: '🚧' },
  goods: { label: '货物堆放违规', color: '#f39c12', icon: '📦' },
  waterlogging: { label: '积水内涝', color: '#2980b9', icon: '🌊' },
}

// ---------- 默认设备类型（场景可用 deviceKinds 自定义） ----------
export const DEFAULT_DEVICE_KINDS: DeviceKind[] = [
  { id: 'bin', name: '垃圾桶', color: '#2f6b3a', shape: 'square', check: '垃圾分类' },
  { id: 'bench', name: '长椅', color: '#a0672f', shape: 'bar', check: '烟头' },
  { id: 'lawn', name: '草坪', color: '#5da75f', shape: 'circle', check: '植被缺水' },
  { id: 'shelf', name: '货架', color: '#8d6e63', shape: 'square', check: '货物堆放' },
  { id: 'hydrant', name: '消防栓', color: '#c0392b', shape: 'circle', check: '消防设施' },
  { id: 'exit', name: '安全出口', color: '#e6a23c', shape: 'circle', check: '通道占用' },
  { id: 'camera', name: '摄像头', color: '#155eab', shape: 'circle', check: '画面巡检' },
]

/** 查场景设备类型定义（场景优先，回退全局默认） */
export function kindOf(scene: Scene | null | undefined, kindId: string): DeviceKind | undefined {
  return (scene?.deviceKinds ?? DEFAULT_DEVICE_KINDS).find((k) => k.id === kindId)
}

/** 异常类型元数据（场景优先，回退全局） */
export function anomalyMeta(scene: Scene | null | undefined, type: string): AnomalyTypeMeta {
  const t = (scene?.anomalyTypes ?? []).find((x) => x.type === type)
  return t ?? ANOMALY_TYPE_META[type] ?? { label: type, color: '#409eff', icon: '●' }
}

/**
 * 某分区的检查点位（定点详查/环视检查用）
 * = 分区矩形内的设备点位，检查项取设备类型的默认检查项
 */
export function getZonePoints(scene: Scene | null | undefined, zoneId: string): ZonePoint[] {
  const z = scene?.zones?.find((zz) => zz.id === zoneId)
  if (!z) return []
  const [zx, zy, zw, zh] = z.rect
  return (scene?.devices ?? [])
    .filter((d) => d.x >= zx && d.x <= zx + zw && d.y >= zy && d.y <= zy + zh)
    .map((d) => ({
      placeId: d.id,
      x: d.x,
      y: d.y,
      zone: zoneId,
      check: kindOf(scene, d.kind)?.check ?? '常规巡检',
      label: d.label,
    }))
}

/** 设备 id → 真值异常类型映射（anomalies[].near 指向设备 id） */
export function getPointAnomalyMap(scene: Scene | null | undefined): Record<string, string> {
  const map: Record<string, string> = {}
  for (const a of scene?.anomalies ?? []) {
    if (a.near) map[a.near] = a.type
  }
  return map
}

/** 异常真值按所属分区分组：{ zoneId: [anomalyIndex, ...] }（按 near 设备坐标判定归属） */
export function anomaliesByZone(scene: Scene | null | undefined): Record<string, number[]> {
  const out: Record<string, number[]> = {}
  const list = scene?.anomalies ?? []
  list.forEach((a, i) => {
    const dev = (scene?.devices ?? []).find((d) => d.id === a.near)
    let zoneId = ''
    if (dev) {
      const z = (scene?.zones ?? []).find((zz) => {
        const [zx, zy, zw, zh] = zz.rect
        return dev.x >= zx && dev.x <= zx + zw && dev.y >= zy && dev.y <= zy + zh
      })
      zoneId = z?.id ?? ''
    }
    ;(out[zoneId] ??= []).push(i)
  })
  return out
}

/** 按类型找真值异常下标 */
export function findAnomalyIndexByType(scene: Scene | null | undefined, type: string): number {
  return (scene?.anomalies ?? []).findIndex((a) => a.type === type)
}

/** 场景基础校验（返回错误列表，空数组=通过） */
export function validateScene(scene: Scene | null | undefined): string[] {
  const errs: string[] = []
  if (!scene?.id) errs.push('缺少 id')
  if (!scene?.name) errs.push('缺少 name')
  if (!scene?.world?.w || !scene?.world?.h) errs.push('缺少 world 尺寸')
  if (!Array.isArray(scene?.zones) || !scene.zones.length) errs.push('至少需要一个分区')
  if (!Array.isArray(scene?.devices)) errs.push('缺少设备点位列表')
  if (!scene?.routes || typeof scene.routes !== 'object') errs.push('缺少巡逻路线')
  for (const z of scene?.zones ?? []) {
    if (!scene?.routes?.[z.id]) errs.push(`分区 ${z.name || z.id} 缺少巡逻路线`)
  }
  return errs
}

/**
 * 任务规划（UI 画规划线 & SimAdapter 推演共用）
 * zoneIds：巡逻范围（单分区/多分区/全园，保持点选顺序）
 * mode：quick 沿线快速 / point 定点详查 / sweep 环视检查
 */
export function buildMission(
  scene: Scene,
  zoneIds?: string[] | null,
  mode: PatrolMode = 'quick',
): Mission {
  const zones = zoneIds?.length ? [...zoneIds] : scene?.zones?.[0]?.id ? [scene.zones[0].id] : []

  if (mode === 'quick') {
    // 拼接各分区路线（相邻重复点去重，弧长连续）
    const route: Point2[] = []
    const segZone: string[] = []
    for (const z of zones) {
      const r = scene?.routes?.[z]
      if (!r) continue
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
    const zoneRanges: ZoneRange[] = []
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
  const points = zones.flatMap((z) => getZonePoints(scene, z))
  const route: Point2[] = [[scene.dock.x, scene.dock.y], ...points.map((p) => [p.x, p.y] as Point2)]
  const cum = [0]
  for (let i = 1; i < route.length; i++) {
    cum.push(cum[i - 1] + Math.hypot(route[i][0] - route[i - 1][0], route[i][1] - route[i - 1][1]))
  }
  return { mode, zones, points, route, total: cum[cum.length - 1] }
}