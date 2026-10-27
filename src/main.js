// ============================================================
// main.js —— 应用入口：装配 Element Plus 并挂载根组件
// ============================================================
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './style.css'
import App from './App.vue'

createApp(App).use(ElementPlus).mount('#app')