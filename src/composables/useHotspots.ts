// ============================================================
// useHotspots —— 点位热点统计（工单历史 → 热点排名 → 巡逻优先）
// ------------------------------------------------------------
// 数据来源：每轮巡检结束后，把异常点位写入本地历史（localStorage，最多 200 条）
// 统计口径：按点位（near）聚合出现次数；越近期权重越高（半衰期 5 轮）
// 用途：
//   1. 地图热力层：按热度画半透明圆斑
//   2. 定点详查「热点优先」：把高频点位排到路线最前面
// 说明：全部本地计算、不上传；首次使用会写入 3 条标注为示例的历史，便于演示
// ============================================================

export interface HotspotRecord {
  near: string
  type: string
  label: string
  ts: number
  round: number
}

export interface Hotspot {
  near: string
  x: number
  y: number
  count: number
  score: number
  types: string[]
  labels: string[]
  lastTs: number
}

const KEY = 'smartpatrol-hotspot-history'
const MAX_RECORDS = 200

function read(): HotspotRecord[] {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return []
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? (arr as HotspotRecord[]) : []
  } catch {
    return []
  }
}

function write(records: HotspotRecord[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(records.slice(-MAX_RECORDS)))
  } catch {
    /* 存储不可用时静默（隐私模式等） */
  }
}

/** 追加一轮工单记录（同轮同点位去重） */
export function archiveRound(
  items: Array<{ near: string; type: string; label: string }>,
  round: number,
): void {
  if (!items.length) return
  const records = read()
  const seen = new Set<string>()
  for (const it of items) {
    if (!it?.near || seen.has(it.near)) continue
    seen.add(it.near)
    records.push({ near: it.near, type: it.type, label: it.label, ts: Date.now(), round })
  }
  write(records)
}

export function historyRecords(): HotspotRecord[] {
  return read()
}

/**
 * 聚合热点：按点位汇总，近期权重更高（score = Σ 1/(1+0.2*轮次差)）
 * points 提供点位坐标（来自当前场景 anomaly 真值或设备点位）
 */
export function computeHotspots(
  points: Array<{ near: string; x: number; y: number }>,
  topN = 8,
): Hotspot[] {
  const records = read()
  if (!records.length) return []
  const maxRound = records.reduce((m, r) => Math.max(m, r.round ?? 0), 0)
  const map = new Map<string, Hotspot>()

  for (const r of records) {
    const p = points.find((pt) => pt.near === r.near)
    if (!p) continue          // 场景里找不到该点位（换场景后忽略）
    const cur = map.get(r.near) ?? {
      near: r.near, x: p.x, y: p.y, count: 0, score: 0, types: [], labels: [], lastTs: 0,
    }
    const gap = Math.max(0, maxRound - (r.round ?? 0))
    cur.count += 1
    cur.score += 1 / (1 + 0.2 * gap)
    cur.lastTs = Math.max(cur.lastTs, r.ts ?? 0)
    if (!cur.types.includes(r.type)) cur.types.push(r.type)
    if (!cur.labels.includes(r.label)) cur.labels.push(r.label)
    map.set(r.near, cur)
  }

  return [...map.values()].sort((a, b) => b.score - a.score).slice(0, topN)
}

/** 首次运行的演示数据（明确标注为示例，仅用于热力图可见） */
export function seedDemoHistoryIfEmpty(
  samples: Array<{ near: string; type: string; label: string; round: number }>,
): boolean {
  if (read().length) return false
  write(samples.map((s) => ({ ...s, ts: Date.now() - (3 - s.round) * 86400000 })))
  return true
}

export function clearHistory(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    /* ignore */
  }
}