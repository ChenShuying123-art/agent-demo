<script setup lang="ts">
/**
 * 文档列表（spec §9.2）：勾选 / 文件名 / 状态徽标 / chunk 数 / 删除，
 * 顶部有"向量化选中文档"按钮。勾选状态通过 v-model 与 App 同步。
 */
import { computed } from 'vue'
import type { DocumentItem } from '../api'

const props = defineProps<{
  documents: DocumentItem[]
  selected: string[]
  busy: boolean
}>()

const emit = defineEmits<{
  (e: 'update:selected', ids: string[]): void
  (e: 'index', ids: string[]): void
  (e: 'delete', id: string): void
}>()

const allChecked = computed(
  () => props.documents.length > 0 && props.selected.length === props.documents.length,
)

function toggle(docId: string): void {
  const next = props.selected.includes(docId)
    ? props.selected.filter((id) => id !== docId)
    : [...props.selected, docId]
  emit('update:selected', next)
}

function toggleAll(): void {
  emit('update:selected', allChecked.value ? [] : props.documents.map((d) => d.doc_id))
}

function indexSelected(): void {
  if (props.selected.length > 0) emit('index', props.selected)
}

/** 文件大小：>1MB 显示 MB，否则显示 KB */
function fmtSize(bytes: number): string {
  return bytes >= 1024 * 1024
    ? `${(bytes / 1024 / 1024).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`
}
</script>

<template>
  <section class="card">
    <div class="head">
      <h2>2. 文档列表</h2>
      <button
        class="primary"
        :disabled="selected.length === 0 || busy"
        @click="indexSelected"
      >
        {{ busy ? '处理中…' : `向量化选中文档（${selected.length}）` }}
      </button>
    </div>

    <p v-if="documents.length === 0" class="empty">还没有文档，先在上面上传一篇。</p>

    <table v-else>
      <thead>
        <tr>
          <th class="check">
            <input type="checkbox" :checked="allChecked" @change="toggleAll" />
          </th>
          <th>文件名</th>
          <th>状态</th>
          <th>Chunk 数</th>
          <th>大小</th>
          <th class="check"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="doc in documents" :key="doc.doc_id">
          <td class="check">
            <input
              type="checkbox"
              :checked="selected.includes(doc.doc_id)"
              @change="toggle(doc.doc_id)"
            />
          </td>
          <td>
            <span class="fname">{{ doc.filename }}</span>
            <span class="doc-id" :title="doc.doc_id">{{ doc.doc_id }}</span>
          </td>
          <td>
            <span class="badge" :class="doc.indexed ? 'ok' : 'pending'">
              {{ doc.indexed ? '已索引' : '未索引' }}
            </span>
          </td>
          <td>{{ doc.chunk_count }}</td>
          <td>{{ fmtSize(doc.size) }}</td>
          <td class="check">
            <button class="danger" :disabled="busy" @click="emit('delete', doc.doc_id)">
              删除
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.empty {
  color: var(--muted);
  font-size: 14px;
}
.check {
  width: 40px;
  text-align: center;
}
.fname {
  font-weight: 600;
}
.doc-id {
  display: block;
  margin-top: 2px;
  color: var(--muted);
  font-size: 12px;
  font-family: var(--mono);
}
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
}
.badge.ok {
  background: #e5f6ec;
  color: #1a7f4b;
}
.badge.pending {
  background: #f1f2f4;
  color: #6b7280;
}
</style>
