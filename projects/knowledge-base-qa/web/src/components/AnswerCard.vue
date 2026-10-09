<script setup lang="ts">
/**
 * 答案卡片（spec §9.2 / §9.3）：答案文本、引用来源列表、可折叠的"召回 → 重排"面板。
 *
 * 这个面板是本项目最有价值的 UI（§9.3）：左列是召回顺序（cosine 分数），
 * 右列是重排顺序（rerank 分数 + 从第几名升/降上来），一眼看出两阶段的差别。
 */
import { computed, ref } from 'vue'
import {
  STYLE_LABELS,
  type QAResult,
  type RerankResult,
  type SearchResult,
} from '../api'

const props = defineProps<{ result: QAResult }>()

const showPanel = ref(false)
const showFolded = ref(false)

const styleLabel = computed(() => STYLE_LABELS[props.result.style] ?? props.result.style)

/** 是否真的做了重排：全是 degraded（或没有 used）就说明只截断了召回结果 */
const reranked = computed(
  () => props.result.used.length > 0 && !props.result.used.some((u) => u.degraded),
)

/** 进了 Top-N 的 chunk_id，用来把其余候选折叠起来 */
const usedIds = computed(() => new Set(props.result.used.map((u) => u.chunk.chunk_id)))
const folded = computed(() =>
  props.result.candidates.filter((c) => !usedIds.value.has(c.chunk.chunk_id)),
)

/** 排名变化箭头：original_rank - new_rank > 0 表示上升 */
function delta(item: RerankResult): string {
  const diff = item.original_rank - item.new_rank
  if (diff > 0) return `↑${diff}`
  if (diff < 0) return `↓${-diff}`
  return '—'
}

function position(rank: number): string {
  return `#${rank + 1}`
}

function refOf(chunk: { filename: string; index: number }): string {
  return `${chunk.filename}#${String(chunk.index).padStart(4, '0')}`
}

function score(v: number): string {
  return v.toFixed(4)
}

function candidateClass(item: SearchResult): string {
  return usedIds.value.has(item.chunk.chunk_id) ? 'kept' : ''
}
</script>

<template>
  <article class="card answer-card">
    <div class="head">
      <span class="style-tag">{{ styleLabel }}</span>
      <span class="meta">{{ result.latency_ms }} ms · 引用 {{ result.citations.length }} 处</span>
    </div>

    <p v-if="!result.answer" class="empty">（无答案）</p>
    <div v-else class="answer">{{ result.answer }}</div>

    <div v-if="result.citations.length > 0" class="citations">
      <span class="label">引用来源：</span>
      <span v-for="c in result.citations" :key="c" class="chip">{{ c }}</span>
    </div>

    <button class="toggle" @click="showPanel = !showPanel">
      {{ showPanel ? '收起' : '查看' }}召回 → 重排（{{ result.candidates.length }} → {{ result.used.length }}）
    </button>

    <div v-if="showPanel" class="panel">
      <div class="col">
        <h4>召回 Top-{{ result.candidates.length }}（cosine）</h4>
        <ol class="list">
          <li v-for="item in result.candidates" :key="item.chunk.chunk_id" :class="candidateClass(item)">
            <span class="pos">{{ position(item.rank) }}</span>
            <span class="ref">{{ refOf(item.chunk) }}</span>
            <span class="score">{{ score(item.score) }}</span>
          </li>
        </ol>
      </div>

      <div class="col">
        <h4>重排 Top-{{ result.used.length }}（rerank）</h4>
        <p v-if="!reranked" class="not-reranked">未重排（use_rerank=false 或重排降级）</p>
        <ol v-else class="list">
          <li v-for="item in result.used" :key="item.chunk.chunk_id">
            <span class="pos">{{ position(item.new_rank) }}</span>
            <span class="ref">{{ refOf(item.chunk) }}</span>
            <span class="score">{{ score(item.rerank_score) }}</span>
            <span class="move" :class="{ up: item.original_rank > item.new_rank, down: item.original_rank < item.new_rank }">
              {{ delta(item) }} 原 {{ position(item.original_rank) }}
            </span>
          </li>
        </ol>

        <div v-if="folded.length > 0" class="folded">
          <button class="link" @click="showFolded = !showFolded">
            {{ showFolded ? '收起' : '展开' }}未进入 Top-{{ result.used.length }} 的 {{ folded.length }} 条候选
          </button>
          <ol v-if="showFolded" class="list muted">
            <li v-for="item in folded" :key="item.chunk.chunk_id">
              <span class="pos">{{ position(item.rank) }}</span>
              <span class="ref">{{ refOf(item.chunk) }}</span>
              <span class="score">{{ score(item.score) }}</span>
            </li>
          </ol>
        </div>
      </div>
    </div>
  </article>
</template>

<style scoped>
.answer-card {
  display: flex;
  flex-direction: column;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.style-tag {
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
.empty {
  color: var(--muted);
}
.citations {
  margin-top: 12px;
  font-size: 13px;
}
.citations .label {
  color: var(--muted);
}
.chip {
  display: inline-block;
  margin: 2px 4px 2px 0;
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-family: var(--mono);
  font-size: 12px;
}
.toggle {
  margin-top: 14px;
  align-self: flex-start;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fafafa;
  cursor: pointer;
  font-size: 13px;
}
.toggle:hover {
  background: #f0f0f2;
}
.panel {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px dashed var(--border);
}
@media (max-width: 720px) {
  .panel {
    grid-template-columns: 1fr;
  }
}
.col h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--muted);
}
.list {
  margin: 0;
  padding: 0;
  list-style: none;
  font-family: var(--mono);
  font-size: 12.5px;
}
.list li {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 3px 0;
  border-bottom: 1px solid #f2f2f4;
}
.list li.kept {
  background: #f6fbf8;
}
.pos {
  width: 34px;
  color: var(--muted);
}
.ref {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.score {
  font-variant-numeric: tabular-nums;
}
.move {
  width: 92px;
  text-align: right;
  color: var(--muted);
}
.move.up {
  color: #1a7f4b;
}
.move.down {
  color: #b45309;
}
.not-reranked {
  margin: 0;
  padding: 10px;
  border-radius: 8px;
  background: #fff7ed;
  color: #9a3412;
  font-size: 13px;
}
.folded {
  margin-top: 10px;
}
.link {
  border: none;
  background: none;
  padding: 0;
  color: #3730a3;
  cursor: pointer;
  font-size: 13px;
}
.list.muted {
  color: var(--muted);
  margin-top: 6px;
}
</style>
