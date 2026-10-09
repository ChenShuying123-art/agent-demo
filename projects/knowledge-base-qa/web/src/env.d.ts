/// <reference types="vite/client" />

// 让 TypeScript 认识 `import App from './App.vue'` 这种导入（.vue 文件由 Vite 处理）
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}
