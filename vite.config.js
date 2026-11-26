import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    // Element Plus 按需引入：模板中用到的 el-* 组件自动按需打包（JS）。
    // importStyle: false —— 样式仍走 main.js 的全量 CSS（暗色主题覆盖零风险）；
    // 函数式 API（ElMessage）样式同样由全量 CSS 覆盖。
    Components({
      resolvers: [ElementPlusResolver({ importStyle: false })],
      dts: false,                           // 无 TS，不生成类型声明
      directoryAsNamespace: false,
    }),
  ],
  base: './',                             // 相对路径：适配 GitHub/Gitee Pages 子路径托管（在线演示）
  server: {
    port: 5199, strictPort: true,
    host: '127.0.0.1',                    // 显式 IPv4：避免部分环境 localhost 解析到 ::1 打不开
    watch: { ignored: ['**/server/**'] }, // dev 不 watch 后端目录（.venv 内 HTML 曾触发整页 reload 风暴）
  },
})
