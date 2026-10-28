<!-- AICenter.vue —— AI 识别中心
     职责：真图识别（虚→实）入口——上传真实巡检照片，经本地后端调用多模态大模型判读，
     识别结果（类型/把握/证据）留档于识别记录，可一键「回填到当前场景」进入巡检闭环。
     同页提供模型配置（Base URL / API Key / 模型名，保存前自动试连校验，
     Key 仅落本机 server/config.local.json 不出机）；
     后端离线时自动降级为提示模式，页面其余功能不受影响。 -->
<template>
  <div class="ai-center">
    <!-- 左：模型配置 + 上传与识别 -->
    <aside class="ai-side">
      <el-card class="ai-card">
        <template #header>
          <b>🔑 模型配置</b>
          <span :class="['dot', modelCfg.configured ? 'ok' : 'warn']" style="margin-left:8px"></span>
          <span class="cfg-state">{{ modelCfg.configured ? `已连接：${modelCfg.model}` : '未配置（离线模式）' }}</span>
          <el-button v-if="modelCfg.configured && !editing" size="small" text type="primary" @click="startEdit">修改</el-button>
        </template>
        <template v-if="editing || !modelCfg.configured">
          <div class="cfg-form">
            <el-input v-model="form.baseUrl" placeholder="接口地址，如 https://api.xx.com/v1" size="small" clearable>
              <template #prepend>接口地址</template>
            </el-input>
            <el-input v-model="form.apiKey" type="password" show-password size="small" clearable
              :placeholder="modelCfg.configured ? '留空则沿用已保存的 Key' : '你的 API Key（sk-…）'">
              <template #prepend>API Key</template>
            </el-input>
            <el-input v-model="form.model" placeholder="模型名，如 qwen-vl-plus / gpt-4o-mini" size="small" clearable>
              <template #prepend>模型名</template>
            </el-input>
            <div class="cfg-tip">支持任意 OpenAI 兼容多模态接口；Key 只保存在本机 server/config.local.json（已加入 .gitignore），不出本机。</div>
            <div class="cfg-btns">
              <el-button type="primary" size="small" :loading="saving" @click="saveConfig">保存并验证</el-button>
              <el-button v-if="modelCfg.configured" size="small" @click="editing = false">取消</el-button>
            </div>
            <div v-if="cfgError" class="cfg-err">⚠️ {{ cfgError }}</div>
          </div>
        </template>
        <div v-else class="cfg-brief">
          <template v-if="modelCfg.configured">
            接口 {{ modelCfg.baseUrl }} · Key {{ modelCfg.apiKeyMasked }}
          </template>
          <template v-else>
            填入你自己的模型 Key 即可启用 AI 识别与巡检助手的大模型能力；不填也能用（识别中心上传回填、助手规则模式仍可用）。
          </template>
        </div>
      </el-card>

      <el-card class="ai-card upload-card">
        <template #header><b>📷 上传巡检照片</b></template>
        <label class="ai-drop" :class="{ has: imgUrl }">
          <img v-if="imgUrl" :src="imgUrl" alt="待识别照片" />
          <div v-else class="ai-drop-tip">
            <div class="big">📷</div>
            <div>点击选择照片</div>
            <div class="sub">或拖拽到此处（jpg / png，≤8MB）</div>
          </div>
          <input type="file" accept="image/jpeg,image/png,image/webp" hidden @change="onFile" />
        </label>
        <el-button type="primary" size="large" style="width:100%; margin-top: 12px"
          :disabled="!imgUrl" :loading="loading" @click="recognize">
          {{ loading ? '🔍 识别中…' : '🔍 开始识别' }}
        </el-button>
        <div class="ai-tip">
          识别由本地后端调用多模态大模型完成（key 留在本机配置文件，不出网不留档）。
          <span :class="['dot', backendOk ? 'ok' : 'bad']"></span>{{ backendText }}
        </div>
      </el-card>
      <el-card class="ai-card" v-if="result">
        <template #header><b>识别结果</b><el-tag v-if="result.found" size="small" type="danger" style="margin-left:8px">{{ result.label }}</el-tag><el-tag v-else size="small" type="success" style="margin-left:8px">未发现异常</el-tag></template>
        <template v-if="result.found">
          <div class="ai-meta">
            <div class="row"><span class="k">异常类型</span><b>{{ result.label }}（{{ result.type }}）</b></div>
            <div class="row"><span class="k">把握程度</span>
              <el-progress :percentage="Math.round(result.confidence * 100)" :stroke-width="12"
                :color="result.confidence >= 0.9 ? '#f56c6c' : '#e6a23c'" style="flex:1" />
            </div>
            <div class="row"><span class="k">画面描述</span><span class="v">{{ result.evidence }}</span></div>
          </div>
          <el-button type="warning" style="width:100%; margin-top: 12px" @click="fillToScene">📍 回填到当前场景</el-button>
          <div class="ai-tip">回填后：异常进当前场景的地图与巡检报告，证据照片进入证据系统（虚→实）</div>
        </template>
        <div v-else class="ai-clean">✅ 照片未见巡检异常类型（{{ typesText }}）</div>
      </el-card>
    </aside>

    <!-- 右：识别记录 -->
    <section class="ai-main">
      <el-card class="ai-card">
        <template #header>
          <b>📋 识别记录</b><span class="ai-count">{{ history.length }} 条</span>
          <el-button v-if="history.length" size="small" text type="danger" style="margin-left:10px" @click="clearHistory">清空</el-button>
        </template>
        <div v-if="!history.length" class="ai-empty">还没有识别记录。上传一张真实巡检照片试试——识别结果会在这里留档，回填后进入巡检闭环。</div>
        <div v-for="h in history.slice().reverse()" :key="h.id" class="ai-hitem" :class="{ found: h.found }">
          <img class="thumb" :src="h.img" alt="" @click="previewImg = h.img" />
          <div class="hbody">
            <div class="h1">
              <b>{{ h.found ? h.label : '无异常' }}</b>
              <span class="conf">{{ h.found ? `把握 ${(h.confidence * 100) | 0}%` : '—' }}</span>
              <el-tag v-if="h.filled" size="small" type="success">已回填</el-tag>
            </div>
            <div class="h2">{{ h.evidence }}</div>
            <div class="h3">{{ fmtTime(h.ts) }}</div>
          </div>
          <el-button v-if="h.found && !h.filled" size="small" type="warning" plain @click="fillFromHistory(h)">回填</el-button>
        </div>
      </el-card>
    </section>

    <!-- 大图预览 -->
    <el-dialog v-model="previewShown" width="640px" align-center>
      <img :src="previewImg" style="width:100%; border-radius:8px" alt="预览" />
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElButton, ElCard, ElDialog, ElInput, ElMessage, ElProgress, ElTag } from 'element-plus'
import { anomalyMeta } from './scenes/sceneSchema.js'

