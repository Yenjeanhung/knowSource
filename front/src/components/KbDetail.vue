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
const processing = ref({}) // { fileId: progress }
let pollTimers = {}

onMounted(async () => {
  try {
    kb.value = await getKb(props.kbId)
    files.value = (kb.value.files || []).map(f => ({
      ...f,
      // 服务端 indexed 状态映射到前端
      _status: f.status === 'indexed' ? 'indexed' : f.status === 'failed' ? 'failed' : f.status,
    }))
    // 恢复正在处理中的文件轮询
    for (const f of files.value) {
      if (f.status === 'processing') startPolling(f.id)
    }
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

async function startProcess(fileId) {
  try {
    await processFile(fileId)
    const f = files.value.find(f => f.id === fileId)
    if (f) f.status = 'processing'
    processing.value[fileId] = 0
    startPolling(fileId)
  } catch {}
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
      <button class="btn danger sm" @click="emit('deleted')">Delete KB</button>
    </div>

    <!-- Upload Zone -->
    <div class="upload-zone" @click="triggerUpload" @dragover.prevent="$event.currentTarget.classList.add('drag-over')" @dragleave="$event.currentTarget.classList.remove('drag-over')" @drop="handleFileDrop">
      <div class="icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
        </svg>
      </div>
      <div class="label">Drop files or click to upload</div>
      <div class="hint">Chunked upload, max 512KB per chunk</div>
      <input id="fileInput" type="file" multiple accept=".txt,.pdf,.md,.csv,.json,.docx,.html" @change="handleFilePick" style="display:none">
    </div>

    <!-- File List -->
    <div class="section-title">Files ({{ files.length }})</div>
    <div class="file-list" v-if="files.length">
      <div class="file-row" v-for="f in files" :key="f.id">
        <svg class="file-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
        </svg>
        <span class="file-name">{{ f.name }}</span>
        <span class="file-meta">{{ fmtSize(f.size) }}</span>

        <!-- 上传进度 -->
        <template v-if="uploading[f.id]">
          <div class="progress-track"><div class="progress-fill" :style="{ width: getProgress(f.id) + '%' }"></div></div>
          <span class="file-status uploading">{{ getProgress(f.id) }}%</span>
        </template>

        <!-- 已上传，等待确认 -->
        <template v-else-if="f.status === 'uploaded'">
          <button class="btn process-btn" @click="startProcess(f.id)">Process</button>
        </template>

        <!-- 处理中，显示进度 -->
        <template v-else-if="f.status === 'processing'">
          <div class="progress-track"><div class="progress-fill processing" :style="{ width: getProcessingProgress(f.id) + '%' }"></div></div>
          <span class="file-status processing">{{ getProcessingProgress(f.id) }}%</span>
        </template>

        <!-- 完成 / 失败 -->
        <template v-else>
          <span class="file-status" :class="f.status">{{ f.status === 'indexed' ? 'Indexed' : f.status === 'error' ? 'Error' : f.status }}</span>
        </template>

        <button class="del-btn" @click="deleteFile(f.id)">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    </div>
    <div v-else class="empty-state" style="padding:24px">
      <div class="desc">No files in this knowledge base</div>
    </div>
  </div>
</template>

<style scoped>
.detail-header { display: flex; align-items: center; gap: 10px; margin-bottom: 20px; }
.back { cursor: pointer; color: var(--c-secondary); display: flex; align-items: center; transition: color 150ms; background: none; border: none; padding: 4px; }
.back:hover { color: var(--c-fg); }
h2 { font-size: 16px; font-weight: 700; flex: 1; }
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
.upload-zone .hint { font-size: 12px; color: var(--c-secondary); margin-top: 2px; }

.section-title { font-size: 13px; font-weight: 700; color: var(--c-secondary); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px; }

.file-list { display: flex; flex-direction: column; gap: 3px; }
.file-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 10px; border-radius: var(--radius-sm); font-size: 13px;
  transition: background 150ms;
}
.file-row:hover { background: var(--c-muted); }
.file-icon { color: var(--c-secondary); flex-shrink: 0; }
.file-name { flex: 1; min-width: 0; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.file-meta { font-size: 12px; color: var(--c-secondary); flex-shrink: 0; }
.file-status { font-size: 12px; flex-shrink: 0; }
.file-status.indexed { color: var(--c-success); }
.file-status.uploading { color: var(--c-accent); }
.file-status.processing { color: var(--c-accent); }
.file-status.error { color: var(--c-danger); }
.file-status.failed { color: var(--c-danger); }

.progress-track { width: 60px; height: 3px; background: var(--c-border); border-radius: 2px; overflow: hidden; flex-shrink: 0; }
.progress-fill { height: 100%; background: var(--c-fg); border-radius: 2px; transition: width 200ms; }
.progress-fill.processing { background: var(--c-accent); }

.process-btn {
  padding: 3px 10px; font-size: 11px; font-weight: 600;
  border-radius: var(--radius-sm); border: 1px solid var(--c-border);
  background: var(--c-muted); cursor: pointer;
  transition: background 150ms, border-color 150ms;
}
.process-btn:hover { background: var(--c-fg); color: var(--c-bg); border-color: var(--c-fg); }

.del-btn {
  background: none; border: none; cursor: pointer; color: var(--c-secondary);
  padding: 2px; border-radius: 3px; display: flex; align-items: center;
  transition: color 150ms; flex-shrink: 0;
}
.del-btn:hover { color: var(--c-danger); }
</style>
