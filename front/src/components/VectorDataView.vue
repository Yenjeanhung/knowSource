<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  fetchKbs,
  fetchVectorRecords,
  fetchVectorSearchTest,
  fetchVectorSummaryExport,
} from '../api'

const kbs = ref([])
const selectedKbId = ref('')
const searchText = ref('')
const onlyUnsynced = ref(false)
const records = ref([])
const provider = ref('')
const total = ref(0)
const loading = ref(false)
const error = ref('')
const expandedRows = ref({})

const testQuery = ref('')
const testTopK = ref(8)
const testLoading = ref(false)
const testResults = ref([])
const exportLoading = ref(false)

const groupedRecords = computed(() => {
  const kbMap = new Map()
  for (const row of records.value) {
    if (!kbMap.has(row.kb_id)) {
      kbMap.set(row.kb_id, {
        kb_id: row.kb_id,
        kb_name: row.kb_name,
        files: new Map(),
      })
    }
    const kbGroup = kbMap.get(row.kb_id)
    if (!kbGroup.files.has(row.file_id)) {
      kbGroup.files.set(row.file_id, {
        file_id: row.file_id,
        file_name: row.file_name,
        rows: [],
      })
    }
    kbGroup.files.get(row.file_id).rows.push(row)
  }
  return Array.from(kbMap.values()).map(group => ({
    ...group,
    files: Array.from(group.files.values()),
  }))
})

async function loadKbs() {
  try {
    kbs.value = await fetchKbs()
    if (!selectedKbId.value && kbs.value.length) selectedKbId.value = kbs.value[0].id
  } catch {}
}

async function loadRecords() {
  loading.value = true
  error.value = ''
  expandedRows.value = {}
  try {
    const data = await fetchVectorRecords({
      kbId: selectedKbId.value,
      q: searchText.value.trim(),
      unsyncedOnly: onlyUnsynced.value,
      limit: 100,
      offset: 0,
    })
    records.value = data.items || []
    provider.value = data.provider || ''
    total.value = data.total || 0
  } catch (err) {
    error.value = err.message || '加载失败'
  }
  loading.value = false
}

function toggleRow(chunkId) {
  expandedRows.value[chunkId] = !expandedRows.value[chunkId]
}

async function runSearchTest() {
  if (!selectedKbId.value || !testQuery.value.trim()) return
  testLoading.value = true
  error.value = ''
  try {
    const data = await fetchVectorSearchTest({
      kbId: selectedKbId.value,
      query: testQuery.value.trim(),
      topK: testTopK.value,
    })
    testResults.value = data.items || []
  } catch (err) {
    error.value = err.message || '检索测试失败'
  }
  testLoading.value = false
}

