<script setup>
import { ref, computed, onMounted, watch, reactive, nextTick } from 'vue'
import { marked } from 'marked'
import { fetchKbs, queryRagStream } from '../api'
import PreviewModal from './PreviewModal.vue'

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

const CITE_COLORS = ['#6366f1', '#ec4899', '#f59e0b', '#10b981', '#3b82f6', '#ef4444', '#8b5cf6', '#14b8a6']
function chunkColor(idx) { return CITE_COLORS[idx % CITE_COLORS.length] }

// ---------- 思考过程 ----------
// 兼容 Qwen <think>...</think>，DeepSeek 不用此格式
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
  if (blocks.length) {
    thinkBlocks.value = blocks.map(c => ({ content: c }))
    s = s.replace(/<think>[\s\S]*?<\/think>/g, '').trim()
  }
  return s
})

const thinkExpanded = ref(false)

// ---------- 分片展开 ----------
const expandedSources = reactive({})

// ---------- hover ----------
const hoveredChunk = ref(null)

// ---------- PDF 预览弹窗 ----------
const previewVisible = ref(false)
const previewFileId = ref('')
const previewFileName = ref('')
const previewFileExt = ref('')
const previewPageNumber = ref(1)
const previewStartOffset = ref(0)
const previewEndOffset = ref(0)
const previewChunkText = ref('')

