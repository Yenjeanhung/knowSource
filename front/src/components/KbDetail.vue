<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { getKb, deleteFile as apiDeleteFile, uploadChunk, processFile, getFileStatus } from '../api'

const CHUNK_SIZE = 512 * 1024
const uuid = () => ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g,c=>(c^crypto.getRandomValues(new Uint8Array(1))[0]&15>>c/4).toString(16))

const props = defineProps({ kbId: { type: String, required: true } })
const emit = defineEmits(['back', 'deleted'])

const kb = ref(null)
const files = ref([])
const uploading = ref({})
const processing = ref({})
let pollTimers = {}

onMounted(async () => {
  try {
    kb.value = await getKb(props.kbId)
    files.value = kb.value.files || []
  } catch {}
})

onUnmounted(() => {
  Object.values(pollTimers).forEach(clearInterval)
})

function fmtSize(v) {
  return v < 1024 ? v + ' B' : v < 1048576 ? (v / 1024).toFixed(1) + ' KB' : (v / 1048576).toFixed(1) + ' MB'
}
function triggerUpload() {
  const input = document.getElementById('fileInput')
  if (input) input.click()
}

async function handleFileDrop(e) {
  e.preventDefault()
  e.currentTarget.classList.remove('drag-over')
  await handleFileList(e.dataTransfer.files)
}

async function handleFilePick(e) {
  await handleFileList(e.target.files)
  e.target.value = ''
}

async function handleFileList(list) {
  for (const file of list) {
    const id = uuid()
    files.value.push({ id, name: file.name, size: file.size, status: 'uploading' })
    uploading.value[id] = { progress: 0 }
    await uploadFile(id, file)
  }
}

async function uploadFile(fileId, file) {
  const total = Math.ceil(file.size / CHUNK_SIZE)
  try {
    for (let i = 0; i < total; i++) {
      const chunk = file.slice(i * CHUNK_SIZE, (i + 1) * CHUNK_SIZE)
      await uploadChunk({
        fileId, fileName: file.name, fileSize: file.size,
        kbId: props.kbId, chunkIndex: i, totalChunks: total, chunk,
      })
      uploading.value[fileId] = { progress: Math.round(((i + 1) / total) * 100) }
    }
    const f = files.value.find(f => f.id === fileId)
    if (f) f.status = 'uploaded'
  } catch {
    const f = files.value.find(f => f.id === fileId)
    if (f) f.status = 'error'
  }
  delete uploading.value[fileId]
}

// -- 分片 --
async function startProcess(fileId) {
  try {
    await processFile(fileId)
    const f = files.value.find(f => f.id === fileId)
    if (f) f.status = 'processing'
    processing.value[fileId] = 0
    startPolling(fileId)
  } catch {}
}

async function batchProcess() {
  const pending = files.value.filter(f => f.status === 'uploaded')
  for (const f of pending) {
    await startProcess(f.id)
  }
}

function startPolling(fileId) {
  processing.value[fileId] = processing.value[fileId] || 0
  const timer = setInterval(async () => {
    try {
      const data = await getFileStatus(fileId)
      processing.value[fileId] = data.progress || 0
      if (data.status === 'indexed' || data.status === 'failed') {
        clearInterval(timer)
        delete pollTimers[fileId]
        const f = files.value.find(f => f.id === fileId)
        if (f) {
          f.status = data.status
          if (data.message) f.message = data.message
          if (data.status === 'indexed') delete processing.value[fileId]
        }
      }
    } catch {
      clearInterval(timer)
      delete pollTimers[fileId]
    }
  }, 1000)
  pollTimers[fileId] = timer
}

async function deleteFile(fileId) {
  if (pollTimers[fileId]) {
    clearInterval(pollTimers[fileId])
    delete pollTimers[fileId]
  }
  delete processing.value[fileId]
  try { await apiDeleteFile(fileId) } catch {}
  files.value = files.value.filter(f => f.id !== fileId)
}

function getProgress(fileId) {
  return uploading.value[fileId]?.progress || 0
}

function getProcessingProgress(fileId) {
  return processing.value[fileId] || 0
}

const uploadedCount = () => files.value.filter(f => f.status === 'uploaded').length
</script>

