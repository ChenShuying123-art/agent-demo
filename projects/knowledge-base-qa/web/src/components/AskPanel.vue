<script setup lang="ts">
/**
 * 提问面板（spec §9.2）：问题输入、风格下拉（三种 + "全部对比"）、Rerank 开关、提问按钮。
 *
 * 说明：spec §9.2 还提到 retrieve_top_k / rerank_top_n 调参，但后端 §8 的 /api/qa、/api/retrieve
 * 并未接收这两个参数（它们是服务端 .env 里的全局配置），所以这里不提供会"点了没反应"的假控件。
 */
import { computed, ref } from 'vue'
import { PROMPT_STYLES, STYLE_LABELS, type AskOptions } from '../api'

const props = defineProps<{
  selectedCount: number
  busy: boolean
}>()

const emit = defineEmits<{ (e: 'ask', opts: AskOptions): void }>()

const question = ref('')
const style = ref<string>(PROMPT_STYLES[0])
const useRerank = ref(true)

/** 「全部对比」走 /api/qa/compare，该接口按 §8 不接受 use_rerank，固定用服务端默认参数 */
const isCompare = computed(() => style.value === 'all')

function submit(): void {
  const text = question.value.trim()
  if (!text || props.busy) return
  emit('ask', { question: text, style: style.value, useRerank: useRerank.value })
}
</script>

<template>
  <section class="card">
    <h2>3. 提问</h2>
    <textarea
      v-model="question"
      rows="3"
      placeholder="就上传的文档提问，例如：两阶段检索里召回和重排各返回多少条？"
      @keydown.ctrl.enter="submit"
    ></textarea>

    <div class="controls">
      <label>
        风格
        <select v-model="style">
          <option v-for="s in PROMPT_STYLES" :key="s" :value="s">
            {{ STYLE_LABELS[s] }}
          </option>
          <option value="all">全部对比（三种并排）</option>
        </select>
      </label>

      <label class="switch">
        <input v-model="useRerank" type="checkbox" :disabled="isCompare" />
        启用 Rerank 重排
      </label>

      <button class="primary" :disabled="!question.trim() || busy" @click="submit">
        {{ busy ? '生成中…' : '提问' }}
      </button>
    </div>

    <p v-if="isCompare" class="hint warn">
      「全部对比」使用服务端默认检索参数（含 Rerank），此开关在对比模式下不生效。
    </p>

    <p class="hint">
      <template v-if="selectedCount > 0">检索范围：已勾选 {{ selectedCount }} 篇文档。</template>
      <template v-else>未勾选文档 → 检索全库。</template>
      可按 <kbd>Ctrl</kbd> + <kbd>Enter</kbd> 快速提问。
    </p>
  </section>
</template>

<style scoped>
textarea {
  width: 100%;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font: inherit;
  resize: vertical;
  box-sizing: border-box;
}
.controls {
  display: flex;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 12px;
}
label {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  font-size: 14px;
}
select {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
  font: inherit;
}
.hint {
  margin: 12px 0 0;
  color: var(--muted);
  font-size: 13px;
}
.hint.warn {
  margin-top: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #fff7ed;
  color: #9a3412;
}
kbd {
  padding: 1px 5px;
  border: 1px solid var(--border);
  border-bottom-width: 2px;
  border-radius: 4px;
  font-size: 12px;
  font-family: var(--mono);
}
</style>
