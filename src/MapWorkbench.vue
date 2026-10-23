<template>
  <div class="workbench">
    <!-- 左：工具面板 -->
    <aside class="wb-side">
      <el-card class="wb-card">
        <template #header><b>① 场景信息</b></template>
        <div class="wb-row"><span class="wb-k">场景名称</span>
          <el-input v-model="draft.name" size="small" placeholder="如：教学楼一层" />
        </div>
        <div class="wb-row"><span class="wb-k">场地宽 (m)</span>
          <el-input-number v-model="draft.world.w" :min="10" :max="200" size="small" controls-position="right" />
        </div>
        <div class="wb-row"><span class="wb-k">场地高 (m)</span>
          <el-input-number v-model="draft.world.h" :min="10" :max="200" size="small" controls-position="right" />
        </div>
        <div class="wb-row"><span class="wb-k">底图图片</span>
          <label class="wb-file-btn">
            {{ draft.bg.image ? '更换底图' : '上传底图' }}
            <input type="file" accept="image/*" hidden @change="onBgFile" />
          </label>
          <el-button v-if="draft.bg.image" size="small" text type="danger" @click="draft.bg.image = null">移除</el-button>
        </div>
        <div class="wb-tip">上传场地平面图或照片作描点参考（自动压缩存储）</div>
      </el-card>

      <el-card class="wb-card">
        <template #header><b>② 绘制</b></template>
        <div class="wb-modes">
          <el-check-tag v-for="m in MODES" :key="m.id" :checked="mode === m.id" @change="setMode(m.id)">{{ m.label }}</el-check-tag>
        </div>
        <div class="wb-row" v-if="mode === 'device'">
          <span class="wb-k">设备类型</span>
          <el-select v-model="deviceKind" size="small" style="flex:1">
            <el-option v-for="k in kinds" :key="k.id" :value="k.id" :label="k.name" />
          </el-select>
        </div>
        <template v-if="mode === 'route'">
          <div class="wb-row"><span class="wb-k">目标分区</span>
            <el-select v-model="routeZone" size="small" style="flex:1" placeholder="先画分区">
              <el-option v-for="z in draft.zones" :key="z.id" :value="z.id" :label="z.name" />
            </el-select>
          </div>
          <el-button size="small" type="primary" plain :disabled="!routeDraft.length" @click="finishRoute" style="width:100%; margin-top:8px">
            完成路线（已描 {{ routeDraft.length }} 点）
          </el-button>
        </template>
        <div class="wb-hint">💡 {{ hint }}</div>
      </el-card>

      <el-card class="wb-card" v-if="selectedObj">
        <template #header><b>选中：{{ selectedTitle }}</b></template>
        <template v-if="selected.kind === 'zone'">
          <div class="wb-row"><span class="wb-k">分区名称</span>
            <el-input v-model="selectedObj.name" size="small" />
          </div>
          <div class="wb-tip">范围：{{ selectedObj.rect.map(v => v.toFixed(1)).join(' / ') }}（x, y, w, h 米）</div>
        </template>
        <template v-else-if="selected.kind === 'device'">
          <div class="wb-row"><span class="wb-k">点位名称</span>
            <el-input v-model="selectedObj.label" size="small" />
          </div>
          <div class="wb-tip">类型：{{ kindOf(null, selectedObj.kind)?.name }} · 坐标：({{ selectedObj.x.toFixed(1) }}, {{ selectedObj.y.toFixed(1) }})</div>
        </template>
        <template v-else>
          <div class="wb-tip">停靠点：({{ selectedObj.x.toFixed(1) }}, {{ selectedObj.y.toFixed(1) }}) —— 设备出发与补给位置</div>
        </template>
        <el-button size="small" type="danger" plain @click="deleteSelected" style="width:100%; margin-top:8px">删除选中</el-button>
      </el-card>

      <el-card class="wb-card">
        <template #header><b>③ 清单</b><span class="wb-count">{{ draft.zones.length }} 分区 · {{ draft.devices.length }} 设备 · {{ routeCount }} 路线</span></template>
        <div class="wb-list">
          <div class="wb-list-item" v-for="z in draft.zones" :key="z.id">
            <span @click="selectZone(z.id)">🟦 {{ z.name }}</span>
            <span class="wb-list-sub">
              {{ (draft.routes[z.id]?.length ?? 0) }} 点
              <el-button v-if="draft.routes[z.id]?.length" size="small" text type="danger" @click="draft.routes[z.id] = []">清路线</el-button>
            </span>
          </div>
          <div class="wb-list-empty" v-if="!draft.zones.length">还没有分区，用「分区」模式拖拽画一个</div>
        </div>
      </el-card>

      <el-card class="wb-card">
        <template #header><b>④ 可识别异常</b></template>
        <div class="wb-types">
          <el-check-tag v-for="t in allTypes" :key="t.type"
            :checked="checkedTypes.includes(t.type)" @change="toggleType(t.type)">{{ t.label }}</el-check-tag>
        </div>
        <div class="wb-tip">点选本场景需要 AI 识别的异常类型</div>
      </el-card>

      <el-card class="wb-card">
        <template #header><b>⑤ 场景管理</b></template>
        <div class="wb-actions">
          <el-button type="primary" @click="save">💾 保存场景</el-button>
          <el-button @click="exportJson">导出 JSON</el-button>
          <label class="wb-file-btn">导入 JSON<input type="file" accept=".json,application/json" hidden @change="importJson" /></label>
        </div>
        <div class="wb-row" style="margin-top:10px"><span class="wb-k">载入现有</span>
          <el-select v-model="loadFromId" size="small" style="flex:1" placeholder="选择场景载入编辑">
            <el-option v-for="s in loadScenes" :key="s.id" :value="s.id" :label="s.name" />
          </el-select>
          <el-button size="small" :disabled="!loadFromId" @click="loadFrom">载入</el-button>
        </div>
        <div class="wb-tip">载入内置场景会另存为副本，不影响原场景</div>
      </el-card>
    </aside>

    <!-- 右：编辑画布 -->
    <section class="wb-map-wrap">
      <canvas ref="canvasRef" :width="cw" :height="ch"
        @mousedown="onMouseDown" @mousemove="onMouseMove" @mouseup="onMouseUp"
        @mouseleave="onMouseLeave" @dblclick="onDblClick" @contextmenu.prevent="onContextMenu" />
      <div class="wb-coord">{{ hoverText }}</div>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  ElButton, ElCard, ElCheckTag, ElInput, ElInputNumber,
  ElMessage, ElOption, ElSelect,
} from 'element-plus'
import {
  ANOMALY_TYPE_META, DEFAULT_DEVICE_KINDS, kindOf, validateScene,
  allScenes, saveCustomScene, BUILTIN_SCENES,
} from './scenes/index.js'

