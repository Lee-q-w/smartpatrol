<!-- SplashScreen.vue —— 启动引导页（品牌展示 + 加载占位）
     职责：应用冷启动/慢网加载时提供品牌化过渡层，避免首屏白屏；
     自动播放 2.4s 后淡出，或点击任意处跳过；结束后 emit('done') 通知父组件卸载。 -->
<template>
  <Transition name="splash-fade">
    <div v-if="visible" class="splash" :class="{ leaving }" @click="skip">
      <div class="splash-inner">
        <div class="logo-mark">
          <div class="ring"></div>
          <div class="ring r2"></div>
          <div class="core">🛰</div>
        </div>
        <h1 class="title">智巡 <span>SmartPatrol</span></h1>
        <p class="tagline">虚实结合的园区智能巡检平台</p>
        <div class="features">
          <span>🗺 任意场地建图</span>
          <span>🛰 多模式协同巡逻</span>
          <span>🤖 真图 AI 识别</span>
          <span>📄 巡检报告导出</span>
        </div>
        <div class="bar"><div class="fill"></div></div>
        <button class="skip-btn">点击跳过</button>
      </div>
      <div class="brand-foot">省赛真实数据驱动 · 仿真推演 · 历史回放 · 真机接口预留</div>
    </div>
  </Transition>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

const emit = defineEmits(['done'])
const visible = ref(true)
const leaving = ref(false)

// finish()：先标记 leaving 触发淡出过渡，450ms 过渡结束后真正卸载并通知父组件
function finish() {
  if (!visible.value) return
  leaving.value = true
  setTimeout(() => { visible.value = false; emit('done') }, 450)
}
function skip() { finish() }

// 自动播放 2.4s（与进度条动画时长同步）；组件卸载时清理，避免内存泄漏
let timer = null
onMounted(() => { timer = setTimeout(finish, 2400) })
onBeforeUnmount(() => clearTimeout(timer))
</script>

<style scoped>
.splash {
  position: fixed; inset: 0; z-index: 2000;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: radial-gradient(ellipse at 50% 35%, #16324e 0%, #0b1622 60%, #081018 100%);
  cursor: pointer; user-select: none;
}
.splash-inner { display: flex; flex-direction: column; align-items: center; animation: rise .8s ease both; }
.logo-mark { position: relative; width: 130px; height: 130px; margin-bottom: 26px; }
.ring {
  position: absolute; inset: 0; border-radius: 50%;
  border: 2px solid rgba(64,158,255,0.45);
  border-top-color: #409eff; border-right-color: transparent;
  animation: spin 2.2s linear infinite;
}
.ring.r2 { inset: 18px; border-width: 1.5px; animation-duration: 1.6s; animation-direction: reverse;
  border-top-color: #67c23a; border-bottom-color: transparent; }
.core {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  font-size: 46px; filter: drop-shadow(0 0 18px rgba(64,158,255,0.65));
  animation: pulse 2.4s ease-in-out infinite;
}
.title { color: #e8f0ff; font-size: 40px; font-weight: 800; letter-spacing: 2px; margin: 0;
  text-shadow: 0 0 24px rgba(64,158,255,0.55); }
.title span { color: #409eff; font-size: 26px; font-weight: 600; margin-left: 6px; }
.tagline { color: #8fb0d0; margin: 12px 0 26px; font-size: 15px; letter-spacing: 4px; }
.features { display: flex; gap: 14px; flex-wrap: wrap; justify-content: center; max-width: 560px; }
.features span {
  color: #cfe0f5; font-size: 13px; padding: 6px 14px; border: 1px solid rgba(64,158,255,0.35);
  border-radius: 999px; background: rgba(20,40,64,0.55); backdrop-filter: blur(4px);
  animation: rise .7s ease both;
}
.features span:nth-child(2) { animation-delay: .12s }
.features span:nth-child(3) { animation-delay: .24s }
.features span:nth-child(4) { animation-delay: .36s }
.bar { width: 240px; height: 3px; margin-top: 34px; border-radius: 3px; overflow: hidden;
  background: rgba(255,255,255,0.12); }
.fill { height: 100%; background: linear-gradient(90deg, #409eff, #67c23a); border-radius: 3px;
  animation: load 2.4s linear forwards; }
.skip-btn { margin-top: 18px; background: none; border: none; color: #5d7a99; font-size: 12px;
  letter-spacing: 2px; cursor: pointer; padding: 6px 12px; }
.skip-btn:hover { color: #9fb8d4; }
.brand-foot { position: absolute; bottom: 34px; color: #3a506b; font-size: 12px; letter-spacing: 1px; }
.splash.leaving { opacity: 0; transform: scale(1.04); transition: all .45s ease; }

@keyframes spin { to { transform: rotate(360deg) } }
@keyframes pulse { 0%,100% { transform: scale(1) } 50% { transform: scale(1.12) } }
@keyframes rise { from { opacity: 0; transform: translateY(14px) } to { opacity: 1; transform: none } }
@keyframes load { from { width: 0 } to { width: 100% } }

/* 淡出过渡（Transition 组件） */
.splash-fade-leave-active { transition: opacity .4s ease; }
.splash-fade-leave-to { opacity: 0; }
</style>
