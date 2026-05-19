<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { marked } from 'marked'
import { fetchKbs, queryRagStream } from '../api'

const kbs = ref([])
const queryKbId = ref('')
const queryText = ref('')
const querying = ref(false)
const answerRaw = ref('')
const chunks = ref([])

const queryKbList = computed(() => kbs.value.filter(kb => kb.file_count > 0))

function renderMd(text) {
  if (!text) return ''
  return marked.parse(text)
}

/* 解析 <think>...</think> 块 */
const thinkBlocks = ref([])
const answerExThink = computed(() => {
  let s = answerRaw.value
  thinkBlocks.value = []
  const re = /<think>([\s\S]*?)<\/think>/g
  const blocks = []
  let m
  while ((m = re.exec(s)) !== null) {
    blocks.push(m[1].trim())
  }
  thinkBlocks.value = blocks.map(c => ({ content: c }))
  return s.replace(/<think>[\s\S]*?<\/think>/g, '').trim()
})

const thinkExpanded = ref(false)

/* 回答区域动态高度 */
const answerBoxRef = ref(null)
const answerMaxH = ref('50vh')

function updateAnswerHeight() {
  if (!answerBoxRef.value) return
  const rect = answerBoxRef.value.getBoundingClientRect()
  const spaceBelow = window.innerHeight - rect.top - 24
  answerMaxH.value = Math.max(120, spaceBelow) + 'px'
}

watch([answerExThink, querying], () => {
  if (!querying.value) {
    requestAnimationFrame(updateAnswerHeight)
  }
})

async function loadKbs() {
  try { kbs.value = await fetchKbs() } catch {}
}

async function runQuery() {
  const q = queryText.value.trim()
  if (!q || !queryKbId.value) return
  querying.value = true
  answerRaw.value = ''
  chunks.value = []
  thinkBlocks.value = []
  thinkExpanded.value = false
  try {
    await queryRagStream(queryKbId.value, q, {
      onChunks(data) { chunks.value = data },
      onToken(token) {
        answerRaw.value += token
      },
    })
  } catch (err) {
    answerRaw.value = `Error: ${err.message}`
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
    <div class="results" v-if="answerRaw || chunks.length">
      <div class="results-header" v-if="chunks.length">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        {{ chunks.length }} chunk{{ chunks.length > 1 ? 's' : '' }} retrieved
      </div>

      <!-- Think Block -->
      <div class="think-card" v-for="(b, i) in thinkBlocks" :key="i">
        <div class="think-toggle" @click="thinkExpanded = !thinkExpanded">
          <svg class="think-icon" :class="{ open: thinkExpanded }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
          <span>{{ thinkExpanded ? '收起思考过程' : '查看思考过程' }}</span>
        </div>
        <div class="think-content markdown-body" v-show="thinkExpanded" v-html="renderMd(b.content)"></div>
      </div>

      <div class="answer-card" ref="answerBoxRef" v-if="answerExThink" :class="{ streaming: querying }">
        <h4>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5"/></svg>
          Answer
        </h4>
        <div class="answer-text" :style="{ maxHeight: answerMaxH }">
          <div class="markdown-body" v-html="renderMd(answerExThink)"></div>
        </div>
      </div>

      <!-- Fallback: no think tags -->
      <div class="answer-card" ref="answerBoxRef" v-if="!answerExThink && answerRaw" :class="{ streaming: querying }">
        <h4>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5"/></svg>
          Answer
        </h4>
        <div class="answer-text" :style="{ maxHeight: answerMaxH }">
          <div class="markdown-body" v-html="renderMd(answerRaw)"></div>
        </div>
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

/* Think card */
.think-card {
  border: 1px solid #e2d9f3;
  border-radius: var(--radius);
  background: #f8f5ff;
  overflow: hidden;
}
.think-toggle {
  display: flex; align-items: center; gap: 6px;
  padding: 10px 14px; cursor: pointer; user-select: none;
  font-size: 13px; color: #7c3aed; font-weight: 500;
  transition: background 150ms;
}
.think-toggle:hover { background: #f0eaff; }
.think-icon { transition: transform 200ms; color: #7c3aed; }
.think-icon.open { transform: rotate(180deg); }
.think-content {
  padding: 0 14px 12px;
  font-size: 13px; line-height: 1.65; color: #6b7280;
  border-top: 1px solid #e2d9f3;
  padding-top: 10px;
}

.answer-card { border: 1px solid var(--c-border); border-radius: var(--radius); padding: 14px 16px; }
.answer-card h4 { font-size: 13px; font-weight: 700; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; color: var(--c-secondary); }
.answer-card .answer-text {
  font-size: 14px; line-height: 1.7;
  overflow-y: auto;
}

/* streaming cursor via ::after on answer-card */
.answer-card.streaming .markdown-body::after {
  content: '|';
  animation: blink 0.7s step-end infinite;
  font-weight: 100;
  color: var(--c-secondary);
}
@keyframes blink { 50% { opacity: 0; } }

.chunk-item { border: 1px solid var(--c-border); border-radius: var(--radius); padding: 12px 14px; font-size: 13px; }
.chunk-header { display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 12px; color: var(--c-secondary); }
.chunk-score { font-weight: 700; color: var(--c-accent); }
.chunk-text { line-height: 1.6; }

/* Markdown body styles (not scoped — apply to v-html content) */
</style>

<style>
.markdown-body h1, .markdown-body h2, .markdown-body h3 {
  margin: 12px 0 6px; font-weight: 600; color: var(--c-fg);
}
.markdown-body h1 { font-size: 1.25em; }
.markdown-body h2 { font-size: 1.15em; }
.markdown-body h3 { font-size: 1.05em; }
.markdown-body p { margin: 6px 0; }
.markdown-body ul, .markdown-body ol { padding-left: 1.5em; margin: 6px 0; }
.markdown-body li { margin: 2px 0; }
.markdown-body code {
  background: #f5f5f5; padding: 2px 6px; border-radius: 3px;
  font-size: 0.9em; font-family: var(--font-mono, 'Consolas', monospace);
}
.markdown-body pre {
  background: #1e1e1e; color: #d4d4d4; padding: 12px 16px;
  border-radius: 6px; overflow-x: auto; margin: 8px 0; line-height: 1.5;
}
.markdown-body pre code { background: none; padding: 0; color: inherit; font-size: 13px; }
.markdown-body table {
  border-collapse: collapse; width: 100%; margin: 8px 0;
}
.markdown-body th, .markdown-body td {
  border: 1px solid var(--c-border); padding: 6px 10px; text-align: left; font-size: 13px;
}
.markdown-body th { background: #f9fafb; font-weight: 600; }
.markdown-body blockquote {
  border-left: 3px solid #7c3aed; padding: 4px 12px; margin: 8px 0;
  color: #6b7280; background: #f8f5ff;
}
.markdown-body hr { border: none; border-top: 1px solid var(--c-border); margin: 12px 0; }
.markdown-body a { color: #7c3aed; }
.markdown-body strong { font-weight: 600; }
.markdown-body img { max-width: 100%; border-radius: 4px; }
</style>