const emit = defineEmits(['saved'])

// ---------- 草稿（编辑中的场景） ----------
function emptyDraft() {
  return {
    id: 'custom-' + Date.now(),
    name: '',
    desc: '自建场景（地图工作台绘制）',
    world: { w: 40, h: 30 },
    bg: { color: '#eef2f5', image: null },
    decor: { roads: [], areas: [], rects: [] },
    zones: [], devices: [], routes: {},
    dock: null,
  }
}
const draft = reactive(emptyDraft())

// ---------- 绘制模式 ----------
const MODES = [
  { id: 'select', label: '选择' },
  { id: 'zone', label: '分区' },
  { id: 'device', label: '设备' },
  { id: 'route', label: '路线' },
  { id: 'dock', label: '停靠点' },
]
const HINTS = {
  select: '点击画布中的分区 / 设备 / 停靠点选中，右侧面板可改名或删除',
  zone: '在画布上按住鼠标拖拽，画出一个分区矩形（最小 2×2 米）',
  device: '选好设备类型后，点击画布逐个放置点位（垃圾桶、货架…）',
  route: '选目标分区 → 依次点击画布描路线点 → 双击或点「完成路线」结束',
  dock: '点击画布设置停靠点（设备出发与补给位置）',
}
const mode = ref('select')
const hint = computed(() => HINTS[mode.value] ?? '')

