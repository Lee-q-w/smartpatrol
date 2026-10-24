<template>
  <div class="home-view">
    <!-- 问候与行动条（替代原 Hero：不重复顶栏的 logo/产品名，直接给状态与行动） -->
    <section class="greet-bar">
      <div class="greet-left">
        <h2>{{ greeting }} 👋</h2>
        <p class="greet-status" :class="{ warn: stats.pending > 0 }">
          <template v-if="stats.pending > 0">当前有 <b>{{ stats.pending }}</b> 处异常待处理 · {{ sceneName }} · {{ phaseText }}</template>
          <template v-else>{{ sceneName }}一切正常 · {{ phaseText }}</template>
        </p>
        <div class="greet-tags">
          <span>🤖 AI Agent 驱动</span>
          <span>📋 发现 → 处置 → 报告 全闭环</span>
          <span>🔓 {{ modelConfigured ? '大模型已连接' : '开箱即用 · 填 Key 解锁大模型' }}</span>
        </div>
      </div>
      <div class="greet-right">
        <button class="big-cta" @click="$emit('quick-patrol')">▶ 一键全面体检</button>
        <span class="cta-sub">自动巡逻全园 · AI 识别异常 · 生成报告</span>
      </div>
    </section>

    <!-- 四大模块入口（大模块形态：参考获奖作品的干净卡片网格——大图标 + 名称 + 一句话） -->
    <section class="modules">
      <div
        v-for="m in modules" :key="m.key" class="mod-card"
        :style="{ '--tint': m.tint, '--glow': m.glow }"
        @click="$emit('enter', m.key)"
      >
        <div class="mod-icon">{{ m.icon }}</div>
        <b class="mod-title">{{ m.title }}</b>
        <p class="mod-sub">{{ m.sub }}</p>
      </div>
    </section>

    <!-- 当前状态概览（首页也要"活"） -->
    <section class="overview">
      <div class="ov-grid">
        <div class="ov-cell">
          <span class="ov-k">当前场景</span>
          <b class="ov-v">{{ sceneName }}</b>
          <span class="ov-sub">{{ sceneCount }} 个场地可切换</span>
        </div>
        <div class="ov-cell" :class="stats.pending > 0 ? 'warn glow' : 'ok'">
          <span class="ov-k">待处理异常</span>
          <b class="ov-v">{{ stats.pending }}</b>
          <span class="ov-sub">{{ stats.pending > 0 ? '点击「实时巡检」去处置' : '暂无待办，一切正常' }}</span>
        </div>
        <div class="ov-cell ok">
          <span class="ov-k">已处置</span>
          <b class="ov-v">{{ stats.resolved }}</b>
          <span class="ov-sub">累计发现 {{ stats.total }} 处</span>
        </div>
        <div class="ov-cell">
          <span class="ov-k">巡逻车电量</span>
          <b class="ov-v">{{ battery }}%</b>
          <span class="ov-sub">{{ phaseText }}</span>
        </div>
      </div>

      <!-- 最新情报（CTA 已上移至顶部问候条，情报流拉满宽度） -->
      <div class="ov-feed">
        <span class="ov-feed-title">最新情报</span>
        <div v-if="recentLogs.length" class="ov-feed-list">
          <div v-for="(l, i) in recentLogs" :key="i" class="ov-feed-line">{{ l }}</div>
        </div>
        <div v-else class="ov-feed-empty">还没有巡检记录，点右上角「一键全面体检」开始 →</div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  sceneName: { type: String, default: '—' },
  sceneCount: { type: Number, default: 0 },
  stats: { type: Object, default: () => ({ pending: 0, processing: 0, resolved: 0, total: 0 }) },
  battery: { type: Number, default: 96 },
  phase: { type: String, default: 'idle' },
  recentLogs: { type: Array, default: () => [] },
  modelConfigured: { type: Boolean, default: false },
})
defineEmits(['enter', 'quick-patrol'])

// 按时间问候（首页第一眼是“服务你”而不是重复品牌）
const greeting = computed(() => {
  const h = new Date().getHours()
  if (h >= 5 && h < 11) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  if (h < 23) return '晚上好'
  return '夜深了'
})

