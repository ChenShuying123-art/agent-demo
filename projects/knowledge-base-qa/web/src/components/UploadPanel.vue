<script setup lang="ts">
/**
 * 上传面板（spec §9.2）：选文件 + 上传。
 * 只负责"选"和"发事件"，真正的网络调用交给 App（保持组件职责单一）。
 */
import { ref } from 'vue'

defineProps<{ busy: boolean }>()
const emit = defineEmits<{ (e: 'upload', file: File): void }>()

const picked = ref<File | null>(null)

function onChange(event: Event): void {
  const files = (event.target as HTMLInputElement).files
  picked.value = files && files.length > 0 ? files[0] : null
}

function submit(): void {
  if (picked.value) emit('upload', picked.value)
}
</script>

<template>
  <section class="card">
    <h2>1. 上传文档</h2>
    <p class="hint">支持 <code>.txt</code> / <code>.md</code>，内容相同的文件会自动去重。</p>
    <div class="row">
      <input type="file" accept=".txt,.md" @change="onChange" />
      <button class="primary" :disabled="!picked || busy" @click="submit">
        {{ busy ? '上传中…' : '上传' }}
      </button>
    </div>
    <p v-if="picked" class="picked">已选择：{{ picked.name }}（{{ Math.ceil(picked.size / 1024) }} KB）</p>
  </section>
</template>

<style scoped>
.hint {
  margin: 0 0 10px;
  color: var(--muted);
  font-size: 13px;
}
.row {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.picked {
  margin: 10px 0 0;
  font-size: 13px;
  color: var(--muted);
}
</style>