const kinds = DEFAULT_DEVICE_KINDS
const deviceKind = ref('bin')
const routeZone = ref('')
const allTypes = Object.values(ANOMALY_TYPE_META)
const checkedTypes = ref(allTypes.map(t => t.type))

function toggleType(t) {
  const i = checkedTypes.value.indexOf(t)
  if (i >= 0) {
    if (checkedTypes.value.length > 1) checkedTypes.value.splice(i, 1)   // 至少保留 1 类
  } else {
    checkedTypes.value.push(t)
  }
}

function setMode(m) {
  mode.value = m
  if (m !== 'route') routeDraft.value = []
  selected.value = null
  draw()
}

// ---------- 画布与坐标 ----------
const canvasRef = ref(null)
const BASE_W = 1200   // 逻辑分辨率（显示时按容器 CSS 缩放，指针换算已补偿）
const scale = computed(() => BASE_W / draft.world.w)
const cw = computed(() => BASE_W)
const ch = computed(() => Math.round(draft.world.h * scale.value))

const hover = ref(null)
const dragStart = ref(null)   // 分区拖拽起点（世界坐标）
const dragCur = ref(null)     // 拖拽当前点
const routeDraft = ref([])    // 正在描的路线点 [[x,y],...]
const selected = ref(null)    // {kind:'zone'|'device'|'dock', index}

const selectedObj = computed(() => {
  const s = selected.value
  if (!s) return null
  if (s.kind === 'zone') return draft.zones[s.index] ?? null
  if (s.kind === 'device') return draft.devices[s.index] ?? null
  return draft.dock
})
const selectedTitle = computed(() => {
  const s = selected.value
  return s?.kind === 'zone' ? '分区' : s?.kind === 'device' ? '设备点位' : '停靠点'
})
const routeCount = computed(() => Object.values(draft.routes).filter(p => p.length >= 2).length)
const hoverText = computed(() =>
  hover.value ? `鼠标：(${hover.value.x.toFixed(1)}, ${hover.value.y.toFixed(1)}) 米` : '把鼠标移到画布上查看坐标')

function evtToWorld(e) {
  const rect = canvasRef.value.getBoundingClientRect()
  const k = rect.width / canvasRef.value.width || 1   // CSS 缩放补偿（画布自适应容器宽）
  return { x: (e.clientX - rect.left) / (scale.value * k), y: (e.clientY - rect.top) / (scale.value * k) }
}
const round2 = v => Math.round(v * 10) / 10

// ---------- 底图 ----------
const bgImg = ref(null)
watch(() => draft.bg.image, (src) => {
  bgImg.value = null
  if (!src) { draw(); return }
  const img = new Image()
  img.onload = () => { bgImg.value = img; draw() }
  img.src = src
}, { immediate: true })

async function onBgFile(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  try {
    draft.bg.image = await compressImage(file)
    ElMessage.success('底图已载入，可开始描点')
  } catch (err) {
    ElMessage.error('底图载入失败：' + err.message)
  }
}

// 图片压缩到 ≤1280 宽 JPEG（控制 localStorage 体积）
function compressImage(file, maxW = 1280) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      const k = Math.min(1, maxW / img.width)
      const cv = document.createElement('canvas')
      cv.width = Math.round(img.width * k)
      cv.height = Math.round(img.height * k)
      cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height)
      URL.revokeObjectURL(url)
      resolve(cv.toDataURL('image/jpeg', 0.82))
    }
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('图片解析失败')) }
    img.src = url
  })
}