// 大模块入口（只保留大模块形态：大图标 + 名称 + 一句话；细节状态看下方概览区）
const modules = [
  { key: 'patrol', icon: '🛰', title: '实时巡检', sub: '巡逻 · 识别 · 处置', tint: 'linear-gradient(135deg,#e8f3ff,#d4e9ff)', glow: 'rgba(64,158,255,.3)' },
  { key: 'workbench', icon: '🗺', title: '地图工作台', sub: '自建巡检场地', tint: 'linear-gradient(135deg,#e8f8f0,#d2f1e2)', glow: 'rgba(103,194,58,.3)' },
  { key: 'ai', icon: '🤖', title: 'AI 识别中心', sub: '照片智能判读', tint: 'linear-gradient(135deg,#f0ecff,#e0d8ff)', glow: 'rgba(139,92,246,.3)' },
  { key: 'screen', icon: '🖥', title: '值守大屏', sub: '值班室全景', tint: 'linear-gradient(135deg,#fff4e0,#ffe8c7)', glow: 'rgba(230,162,60,.3)' },
]

const phaseText = computed(() => ({
  idle: '待命中', patrol: '巡逻中', detect: '识别异常中', recheck: '复核中', report: '本轮已完成',
}[props.phase] ?? '待命中'))
</script>

