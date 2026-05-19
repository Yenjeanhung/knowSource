<script setup>
import { ref, computed, onMounted, watch, reactive } from 'vue'
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

/* 每个 source chip 独立展开状态 */
const expandedSources = reactive({})
function toggleSource(idx) {
  expandedSources[idx] = !expandedSources[idx]
}

/* Answer 区域动态高度 */
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

function pct(c) { return Math.round(c.score * 100) }

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
  Object.keys(expandedSources).forEach(k => delete expandedSources[k])
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
      <label>选择知识库</label>
      <select v-model="queryKbId">
        <option value="" disabled>请选择知识库...</option>
        <option v-for="kb in queryKbList" :key="kb.id" :value="kb.id">{{ kb.name }} ({{ kb.file_count }} 个文件)</option>
      </select>
    </div>

    <div class="query-row">
      <input type="text" v-model="queryText" placeholder="输入问题..." @keydown.enter="runQuery" :disabled="!queryKbId || querying">
      <button class="btn primary" @click="runQuery" :disabled="!queryKbId || !queryText.trim() || querying">
        <span class="spinner" v-if="querying"></span>
        <template v-else>搜索</template>
      </button>
    </div>

    <!-- Results -->
    <div class="results" v-if="answerRaw || chunks.length">

      <!-- Think Block -->
      <div class="think-card" v-for="(b, i) in thinkBlocks" :key="i">
        <div class="think-toggle" @click="thinkExpanded = !thinkExpanded">
          <svg class="think-icon" :class="{ open: thinkExpanded }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
          <span>{{ thinkExpanded ? '收起思考过程' : '查看思考过程' }}</span>
        </div>
        <div class="think-content markdown-body" v-show="thinkExpanded" v-html="renderMd(b.content)"></div>
      </div>

      <!-- Answer + Sources side-by-side -->
      <div class="content-row">
        <!-- Answer (left) -->
        <div class="answer-col">
          <div class="answer-card" ref="answerBoxRef" v-if="answerExThink" :class="{ streaming: querying }">
            <h4>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5"/></svg>
              回答
            </h4>
            <div class="answer-text" :style="{ maxHeight: answerMaxH }">
              <div class="markdown-body" v-html="renderMd(answerExThink)"></div>
            </div>
          </div>

          <div class="answer-card" ref="answerBoxRef" v-if="!answerExThink && answerRaw" :class="{ streaming: querying }">
            <h4>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5"/></svg>
              回答
            </h4>
            <div class="answer-text" :style="{ maxHeight: answerMaxH }">
              <div class="markdown-body" v-html="renderMd(answerRaw)"></div>
            </div>
          </div>
        </div>

        <!-- Sources (right sidebar) -->
        <div class="sources-col" v-if="chunks.length">
          <div class="sources-header">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
            来源 · {{ chunks.length }}
          </div>
          <div class="sources-scroll">
            <div
              v-for="(c, i) in chunks" :key="i"
              class="source-chip"
              :class="{ active: expandedSources[i] }"
            >
              <div class="source-chip-top" @click="toggleSource(i)">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                <span class="source-name">{{ c.file_name }}</span>
                <span class="source-pct">{{ pct(c) }}%</span>
                <svg class="source-chevron" :class="{ open: expandedSources[i] }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
              </div>
              <div class="source-text" v-show="expandedSources[i]">{{ c.text }}</div>
            </div>
          </div>
        </div>
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

/* Think card */
.think-card {
  border: 1px solid #e2d9f3; border-radius: var(--radius); background: #f8f5ff; overflow: hidden;
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
  padding: 0 14px 12px; font-size: 13px; line-height: 1.65; color: #6b7280;
  border-top: 1px solid #e2d9f3; padding-top: 10px;
}

/* Content row: answer + sources side-by-side */
.content-row {
  display: flex; gap: 20px; align-items: flex-start;
}

/* Answer column */
.answer-col { flex: 1; min-width: 0; }
.answer-card { border: 1px solid var(--c-border); border-radius: var(--radius); padding: 14px 16px; }
.answer-card h4 { font-size: 13px; font-weight: 700; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; color: var(--c-secondary); }
.answer-card .answer-text { font-size: 14px; line-height: 1.7; overflow-y: auto; }

.answer-card.streaming .markdown-body::after {
  content: '|';
  animation: blink 0.7s step-end infinite;
  font-weight: 100; color: var(--c-secondary);
}
@keyframes blink { 50% { opacity: 0; } }

/* Sources sidebar */
.sources-col {
  width: 220px; flex-shrink: 0;
  border: 1px solid var(--c-border); border-radius: var(--radius);
  overflow: hidden;
  max-height: calc(100vh - 200px);
  display: flex; flex-direction: column;
}
.sources-header {
  display: flex; align-items: center; gap: 6px;
  padding: 10px 14px;
  font-size: 12px; color: var(--c-secondary); font-weight: 600;
  border-bottom: 1px solid var(--c-border);
  flex-shrink: 0;
}
.sources-scroll {
  overflow-y: auto; flex: 1;
  padding: 8px;
  display: flex; flex-direction: column; gap: 6px;
}

.source-chip {
  border: 1px solid var(--c-border); border-radius: var(--radius-sm);
  background: #fafafa;
  transition: border-color 150ms, background 150ms;
}
.source-chip:hover { border-color: #d0d0d0; }
.source-chip.active { border-color: var(--c-fg); background: #fff; }

.source-chip-top {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 10px; font-size: 12px; cursor: pointer; user-select: none;
}
.source-name {
  flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--c-fg); font-weight: 500; font-size: 11px;
}
.source-pct {
  font-size: 10px; color: var(--c-accent); font-weight: 700;
  background: #eef2ff; padding: 1px 6px; border-radius: 10px;
  flex-shrink: 0;
}
.source-chevron {
  flex-shrink: 0; color: var(--c-secondary); transition: transform 200ms;
}
.source-chevron.open { transform: rotate(180deg); }

.source-text {
  font-size: 12px; line-height: 1.6; color: var(--c-secondary);
  padding: 0 10px 10px;
  border-top: 1px solid var(--c-border);
  padding-top: 8px;
  white-space: pre-wrap;
  max-height: 140px; overflow-y: auto;
}

/* Mobile: stack */
@media (max-width: 720px) {
  .content-row { flex-direction: column; }
  .sources-col { width: 100%; max-height: 360px; }
}
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