// ---------- 鼠标交互 ----------
function onMouseDown(e) {
  const p = evtToWorld(e)
  if (mode.value === 'zone') { dragStart.value = p; dragCur.value = p }
}
function onMouseMove(e) {
  hover.value = evtToWorld(e)
  if (dragStart.value) dragCur.value = evtToWorld(e)
  draw()
}
function onMouseUp(e) {
  if (!dragStart.value) return
  const p = evtToWorld(e)
  const a = dragStart.value, b = p
  dragStart.value = null; dragCur.value = null
  const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y)
  const w = Math.abs(a.x - b.x), h = Math.abs(a.y - b.y)
  if (w < 2 || h < 2) { draw(); return }
  const name = `分区 ${String.fromCharCode(65 + draft.zones.length)}`
  draft.zones.push({ id: nextZoneId(), name, rect: [round2(x), round2(y), round2(w), round2(h)] })
  if (!routeZone.value) routeZone.value = draft.zones[draft.zones.length - 1].id
  draw()
}
function onMouseLeave() { hover.value = null; draw() }

function onClickCanvas(e) {
  const p = evtToWorld(e)
  if (mode.value === 'device') {
    const kind = kindOf(null, deviceKind.value)
    const n = nextDeviceNum(deviceKind.value)
    draft.devices.push({
      id: `${deviceKind.value}-${n}`, kind: deviceKind.value,
      x: round2(p.x), y: round2(p.y), label: `${kind.name} ${n}`,
    })
    draw()
    return
  }
  if (mode.value === 'dock') {
    draft.dock = { x: round2(p.x), y: round2(p.y) }
    draw()
    return
  }
  if (mode.value === 'route' && routeZone.value) {
    routeDraft.value.push([round2(p.x), round2(p.y)])
    draw()
    return
  }
  if (mode.value === 'select') {
    selected.value = hitTest(p)
    draw()
  }
}
function onDblClick(e) {
  if (mode.value === 'route' && routeDraft.value.length) {
    routeDraft.value.pop()   // dblclick 前的两次 click 会加重复点，弹掉最后一个
    finishRoute()
  }
}
function onContextMenu() {
  if (mode.value === 'route' && routeDraft.value.length) finishRoute()
}

let boundCanvas = null
onMounted(() => {
  boundCanvas = canvasRef.value
  boundCanvas?.addEventListener('click', onClickCanvas)
  draw()
})
onBeforeUnmount(() => boundCanvas?.removeEventListener('click', onClickCanvas))

function finishRoute() {
  if (!routeZone.value || routeDraft.value.length < 2) return
  draft.routes[routeZone.value] = [...routeDraft.value]
  routeDraft.value = []
  ElMessage.success(`路线已保存到「${draft.zones.find(z => z.id === routeZone.value)?.name ?? routeZone.value}」`)
  draw()
}

// ---------- 命中检测与选中 ----------
function hitTest(p) {
  const s = scale.value
  if (draft.dock && Math.hypot(p.x - draft.dock.x, p.y - draft.dock.y) * s < 13) return { kind: 'dock' }
  for (let i = draft.devices.length - 1; i >= 0; i--) {
    const d = draft.devices[i]
    if (Math.hypot(p.x - d.x, p.y - d.y) * s < 11) return { kind: 'device', index: i }
  }
  for (let i = draft.zones.length - 1; i >= 0; i--) {
    const [zx, zy, zw, zh] = draft.zones[i].rect
    if (p.x >= zx && p.x <= zx + zw && p.y >= zy && p.y <= zy + zh) return { kind: 'zone', index: i }
  }
  return null
}
function selectZone(zid) {
  const i = draft.zones.findIndex(z => z.id === zid)
  if (i >= 0) { selected.value = { kind: 'zone', index: i }; draw() }
}
function deleteSelected() {
  const s = selected.value
  if (!s) return
  if (s.kind === 'dock') draft.dock = null
  else if (s.kind === 'device') draft.devices.splice(s.index, 1)
  else if (s.kind === 'zone') {
    const z = draft.zones[s.index]
    draft.zones.splice(s.index, 1)
    delete draft.routes[z.id]
  }
  selected.value = null
  draw()
}

