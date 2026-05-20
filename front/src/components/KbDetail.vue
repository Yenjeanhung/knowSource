<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { getKb, deleteFile as apiDeleteFile, uploadChunk, processFile, getFileStatus } from '../api'

const CHUNK_SIZE = 512 * 1024
const uuid = () => ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g,c=>(c^crypto.getRandomValues(new Uint8Array(1))[0]&15>>c/4).toString(16))

const props = defineProps({ kbId: { type: String, required: true } })
const router = useRouter()

const kb = ref(null)
const files = ref([])
const uploading = ref({})
const processing = ref({})
let pollTimers = {}

onMounted(async () => {
  try { kb.value = await getKb(props.kbId); files.value = kb.value.files || [] } catch {}
})

onUnmounted(() => { Object.values(pollTimers).forEach(clearInterval) })

function fmtSize(v) { return v<1024?v+' B':v<1048576?(v/1024).toFixed(1)+' KB':(v/1048576).toFixed(1)+' MB' }
function triggerUpload() { const el=document.getElementById('fileInput'); if(el)el.click() }
async function handleFileDrop(e) { e.preventDefault(); e.currentTarget.classList.remove('drag-over'); await handleFileList(e.dataTransfer.files) }
async function handleFilePick(e) { await handleFileList(e.target.files); e.target.value='' }

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
      await uploadChunk({ fileId, fileName: file.name, fileSize: file.size, kbId: props.kbId, chunkIndex: i, totalChunks: total, chunk })
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

async function batchProcess() {
  for (const f of files.value.filter(f => f.status === 'uploaded')) await startProcess(f.id)
}

function startPolling(fileId) {
  processing.value[fileId] = processing.value[fileId] || 0
  const timer = setInterval(async () => {
    try {
      const data = await getFileStatus(fileId)
      processing.value[fileId] = data.progress || 0
      if (data.status === 'indexed' || data.status === 'failed') {
        clearInterval(timer); delete pollTimers[fileId]
        const f = files.value.find(f => f.id === fileId)
        if (f) { f.status = data.status; if (data.message) f.message = data.message; if (data.status === 'indexed') delete processing.value[fileId] }
      }
    } catch { clearInterval(timer); delete pollTimers[fileId] }
  }, 1000)
  pollTimers[fileId] = timer
}

async function deleteFile(fileId) {
  if (pollTimers[fileId]) { clearInterval(pollTimers[fileId]); delete pollTimers[fileId] }
  delete processing.value[fileId]
  try { await apiDeleteFile(fileId) } catch {}
  files.value = files.value.filter(f => f.id !== fileId)
}

const getProgress = (id) => uploading.value[id]?.progress || 0
const getProcProgress = (id) => processing.value[id] || 0
const uploadedCount = () => files.value.filter(f => f.status === 'uploaded').length
</script>

<template>
  <div>
    <div class="page-head">
      <button class="back-btn" @click="router.push('/')">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>
      </button>
      <div class="head-title">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/></svg>
        <h1>{{ kb?.name || '加载中...' }}</h1>
      </div>
    </div>

    <!-- Upload -->
    <div class="dropzone" @click="triggerUpload" @dragover.prevent="$event.currentTarget.classList.add('drag')" @dragleave="$event.currentTarget.classList.remove('drag')" @drop="handleFileDrop">
      <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" class="dz-icon"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
      <div class="dz-title">拖拽或点击上传文件</div>
      <div class="dz-hint">TXT · PDF · Markdown · DOCX · CSV · JSON · HTML</div>
      <input id="fileInput" type="file" multiple accept=".txt,.pdf,.md,.csv,.json,.docx,.html" @change="handleFilePick" style="display:none">
    </div>

    <!-- List header -->
    <div class="sec-head">
      <span class="sec-title">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        文件列表 · {{ files.length }}
      </span>
      <button v-if="uploadedCount() > 1" class="batch-btn" @click="batchProcess">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="13 2 3 14 12 14 19 8"/><polyline points="3 22 12 13 21 22"/></svg>
        批量分片 ({{ uploadedCount() }})
      </button>
    </div>

    <!-- Files -->
    <div class="file-list" v-if="files.length">
      <div class="file-card" v-for="f in files" :key="f.id">
        <div class="file-main">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" class="ft-icon"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          <div class="file-info">
            <div class="file-name">{{ f.name }}</div>
            <div class="file-size">{{ fmtSize(f.size) }}</div>
          </div>

          <template v-if="uploading[f.id]">
            <div class="mini-bar"><div class="mini-fill" :style="{width:getProgress(f.id)+'%'}"></div></div>
            <span class="tag tag-up">{{ getProgress(f.id) }}%</span>
          </template>
          <template v-else-if="f.status === 'uploaded'">
            <button class="proc-btn" @click="startProcess(f.id)">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="13 2 3 14 12 14 19 8"/></svg>
              分片
            </button>
          </template>
          <template v-else-if="f.status === 'processing'">
            <span class="tag tag-proc">分片中</span>
          </template>
          <template v-else>
            <span class="tag" :class="f.status==='indexed'?'tag-ok':'tag-err'">{{ f.status==='indexed'?'已完成':'失败' }}</span>
          </template>

          <button class="rm-btn" @click="deleteFile(f.id)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="file-sub" v-if="f.status==='processing'">
          <span class="sub-label">分片中</span>
          <div class="mini-bar wide"><div class="mini-fill pro" :style="{width:getProcProgress(f.id)+'%'}"></div></div>
          <span class="sub-pct">{{ getProcProgress(f.id) }}%</span>
        </div>
        <div class="file-sub err" v-if="f.status==='failed' && f.message">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          {{ f.message }}
        </div>
      </div>
    </div>
    <div v-else class="empty-state">
      <div class="empty-icon"><svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div>
      <div class="empty-title">暂无文件</div>
      <div class="empty-desc">上传文档开始使用</div>
    </div>
  </div>
