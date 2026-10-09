import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发模式（spec §9.1）：Vite 跑 5173，把 /api 代理到后端 8000，避免跨域。
// 生产模式：npm run build 产出 dist/，交给 FastAPI 的 StaticFiles 托管（同源，无需代理）。
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    // 直接用默认的 dist/（FastAPI main.py 里挂载的正是 web/dist）
    outDir: 'dist',
  },
})