// ---------- id / 编号 ----------
function nextZoneId() {
  const used = new Set(draft.zones.map(z => z.id))
  for (let i = 0; i < 26; i++) {
    const id = 'zone-' + String.fromCharCode(97 + i)
    if (!used.has(id)) return id
  }
  return 'zone-' + Date.now()
}
function nextDeviceNum(kindId) {
  let max = 0
  for (const d of draft.devices) {
    if (d.kind !== kindId) continue
    const n = parseInt(d.id.split('-').pop(), 10)
    if (Number.isFinite(n) && n > max) max = n
  }
  return max + 1
}

// ---------- 渲染 ----------
function draw() {
  const c = canvasRef.value
  if (!c) return
  const ctx = c.getContext('2d')
  const s = scale.value
  const W = c.width, H = c.height

  // 底图
  if (bgImg.value) ctx.drawImage(bgImg.value, 0, 0, W, H)
  else { ctx.fillStyle = draft.bg.color; ctx.fillRect(0, 0, W, H) }

  // 网格（5 米）
  ctx.strokeStyle = 'rgba(0,0,0,0.06)'; ctx.lineWidth = 1
  for (let gx = 5; gx < draft.world.w; gx += 5) {
    ctx.beginPath(); ctx.moveTo(gx * s, 0); ctx.lineTo(gx * s, H); ctx.stroke()
  }
  for (let gy = 5; gy < draft.world.h; gy += 5) {
    ctx.beginPath(); ctx.moveTo(0, gy * s); ctx.lineTo(W, gy * s); ctx.stroke()
  }

  // 分区
  draft.zones.forEach((z, i) => {
    const [zx, zy, zw, zh] = z.rect
    const sel = selected.value?.kind === 'zone' && selected.value.index === i
    ctx.setLineDash([6, 5]); ctx.lineWidth = sel ? 2.5 : 1.5
    ctx.strokeStyle = sel ? '#f56c6c' : 'rgba(64,128,200,0.6)'
    ctx.strokeRect(zx * s, zy * s, zw * s, zh * s)
    ctx.setLineDash([])
    ctx.fillStyle = 'rgba(64,128,200,0.08)'
    ctx.fillRect(zx * s, zy * s, zw * s, zh * s)
    ctx.fillStyle = 'rgba(60,90,130,0.85)'
    ctx.font = '12px sans-serif'
    ctx.fillText(z.name, zx * s + 8, zy * s + 18)
  })

  // 分区拖拽预览
  if (dragStart.value && dragCur.value) {
    const x = Math.min(dragStart.value.x, dragCur.value.x) * s
    const y = Math.min(dragStart.value.y, dragCur.value.y) * s
    const w = Math.abs(dragStart.value.x - dragCur.value.x) * s
    const h = Math.abs(dragStart.value.y - dragCur.value.y) * s
    ctx.strokeStyle = '#409eff'; ctx.lineWidth = 2; ctx.setLineDash([6, 4])
    ctx.strokeRect(x, y, w, h); ctx.setLineDash([])
    ctx.fillStyle = 'rgba(64,158,255,0.12)'; ctx.fillRect(x, y, w, h)
  }

  // 已保存路线
  for (const [zid, pts] of Object.entries(draft.routes)) {
    if (!pts?.length) continue
    const px = pts.map(p => [p[0] * s, p[1] * s])
    strokePolyline(ctx, px, 'rgba(64,128,255,0.75)', 3, false)
    markDots(ctx, px, '#409eff')
  }

  // 正在描的路线 + hover 预览
  if (routeDraft.value.length) {
    const pts = routeDraft.value.map(p => [p[0] * s, p[1] * s])
    strokePolyline(ctx, pts, '#e6a23c', 3, true)
    markDots(ctx, pts, '#e6a23c')
    if (hover.value && mode.value === 'route') {
      const last = pts[pts.length - 1]
      ctx.strokeStyle = 'rgba(230,162,60,0.6)'; ctx.lineWidth = 2; ctx.setLineDash([5, 5])
      ctx.beginPath(); ctx.moveTo(last[0], last[1]); ctx.lineTo(hover.value.x * s, hover.value.y * s); ctx.stroke()
      ctx.setLineDash([])
    }
  }

  // 设备点位
  draft.devices.forEach((d, i) => {
    const kind = kindOf(null, d.kind)
    const bx = d.x * s, by = d.y * s
    const sel = selected.value?.kind === 'device' && selected.value.index === i
    const hov = hover.value && Math.hypot(hover.value.x - d.x, hover.value.y - d.y) * s < 11
    ctx.fillStyle = kind?.color ?? '#606266'
    if (kind?.shape === 'square') {
      ctx.fillRect(bx - 7, by - 7, 14, 14)
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.strokeRect(bx - 7, by - 7, 14, 14)
    } else if (kind?.shape === 'bar') {
      ctx.fillRect(bx - 9, by - 4, 18, 8)
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.strokeRect(bx - 9, by - 4, 18, 8)
    } else {
      ctx.beginPath(); ctx.arc(bx, by, 6, 0, Math.PI * 2); ctx.fill()
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5; ctx.stroke()
    }
    if (sel || hov) {
      ctx.strokeStyle = '#f56c6c'; ctx.lineWidth = 2
      ctx.beginPath(); ctx.arc(bx, by, 12, 0, Math.PI * 2); ctx.stroke()
      // 名称标签
      const label = d.label
      ctx.font = 'bold 11px sans-serif'
      const tw = ctx.measureText(label).width
      ctx.fillStyle = 'rgba(0,0,0,0.75)'
      ctx.fillRect(bx + 12, by - 8, tw + 8, 16)
      ctx.fillStyle = '#fff'
      ctx.fillText(label, bx + 16, by + 4)
    }
  })

  // 停靠点
  if (draft.dock) {
    const dx = draft.dock.x * s, dy = draft.dock.y * s
    const sel = selected.value?.kind === 'dock'
    ctx.strokeStyle = sel ? '#f56c6c' : '#155eab'; ctx.lineWidth = sel ? 3 : 2
    ctx.beginPath(); ctx.arc(dx, dy, 10, 0, Math.PI * 2); ctx.stroke()
    ctx.fillStyle = '#155eab'; ctx.font = '10px sans-serif'; ctx.textAlign = 'center'
    ctx.fillText('dock', dx, dy + 24); ctx.textAlign = 'left'
  }

  // 模式光标提示（设备/停靠点跟随鼠标）
  if (hover.value && (mode.value === 'device' || mode.value === 'dock')) {
    const hx = hover.value.x * s, hy = hover.value.y * s
    ctx.strokeStyle = mode.value === 'device' ? 'rgba(96,98,102,0.8)' : 'rgba(21,94,171,0.8)'
    ctx.lineWidth = 1.5
    ctx.beginPath(); ctx.arc(hx, hy, 8, 0, Math.PI * 2); ctx.stroke()
    ctx.beginPath(); ctx.moveTo(hx - 12, hy); ctx.lineTo(hx + 12, hy)
    ctx.moveTo(hx, hy - 12); ctx.lineTo(hx, hy + 12); ctx.stroke()
  }
}