<template>
  <div>
    <div class="detail-header">
      <button class="back" @click="emit('back')">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="m15 18-6-6 6-6"/>
        </svg>
      </button>
      <h2>{{ kb?.name || '...' }}</h2>
      <div class="flex-1"></div>
      <button class="btn danger sm" @click="emit('deleted')">删除知识库</button>
    </div>

    <!-- Upload Zone -->
    <div class="upload-zone" @click="triggerUpload" @dragover.prevent="$event.currentTarget.classList.add('drag-over')" @dragleave="$event.currentTarget.classList.remove('drag-over')" @drop="handleFileDrop">
      <div class="icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
      </div>
      <div class="label">拖拽文件到此处，或点击上传</div>
      <div class="hint">支持 TXT、PDF、Markdown、DOCX、CSV、JSON、HTML</div>
      <input id="fileInput" type="file" multiple accept=".txt,.pdf,.md,.csv,.json,.docx,.html" @change="handleFilePick" style="display:none">
    </div>

    <!-- File List -->
    <div class="section-header">
      <span class="section-title">文件列表 ({{ files.length }})</span>
      <button v-if="uploadedCount() > 1" class="batch-btn" @click="batchProcess">批量分片 ({{ uploadedCount() }})</button>
    </div>
    <div class="file-list" v-if="files.length">
      <div class="file-item" v-for="f in files" :key="f.id">
        <div class="file-row">
          <svg class="file-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
          </svg>
          <span class="file-name">{{ f.name }}</span>
          <span class="file-meta">{{ fmtSize(f.size) }}</span>

          <!-- 上传进度 -->
          <template v-if="uploading[f.id]">
            <div class="upload-progress-track"><div class="upload-progress-fill" :style="{ width: getProgress(f.id) + '%' }"></div></div>
            <span class="file-status uploading">{{ getProgress(f.id) }}%</span>
          </template>

          <!-- 已上传，等待确认 -->
          <template v-else-if="f.status === 'uploaded'">
            <button class="process-btn" @click="startProcess(f.id)">分片</button>
          </template>

          <!-- 处理中 -->
          <template v-else-if="f.status === 'processing'">
            <span class="file-status processing">分片中...</span>
          </template>

          <!-- 完成 / 失败 -->
          <template v-else>
            <span class="file-status" :class="f.status">{{ f.status === 'indexed' ? '已完成' : f.status === 'error' ? '失败' : f.status === 'failed' ? '失败' : f.status }}</span>
          </template>

          <button class="del-btn" @click="deleteFile(f.id)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <!-- 分片进度条 -->
        <div class="chunk-progress" v-if="f.status === 'processing'">
          <span class="chunk-progress-label">分片中</span>
          <div class="chunk-progress-track">
            <div class="chunk-progress-fill" :style="{ width: getProcessingProgress(f.id) + '%' }"></div>
          </div>
          <span class="chunk-progress-pct">{{ getProcessingProgress(f.id) }}%</span>
        </div>
        <!-- 失败原因 -->
        <div class="fail-reason" v-if="f.status === 'failed' && f.message">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          {{ f.message }}
        </div>
      </div>
    </div>
    <div v-else class="empty-state" style="padding:24px">
      <div class="desc">暂无文件，上传文档开始使用</div>
    </div>
  </div>
</template>

<style scoped>
.detail-header { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; flex-wrap: wrap; }
.back { cursor: pointer; color: var(--c-secondary); display: flex; align-items: center; transition: color 150ms; background: none; border: none; padding: 4px; }
.back:hover { color: var(--c-fg); }
h2 { font-size: 16px; font-weight: 700; margin: 0; flex: 1; }
.flex-1 { flex: 1; }
.sm { padding: 5px 10px; font-size: 12px; }

.upload-zone {
  border: 1.5px dashed var(--c-border); border-radius: var(--radius);
  padding: 24px; text-align: center; cursor: pointer;
  background: var(--c-muted); transition: border-color 150ms, background 150ms;
  margin-bottom: 16px;
}
.upload-zone:hover, .upload-zone.drag-over { border-color: var(--c-fg); background: var(--c-muted-hover); }
.upload-zone .icon { color: var(--c-secondary); margin-bottom: 6px; }
.upload-zone .label { font-size: 14px; font-weight: 600; }
.upload-zone .hint { font-size: 12px; color: var(--c-secondary); margin-top: 4px; }

.section-header { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.section-title { font-size: 13px; font-weight: 700; color: var(--c-secondary); text-transform: uppercase; letter-spacing: 0.5px; }
.batch-btn {
  padding: 3px 12px; font-size: 11px; font-weight: 600;
  border-radius: var(--radius-sm); border: 1px solid #6366f1;
  background: transparent; color: #6366f1; cursor: pointer;
  transition: background 150ms, color 150ms;
}
.batch-btn:hover { background: #6366f1; color: #fff; }

.file-list { display: flex; flex-direction: column; gap: 3px; }
.file-item { border-radius: var(--radius-sm); transition: background 150ms; }
.file-item:hover { background: var(--c-muted); }
.file-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 10px; font-size: 13px;
}
.file-icon { color: var(--c-secondary); flex-shrink: 0; }
.file-name { flex: 1; min-width: 0; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.file-meta { font-size: 12px; color: var(--c-secondary); flex-shrink: 0; }
.file-status { font-size: 12px; flex-shrink: 0; }
.file-status.indexed { color: var(--c-success); }
.file-status.uploading { color: var(--c-accent); }
.file-status.processing { color: #6366f1; }
.file-status.error { color: var(--c-danger); }
.file-status.failed { color: var(--c-danger); }

.upload-progress-track { width: 60px; height: 3px; background: var(--c-border); border-radius: 2px; overflow: hidden; flex-shrink: 0; }
.upload-progress-fill { height: 100%; background: var(--c-fg); border-radius: 2px; transition: width 200ms; }

.chunk-progress {
  display: flex; align-items: center; gap: 10px;
  padding: 2px 10px 8px 42px;
}
.chunk-progress-label { font-size: 11px; font-weight: 600; color: #6366f1; flex-shrink: 0; }
.chunk-progress-track { flex: 1; height: 5px; background: var(--c-border); border-radius: 3px; overflow: hidden; }
.chunk-progress-fill { height: 100%; background: #6366f1; border-radius: 3px; transition: width 300ms ease-out; }
.chunk-progress-pct { font-size: 11px; color: #6366f1; font-weight: 600; flex-shrink: 0; min-width: 30px; text-align: right; }

.process-btn {
  padding: 4px 14px; font-size: 12px; font-weight: 600;
  border-radius: var(--radius-sm); border: 1px solid #6366f1;
  background: transparent; color: #6366f1; cursor: pointer;
  transition: background 150ms, color 150ms;
}
.process-btn:hover { background: #6366f1; color: #fff; }

.del-btn {
  background: none; border: none; cursor: pointer; color: var(--c-secondary);
  padding: 2px; border-radius: 3px; display: flex; align-items: center;
  transition: color 150ms; flex-shrink: 0;
}
.del-btn:hover { color: var(--c-danger); }

.fail-reason {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 10px 8px 42px;
  font-size: 11px; color: var(--c-danger); opacity: 0.85;
}
</style>
