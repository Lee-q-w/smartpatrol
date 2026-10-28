<!-- EvidenceDialog.vue —— 异常证据详情弹窗
     职责：以只读视角展示单条异常的完整证据链：
     近景照片（frameRef）+ 无人机俯拍复核帧 + 元信息（类型/位置/把握程度/复核状态/处置进度/证据描述）。
     数据源：父组件传入的 anomaly 对象（三数据源统一协议产出），
     通过 defineExpose({ open }) 供父组件以 ref 方式唤起。 -->
<template>
  <el-dialog v-model="visible" :title="anomaly ? `${anomaly.label} — 证据详情` : '证据详情'" width="720px" align-center>
    <div class="evi-body" v-if="anomaly">
      <div class="evi-photos">
        <figure v-if="anomaly.frameRef">
          <img :src="anomaly.frameRef" :alt="anomaly.frameTitle" />
          <figcaption>{{ anomaly.frameTitle }}<span v-if="anomaly.frameDesc">{{ anomaly.frameDesc }}</span></figcaption>
        </figure>
        <figure v-else class="no-photo">
          <div class="no-photo-box">📷<b>暂无照片</b><span>接入真图识别后自动采集补充</span></div>
        </figure>
        <figure v-if="showDroneFrame">
          <img :src="DRONE_FRAME.ref" :alt="DRONE_FRAME.title" />
          <figcaption>{{ DRONE_FRAME.title }}<span>无人机 8 米悬停俯拍，与地面照片交叉确认。</span></figcaption>
        </figure>
      </div>
      <div class="evi-meta">
        <div class="meta-row"><span class="k">类型</span><span>{{ anomaly.label }}</span></div>
        <div class="meta-row"><span class="k">位置</span><span>{{ anomaly.near }}（世界坐标 {{ fmtPos(anomaly.pos) }}）</span></div>
        <div class="meta-row">
          <span class="k">把握程度</span>
          <el-progress :percentage="Math.round(anomaly.confidence * 100)" :stroke-width="12"
            :color="anomaly.confidence >= 0.95 ? '#f56c6c' : '#e6a23c'" style="flex:1" />
        </div>
        <div class="meta-row"><span class="k">复核状态</span>
          <el-tag size="small" :type="anomaly.stage === 'confirmed' ? 'danger' : anomaly.stage === 'rechecking' ? 'warning' : 'info'">
            {{ stageName }}
          </el-tag>
        </div>
        <div class="meta-row"><span class="k">处置进度</span>
          <el-tag size="small" :type="ticketType" round>📋 {{ ticketName }}</el-tag>
          <span v-if="anomaly.handle?.note" class="ticket-note">{{ anomaly.handle.note }}</span>
        </div>
        <div class="meta-row"><span class="k">证据描述</span><span class="evi-text">{{ anomaly.evidence }}</span></div>
      </div>
    </div>
    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElDialog, ElButton, ElProgress, ElTag } from 'element-plus'
import { DRONE_FRAME } from './parkData.js'

const props = defineProps({ anomaly: { type: Object, default: null } })
const visible = ref(false)

// 已复核确认且非真机实拍：可展示无人机俯拍帧做交叉确认（真机实拍无对应俯拍数据）
const showDroneFrame = computed(() => props.anomaly?.stage === 'confirmed' && props.anomaly?.source !== 'real-ai')
// 复核/工单状态的中文标签与标签色映射（detected→灰 / rechecking→黄 / confirmed→红）
const stageName = computed(() => ({ detected: '初步判断（待复核）', rechecking: '无人机复核中', confirmed: '已复核确认' }[props.anomaly?.stage]))
const ticketName = computed(() => ({ pending: '未处理', processing: '处理中', resolved: '已处置完成' }[props.anomaly?.handle?.status] ?? '未处理'))
const ticketType = computed(() => ({ pending: 'warning', processing: 'primary', resolved: 'success' }[props.anomaly?.handle?.status] ?? 'warning'))

// open()：供父组件通过 ref 调用唤起弹窗
function open() { visible.value = true }
// fmtPos()：世界坐标保留一位小数展示
function fmtPos(p) { return `(${p.x.toFixed(1)}, ${p.y.toFixed(1)})` }
defineExpose({ open })
</script>

<style scoped>
.evi-body { display: flex; flex-direction: column; gap: 16px; }
.evi-photos { display: flex; gap: 14px; }
.evi-photos figure { flex: 1; margin: 0; }
.no-photo-box { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; min-height: 180px; border: 1px dashed #c0c4cc; border-radius: 8px; color: #909399; font-size: 22px; }
.no-photo-box b { font-size: 13px; color: #606266; }
.ticket-note { color: #909399; font-size: 12px; margin-left: 8px; }
.no-photo-box span { font-size: 12px; color: #909399; }
.evi-photos img { width: 100%; border-radius: 8px; border: 1px solid #dcdfe6; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
.evi-photos figcaption { font-size: 12px; color: #606266; margin-top: 6px; line-height: 1.6; }
.evi-photos figcaption span { display: block; color: #909399; }
.evi-meta { display: flex; flex-direction: column; gap: 10px; }
.meta-row { display: flex; gap: 12px; align-items: center; font-size: 13px; }
.meta-row .k { color: #909399; flex: none; width: 70px; }
.evi-text { color: #606266; line-height: 1.6; }
</style>