function strokePolyline(ctx, pts, color, width, dashed) {
  if (pts.length < 2) return
  ctx.strokeStyle = color; ctx.lineWidth = width
  if (dashed) ctx.setLineDash([8, 6])
  ctx.beginPath(); ctx.moveTo(pts[0][0], pts[0][1])
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1])
  ctx.stroke()
  ctx.setLineDash([])
}
function markDots(ctx, pts, color) {
  ctx.fillStyle = color
  for (const p of pts) {
    ctx.beginPath(); ctx.arc(p[0], p[1], 4, 0, Math.PI * 2); ctx.fill()
  }
}

watch(() => [draft.zones, draft.devices, draft.routes, draft.dock, draft.world.w, draft.world.h, draft.name, mode.value, routeDraft.value, selected.value],
  draw, { deep: true })

// ---------- 草稿 ↔ Scene ----------
function draftToScene() {
  return {
    id: draft.id || 'custom-' + Date.now(),
    name: draft.name.trim(),
    desc: draft.desc,
    world: { w: draft.world.w, h: draft.world.h },
    bg: { color: draft.bg.color, image: draft.bg.image ?? undefined },
    decor: { roads: [], areas: [], rects: [] },
    zones: draft.zones.map(z => ({ id: z.id, name: z.name, rect: [...z.rect] })),
    devices: draft.devices.map(d => ({ id: d.id, kind: d.kind, x: d.x, y: d.y, label: d.label })),
    routes: Object.fromEntries(Object.entries(draft.routes).map(([k, v]) => [k, v.map(p => [...p])])),
    dock: draft.dock ? { ...draft.dock } : null,
    anomalyTypes: checkedTypes.value.map(t => ({ type: t, ...ANOMALY_TYPE_META[t] })),
    anomalies: [],
    findings: [],
  }
}
function applyDraft(scene) {
  Object.assign(draft, JSON.parse(JSON.stringify({
    id: scene.id, name: scene.name, desc: scene.desc ?? '自建场景（地图工作台绘制）',
    world: scene.world, bg: { color: scene.bg?.color ?? '#eef2f5', image: scene.bg?.image ?? null },
    decor: scene.decor ?? { roads: [], areas: [], rects: [] },
    zones: scene.zones ?? [], devices: scene.devices ?? [], routes: scene.routes ?? {},
    dock: scene.dock ?? null,
  })))
  const types = (scene.anomalyTypes ?? []).map(t => t.type)
  checkedTypes.value = types.length ? types : allTypes.map(t => t.type)
  selected.value = null
  routeDraft.value = []
  routeZone.value = draft.zones[0]?.id ?? ''
}

