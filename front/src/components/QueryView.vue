<script setup>
import { ref, computed, onMounted } from 'vue'
import { fetchKbs, queryRag } from '../api'

const kbs = ref([])
const queryKbId = ref('')
const queryText = ref('')
const querying = ref(false)
const answer = ref('')
const chunks = ref([])

const queryKbList = computed(() => kbs.value.filter(kb => kb.file_count > 0))

async function loadKbs() {
  try { kbs.value = await fetchKbs() } catch {}
}

async function runQuery() {
  const q = queryText.value.trim()
  if (!q || !queryKbId.value) return
  querying.value = true
  answer.value = ''
  chunks.value = []
  try {
    const data = await queryRag(queryKbId.value, q)
    answer.value = data.answer || ''
    chunks.value = data.chunks || []
  } catch (err) {
    answer.value = `Error: ${err.message}`
  }
  querying.value = false
}

onMounted(loadKbs)
</script>

<template>
  <div class="query-section">
    <div class="kb-select">
      <label>Knowledge Base</label>
      <select v-model="queryKbId">
        <option value="" disabled>Select a knowledge base...</option>
        <option v-for="kb in queryKbList" :key="kb.id" :value="kb.id">{{ kb.name }} ({{ kb.file_count }} files)</option>
      </select>
    </div>

    <div class="query-row">
      <input type="text" v-model="queryText" placeholder="Ask a question..." @keydown.enter="runQuery" :disabled="!queryKbId || querying">
      <button class="btn primary" @click="runQuery" :disabled="!queryKbId || !queryText.trim() || querying">
        <span class="spinner" v-if="querying"></span>
        <template v-else>Search</template>
      </button>
    </div>

    <!-- Results -->
    <div class="results" v-if="answer || chunks.length">
      <div class="results-header" v-if="chunks.length">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        {{ chunks.length }} chunk{{ chunks.length > 1 ? 's' : '' }} retrieved
      </div>

      <div class="answer-card" v-if="answer">
        <h4>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5"/></svg>
          Answer
        </h4>
        <div class="answer-text">{{ answer }}</div>
      </div>

      <div v-for="(c, i) in chunks" :key="i" class="chunk-item">
        <div class="chunk-header">
          <span>{{ c.file_name }}</span>
          <span class="chunk-score">{{ c.score.toFixed(4) }}</span>
        </div>
        <div class="chunk-text">{{ c.text }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.query-section { display: flex; flex-direction: column; gap: 16px; }
.kb-select { display: flex; flex-direction: column; gap: 6px; }
.kb-select label { font-size: 13px; font-weight: 600; color: var(--c-secondary); }
.kb-select select {
  padding: 8px 12px; border: 1px solid var(--c-border); border-radius: var(--radius-sm);
  font-size: 14px; font-family: var(--font); outline: none; background: var(--c-bg);
  transition: border-color 150ms; cursor: pointer;
}
.kb-select select:focus { border-color: var(--c-fg); }

.query-row { display: flex; gap: 8px; }
.query-row input { flex: 1; }

.results { display: flex; flex-direction: column; gap: 12px; }
.results-header { font-size: 13px; color: var(--c-secondary); display: flex; align-items: center; gap: 6px; }
.answer-card { border: 1px solid var(--c-border); border-radius: var(--radius); padding: 14px 16px; }
.answer-card h4 { font-size: 13px; font-weight: 700; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; color: var(--c-secondary); }
.answer-card .answer-text { font-size: 14px; line-height: 1.7; white-space: pre-wrap; }

.chunk-item { border: 1px solid var(--c-border); border-radius: var(--radius); padding: 12px 14px; font-size: 13px; }
.chunk-header { display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 12px; color: var(--c-secondary); }
.chunk-score { font-weight: 700; color: var(--c-accent); }
.chunk-text { line-height: 1.6; }

@media (max-width: 480px) {
  .query-row { flex-direction: column; }
  .query-row .btn { width: 100%; justify-content: center; }
}
</style>
