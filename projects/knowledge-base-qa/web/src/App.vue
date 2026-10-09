<script setup lang="ts">
/**
 * 应用根组件：负责页面布局 + 状态编排（所有网络调用都收在这里，组件只发事件）。
 * 这样组件保持"展示型"，出错处理、loading、刷新逻辑只有一份。
 */
import { onMounted, ref } from 'vue'
import { ApiError, api, type AskOptions, type DocumentItem, type Health, type QAResult } from './api'
import UploadPanel from './components/UploadPanel.vue'
import DocumentList from './components/DocumentList.vue'
import AskPanel from './components/AskPanel.vue'
import AnswerCard from './components/AnswerCard.vue'

const health = ref<Health | null>(null)
const documents = ref<DocumentItem[]>([])
const selected = ref<string[]>([])
const results = ref<QAResult[]>([])
const errorMsg = ref('')
const busy = ref(false)

/** 统一跑一次异步操作：负责 busy 开关与错误提示，业务代码不用重复 try/catch */
async function run<T>(task: () => Promise<T>): Promise<T | undefined> {
  busy.value = true
  errorMsg.value = ''
  try {
    return await task()
  } catch (err) {
    errorMsg.value =
      err instanceof ApiError ? `[${err.code}] ${err.message}` : (err as Error).message
    return undefined
  } finally {
    busy.value = false
  }
}

async function refreshDocuments(): Promise<void> {
  documents.value = await api.listDocuments()
  // 丢掉已经不存在的选中项（例如刚被删除的文档）
  const ids = new Set(documents.value.map((d) => d.doc_id))
  selected.value = selected.value.filter((id) => ids.has(id))
}

onMounted(() => {
  void run(async () => {
    health.value = await api.health()
    await refreshDocuments()
  })
})

function onUpload(file: File): void {
  void run(async () => {
    await api.uploadDocument(file)
    await refreshDocuments()
  })
}

function onIndex(docIds: string[]): void {
  void run(async () => {
    await api.indexDocuments(docIds)
    await refreshDocuments() // 刷新后徽标会变成"已索引"并显示 chunk 数
  })
}

function onDelete(docId: string): void {
  void run(async () => {
    await api.deleteDocument(docId)
    await refreshDocuments()
  })
}

function onAsk(opts: AskOptions): void {
  void run(async () => {
    results.value =
      opts.style === 'all'
        ? await api.askAllStyles(opts.question, selected.value)
        : [await api.ask(opts.question, opts.style, selected.value, opts.useRerank)]
  })
}
</script>

<template>
  <div class="page">
    <header class="hero">
      <h1>知识库问答 Agent</h1>
      <p class="sub">上传文档 → 向量化 → 提问，并观察「召回 → 重排」两阶段的变化。</p>
      <p v-if="health" class="models">
        对话 <code>{{ health.chat_model }}</code> ·
        向量 <code>{{ health.embedding_model }}</code> ·
        重排 <code>{{ health.rerank_model }}</code>
      </p>
    </header>

    <p v-if="errorMsg" class="error">请求失败：{{ errorMsg }}</p>

    <UploadPanel :busy="busy" @upload="onUpload" />
    <DocumentList
      v-model:selected="selected"
      :documents="documents"
      :busy="busy"
      @index="onIndex"
      @delete="onDelete"
    />
    <AskPanel :selected-count="selected.length" :busy="busy" @ask="onAsk" />

    <section v-if="results.length > 0" class="results">
      <h2>4. 回答</h2>
      <div :class="['answer-grid', { compare: results.length > 1 }]">
        <AnswerCard v-for="(r, i) in results" :key="i" :result="r" />
      </div>
    </section>

    <footer class="foot">
      前端仅调用 <code>/api/*</code>；两阶段检索的排名变化见每张答案卡里的「召回 → 重排」面板。
    </footer>
  </div>
</template>

<style>
/* 全局基础样式（非 scoped）：CSS 变量 + 复位 + 通用控件外观，组件内只写自己的部分 */
:root {
  --bg: #f6f7f9;
  --fg: #1f2430;
  --muted: #6b7280;
  --border: #e2e4e9;
  --accent: #3730a3;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
* {
  box-sizing: border-box;
}
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: system-ui, -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  line-height: 1.6;
}
code {
  font-family: var(--mono);
  font-size: 0.92em;
  background: #eef0f3;
  padding: 1px 5px;
  border-radius: 4px;
}
button {
  font: inherit;
}
button.primary {
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
}
button.primary:disabled {
  background: #b9bcc9;
  cursor: not-allowed;
}
button.danger {
  padding: 4px 10px;
  border: 1px solid #f0c8c8;
  border-radius: 6px;
  background: #fff;
  color: #b91c1c;
  cursor: pointer;
  font-size: 13px;
}
button.danger:disabled {
  color: #c9a3a3;
  cursor: not-allowed;
}
.card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px;
  margin-bottom: 18px;
}
.card h2 {
  margin: 0 0 12px;
  font-size: 16px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
th,
td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
}
th {
  color: var(--muted);
  font-weight: 500;
  font-size: 13px;
}

/* ---- 页面布局（也放在全局块里，方便统一维护）---- */
.page {
  max-width: 1180px;
  margin: 0 auto;
  padding: 28px 20px 60px;
}
.hero h1 {
  margin: 0 0 6px;
  font-size: 24px;
}
.hero .sub {
  margin: 0;
  color: var(--muted);
}
.hero .models {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 13px;
}
.error {
  padding: 10px 14px;
  border: 1px solid #f3c2c2;
  border-radius: 8px;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 14px;
}
.results {
  margin-top: 6px;
}
.results h2 {
  font-size: 16px;
  margin: 0 0 12px;
}
/* 单列：一次一种风格；对比模式：三列并排（窄屏自动回落单列） */
.answer-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
}
.answer-grid.compare {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
@media (max-width: 980px) {
  .answer-grid.compare {
    grid-template-columns: 1fr;
  }
}
.foot {
  margin-top: 28px;
  color: var(--muted);
  font-size: 13px;
  text-align: center;
}
</style>
