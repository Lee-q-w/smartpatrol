// ============================================================
// main.js —— 应用入口：挂载根组件
// 组件引入方式：模板组件由 unplugin-vue-components 按需打包
// （vite.config.js 配置 ElementPlusResolver），业务代码中的手动
// import 兼容保留；样式走下方全量 CSS，函数式 API（ElMessage）
// 的样式同样由此覆盖，暗色主题（CSS 变量覆盖方式）不受影响。
// ============================================================
import { createApp } from 'vue'
import 'element-plus/dist/index.css'
import './style.css'
import App from './App.vue'

createApp(App).mount('#app')