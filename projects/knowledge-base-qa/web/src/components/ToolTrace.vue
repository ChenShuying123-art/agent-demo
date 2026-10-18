<script setup lang="ts">
/**
 * 工具调用轨迹（spec-agent §19.10）。
 *
 * 只负责渲染 AgentRun.steps：序号 / 工具名 / 参数 / 结果摘要 / 耗时 / 成功失败。
 * 失败步骤标红并默认展开，方便一眼看到模型踩了什么坑。
 */
import { computed } from 'vue'
import type { AgentStep } from '../api'

const props = defineProps<{ steps: AgentStep[] }>()

const totalMs = computed(() => props.steps.reduce((sum, step) => sum + step.elapsed_ms, 0))

function argsText(args: Record<string, unknown>): string {
  try {
    return JSON.stringify(args)
  } catch {
    return String(args)
  }
}
</script>

<template>
  <div class="trace">
    <div class="trace-head">
      <h4>工具轨迹（{{ steps.length }} 步 · {{ totalMs }} ms）</h4>
      <span v-if="steps.length === 0" class="muted">本次没有调用工具</span>
    </div>

    <ol class="steps">
      <li v-for="step in steps" :key="step.index" :class="['step', { failed: !step.ok }]">
        <details :open="!step.ok">
          <summary>
            <span class="index">#{{ step.index + 1 }}</span>
            <span class="tool">{{ step.tool }}</span>
            <span :class="['badge', step.ok ? 'ok' : 'bad']">{{ step.ok ? '成功' : '失败' }}</span>
            <span class="ms">{{ step.elapsed_ms }} ms</span>
          </summary>

          <div class="body">
            <p class="label">参数</p>
            <pre>{{ argsText(step.arguments) }}</pre>
            <p class="label">结果（{{ step.result_text.length }} 字）</p>
            <pre class="result">{{ step.result_text }}</pre>
          </div>
        </details>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.trace {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px dashed var(--border);
}
.trace-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
}
.trace-head h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--muted);
}
.muted {
  color: var(--muted);
  font-size: 12px;
}
.steps {
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 13px;
}
.step {
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 6px;
  background: #fff;
}
.step.failed {
  border-color: #f0c8c8;
  background: #fffafa;
}
summary {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 7px 10px;
  cursor: pointer;
  list-style: none;
}
summary::-webkit-details-marker {
  display: none;
}
.index {
  color: var(--muted);
  font-family: var(--mono);
}
.tool {
  flex: 1;
  font-family: var(--mono);
  font-weight: 600;
}
.badge {
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 12px;
}
.badge.ok {
  background: #e8f6ee;
  color: #1a7f4b;
}
.badge.bad {
  background: #fdeaea;
  color: #b91c1c;
}
.ms {
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.body {
  padding: 0 10px 10px;
}
.label {
  margin: 6px 0 4px;
  color: var(--muted);
  font-size: 12px;
}
pre {
  margin: 0;
  padding: 8px 10px;
  border-radius: 6px;
  background: #f6f7f9;
  font-family: var(--mono);
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 220px;
  overflow: auto;
}
pre.result {
  background: #fafafa;
}
</style>