// ---------- 保存 / 导入 / 导出 / 载入 ----------
function save() {
  if (!draft.name.trim()) { ElMessage.warning('请先填写场景名称'); return }
  if (!draft.zones.length) { ElMessage.warning('请至少绘制一个分区（用「分区」模式拖拽）'); return }
  if (!draft.dock) { ElMessage.warning('请设置停靠点（用「停靠点」模式点击画布）'); return }
  if (!checkedTypes.value.length) { ElMessage.warning('请至少点选一种可识别异常类型'); return }
  for (const z of draft.zones) {
    if (!draft.routes[z.id] || draft.routes[z.id].length < 2) {
      ElMessage.warning(`分区「${z.name}」还缺巡逻路线：用「路线」模式描点`); return
    }
  }
  const scene = draftToScene()
  const errs = validateScene(scene)
  if (errs.length) { ElMessage.error('场景数据不完整：' + errs.join('；')); return }
  try {
    saveCustomScene(scene)
    ElMessage.success(`场景「${scene.name}」已保存，切到「实时巡检」即可使用`)
    emit('saved')
  } catch (err) {
    ElMessage.error('保存失败：' + (err?.message ?? err) + '（可先「导出 JSON」备份，底图过大时会超出本地存储上限）')
  }
}

function exportJson() {
  const scene = draftToScene()
  const blob = new Blob([JSON.stringify(scene, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${scene.id}.json`
  a.click()
  URL.revokeObjectURL(a.href)
}

async function importJson(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  try {
    const scene = JSON.parse(await file.text())
    const errs = validateScene(scene)
    if (errs.length) throw new Error(errs.join('；'))
    applyDraft(scene)
    ElMessage.success(`已导入「${scene.name}」，可继续编辑`)
  } catch (err) {
    ElMessage.error('导入失败：' + (err?.message ?? err))
  }
}

// 载入现有场景（内置 → 生成副本；自建 → 原地覆盖保存）
const loadScenes = computed(() => allScenes())
const loadFromId = ref('')
function loadFrom() {
  const s = loadScenes.value.find(x => x.id === loadFromId.value)
  if (!s) return
  const copy = JSON.parse(JSON.stringify(s))
  if (BUILTIN_SCENES.some(b => b.id === s.id)) {
    copy.id = 'custom-' + Date.now()
    copy.name = s.name + '（副本）'
  }
  applyDraft(copy)
  ElMessage.success(`已载入「${s.name}」${BUILTIN_SCENES.some(b => b.id === s.id) ? '（副本，保存不影响原场景）' : ''}`)
}
</script>

<style scoped>
.workbench { display: flex; gap: 18px; align-items: stretch; height: calc(100vh - 238px); min-height: 520px; }
.wb-side { width: 320px; flex: none; display: flex; flex-direction: column; gap: 12px; overflow-y: auto; padding-right: 4px; }
.wb-card :deep(.el-card__body) { display: flex; flex-direction: column; gap: 8px; }
.wb-row { display: flex; align-items: center; gap: 8px; }
.wb-k { font-size: 13px; color: #909399; flex: none; width: 64px; }
.wb-tip { font-size: 12px; color: #909399; line-height: 1.5; }
.wb-hint { font-size: 12px; color: #909399; background: #f4f7fa; border-radius: 6px; padding: 8px 10px; line-height: 1.6; }
.wb-modes { display: flex; flex-wrap: wrap; gap: 6px; }
.wb-types { display: flex; flex-wrap: wrap; gap: 6px; }
.wb-count { margin-left: auto; font-size: 12px; color: #909399; font-weight: normal; }
.wb-list { max-height: 160px; overflow-y: auto; }
.wb-list-item { display: flex; justify-content: space-between; align-items: center; padding: 4px 2px; font-size: 13px; cursor: pointer; border-bottom: 1px dashed #f0f0f0; }
.wb-list-item:hover { color: #409eff; }
.wb-list-sub { color: #909399; font-size: 12px; display: flex; gap: 4px; align-items: center; }
.wb-list-empty { color: #c0c4cc; font-size: 12px; text-align: center; padding: 12px 0; }
.wb-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.wb-file-btn { display: inline-flex; align-items: center; padding: 5px 12px; border: 1px solid #dcdfe6; border-radius: 4px; font-size: 13px; color: #606266; cursor: pointer; }
.wb-file-btn:hover { color: #409eff; border-color: #c6e2ff; background: #ecf5ff; }
.wb-map-wrap { flex: 1; min-width: 0; padding: 14px; border-radius: 8px; background: #fff; box-shadow: 0 2px 12px rgba(0,0,0,0.08); position: relative; display: flex; align-items: center; justify-content: center; }
.wb-map-wrap canvas { border-radius: 8px; cursor: crosshair; display: block; max-width: 100%; max-height: 100%; width: auto; height: auto; }
.wb-coord { position: absolute; right: 18px; bottom: 16px; background: rgba(0,0,0,0.65); color: #fff; font-size: 12px; padding: 3px 10px; border-radius: 10px; }

/* 窄窗口降级单列 */
@media (max-width: 1180px) {
  .workbench { flex-direction: column; min-height: 0; height: auto; }
  .wb-side { width: auto; overflow-y: visible; }
  .wb-map-wrap canvas { max-height: none; }
}

/* 深色主题 */
.app[data-theme='dark'] .wb-map-wrap { background: #101d2d; box-shadow: 0 0 24px rgba(64,158,255,0.15); }
.app[data-theme='dark'] .wb-hint { background: #14273d; }
.app[data-theme='dark'] .wb-tip, .app[data-theme='dark'] .wb-k,
.app[data-theme='dark'] .wb-count, .app[data-theme='dark'] .wb-list-sub { color: #5d7a99; }
.app[data-theme='dark'] .wb-list-item { border-bottom-color: #14273d; }
.app[data-theme='dark'] .wb-file-btn { color: #9fb8d4; border-color: #1d3350; }
</style>