<style scoped>
.home-view { display: flex; flex-direction: column; gap: 18px; padding: 8px 4px 0; }
/* 问候与行动条 */
.greet-bar {
  background: linear-gradient(120deg, #ecf5ff 0%, #f4f9ff 55%, #fdf6ec 100%);
  border-radius: 14px; padding: 16px 24px; display: flex; align-items: center; gap: 20px;
  box-shadow: 0 2px 12px rgba(0,0,0,.05), inset 0 0 0 1px rgba(31,45,61,.04);
}
.greet-left { flex: 1; min-width: 0; }
.greet-left h2 { font-size: 22px; font-weight: 800; color: #1f2d3d; letter-spacing: 1px; }
.greet-status { color: #606266; font-size: 13.5px; margin: 4px 0 8px; }
.greet-status b { color: #e6a23c; font-size: 15px; }
.greet-status.warn b { text-shadow: 0 0 10px rgba(230,162,60,.4); }
.greet-tags { display: flex; gap: 8px; flex-wrap: wrap; }
.greet-tags span { font-size: 11.5px; color: #5a8ab8; background: rgba(236,245,255,.6); padding: 3px 10px; border-radius: 12px; }
.greet-right { flex: none; display: flex; flex-direction: column; gap: 6px; align-items: center; }
/* 四大模块大卡片（获奖作品风格：居中大图标 + 名称 + 一句话，干净统一） */
.modules { display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; }
.mod-card {
  --tint: #f4f7fa; --glow: rgba(64,158,255,.3);
  background: #fff; border-radius: 16px; padding: 32px 18px 26px; cursor: pointer;
  box-shadow: 0 2px 12px rgba(0,0,0,.06), inset 0 0 0 1px rgba(31,45,61,.04);
  display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 12px;
  transition: transform .22s, box-shadow .22s; min-height: 224px;
}
.mod-card:hover { transform: translateY(-6px); box-shadow: 0 16px 34px var(--glow), inset 0 0 0 1px rgba(31,45,61,.05); }
.mod-icon {
  width: 80px; height: 80px; border-radius: 24px; background: var(--tint);
  display: flex; align-items: center; justify-content: center; font-size: 42px;
  transition: transform .22s;
}
.mod-card:hover .mod-icon { transform: scale(1.07); }
.mod-title { font-size: 19px; color: #1f2d3d; letter-spacing: 2px; }
.mod-sub { font-size: 12.5px; color: #909399; letter-spacing: 1px; }
/* 状态概览 */
.overview { background: #fff; border-radius: 14px; padding: 18px 20px; box-shadow: 0 2px 12px rgba(0,0,0,.06), inset 0 0 0 1px rgba(31,45,61,.04); }
.ov-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.ov-cell { background: #f8fafc; border-radius: 10px; padding: 12px 16px; display: flex; flex-direction: column; gap: 3px; }
.ov-k { font-size: 12px; color: #909399; }
.ov-v { font-size: 24px; font-weight: 700; color: #1f2d3d; font-family: Consolas, monospace; }
.ov-cell.warn .ov-v { color: #e6a23c; }
.ov-cell.ok .ov-v { color: #67c23a; }
.ov-cell.warn { background: #fdf6ec; }
.ov-cell.warn.glow { box-shadow: 0 0 0 1.5px #e6a23c; animation: ov-pulse 1.8s infinite; }
@keyframes ov-pulse { 50% { box-shadow: 0 0 14px rgba(230,162,60,.4); } }
.ov-sub { font-size: 11.5px; color: #c0c4cc; }
.ov-feed { margin-top: 14px; background: #fff; border: 1px solid #ebeef5; border-radius: 10px; padding: 10px 14px; }
.ov-feed-title { font-size: 12px; color: #909399; }
.ov-feed-list { margin-top: 6px; }
.ov-feed-line { font-size: 12.5px; color: #606266; padding: 3px 0; border-bottom: 1px dashed #ebeef5; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ov-feed-line:last-child { border-bottom: none; }
.ov-feed-empty { font-size: 12.5px; color: #c0c4cc; margin-top: 6px; }
.ov-actions { display: none; }
.big-cta {
  border: none; cursor: pointer; border-radius: 12px; padding: 14px 18px; font-size: 15px; font-weight: 600; color: #fff;
  background: linear-gradient(135deg, #409eff, #2a6aa8); box-shadow: 0 6px 18px rgba(64,158,255,.35); transition: all .2s;
}
.big-cta:hover { transform: translateY(-2px); box-shadow: 0 10px 24px rgba(64,158,255,.45); }
.cta-sub { text-align: center; font-size: 11.5px; color: #c0c4cc; }
/* 窄屏降级 */
@media (max-width: 1180px) {
  .greet-bar { flex-direction: column; align-items: stretch; }
  .greet-right { align-items: stretch; }
  .modules { grid-template-columns: repeat(2, 1fr); }
  .ov-grid { grid-template-columns: repeat(2, 1fr); }
}
/* 深色主题 */
.app[data-theme='dark'] .greet-bar { background: linear-gradient(120deg, #12233a 0%, #101d2d 55%, rgba(230,162,60,.08) 100%); box-shadow: 0 4px 18px rgba(0,0,0,.35), inset 0 0 0 1px rgba(64,158,255,.08); }
.app[data-theme='dark'] .greet-left h2 { color: #e8f0ff; text-shadow: 0 0 18px rgba(64,158,255,.35); }
.app[data-theme='dark'] .greet-status { color: #9fb8d4; }
.app[data-theme='dark'] .greet-tags span { background: #14273d; border-color: #1d3350; color: #8fb0d0; }
.app[data-theme='dark'] .ov-feed { background: #0e1a29; border-color: #1d3350; }
.app[data-theme='dark'] .mod-card { background: linear-gradient(160deg, #12233a, #101d2d); box-shadow: 0 4px 18px rgba(0,0,0,.35), inset 0 0 0 1px rgba(64,158,255,.08); }
.app[data-theme='dark'] .mod-card:hover { box-shadow: 0 16px 36px rgba(0,0,0,.5), inset 0 0 0 1px rgba(64,158,255,.28); }
.app[data-theme='dark'] .mod-card .mod-icon { filter: brightness(.8) saturate(.9); }
.app[data-theme='dark'] .mod-title { color: #cfe0f5; }
.app[data-theme='dark'] .mod-sub { color: #5d7a99; }
.app[data-theme='dark'] .overview { background: linear-gradient(160deg, #12233a, #101d2d); box-shadow: 0 4px 18px rgba(0,0,0,.35), inset 0 0 0 1px rgba(64,158,255,.08); }
.app[data-theme='dark'] .ov-cell { background: #0e1a29; }
.app[data-theme='dark'] .ov-v { color: #cfe0f5; }
.app[data-theme='dark'] .ov-cell.warn .ov-v { color: #e6a23c; }
.app[data-theme='dark'] .ov-cell.ok .ov-v { color: #67c23a; }
.app[data-theme='dark'] .ov-sub { color: #3a506b; }
.app[data-theme='dark'] .ov-cell.warn { background: rgba(230,162,60,.1); }
.app[data-theme='dark'] .ov-feed-line { color: #9fb8d4; border-bottom-color: #14273d; }
</style>