// ---------- 核心：先替换 [来源N] 再渲染 markdown ----------
const processedAnswerHtml = computed(() => {
  let text = answerExThink.value
  if (!text) return ''

  // 保护代码块（反引号包裹的）
  text = text.replace(/(```[\s\S]*?```|`[^`]*`)/g, (m) => {
    return m.replace(/\[来源(\d+)\]/g, '\x00CITE$1\x00')
  })

  // 替换 [来源N]
  text = text.replace(/\[来源(\d+)\]/g, (_, num) => {
    const idx = parseInt(num) - 1
    const color = chunkColor(idx)
    return `<span class="cite-ref" data-chunk="${num}" style="--c:${color}">[${num}]</span>`
  })

  // 恢复代码块中被保护的
  text = text.replace(/\x00CITE(\d+)\x00/g, '[来源$1]')

  return renderMd(text)
})

// ---------- 点击回答区域（事件委托）----------
function onAnswerClick(e) {
  const cite = e.target.closest('[data-chunk]')
  if (!cite) return
  const num = +cite.dataset.chunk
  // 展开对应分片
  expandedSources[num - 1] = true
  hoveredChunk.value = num
  nextTick(() => {
    const el = document.getElementById(`src-${num}`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  })
  setTimeout(() => { hoveredChunk.value = null }, 1500)
}

// ---------- hover 回答 → 联动分片 ----------
function onAnswerHover(e) {
  const cite = e.target.closest('[data-chunk]')
  hoveredChunk.value = cite ? +cite.dataset.chunk : null
}

// ---------- 点击分片 → 定位回答 ----------
function onSourceClick(idx) {
  const num = idx + 1
  expandedSources[idx] = !expandedSources[idx]
  hoveredChunk.value = num
  nextTick(() => {
    const el = document.getElementById(`src-${num}`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  })
  // 定位回答中第一个对应引用
  nextTick(() => {
    const c = document.querySelector(`.answer-text [data-chunk="${num}"]`)
    if (c) c.scrollIntoView({ behavior: 'smooth', block: 'center' })
  })
  setTimeout(() => { hoveredChunk.value = null }, 1500)
}

// ---------- 双击分片 → PDF 预览弹窗 ----------
function onSourceDblClick(c) {
  if (!c.file_id) return
  previewFileId.value = c.file_id
  previewFileName.value = c.file_name
  previewFileExt.value = c.file_ext || ''
  previewPageNumber.value = c.page_number || 1
  previewStartOffset.value = c.start_offset || 0
  previewEndOffset.value = c.end_offset || 0
  previewChunkText.value = c.text || ''
  previewVisible.value = true
}

// ---------- 动态高度 ----------
const answerBoxRef = ref(null)
const answerMaxH = ref('50vh')

function updateAnswerHeight() {
  if (!answerBoxRef.value) return
  const rect = answerBoxRef.value.getBoundingClientRect()
  const spaceBelow = window.innerHeight - rect.top - 24
  answerMaxH.value = Math.max(120, spaceBelow) + 'px'
}

watch([answerExThink, querying], () => {
  if (!querying.value) nextTick(updateAnswerHeight)
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
  hoveredChunk.value = null
  Object.keys(expandedSources).forEach(k => delete expandedSources[k])
  try {
    await queryRagStream(queryKbId.value, q, {
      onChunks(data) { chunks.value = data },
      onToken(token) { answerRaw.value += token },
    })
  } catch (err) {
    answerRaw.value = `错误: ${err.message}`
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

    <div class="results" v-if="answerRaw || chunks.length">

      <!-- Think -->
      <div class="think-card" v-for="(b, i) in thinkBlocks" :key="i">
        <div class="think-toggle" @click="thinkExpanded = !thinkExpanded">
          <svg class="think-icon" :class="{ open: thinkExpanded }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
          <span>{{ thinkExpanded ? '收起思考过程' : '查看思考过程' }}</span>
        </div>
        <div class="think-content markdown-body" v-show="thinkExpanded" v-html="renderMd(b.content)"></div>
      </div>

      <div class="content-row">
        <!-- Answer -->
        <div class="answer-col">
          <div class="answer-card" ref="answerBoxRef" :class="{ streaming: querying }">
            <h4>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5"/></svg>
              回答
            </h4>
            <div class="answer-text" v-if="answerExThink" :style="{ maxHeight: answerMaxH }">
              <div
                class="markdown-body"
                v-html="processedAnswerHtml"
                @click="onAnswerClick"
                @mouseover="onAnswerHover"
                @mouseleave="hoveredChunk = null"
              ></div>
            </div>
            <div class="answer-text empty-hint" v-else-if="querying"><span class="spinner"></span> 思考中...</div>
          </div>
        </div>

        <!-- Sources -->
        <div class="sources-col" v-if="chunks.length">
          <div class="sources-header">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/></svg>
            来源 · {{ chunks.length }}
          </div>
          <div class="sources-scroll">
            <div
              v-for="(c, i) in chunks" :key="i"
              :id="`src-${i + 1}`"
              class="source-chip"
              :class="{ active: expandedSources[i], highlight: hoveredChunk === (i + 1) }"
              :style="{ '--src-color': chunkColor(i) }"
              @mouseenter="hoveredChunk = i + 1"
              @mouseleave="hoveredChunk = null"
            >
              <div class="source-chip-top" @click="onSourceClick(i)" @dblclick="onSourceDblClick(c)">
                <span class="source-idx" :style="{ background: chunkColor(i) }">{{ i + 1 }}</span>
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

    <!-- PDF 预览弹窗 -->
    <PreviewModal
      :visible="previewVisible"
      :file-id="previewFileId"
      :file-name="previewFileName"
      :file-ext="previewFileExt"
      :page-number="previewPageNumber"
      :start-offset="previewStartOffset"
      :end-offset="previewEndOffset"
      :chunk-text="previewChunkText"
      @close="previewVisible = false"
    />
  </div>
</template>

<style scoped>
.query-section { display: flex; flex-direction: column; gap: 16px; }
.kb-select { display: flex; flex-direction: column; gap: 6px; }
.kb-select label { font-size: 13px; font-weight: 600; color: var(--c-secondary); }
.kb-select select { padding: 8px 12px; border: 1px solid var(--c-border); border-radius: var(--radius-sm); font-size: 14px; font-family: var(--font); outline: none; background: var(--c-bg); transition: border-color 150ms; cursor: pointer; }
.kb-select select:focus { border-color: var(--c-fg); }

.query-row { display: flex; gap: 8px; }
.query-row input { flex: 1; }

.results { display: flex; flex-direction: column; gap: 12px; }

.think-card { border: 1px solid #e2d9f3; border-radius: var(--radius); background: #f8f5ff; overflow: hidden; }
.think-toggle { display: flex; align-items: center; gap: 6px; padding: 10px 14px; cursor: pointer; user-select: none; font-size: 13px; color: #7c3aed; font-weight: 500; transition: background 150ms; }
.think-toggle:hover { background: #f0eaff; }
.think-icon { transition: transform 200ms; color: #7c3aed; }
.think-icon.open { transform: rotate(180deg); }
.think-content { padding: 0 14px 12px; font-size: 13px; line-height: 1.65; color: #6b7280; border-top: 1px solid #e2d9f3; padding-top: 10px; }

.content-row { display: flex; gap: 20px; align-items: flex-start; }

.answer-col { flex: 1; min-width: 0; }
.answer-card { border: 1px solid var(--c-border); border-radius: var(--radius); padding: 14px 16px; }
.answer-card h4 { font-size: 13px; font-weight: 700; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; color: var(--c-secondary); }
.answer-card .answer-text { font-size: 14px; line-height: 1.7; overflow-y: auto; }
.answer-text.empty-hint { color: var(--c-secondary); font-size: 13px; display: flex; align-items: center; gap: 8px; }

.answer-card.streaming .markdown-body::after { content: '|'; animation: blink 0.7s step-end infinite; font-weight: 100; color: var(--c-secondary); }
@keyframes blink { 50% { opacity: 0; } }

.sources-col { width: 240px; flex-shrink: 0; border: 1px solid var(--c-border); border-radius: var(--radius); overflow: hidden; max-height: calc(100vh - 200px); display: flex; flex-direction: column; }
.sources-header { display: flex; align-items: center; gap: 6px; padding: 10px 14px; font-size: 12px; color: var(--c-secondary); font-weight: 600; border-bottom: 1px solid var(--c-border); flex-shrink: 0; }
.sources-scroll { overflow-y: auto; flex: 1; padding: 8px; display: flex; flex-direction: column; gap: 6px; }

.source-chip { border: 1px solid var(--c-border); border-radius: var(--radius-sm); background: #fafafa; transition: border-color 150ms, background 150ms, box-shadow 150ms; border-left: 3px solid var(--src-color); }
.source-chip:hover { border-color: #d0d0d0; }
.source-chip.active { border-color: var(--src-color); background: #fff; }
.source-chip.highlight { border-color: var(--src-color); background: #fff; box-shadow: 0 0 0 2px color-mix(in srgb, var(--src-color) 20%, transparent); }

.source-chip-top { display: flex; align-items: center; gap: 6px; padding: 8px 10px; font-size: 12px; cursor: pointer; user-select: none; }
.source-idx { width: 18px; height: 18px; border-radius: 4px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 700; color: #fff; }
.source-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--c-fg); font-weight: 500; font-size: 11px; }
.source-pct { font-size: 10px; color: var(--c-accent); font-weight: 700; background: #eef2ff; padding: 1px 6px; border-radius: 10px; flex-shrink: 0; }
.source-chevron { flex-shrink: 0; color: var(--c-secondary); transition: transform 200ms; }
.source-chevron.open { transform: rotate(180deg); }

.source-text { font-size: 12px; line-height: 1.6; color: var(--c-secondary); padding: 0 10px 10px; border-top: 1px solid var(--c-border); padding-top: 8px; white-space: pre-wrap; max-height: 140px; overflow-y: auto; }

@media (max-width: 720px) {
  .content-row { flex-direction: column; }
  .sources-col { width: 100%; max-height: 360px; }
}
</style>

<style>
.cite-ref {
  display: inline-block; cursor: pointer;
  color: var(--c); font-weight: 700; font-size: 0.75em;
  background: color-mix(in srgb, var(--c) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--c) 30%, transparent);
  padding: 0 4px; border-radius: 3px; margin: 0 1px;
  vertical-align: super; line-height: 1.4;
  transition: background 150ms, box-shadow 150ms;
}
.cite-ref:hover { background: color-mix(in srgb, var(--c) 25%, transparent); box-shadow: 0 0 0 2px color-mix(in srgb, var(--c) 20%, transparent); }

.markdown-body h1, .markdown-body h2, .markdown-body h3 { margin: 12px 0 6px; font-weight: 600; color: var(--c-fg); }
.markdown-body h1 { font-size: 1.25em; }
.markdown-body h2 { font-size: 1.15em; }
.markdown-body h3 { font-size: 1.05em; }
.markdown-body p { margin: 6px 0; }
.markdown-body ul, .markdown-body ol { padding-left: 1.5em; margin: 6px 0; }
.markdown-body li { margin: 2px 0; }
.markdown-body code { background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; font-family: var(--font-mono, 'Consolas', monospace); }
.markdown-body pre { background: #1e1e1e; color: #d4d4d4; padding: 12px 16px; border-radius: 6px; overflow-x: auto; margin: 8px 0; line-height: 1.5; }
.markdown-body pre code { background: none; padding: 0; color: inherit; font-size: 13px; }
.markdown-body table { border-collapse: collapse; width: 100%; margin: 8px 0; }
.markdown-body th, .markdown-body td { border: 1px solid var(--c-border); padding: 6px 10px; text-align: left; font-size: 13px; }
.markdown-body th { background: #f9fafb; font-weight: 600; }
.markdown-body blockquote { border-left: 3px solid #7c3aed; padding: 4px 12px; margin: 8px 0; color: #6b7280; background: #f8f5ff; }
.markdown-body hr { border: none; border-top: 1px solid var(--c-border); margin: 12px 0; }
.markdown-body a { color: #7c3aed; }
.markdown-body strong { font-weight: 600; }
.markdown-body img { max-width: 100%; border-radius: 4px; }
</style>
