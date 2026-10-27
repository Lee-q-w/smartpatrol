import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  base: './',                             // 相对路径：适配 GitHub/Gitee Pages 子路径托管（在线演示）
  server: { port: 5199, strictPort: true },   // 固定端口：与后端 CORS 白名单/文档一致
})