const props = defineProps({
  scene: { type: Object, required: true },   // 当前巡检场景
})
const emit = defineEmits(['fill-anomaly'])

const API = 'http://127.0.0.1:8788'

// ---------- 上传 ----------
const imgUrl = ref(null)
const imgFile = ref(null)
const loading = ref(false)
const result = ref(null)
const history = ref([])
const previewImg = ref(null)
const previewShown = ref(false)

const backendOk = ref(null)   // null=未探测 true/false
const backendText = computed(() =>
  backendOk.value === null ? '后端探测中…' : backendOk.value
    ? '识别服务在线'
    : '在线静态演示：AI 识别需本地运行后端（见 README），AI 助手已自动降级为离线规则模式')

// ---------- 模型配置（评审自己填 Key，开箱即用） ----------
const modelCfg = ref({ configured: null, baseUrl: '', model: '', apiKeyMasked: '' })
const editing = ref(false)
const saving = ref(false)
const cfgError = ref('')
const form = ref({ baseUrl: '', apiKey: '', model: '' })

async function loadModelCfg() {
  try {
    const r = await fetch(`${API}/api/config/model`, { signal: AbortSignal.timeout(2500) })
    if (r.ok) modelCfg.value = await r.json()
  } catch { /* 后端离线时保持默认 */ }
}
function startEdit() {
  form.value = { baseUrl: modelCfg.value.baseUrl, apiKey: '', model: modelCfg.value.model }
  cfgError.value = ''
  editing.value = true
}
async function saveConfig() {
  saving.value = true
  cfgError.value = ''
  try {
    const r = await fetch(`${API}/api/config/model`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form.value), signal: AbortSignal.timeout(25000),
    })
    const d = await r.json().catch(() => ({}))
    if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`)
    editing.value = false
    await loadModelCfg()
    ElMessage.success(`模型配置已保存（Key ${d.apiKeyMasked}），AI 功能已就绪`)
  } catch (e) {
    cfgError.value = e.message
  } finally {
    saving.value = false
  }
}

const typesText = computed(() => (props.scene?.anomalyTypes ?? []).map(t => t.label).join(' / '))

async function onFile(e) {
  const f = e.target.files?.[0]
  e.target.value = ''
  if (!f) return
  if (f.size > 8 * 1024 * 1024) { ElMessage.warning('图片超过 8MB，请压缩后重试'); return }
  imgFile.value = f
  imgUrl.value = URL.createObjectURL(f)
  result.value = null
  checkBackend()
}

// ---------- 后端探测 ----------
async function checkBackend() {
  if (backendOk.value !== null) return
  try {
    const r = await fetch(`${API}/api/health`, { signal: AbortSignal.timeout(2500) })
    backendOk.value = r.ok
  } catch {
    backendOk.value = false
  }
}
onMounted(loadModelCfg)

// ---------- 识别 ----------
// 识别请求直发本地后端（90s 超时对齐服务端大模型调用上限）；
// 网络类失败（无后端）时给出「静态演示」降级提示，不当作异常报错
async function recognize() {
  if (!imgFile.value) return
  checkBackend()
  loading.value = true
  result.value = null
  try {
    const fd = new FormData()
    fd.append('file', imgFile.value)
    const r = await fetch(`${API}/api/recognize`, { method: 'POST', body: fd, signal: AbortSignal.timeout(90000) })
    if (!r.ok) {
      const err = await r.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${r.status}`)
    }
    const data = await r.json()
    result.value = data
    // 留档
    history.value.push({
      id: Date.now(), img: imgUrl.value, found: data.found, type: data.type,
      label: data.label, confidence: data.confidence, evidence: data.evidence,
      ts: Date.now(), filled: false,
    })
    if (data.found) ElMessage.success(`识别到：${data.label}（把握 ${Math.round(data.confidence * 100)}%）`)
    else ElMessage.success('识别完成：未发现异常')
  } catch (e) {
    const networkFail = /fetch|network|timeout/i.test(String(e?.name) + String(e?.message))
    ElMessage.error(networkFail
      ? '当前为在线静态演示，AI 识别需后端服务——完整 AI 演示请观看演示视频，或按 README 本地部署体验'
      : '识别失败：' + e.message)
  } finally {
    loading.value = false
  }
}

