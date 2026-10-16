<template>
  <div class="park-map-wrap" :class="{ night }">
    <canvas ref="canvasRef" :width="px" :height="py" @click="onClick"></canvas>
    <div class="legend">
      <span v-for="t in legendTypes" :key="t.type">
        <i :style="{ background: t.color }"></i>{{ t.label }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { anomalyMeta, kindOf } from './scenes/sceneSchema.js'

const props = defineProps({
  scene: { type: Object, required: true },        // 当前巡检场景（Scene JSON）
  agv: { type: Object, default: () => ({ x: 30, y: 20, yaw: 0 }) },
  drone: { type: Object, default: () => ({ x: 30, y: 20, active: false }) },
  routeProgress: { type: Number, default: 0 },   // 0~1 巡逻进度
  route: { type: Array, default: null },         // 当前规划路线（世界坐标折线）
  anomalies: { type: Array, default: () => [] }, // 异常列表（含位置）
  showAnomalies: { type: Boolean, default: false },
  droneTarget: { type: Object, default: null },  // 复核点 {x,y}
  night: { type: Boolean, default: false },       // 夜色渲染模式（深色主题联动）
  baseWidth: { type: Number, default: 960 },      // 画布逻辑宽度（值守大屏可传更高值提清晰度）
})

const emit = defineEmits(['anomaly-click'])

const canvasRef = ref(null)

// 画布宽度默认 960（大屏传更高值），比例随场景世界尺寸缩放
const BASE_W = computed(() => props.baseWidth || 960)
const scale = computed(() => BASE_W.value / (props.scene?.world?.w ?? 60))
const px = computed(() => Math.round(BASE_W.value))
const py = computed(() => Math.round((props.scene?.world?.h ?? 40) * scale.value))
const S = () => scale.value

// 底图图片缓存
const bgImg = ref(null)
watch(() => props.scene?.bg?.image, (src) => {
  bgImg.value = null
  if (!src) return
  const img = new Image()
  img.onload = () => { bgImg.value = img; draw() }
  img.src = src
}, { immediate: true })

// 图例：本场景可识别的异常类型
const legendTypes = computed(() => (props.scene?.anomalyTypes ?? []).map(t => ({
  type: t.type, label: t.label, color: t.color,
})))

function m2p(x, y) { return [x * S(), y * S()] }

// 巡逻路径（按进度截断）
function routePath(progress) {
  const pts = (props.route ?? []).map(p => [p[0] * S(), p[1] * S()])
  if (progress <= 0 || pts.length < 2) return []
  if (progress >= 1) return pts
  let total = 0
  const segs = []
  for (let i = 1; i < pts.length; i++) {
    const d = Math.hypot(pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1])
    segs.push(d); total += d
  }
  const target = total * progress
  let acc = 0
  const out = [pts[0]]
  for (let i = 1; i < pts.length; i++) {
    const d = segs[i-1]
    if (acc + d >= target) {
      const t = (target - acc) / d
      out.push([
        pts[i-1][0] + (pts[i][0] - pts[i-1][0]) * t,
        pts[i-1][1] + (pts[i][1] - pts[i-1][1]) * t,
      ])
      break
    }
    out.push(pts[i]); acc += d
  }
  return out
}