async function exportSummary(format) {
  exportLoading.value = true
  error.value = ''
  try {
    const data = await fetchVectorSummaryExport({
      kbId: selectedKbId.value,
      format,
    })
    const content = typeof data === 'string' ? data : JSON.stringify(data, null, 2)
    const blob = new Blob(
      [content],
      {
        type: format === 'md'
          ? 'text/markdown;charset=utf-8'
          : 'application/json;charset=utf-8',
      },
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `vector-summary${selectedKbId.value ? `-${selectedKbId.value}` : ''}.${format === 'md' ? 'md' : 'json'}`
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    error.value = err.message || '导出失败'
  }
  exportLoading.value = false
}

onMounted(async () => {
  await loadKbs()
  await loadRecords()
})
</script>

<template>
  <div class="vectors-page">
    <div class="vectors-toolbar">
      <div class="toolbar-left">
        <div class="toolbar-title">向量数据</div>
        <div class="toolbar-subtitle">按知识库和文件分组查看分片索引记录，并保持对向量库实现无感知</div>
      </div>
      <div class="toolbar-meta">
        <span class="meta-chip">Provider · {{ provider || '--' }}</span>
        <span class="meta-chip">Records · {{ total }}</span>
      </div>
    </div>

    <div class="vectors-filters">
      <select v-model="selectedKbId" @change="loadRecords">
        <option value="">全部知识库</option>
        <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
      </select>
      <input
        type="text"
        v-model="searchText"
        placeholder="搜索文件名、分片内容或向量 ID..."
        @keydown.enter="loadRecords"
      >
      <label class="toggle-box">
        <input type="checkbox" v-model="onlyUnsynced">
        <span>仅看未同步</span>
      </label>
      <button class="btn primary" @click="loadRecords" :disabled="loading">查询</button>
    </div>

    <div class="tools-grid">
      <section class="vectors-card tool-card">
        <div class="tool-title">相似检索测试</div>
        <div class="tool-subtitle">输入问题，直接查看当前知识库在向量库中的 topK 命中分片。</div>
        <div class="test-controls">
          <input
            type="text"
            v-model="testQuery"
            placeholder="输入测试 query，比如：什么是 RLHF？"
            @keydown.enter="runSearchTest"
          >
          <select v-model="testTopK">
            <option :value="5">Top 5</option>
            <option :value="8">Top 8</option>
            <option :value="10">Top 10</option>
          </select>
          <button class="btn primary" @click="runSearchTest" :disabled="testLoading || !selectedKbId || !testQuery.trim()">测试</button>
        </div>
        <div class="test-results" v-if="testResults.length">
          <div class="test-item" v-for="item in testResults" :key="`${item.rank}-${item.file_id}-${item.start_offset}`">
            <div class="test-item-head">
              <span class="test-rank">#{{ item.rank }}</span>
              <span class="test-file">{{ item.file_name }}</span>
              <span class="test-score">{{ Math.round(item.score * 100) }}%</span>
            </div>
            <div class="test-snippet">{{ item.chunk_text }}</div>
          </div>
        </div>
        <div class="loading-row" v-else-if="testLoading"><span class="spinner"></span> 检索测试中...</div>
      </section>

      <section class="vectors-card tool-card">
        <div class="tool-title">导出索引摘要</div>
        <div class="tool-subtitle">导出当前筛选范围内的索引统计，方便排查同步情况或留档。</div>
        <div class="export-actions">
          <button class="btn" @click="exportSummary('json')" :disabled="exportLoading">导出 JSON</button>
          <button class="btn" @click="exportSummary('md')" :disabled="exportLoading">导出 Markdown</button>
        </div>
        <div class="tool-note">导出内容包含 provider、知识库、文件数、chunk 数、同步/未同步统计。</div>
      </section>
    </div>

    <div class="vectors-card" v-if="error">
      <div class="error-text">{{ error }}</div>
    </div>

    <div class="vectors-card" v-else-if="loading">
      <div class="loading-row"><span class="spinner"></span> 加载向量记录中...</div>
    </div>

    <div class="vectors-groups" v-else-if="groupedRecords.length">
      <section v-for="kb in groupedRecords" :key="kb.kb_id" class="vectors-card">
        <div class="group-head">
          <div>
            <div class="group-title">{{ kb.kb_name }}</div>
            <div class="group-sub">{{ kb.files.length }} 个文件</div>
          </div>
        </div>

        <div v-for="file in kb.files" :key="file.file_id" class="file-group">
          <div class="file-head">
            <div class="file-title">{{ file.file_name }}</div>
            <div class="file-sub">{{ file.rows.length }} 个分片</div>
          </div>

          <div class="vector-row" v-for="row in file.rows" :key="row.chunk_id">
            <div class="row-main" @click="toggleRow(row.chunk_id)">
              <div class="row-col chunk-col">
                <div class="cell-title">#{{ row.chunk_index }}</div>
                <div class="cell-sub">{{ row.content_length }} chars</div>
              </div>
              <div class="row-col id-col">
                <div class="mono">{{ row.embedding_id || '--' }}</div>
              </div>
              <div class="row-col status-col">
                <span class="status-chip" :class="{ ok: row.store_found === true, miss: row.store_found === false }">
                  {{ row.store_found === true ? '已同步' : row.store_found === false ? '未命中' : '未校验' }}
                </span>
              </div>
              <div class="row-col preview-col">
                <div class="preview-text">{{ row.store_document_preview || row.content_preview }}</div>
              </div>
              <div class="row-col action-col">
                <span class="expand-indicator">{{ expandedRows[row.chunk_id] ? '收起' : '展开' }}</span>
              </div>
            </div>

            <div v-if="expandedRows[row.chunk_id]" class="row-expanded">
              <div class="expanded-block">
                <div class="expanded-label">完整 Chunk</div>
                <pre class="expanded-pre">{{ row.content_full }}</pre>
              </div>
              <div class="expanded-block" v-if="row.store_metadata && Object.keys(row.store_metadata).length">
                <div class="expanded-label">向量库 Metadata</div>
                <pre class="expanded-pre">{{ JSON.stringify(row.store_metadata, null, 2) }}</pre>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>

    <div class="vectors-card empty-state" v-else>
      <div class="title">暂无向量记录</div>
      <div class="desc">当前筛选条件下没有查到已分片并建索引的数据。</div>
    </div>
  </div>
</template>

<style scoped>
.vectors-page { display: flex; flex-direction: column; gap: 16px; }

.vectors-toolbar {
  display: flex; align-items: flex-end; justify-content: space-between; gap: 16px;
}
.toolbar-title { font-size: 24px; font-weight: 700; letter-spacing: -0.02em; }
.toolbar-subtitle { margin-top: 4px; color: var(--c-secondary); font-size: 13px; }
.toolbar-meta { display: flex; gap: 8px; flex-wrap: wrap; }
.meta-chip {
  border: 1px solid var(--c-border); border-radius: 999px;
  padding: 6px 10px; font-size: 12px; color: var(--c-secondary); background: #fff;
}

.vectors-filters {
  display: grid; grid-template-columns: 220px 1fr auto auto; gap: 10px;
}
.vectors-filters select,
.test-controls select {
  padding: 8px 12px; border: 1px solid var(--c-border); border-radius: var(--radius-sm);
  font-size: 14px; font-family: var(--font); background: #fff; outline: none;
}
.toggle-box {
  display: inline-flex; align-items: center; gap: 8px; padding: 0 6px;
  color: var(--c-secondary); font-size: 13px;
}
.vectors-card {
  border: 1px solid var(--c-border); border-radius: 18px; background: #fff;
  box-shadow: 0 10px 30px rgba(23, 23, 23, 0.04);
}
.tools-grid {
  display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 14px;
}
.tool-card { padding: 18px; }
.tool-title { font-size: 16px; font-weight: 700; }
.tool-subtitle, .tool-note { margin-top: 6px; color: var(--c-secondary); font-size: 13px; line-height: 1.6; }
.test-controls {
  display: grid; grid-template-columns: 1fr 110px auto; gap: 10px; margin-top: 14px;
}
.test-results {
  margin-top: 14px; display: flex; flex-direction: column; gap: 10px; max-height: 340px; overflow: auto;
}
.test-item {
  border: 1px solid #f0f0f0; border-radius: 12px; padding: 12px; background: #fafafa;
}
.test-item-head {
  display: flex; align-items: center; gap: 8px; font-size: 12px; margin-bottom: 8px;
}
.test-rank {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 32px; height: 24px; border-radius: 999px; background: #171717; color: #fff; font-weight: 700;
}
.test-file { font-weight: 600; color: #333; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.test-score { color: var(--c-accent); font-weight: 700; }
.test-snippet {
  color: #444; font-size: 13px; line-height: 1.6;
  display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden;
}
.export-actions { display: flex; gap: 10px; margin-top: 14px; }

.vectors-groups { display: flex; flex-direction: column; gap: 14px; }
.group-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 18px 20px; border-bottom: 1px solid #f0f0f0;
}
.group-title { font-size: 18px; font-weight: 700; }
.group-sub, .file-sub, .cell-sub { margin-top: 4px; font-size: 12px; color: var(--c-secondary); }
.file-group + .file-group { border-top: 1px solid #f5f5f5; }
.file-head { padding: 16px 20px 10px; }
.file-title { font-size: 14px; font-weight: 600; }

.vector-row + .vector-row { border-top: 1px solid #f8f8f8; }
.row-main {
  display: grid; grid-template-columns: 90px minmax(180px, 1.2fr) 120px minmax(260px, 2fr) 52px;
  gap: 12px; padding: 14px 20px; align-items: start; cursor: pointer;
}
.row-main:hover { background: #fcfcfc; }
.cell-title { font-size: 13px; font-weight: 600; }
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px; color: #444; word-break: break-all;
}
.status-chip {
  display: inline-flex; align-items: center; border-radius: 999px; padding: 4px 10px;
  font-size: 12px; font-weight: 600; background: #f5f5f5; color: #666;
}
.status-chip.ok { background: #ecfdf3; color: #15803d; }
.status-chip.miss { background: #fef2f2; color: #b91c1c; }
.preview-text {
  color: #444; font-size: 13px; line-height: 1.6;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.action-col { text-align: right; }
.expand-indicator { font-size: 12px; color: var(--c-secondary); }

.row-expanded {
  display: grid; gap: 10px; padding: 0 20px 16px 20px;
}
.expanded-block {
  border: 1px solid #f0f0f0; border-radius: 12px; background: #fafafa; overflow: hidden;
}
.expanded-label {
  padding: 10px 12px; font-size: 12px; font-weight: 700; color: var(--c-secondary);
  border-bottom: 1px solid #efefef; background: #fcfcfc;
}
.expanded-pre {
  margin: 0; padding: 12px; white-space: pre-wrap; word-break: break-word;
  font-size: 12px; line-height: 1.65; color: #333;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.loading-row {
  display: flex; align-items: center; gap: 8px; padding: 22px 18px; color: var(--c-secondary);
}
.error-text { padding: 18px; color: var(--c-danger); }

@media (max-width: 900px) {
  .vectors-filters { grid-template-columns: 1fr; }
  .tools-grid { grid-template-columns: 1fr; }
  .test-controls { grid-template-columns: 1fr; }
  .row-main { grid-template-columns: 1fr; }
  .action-col { text-align: left; }
}
</style>