// ---------- 回填当前场景 ----------
function fillToScene() {
  if (!result.value?.found) return
  doFill(result.value)
}
function fillFromHistory(h) {
  doFill(h)
}
function doFill(r) {
  const meta = anomalyMeta(props.scene, r.type)
  const near = props.scene.dock ? `人工标注（${props.scene.name}）` : '人工标注'
  // 组装统一协议的异常对象：证据照片用用户上传原图，来源标记「真图识别」
  emit('fill-anomaly', {
    type: r.type,
    label: meta.label || r.label,
    confidence: r.confidence,
    evidence: `真图识别：${r.evidence}`,
    near,
    frameRef: imgUrl.value,     // 证据照片 = 用户上传原图
    frameTitle: `AI 识别证据帧（${meta.label}）`,
    frameDesc: r.evidence,
  })
  r.filled = true
  // 同步「已回填」标记：r 可能是当前结果对象或历史记录对象，两种路径都要置位
  if (result.value && result.value === r) { /* result 视图同步 */ }
  const h = history.value.find(x => (result.value === r ? x.id === history.value.at(-1)?.id : x === r))
  if (h) h.filled = true
  ElMessage.success(`已回填「${meta.label || r.label}」到当前场景`)
}

function clearHistory() {
  history.value.forEach(h => h.img && URL.revokeObjectURL(h.img))
  history.value = []
}

function fmtTime(ts) {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}
</script>