function draw() {
  const c = canvasRef.value
  if (!c) return
  const ctx = c.getContext('2d')
  const scene = props.scene
  const s = S()
  const decor = scene.decor ?? {}
  const night = props.night
  // 夜色配色表
  const C = night ? {
    bg: '#0d1b2a', area: a => a.water ? '#173a5e' : '#1a3324',
    rect: '#3a4a5a', road: '#22303f', zoneStroke: 'rgba(80,160,200,0.4)', zoneText: 'rgba(120,180,220,0.75)',
    route: 'rgba(64,200,255,0.9)', routeDot: 'rgba(64,200,255,0.95)',
    deviceStroke: 'rgba(255,255,255,0.7)',
    grid: 'rgba(255,255,255,0.04)',
    labelBg: 'rgba(0,10,25,0.85)',
    agvGlow: true,
  } : {
    bg: scene.bg?.color ?? '#f0f4ee', area: a => a.color,
    rect: '#9aa5b1', road: '#d8d8d8', zoneStroke: 'rgba(100,150,120,0.35)', zoneText: 'rgba(100,150,120,0.55)',
    route: 'rgba(64,128,255,0.85)', routeDot: 'rgba(64,128,255,0.9)',
    deviceStroke: '#fff',
    grid: null,
    labelBg: 'rgba(0,0,0,0.75)',
    agvGlow: false,
  }

  // 底图：图片或纯色（夜景下盖一层深色滤镜仍可辨认底图）
  if (bgImg.value) {
    ctx.drawImage(bgImg.value, 0, 0, px.value, py.value)
    if (night) { ctx.fillStyle = 'rgba(10,20,35,0.55)'; ctx.fillRect(0, 0, px.value, py.value) }
  } else {
    ctx.fillStyle = C.bg
    ctx.fillRect(0, 0, px.value, py.value)
  }

  // 色块区域（草坪/水域/月台等；夜景下重着色）
  for (const a of decor.areas ?? []) {
    const [x, y, w, h] = a.rect
    ctx.fillStyle = C.area(a)
    ctx.fillRect(x * s, y * s, w * s, h * s)
    if (a.water) {
      ctx.strokeStyle = night ? 'rgba(120,180,255,0.35)' : 'rgba(255,255,255,0.5)'; ctx.lineWidth = 1
      for (let i = 0; i < 5; i++) {
        const wy = (y + 2 + i * (h / 6)) * s
        ctx.beginPath()
        ctx.moveTo((x + 0.6) * s, wy)
        ctx.bezierCurveTo((x + w * 0.35) * s, wy - 6, (x + w * 0.7) * s, wy + 6, (x + w - 0.6) * s, wy)
        ctx.stroke()
      }
    }
  }

  // 实体矩形（建筑/货架）
  for (const b of decor.rects ?? []) {
    ctx.fillStyle = C.rect
    ctx.fillRect(b.x * s, b.y * s, b.w * s, b.h * s)
    ctx.strokeStyle = night ? 'rgba(140,170,200,0.25)' : 'rgba(255,255,255,0.35)'; ctx.lineWidth = 1
    for (let yy = b.y * s; yy < (b.y + b.h) * s; yy += 10) {
      ctx.beginPath(); ctx.moveTo(b.x * s, yy); ctx.lineTo((b.x + b.w) * s, yy); ctx.stroke()
    }
  }

  // 道路
  ctx.fillStyle = C.road
  for (const r of decor.roads ?? []) ctx.fillRect(r.x * s, r.y * s, r.w * s, r.h * s)
  // 贯穿主干道中线
  for (const r of decor.roads ?? []) {
    if (r.w >= scene.world.w * 0.8 && r.h <= scene.world.h * 0.1) {
      ctx.strokeStyle = night ? 'rgba(255,220,120,0.5)' : '#fff'; ctx.lineWidth = 2; ctx.setLineDash([12, 10])
      ctx.beginPath(); ctx.moveTo(0, (r.y + r.h / 2) * s); ctx.lineTo(px.value, (r.y + r.h / 2) * s); ctx.stroke()
      ctx.setLineDash([])
    }
    if (r.h >= scene.world.h * 0.8 && r.w <= scene.world.w * 0.1) {
      ctx.strokeStyle = night ? 'rgba(255,220,120,0.5)' : '#fff'; ctx.lineWidth = 2; ctx.setLineDash([12, 10])
      ctx.beginPath(); ctx.moveTo((r.x + r.w / 2) * s, 0); ctx.lineTo((r.x + r.w / 2) * s, py.value); ctx.stroke()
      ctx.setLineDash([])
    }
  }

  // 分区（淡虚线框）
  ctx.setLineDash([6, 5]); ctx.lineWidth = night ? 1.8 : 1.5
  for (const z of scene.zones) {
    const [zx, zy, zw, zh] = z.rect
    ctx.strokeStyle = C.zoneStroke
    ctx.strokeRect(zx * s, zy * s, zw * s, zh * s)
    ctx.setLineDash([])
    ctx.fillStyle = C.zoneText
    ctx.font = '12px sans-serif'
    ctx.fillText(z.name, zx * s + 8, zy * s + 18)
    ctx.setLineDash([6, 5])
  }
  ctx.setLineDash([])

  // 设备点位（按类型形状/颜色；夜景加微光）
  for (const d of scene.devices ?? []) {
    const kind = kindOf(scene, d.kind)
    const [bx, by] = m2p(d.x, d.y)
    if (night) {
      // 夜景：设备点光晕
      ctx.fillStyle = hexA(kind?.color ?? '#606266', 0.25)
      ctx.beginPath(); ctx.arc(bx, by, 12, 0, Math.PI * 2); ctx.fill()
    }
    ctx.fillStyle = night ? (kind?.nightColor ?? kind?.color ?? '#8899aa') : (kind?.color ?? '#606266')
    if (kind?.shape === 'square') {
      ctx.fillRect(bx - 7, by - 7, 14, 14)
      ctx.strokeStyle = C.deviceStroke; ctx.lineWidth = 1.5; ctx.strokeRect(bx - 7, by - 7, 14, 14)
    } else if (kind?.shape === 'bar') {
      ctx.fillRect(bx - 9, by - 4, 18, 8)
      ctx.strokeStyle = C.deviceStroke; ctx.lineWidth = 1.5; ctx.strokeRect(bx - 9, by - 4, 18, 8)
    } else {
      ctx.beginPath(); ctx.arc(bx, by, 6, 0, Math.PI * 2); ctx.fill()
      ctx.strokeStyle = C.deviceStroke; ctx.lineWidth = 1.5; ctx.stroke()
    }
  }

  // 停靠点
  {
    const [dx, dy] = m2p(scene.dock.x, scene.dock.y)
    ctx.strokeStyle = '#155eab'; ctx.lineWidth = 2
    ctx.beginPath(); ctx.arc(dx, dy, 10, 0, Math.PI * 2); ctx.stroke()
    ctx.fillStyle = '#155eab'; ctx.font = '10px sans-serif'; ctx.textAlign = 'center'
    ctx.fillText('dock', dx, dy + 22); ctx.textAlign = 'left'
  }

  // 巡逻路线
  const path = routePath(props.routeProgress)
  if (path.length > 1) {
    ctx.strokeStyle = C.route; ctx.lineWidth = night ? 3.5 : 3
    if (night) { ctx.shadowColor = 'rgba(64,200,255,0.8)'; ctx.shadowBlur = 8 }
    ctx.setLineDash([])
    ctx.beginPath(); ctx.moveTo(path[0][0], path[0][1])
    for (let i = 1; i < path.length; i++) ctx.lineTo(path[i][0], path[i][1])
    ctx.stroke()
    ctx.shadowBlur = 0
    // 走过的路线点
    ctx.fillStyle = C.routeDot
    const routePts = props.route ?? []
    routePts.forEach((p, i) => {
      if (i / Math.max(1, routePts.length - 1) <= props.routeProgress + 0.02) {
        const [wx, wy] = m2p(p[0], p[1])
        ctx.beginPath(); ctx.arc(wx, wy, 4, 0, Math.PI * 2); ctx.fill()
      }
    })
  }

  // 异常标记（识别后显示，可点击查看证据）
  if (props.showAnomalies) {
    for (const a of props.anomalies) {
      const meta = anomalyMeta(scene, a.type)
      const cx = a.pos.x, cy = a.pos.y
      if (a.rect) {
        // 面状异常（缺水斑块/货物越线等）
        const [ax, ay] = m2p(a.pos.x - a.rect.w / 2, a.pos.y - a.rect.h / 2)
        ctx.fillStyle = hexA(meta.color, 0.5)
        ctx.beginPath()
        ctx.ellipse(ax + a.rect.w * s / 2, ay + a.rect.h * s / 2, a.rect.w * s / 2, a.rect.h * s / 2, 0.3, 0, Math.PI * 2)
        ctx.fill()
        ctx.strokeStyle = meta.color; ctx.lineWidth = 2; ctx.setLineDash([5, 4]); ctx.stroke(); ctx.setLineDash([])
      } else {
        const [ax, ay] = m2p(cx, cy)
        // 已复核的加脉冲光环
        if (a.stage === 'confirmed') {
          const pulse = (Math.sin(Date.now() / 300) + 1) / 2
          ctx.fillStyle = hexA(meta.color, 0.15 + pulse * 0.2)
          ctx.beginPath(); ctx.arc(ax, ay, 12 + pulse * 5, 0, Math.PI * 2); ctx.fill()
        }
        ctx.fillStyle = meta.color
        ctx.beginPath(); ctx.arc(ax, ay, 7, 0, Math.PI * 2); ctx.fill()
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke()
      }
      // 标签
      const [lx, ly] = m2p(cx, cy)
      const label = meta.label + (a.stage === 'confirmed' ? ' ✓' : '')
      ctx.font = 'bold 11px sans-serif'
      const tw = ctx.measureText(label).width
      ctx.fillStyle = C.labelBg
      ctx.fillRect(lx + 10, ly - 8, tw + 10, 18)
      ctx.fillStyle = '#fff'
      ctx.fillText(label, lx + 15, ly + 5)
    }
  }

  // 无人机（复核时）
  if (props.drone && props.drone.active) {
    const [drx, dry] = m2p(props.drone.x, props.drone.y)
    ctx.fillStyle = 'rgba(0,0,0,0.15)'
    ctx.beginPath(); ctx.ellipse(drx + 10, dry + 14, 14, 6, 0, 0, Math.PI * 2); ctx.fill()
    if (night) {  // 夜景导航灯闪烁
      const blink = (Math.sin(Date.now() / 200) + 1) / 2
      ctx.fillStyle = `rgba(255,60,60,${0.4 + blink * 0.6})`
      ctx.beginPath(); ctx.arc(drx - 9, dry - 6, 2.5, 0, Math.PI * 2); ctx.fill()
      ctx.fillStyle = `rgba(80,255,120,${0.4 + (1 - blink) * 0.6})`
      ctx.beginPath(); ctx.arc(drx + 9, dry - 6, 2.5, 0, Math.PI * 2); ctx.fill()
    }
    ctx.fillStyle = '#409eff'
    ctx.fillRect(drx - 10, dry - 3, 20, 6)
    ctx.beginPath(); ctx.arc(drx, dry, 5, 0, Math.PI * 2); ctx.fill()
    ctx.strokeStyle = 'rgba(64,158,255,0.8)'; ctx.lineWidth = 2
    const r = 8 + Math.sin(Date.now() / 60) * 2
    ctx.beginPath(); ctx.moveTo(drx - r, dry - 6); ctx.lineTo(drx - r + 6, dry - 6); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(drx + r - 6, dry - 6); ctx.lineTo(drx + r, dry - 6); ctx.stroke()
    if (props.droneTarget) {
      const [tx, ty] = m2p(props.droneTarget.x, props.droneTarget.y)
      ctx.strokeStyle = 'rgba(64,158,255,0.5)'; ctx.setLineDash([4, 4])
      ctx.beginPath(); ctx.moveTo(drx, dry); ctx.lineTo(tx, ty); ctx.stroke(); ctx.setLineDash([])
    }
  }

  // AGV（夜景加轨迹尾迹与光晕）
  {
    const a = props.agv
    const [ax, ay] = m2p(a.x, a.y)
    const yawRad = (a.yaw * Math.PI) / 180
    if (night) {
      // 轨迹尾迹：沿已走路径的最后一段画渐隐线
      const path = routePath(props.routeProgress)
      if (path.length > 1) {
        const tail = path.slice(-14)
        ctx.lineWidth = 4
        for (let i = 1; i < tail.length; i++) {
          const k = i / tail.length
          ctx.strokeStyle = `rgba(64,200,255,${k * 0.4})`
          ctx.beginPath(); ctx.moveTo(tail[i - 1][0], tail[i - 1][1]); ctx.lineTo(tail[i][0], tail[i][1]); ctx.stroke()
        }
      }
      // 车体光晕
      ctx.fillStyle = 'rgba(31,143,255,0.25)'
      ctx.beginPath(); ctx.arc(ax, ay, 18, 0, Math.PI * 2); ctx.fill()
    }
    ctx.save()
    ctx.translate(ax, ay)
    ctx.rotate(-yawRad)
    ctx.fillStyle = night ? '#4db2ff' : '#1f8fff'
    ctx.beginPath()
    ctx.moveTo(12, 0); ctx.lineTo(-8, -8); ctx.lineTo(-8, 8); ctx.closePath()
    ctx.fill()
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.stroke()
    ctx.restore()
    // 摄像视野扇形（夜景更亮些）
    ctx.fillStyle = night ? 'rgba(64,180,255,0.22)' : 'rgba(31,143,255,0.18)'
    ctx.beginPath(); ctx.moveTo(ax, ay)
    ctx.arc(ax, ay, 42, -yawRad - Math.PI / 5, -yawRad + Math.PI / 5)
    ctx.closePath(); ctx.fill()
  }
}

