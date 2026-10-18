<script setup lang="ts">
/**
 * Agent 对话面板（spec-agent §19.10）。
 *
 * 与固定链路（AskPanel / AnswerCard）并列展示，不改动原有交互。
 * 组件只负责收集问题与 skill、渲染结果；网络调用统一在 App.vue。
 */
import { ref } from 'vue'
import type { AgentRun, SkillInfo } from '../api'
import ToolTrace from './ToolTrace.vue'

const props = defineProps<{
  busy: boolean
  result: AgentRun | null
  skills: SkillInfo[]
}>()

const emit = defineEmits<{
  (e: 'ask', payload: { question: string; skill: string | null; stream: boolean }): void
}>()

const question = ref('')
const skill = ref('')
const stream = ref(true)

function submit(): void {
  const text = question.value.trim()
  if (!text || props.busy) return
  emit('ask', { question: text, skill: skill.value || null, stream: stream.value })
}
</script>

<template>
  <section class="card agent-panel">
    <h2>5. Agent 对话</h2>
    <p class="sub">模型自主决定是否调用工具；工具失败与最大步数都会显示在下面的轨迹里。</p>

    <textarea
      v-model="question"
      rows="3"
      placeholder="例如：今天几号？顺便看看知识库里有没有关于咖啡的记录。"
      @keydown.ctrl.enter="submit"
    ></textarea>

    <div class="controls">
      <label>
        Skill
        <select v-model="skill">
          <option value="">自动</option>
          <option v-for="s in skills" :key="s.name" :value="s.name">{{ s.name }}</option>
        </select>
      </label>

      <label class="switch">
        <input v-model="stream" type="checkbox" />
        流式输出
      </label>

      <button class="primary" :disabled="!question.trim() || busy" @click="submit">
        {{ busy ? '思考中…' : '让 Agent 回答' }}
      </button>
    </div>

    <p class="hint">
      与上方固定链路互不影响。Agent 的检索、日期查询等动作都会记录在工具轨迹里。
    </p>

    <div v-if="result" class="result">
      <div class="head">
        <span class="tag">{{ result.skill ?? '自动' }}</span>
        <span class="meta">
          {{ result.rounds }} 轮 · {{ result.tool_calls_count }} 次工具 · {{ result.latency_ms }} ms
        </span>
      </div>

      <p v-if="result.stop_reason === 'max_steps'" class="warn">
        已达到最大步数，模型未给出最终答案。
      </p>

      <div class="answer">{{ result.answer || '（无答案）' }}</div>
      <ToolTrace :steps="result.steps" />
    </div>
  </section>
</template>

<style scoped>
.sub {
  margin: 0 0 12px;
  color: var(--muted);
  font-size: 13px;
}
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
.result {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}
.head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}
.tag {
  padding: 2px 10px;
  border-radius: 999px;
  background: #eef2ff;
  color: #3730a3;
  font-size: 13px;
  font-weight: 600;
}
.meta {
  color: var(--muted);
  font-size: 12px;
}
.answer {
  white-space: pre-wrap;
  line-height: 1.7;
  word-break: break-word;
}
.warn {
  margin: 0 0 10px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #fff7ed;
  color: #9a3412;
  font-size: 13px;
}
</style>