<style scoped>
.ai-center { display: grid; grid-template-columns: 460px minmax(0, 1fr); gap: 18px; align-items: stretch; min-height: calc(100vh - 238px); }
.ai-side { display: flex; flex-direction: column; gap: 14px; }
.ai-side .ai-card { display: flex; flex-direction: column; }
.ai-side .upload-card { flex: 1; }
.ai-side .upload-card :deep(.el-card__body) { flex: 1; }
.ai-main { min-width: 0; display: flex; flex-direction: column; }
.ai-main .ai-card { flex: 1; display: flex; flex-direction: column; }
.ai-main .ai-card :deep(.el-card__body) { flex: 1; overflow-y: auto; min-height: 0; }
.ai-card :deep(.el-card__body) { display: flex; flex-direction: column; gap: 8px; }
.ai-drop { display: flex; align-items: center; justify-content: center; border: 2px dashed #c0c4cc; border-radius: 10px; min-height: 220px; cursor: pointer; overflow: hidden; transition: border-color .2s; flex: 1; }
.ai-drop:hover { border-color: #409eff; }
.ai-drop.has { border-style: solid; border-color: #dcdfe6; }
.ai-drop img { width: 100%; max-height: 320px; object-fit: contain; display: block; }
.ai-drop-tip { text-align: center; color: #909399; padding: 24px 0; }
.ai-drop-tip .big { font-size: 40px; margin-bottom: 8px; }
.ai-drop-tip .sub { font-size: 12px; margin-top: 6px; color: #c0c4cc; }
.ai-tip { font-size: 12px; color: #909399; line-height: 1.6; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin: 0 5px 0 8px; vertical-align: middle; }
.dot.ok { background: #67c23a; }
.dot.bad { background: #f56c6c; }
.dot.warn { background: #e6a23c; }
.cfg-state { color: #909399; font-size: 12px; font-weight: normal; margin-right: auto; }
.cfg-brief { font-size: 12px; color: #909399; line-height: 1.7; }
.cfg-form { display: flex; flex-direction: column; gap: 8px; }
.cfg-tip { font-size: 11px; color: #c0c4cc; line-height: 1.6; }
.cfg-btns { display: flex; gap: 8px; }
.cfg-err { font-size: 12px; color: #f56c6c; line-height: 1.5; }
.ai-meta { display: flex; flex-direction: column; gap: 10px; }
.ai-meta .row { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.ai-meta .k { color: #909399; flex: none; width: 64px; }
.ai-clean { text-align: center; color: #67c23a; padding: 18px 0; font-size: 14px; }
.ai-count { margin-left: 10px; color: #909399; font-size: 12px; font-weight: normal; }
.ai-empty { color: #c0c4cc; text-align: center; padding: 40px 20px; font-size: 13px; line-height: 1.8; }
.ai-hitem { display: flex; gap: 12px; align-items: center; padding: 10px 4px; border-bottom: 1px dashed #f0f0f0; }
.ai-hitem.found { background: #fffaf4; border-radius: 8px; padding: 10px; margin-bottom: 6px; }
.thumb { width: 64px; height: 48px; object-fit: cover; border-radius: 6px; cursor: pointer; flex: none; }
.hbody { flex: 1; min-width: 0; }
.h1 { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.conf { color: #909399; font-size: 12px; }
.h2 { font-size: 12px; color: #606266; margin: 3px 0; line-height: 1.5; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.h3 { font-size: 11px; color: #c0c4cc; }

/* 深色主题 */
.app[data-theme='dark'] .ai-drop { border-color: #1d3350; }
.app[data-theme='dark'] .ai-drop:hover { border-color: #409eff; }
.app[data-theme='dark'] .ai-drop.has { border-color: #1d3350; }
.app[data-theme='dark'] .ai-tip, .app[data-theme='dark'] .ai-meta .k,
.app[data-theme='dark'] .ai-count, .app[data-theme='dark'] .h2 { color: #5d7a99; }
.app[data-theme='dark'] .ai-hitem { border-bottom-color: #14273d; }
.app[data-theme='dark'] .ai-hitem.found { background: #1a2536; }
.app[data-theme='dark'] .ai-empty { color: #3a506b; }
.app[data-theme='dark'] .cfg-state, .app[data-theme='dark'] .cfg-brief { color: #5d7a99; }
.app[data-theme='dark'] .cfg-tip { color: #3a506b; }

/* 窄窗口降级单列 */
@media (max-width: 1180px) {
  .ai-center { grid-template-columns: 1fr; min-height: 0; }
  .ai-side .upload-card { flex: none; }
  .ai-drop { flex: none; }
}
</style>