// #RRGGBB → rgba
function hexA(hex, alpha) {
  const v = hex.replace('#', '')
  const r = parseInt(v.slice(0, 2), 16), g = parseInt(v.slice(2, 4), 16), b = parseInt(v.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

let timer = null
onMounted(() => {
  draw()
  timer = setInterval(draw, 80) // 无人机旋翼/脉冲动画
})
  watch(() => [props.scene, props.agv, props.drone, props.routeProgress, props.showAnomalies, props.anomalies, props.route, props.night, props.baseWidth], draw, { deep: true })
onBeforeUnmount(() => clearInterval(timer))

// 点击检测：命中异常点 → 弹证据
function onClick(e) {
  const rect = canvasRef.value.getBoundingClientRect()
  // CSS 可能把 canvas 缩放显示（大屏 max-width 自适应）——命中判定按显示像素反算回画布像素
  const k = rect.width / canvasRef.value.width || 1
  const mx = (e.clientX - rect.left) / k
  const my = (e.clientY - rect.top) / k
  for (const a of props.anomalies) {
    const [ax, ay] = [a.pos.x * S(), a.pos.y * S()]
    if (Math.hypot(mx - ax, my - ay) <= 14) {
      emit('anomaly-click', a)
      return
    }
  }
}
</script>

<style scoped>
.park-map-wrap { position: relative; display: inline-block; }
canvas { border-radius: 8px; box-shadow: 0 2px 12px rgba(0,0,0,0.15); background: #fff; }
.legend { position: absolute; left: 10px; bottom: 8px; display: flex; gap: 12px; background: rgba(255,255,255,0.9); padding: 4px 10px; border-radius: 6px; font-size: 12px; color: #606266; }
.park-map-wrap.night .legend { background: rgba(8,18,32,0.85); color: #9fb8d4; border: 1px solid #1d3350; }
.legend span { display: flex; align-items: center; gap: 4px; }
.legend i { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
</style>