</template>

<style scoped>
.page-head { display: flex; align-items: center; gap: 8px; margin-bottom: 20px; }
.back-btn { background: none; border: none; cursor: pointer; color: var(--c-secondary); padding: 4px; border-radius: 6px; display: flex; transition: all 150ms; }
.back-btn:hover { color: var(--c-fg); background: var(--c-muted); }
.head-title { display: flex; align-items: center; gap: 8px; color: var(--c-fg); }
h1 { font-size: 18px; font-weight: 700; }

/* Dropzone */
.dropzone {
  border: 2px dashed var(--c-border); border-radius: 12px; padding: 28px;
  text-align: center; cursor: pointer; background: var(--c-muted);
  transition: border-color 150ms, background 150ms; margin-bottom: 20px;
}
.dropzone:hover, .dropzone.drag { border-color: var(--c-fg); background: var(--c-muted-hover); }
.dz-icon { color: var(--c-secondary); margin-bottom: 8px; }
.dz-title { font-size: 14px; font-weight: 600; }
.dz-hint { font-size: 12px; color: var(--c-secondary); margin-top: 4px; }

/* Section head */
.sec-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.sec-title { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700; color: var(--c-secondary); text-transform: uppercase; letter-spacing: 0.5px; flex: 1; }
.batch-btn { display: inline-flex; align-items: center; gap: 5px; padding: 4px 12px; font-size: 11px; font-weight: 600; border-radius: 6px; border: 1px solid #6366f1; background: transparent; color: #6366f1; cursor: pointer; transition: all 150ms; }
.batch-btn:hover { background: #6366f1; color: #fff; }

/* File list */
.file-list { display: flex; flex-direction: column; gap: 3px; }
.file-card { border-radius: var(--radius); border: 1px solid transparent; transition: background 150ms, border-color 150ms; }
.file-card:hover { background: var(--c-muted); border-color: var(--c-border); }
.file-main { display: flex; align-items: center; gap: 10px; padding: 8px 12px; }
.ft-icon { color: var(--c-secondary); flex-shrink: 0; }
.file-info { flex: 1; min-width: 0; }
.file-name { font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.file-size { font-size: 11px; color: var(--c-secondary); }

/* mini progress bar */
.mini-bar { width: 52px; height: 3px; background: var(--c-border); border-radius: 2px; overflow: hidden; flex-shrink: 0; }
.mini-bar.wide { flex: 1; }
.mini-fill { height: 100%; background: var(--c-fg); border-radius: 2px; transition: width 200ms; }
.mini-fill.pro { background: #6366f1; }

/* Tags */
.tag { font-size: 11px; font-weight: 600; flex-shrink: 0; }
.tag-up { color: var(--c-accent); }
.tag-proc { color: #6366f1; }
.tag-ok { color: var(--c-success); }
.tag-err { color: var(--c-danger); }

/* Process button */
.proc-btn { display: inline-flex; align-items: center; gap: 4px; padding: 4px 12px; font-size: 11px; font-weight: 600; border-radius: 6px; border: 1px solid #6366f1; background: transparent; color: #6366f1; cursor: pointer; transition: all 150ms; }
.proc-btn:hover { background: #6366f1; color: #fff; }

.rm-btn { background: none; border: none; cursor: pointer; color: var(--c-secondary); padding: 3px; border-radius: 4px; display: flex; transition: all 150ms; flex-shrink: 0; }
.rm-btn:hover { color: var(--c-danger); }

/* Sub lines */
.file-sub { display: flex; align-items: center; gap: 10px; padding: 2px 12px 8px 40px; }
.file-sub.err { color: var(--c-danger); font-size: 11px; }
.sub-label { font-size: 11px; font-weight: 600; color: #6366f1; flex-shrink: 0; }
.sub-pct { font-size: 11px; color: #6366f1; font-weight: 600; flex-shrink: 0; }
</style>
