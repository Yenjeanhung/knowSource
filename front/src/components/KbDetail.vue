<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { getKb, deleteFile as apiDeleteFile, uploadChunk, processFile, reprocessFile, getFileStatus, cancelProcessing } from '../api'

const CHUNK_SIZE = 512 * 1024
const uuid = () => ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(
  /[018]/g,
  c => (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16),
)

const props = defineProps({ kbId: { type: String, required: true } })
const router = useRouter()

const kb = ref(null)
const files = ref([])
const uploading = ref({})
const processing = ref({})
const nowTick = ref(Date.now())
const pollTimers = {}
let clockTimer = null
const stageTimers = ref({})

const STAGE_ORDER = ['chunking', 'vectorizing', 'extraction']

function syncStageTimers(fileId, detail) {
  if (!detail?.stages) return
  for (const stageName of STAGE_ORDER) {
    const stage = detail.stages[stageName]
    if (!stage) continue
    const key = `${fileId}-${stageName}`
    const cur = stageTimers.value[key]
    if (!cur) {
      stageTimers.value = { ...stageTimers.value, [key]: { started: null, ended: null } }
    }
    const timer = stageTimers.value[key]
    // 启动计时器的条件：进度大于0，或者标签不是"等待开始"
    const shouldStart = stage.progress > 0 || (stage.label && !stage.label.includes('等待开始'))
    if (shouldStart && !timer.started) {
      const serverStart = stage.started_at ? new Date(stage.started_at).getTime() : null
      stageTimers.value = { ...stageTimers.value, [key]: { ...timer, started: serverStart || Date.now() } }
    }
    if (stage.progress >= 100 && timer.started && !timer.ended && !timer.frozen) {
      const serverEnd = stage.finished_at ? new Date(stage.finished_at).getTime() : null
      stageTimers.value = { ...stageTimers.value, [key]: { ...timer, started: timer.started, ended: serverEnd || Date.now() } }
    }
  }
}
const showProcessDialog = ref(false)
const pendingFileId = ref('')
const pendingFileName = ref('')
const pendingProcessMode = ref('process')

// Confirm dialog state
const showConfirmDialog = ref(false)
const confirmDialogTitle = ref('')
const confirmDialogMessage = ref('')
const confirmDialogConfirmText = ref('确定')
const confirmDialogCancelText = ref('取消')
let confirmDialogCallback = null

const uploadedCount = computed(() => files.value.filter(item => item.status === 'uploaded').length)

onMounted(async () => {
  try {
    kb.value = await getKb(props.kbId)
    files.value = (kb.value.files || []).map(normalizeFile)
    for (const file of files.value) {
      if (file.status === 'processing') startPolling(file.id)
    }
  } catch {}
  clockTimer = setInterval(() => {
    nowTick.value = Date.now()
  }, 1000)
})

onUnmounted(() => {
  Object.values(pollTimers).forEach(clearInterval)
  if (clockTimer) clearInterval(clockTimer)
})

function normalizeFile(file) {
  return {
    ...file,
    detail: file.detail || null,
    logs: Array.isArray(file.logs) ? file.logs : [],
  }
}

function fmtSize(value) {
  if (value < 1024) return `${value} B`
  if (value < 1048576) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1048576).toFixed(1)} MB`
}

function triggerUpload() {
  const el = document.getElementById('fileInput')
  if (el) el.click()
}

async function handleFileDrop(event) {
  event.preventDefault()
  event.currentTarget.classList.remove('drag')
  await handleFileList(event.dataTransfer.files)
}

async function handleFilePick(event) {
  await handleFileList(event.target.files)
  event.target.value = ''
}

async function handleFileList(list) {
  for (const file of list) {
    const id = uuid()
    files.value.push({
      id,
      name: file.name,
      size: file.size,
      status: 'uploading',
      progress: 0,
      message: '',
      detail: null,
      logs: [],
    })
    uploading.value[id] = { progress: 0 }
    await uploadFile(id, file)
  }
}

async function uploadFile(fileId, file) {
  const total = Math.ceil(file.size / CHUNK_SIZE)
  try {
    for (let index = 0; index < total; index += 1) {
      const chunk = file.slice(index * CHUNK_SIZE, (index + 1) * CHUNK_SIZE)
      await uploadChunk({
        fileId,
        fileName: file.name,
        fileSize: file.size,
        kbId: props.kbId,
        chunkIndex: index,
        totalChunks: total,
        chunk,
      })
      uploading.value[fileId] = { progress: Math.round(((index + 1) / total) * 100) }
    }
    const target = files.value.find(item => item.id === fileId)
    if (target) {
      target.status = 'uploaded'
      target.message = '上传完成，等待开始处理'
    }
  } catch {
    const target = files.value.find(item => item.id === fileId)
    if (target) target.status = 'error'
  }
  delete uploading.value[fileId]
}

function showConfirm(title, message, confirmText = '确定', cancelText = '取消') {
  return new Promise(resolve => {
    confirmDialogTitle.value = title
    confirmDialogMessage.value = message
    confirmDialogConfirmText.value = confirmText
    confirmDialogCancelText.value = cancelText
    confirmDialogCallback = resolve
    showConfirmDialog.value = true
  })
}

function confirmDialogOk() {
  showConfirmDialog.value = false
  confirmDialogCallback(true)
}

function confirmDialogCancel() {
  showConfirmDialog.value = false
  confirmDialogCallback(false)
}

function openProcessDialog(file) {
  pendingFileId.value = file.id
  pendingFileName.value = file.name
  pendingProcessMode.value = 'process'
  showProcessDialog.value = true
}

function openReprocessDialog(file) {
  pendingFileId.value = file.id
  pendingFileName.value = file.name
  pendingProcessMode.value = 'reprocess'
  showProcessDialog.value = true
}

async function confirmProcess(extractGraph) {
  showProcessDialog.value = false
  const fileId = pendingFileId.value
  if (!fileId) return
  try {
    const runner = pendingProcessMode.value === 'reprocess' ? reprocessFile : processFile
    await runner(fileId, { extractGraph })
    const target = files.value.find(item => item.id === fileId)
    if (target) {
      target.status = 'processing'
      target.message = pendingProcessMode.value === 'reprocess'
        ? (extractGraph ? '准备重新处理（含图谱抽取）' : '准备重新处理（跳过图谱）')
        : (extractGraph ? '准备开始处理（含图谱抽取）' : '准备开始处理（跳过图谱）')
      target.logs = []
      target.detail = {
        started_at: new Date().toISOString(),
        finished_at: null,
        elapsed_ms: 0,
        stage: 'preparing',
        summary: { chunk_count: 0, entity_count: 0, relation_count: 0 },
        stages: {
          total: { progress: 0, label: '准备开始处理' },
          chunking: { progress: 0, current: 0, total: 0, label: '等待开始' },
          extraction: {
            progress: extractGraph ? 0 : 100,
            processed_batches: 0,
            total_batches: 0,
            started_batches: 0,
            running_batches: 0,
            processed_chunks: 0,
            total_candidate_chunks: 0,
            entity_count: 0,
            relation_count: 0,
            label: extractGraph ? '等待开始' : '已跳过',
          },
        },
      }
    }
    processing.value[fileId] = 0
    startPolling(fileId)
  } catch {}
  pendingFileId.value = ''
  pendingFileName.value = ''
  pendingProcessMode.value = 'process'
}

async function batchProcess(extractGraph = true) {
  for (const file of files.value.filter(item => item.status === 'uploaded')) {
    try {
      await processFile(file.id, { extractGraph })
      const target = files.value.find(item => item.id === file.id)
      if (target) {
        target.status = 'processing'
        target.message = extractGraph ? '准备开始处理（含图谱抽取）' : '准备开始处理（跳过图谱）'
        target.logs = []
        target.detail = {
          started_at: new Date().toISOString(),
          finished_at: null,
          elapsed_ms: 0,
          stage: 'preparing',
          summary: { chunk_count: 0, entity_count: 0, relation_count: 0 },
          stages: {
            total: { progress: 0, label: '准备开始处理' },
            chunking: { progress: 0, current: 0, total: 0, label: '等待开始' },
            extraction: {
              progress: extractGraph ? 0 : 100,
              processed_batches: 0,
              total_batches: 0,
              started_batches: 0,
              running_batches: 0,
              processed_chunks: 0,
              total_candidate_chunks: 0,
              entity_count: 0,
              relation_count: 0,
              label: extractGraph ? '等待开始' : '已跳过',
            },
          },
        }
      }
      processing.value[file.id] = 0
      startPolling(file.id)
    } catch {}
  }
}

async function syncFileStatus(fileId, timer = null) {
  try {
    const data = await getFileStatus(fileId)
    processing.value[fileId] = data.progress || 0
    const target = files.value.find(item => item.id === fileId)
    if (target) {
      target.progress = data.progress || 0
      target.message = data.message || target.message
      target.detail = data.detail || target.detail
      if (target.detail) syncStageTimers(fileId, target.detail)
      target.logs = Array.isArray(data.logs) ? data.logs : target.logs
      target.status = data.status || target.status
    }
    if (data.status === 'indexed' || data.status === 'failed') {
      if (timer) clearInterval(timer)
      if (pollTimers[fileId]) {
        clearInterval(pollTimers[fileId])
        delete pollTimers[fileId]
      }
      if (target && data.status === 'indexed') delete processing.value[fileId]
      return true
    }
  } catch {
    if (timer) clearInterval(timer)
    if (pollTimers[fileId]) {
      clearInterval(pollTimers[fileId])
      delete pollTimers[fileId]
    }
    return true
  }
  return false
}

function startPolling(fileId) {
  if (pollTimers[fileId]) clearInterval(pollTimers[fileId])
  processing.value[fileId] = processing.value[fileId] || 0
  const timer = setInterval(async () => {
    const done = await syncFileStatus(fileId, timer)
    if (done) return
  }, 300)
  pollTimers[fileId] = timer
  syncFileStatus(fileId, timer)
}

async function deleteFile(fileId) {
  const confirmed = await showConfirm(
    '删除文件',
    '确定要删除该文件吗？这将删除所有相关的分片、向量和图谱数据，且无法恢复。',
    '删除文件',
    '取消'
  )
  if (!confirmed) {
    return
  }
  if (pollTimers[fileId]) {
    clearInterval(pollTimers[fileId])
    delete pollTimers[fileId]
  }
  delete processing.value[fileId]
  // clean up stage timers for this file
  const cleaned = { ...stageTimers.value }
  for (const key of Object.keys(cleaned)) {
    if (key.startsWith(`${fileId}-`)) delete cleaned[key]
  }
  stageTimers.value = cleaned
  try {
    await apiDeleteFile(fileId)
  } catch {}
  files.value = files.value.filter(item => item.id !== fileId)
}

async function handleCancel(fileId) {
  const confirmed = await showConfirm(
    '取消处理',
    '确定要取消处理吗？这将删除已入库的分片、向量和图谱数据，但保留原文件。',
    '取消处理',
    '继续处理'
  )
  if (!confirmed) {
    return
  }
  if (pollTimers[fileId]) {
    clearInterval(pollTimers[fileId])
    delete pollTimers[fileId]
  }
  delete processing.value[fileId]
  // clean up stage timers for this file
  const cleaned = { ...stageTimers.value }
  for (const key of Object.keys(cleaned)) {
    if (key.startsWith(`${fileId}-`)) delete cleaned[key]
  }
  stageTimers.value = cleaned
  try {
    await cancelProcessing(fileId)
    // 刷新文件状态
    kb.value = await getKb(props.kbId)
    files.value = (kb.value.files || []).map(normalizeFile)
  } catch (e) {
    console.error('Cancel processing failed:', e)
  }
}

function getUploadProgress(id) {
  return uploading.value[id]?.progress || 0
}

function getElapsedLabel(file) {
  const _t = nowTick.value
  const detail = file.detail
  if (!detail?.started_at) return '--'
  const started = new Date(detail.started_at).getTime()
  const ended = detail.finished_at ? new Date(detail.finished_at).getTime() : _t
  const totalSeconds = Math.max(0, Math.floor((ended - started) / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

function getStageProgress(file, stageName) {
  return file.detail?.stages?.[stageName]?.progress || 0
}

function getStageLabel(file, stageName, fallback = '等待开始') {
  return file.detail?.stages?.[stageName]?.label || fallback
}

function getExtractionStats(file) {
  const extraction = file.detail?.stages?.extraction || {}
  return {
    batches: extraction.total_batches ? `${extraction.processed_batches}/${extraction.total_batches}` : '--',
    chunks: extraction.total_candidate_chunks ? `${extraction.processed_chunks}/${extraction.total_candidate_chunks}` : '--',
    entities: extraction.entity_count ?? 0,
    relations: extraction.relation_count ?? 0,
  }
}

function fmtDuration(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

function getStatusTitle(status) {
  const titles = {
    uploading: '上传中',
    uploaded: '等待处理',
    processing: '处理中',
    indexed: '已完成',
    failed: '处理失败'
  }
  return titles[status] || ''
}

function getStageTimeStr(file, stageName) {
  const _t = nowTick.value
  const stage = file.detail?.stages?.[stageName]
  if (!stage || stage.progress <= 0) return ''
  if (stageSkipped(file, stageName)) return ''

  // 对于 chunking 阶段，需要特殊处理：合并显示 chunking + vectorizing 的时间
  if (stageName === 'chunking') {
    const chunkingStage = file.detail?.stages?.chunking
    const vectorizingStage = file.detail?.stages?.vectorizing
    
    // 使用 chunking 的开始时间
    const startedAt = chunkingStage?.started_at
    if (!startedAt) return ''
    
    const started = new Date(startedAt).getTime()
    
    // 如果 vectorizing 还在进行中，使用当前时间；否则使用 vectorizing 的结束时间
    let ended
    if (vectorizingStage?.progress < 100) {
      ended = _t
    } else {
      ended = vectorizingStage?.finished_at ? new Date(vectorizingStage.finished_at).getTime() : _t
    }
    
    if (ended > started) return fmtDuration(ended - started)
    return ''
  }

  // 其他阶段使用正常逻辑
  if (stage.started_at) {
    const started = new Date(stage.started_at).getTime()
    const ended = stage.finished_at ? new Date(stage.finished_at).getTime() : _t
    if (ended > started) return fmtDuration(ended - started)
  }

  // 兜底：无后端时间戳时使用本地计时器
  const timer = stageTimers.value[`${file.id}-${stageName}`]
  const startTime = timer?.started
  if (!startTime) return ''
  const end = timer?.ended || _t
  return fmtDuration(Math.max(0, end - startTime))
}

function stageIcon(file, stageName) {
  const progress = getStageProgress(file, stageName)
  if (progress >= 100) return '✓'
  if (progress > 0) return '◉'
  return '○'
}

function stageSkipped(file, stageName) {
  // 只根据后端设置的 label 判断是否跳过
  const label = file.detail?.stages?.[stageName]?.label || ''
  return label.includes('跳过')
}

function stageIconClass(file, stageName) {
  const progress = getStageProgress(file, stageName)
  if (progress >= 100) return 'icon-done'
  if (progress > 0) return 'icon-active'
  return 'icon-pending'
}
</script>

<template>
  <div>
    <div class="page-head">
      <button class="back-btn" @click="router.push('/')">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="m15 18-6-6 6-6" />
        </svg>
      </button>
      <div class="head-title">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
          <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z" />
        </svg>
        <h1>{{ kb?.name || '加载中...' }}</h1>
      </div>
    </div>

    <div
      class="dropzone"
      @click="triggerUpload"
      @dragover.prevent="$event.currentTarget.classList.add('drag')"
      @dragleave="$event.currentTarget.classList.remove('drag')"
      @drop="handleFileDrop"
    >
      <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" class="dz-icon">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
        <polyline points="17 8 12 3 7 8" />
        <line x1="12" y1="3" x2="12" y2="15" />
      </svg>
      <div class="dz-title">拖拽或点击上传文件</div>
      <div class="dz-hint">TXT · PDF · Markdown · DOCX · CSV · JSON · HTML</div>
      <input id="fileInput" type="file" multiple accept=".txt,.pdf,.md,.csv,.json,.docx,.html" @change="handleFilePick" style="display:none">
    </div>

    <div class="sec-head">
      <span class="sec-title">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
        文件列表 · {{ files.length }}
      </span>
      <div class="batch-wrap" v-if="uploadedCount > 1">
        <button class="batch-btn" @click="batchProcess(true)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="13 2 3 14 12 14 19 8" />
            <polyline points="3 22 12 13 21 22" />
          </svg>
          批量处理 ({{ uploadedCount }})
        </button>
        <button class="batch-btn batch-fast" @click="batchProcess(false)" title="仅分片，不抽取图谱">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="5 12 10 17 19 8" />
          </svg>
          快速分片
        </button>
      </div>
    </div>

    <div class="file-list" v-if="files.length">
      <div class="file-card" v-for="file in files" :key="file.id">
        <div class="file-main">
          <div class="status-lamp" :class="file.status" :title="getStatusTitle(file.status)"></div>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" class="ft-icon">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
          <div class="file-info">
            <div class="file-name">{{ file.name }}</div>
            <div class="file-size">{{ fmtSize(file.size) }}</div>
          </div>

          <template v-if="uploading[file.id]">
            <div class="mini-bar"><div class="mini-fill" :style="{ width: `${getUploadProgress(file.id)}%` }"></div></div>
            <span class="tag tag-up">{{ getUploadProgress(file.id) }}%</span>
          </template>
          <template v-else-if="file.status === 'uploaded'">
            <button class="proc-btn" @click="openProcessDialog(file)">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="13 2 3 14 12 14 19 8" />
              </svg>
              处理
            </button>
          </template>
          <template v-else-if="file.status === 'processing'">
            <span class="tag tag-proc">处理中</span>
            <button class="cancel-btn" @click="handleCancel(file.id)" title="取消处理">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <line x1="9" y1="9" x2="15" y2="15" />
                <line x1="15" y1="9" x2="9" y2="15" />
              </svg>
            </button>
          </template>
          <template v-else>
            <button class="proc-btn proc-btn-retry" @click="openReprocessDialog(file)">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 12a9 9 0 1 1-2.64-6.36" />
                <polyline points="21 3 21 9 15 9" />
              </svg>
              重新处理
            </button>
            <span class="tag" :class="file.status === 'indexed' ? 'tag-ok' : 'tag-err'">
              {{ file.status === 'indexed' ? '已完成' : '失败' }}
            </span>
          </template>

          <button class="rm-btn" @click="deleteFile(file.id)" title="删除文件">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M3 6h18" />
              <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
              <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
              <line x1="10" y1="11" x2="10" y2="17" />
              <line x1="14" y1="11" x2="14" y2="17" />
            </svg>
          </button>
        </div>

        <div class="process-panel" v-if="file.status === 'processing' || file.status === 'indexed' || file.status === 'failed'">
          <div class="terminal">
            <div class="terminal-bar">
            <span class="terminal-title">
              {{ file.status === 'indexed' ? '处理完成' : (file.status === 'failed' ? '处理失败' : '处理中...') }}
              &mdash; {{ file.name }}
            </span>
            <span class="terminal-meta">
              <span class="terminal-pill" v-if="!stageSkipped(file, 'extraction')">{{ file.progress || 0 }}%</span>
              <span class="terminal-time-display" v-if="file.status === 'processing'">处理时间 {{ getElapsedLabel(file) }}</span>
            <span class="terminal-time-display done" v-else-if="file.status === 'indexed' || file.status === 'failed'">总耗时 {{ getElapsedLabel(file) }}</span>
              <span v-if="file.detail?.summary" class="terminal-pill">
                分片 {{ file.detail.summary.chunk_count || 0 }}
              </span>
              <span v-if="file.detail?.summary?.entity_count" class="terminal-pill">
                实体 {{ file.detail.summary.entity_count }}
              </span>
              <span v-if="file.detail?.summary?.relation_count" class="terminal-pill">
                关系 {{ file.detail.summary.relation_count }}
              </span>
            </span>
          </div>
            <div class="terminal-body stages-body">
              <!-- Overall progress - only show when extraction will run -->
              <div class="stage-row stage-overall" v-if="!stageSkipped(file, 'extraction')">
                <div class="stage-bar-wrap">
                  <div class="stage-bar-track stage-track--main">
                    <div class="stage-bar-fill stage-fill--main" :style="{ width: `${file.progress || 0}%` }"></div>
                  </div>
                  <span class="stage-pct stage-pct--main">{{ file.progress || 0 }}%</span>
                </div>
              </div>

              <!-- Chunking + Vectorizing combined stage -->
              <div class="stage-row" v-if="file.detail?.stages?.chunking">
                <div class="stage-head">
                  <span class="stage-icon" :class="stageIconClass(file, 'chunking')">{{ stageIcon(file, 'chunking') }}</span>
                  <span class="stage-label">分片与向量化</span>
                  <span class="stage-pct">{{ getStageProgress(file, 'chunking') }}%</span>
                  <span class="stage-time" v-if="getStageTimeStr(file, 'chunking')">{{ getStageTimeStr(file, 'chunking') }}</span>
                </div>
                <div class="stage-bar-wrap">
                  <div class="stage-bar-track stage-track--sub">
                    <div class="stage-bar-fill stage-fill--chunk" :style="{ width: `${getStageProgress(file, 'chunking')}%` }"></div>
                  </div>
                </div>
                <div class="stage-detail">
                  <template v-if="getStageProgress(file, 'chunking') >= 100">
                    共 {{ file.detail.stages.chunking.total || 0 }} 个分片，已全部写入向量库
                  </template>
                  <template v-else-if="getStageProgress(file, 'chunking') > 0">
                    分片 {{ file.detail.stages.chunking.current || 0 }}/{{ file.detail.stages.chunking.total || 0 }} · 已写入向量 {{ file.detail.stages.vectorizing?.current || file.detail.stages.chunking.current || 0 }}/{{ file.detail.stages.vectorizing?.total || file.detail.stages.chunking.total || 0 }}
                  </template>
                  <template v-else>等待中...</template>
                </div>
              </div>

              <!-- Extraction stage - only show when extraction will actually run -->
              <div class="stage-row" v-if="file.detail?.stages?.extraction && !stageSkipped(file, 'extraction')">
                <div class="stage-head">
                  <span class="stage-icon" :class="stageIconClass(file, 'extraction')">{{ stageIcon(file, 'extraction') }}</span>
                  <span class="stage-label">实体/关系抽取与生成图谱</span>
                  <span class="stage-pct">{{ getStageProgress(file, 'extraction') }}%</span>
                  <span class="stage-time" v-if="getStageTimeStr(file, 'extraction')">{{ getStageTimeStr(file, 'extraction') }}</span>
                </div>
                <div class="stage-bar-wrap">
                  <div class="stage-bar-track stage-track--sub">
                    <div class="stage-bar-fill stage-fill--extract" :style="{ width: `${getStageProgress(file, 'extraction')}%` }"></div>
                  </div>
                </div>
                <div class="stage-detail" v-if="getStageProgress(file, 'extraction') > 0 || file.detail.stages.extraction.entity_count">
                  <template v-if="getStageProgress(file, 'extraction') >= 100">
                    已抽取 {{ file.detail.stages.extraction.entity_count || 0 }} 个实体 · {{ file.detail.stages.extraction.relation_count || 0 }} 个关系
                  </template>
                  <template v-else>
                    <span v-if="file.detail.stages.extraction.total_batches">批次 {{ file.detail.stages.extraction.processed_batches }}/{{ file.detail.stages.extraction.total_batches }}</span>
                    <span v-if="file.detail.stages.extraction.started_batches"> · 已发起 {{ file.detail.stages.extraction.started_batches }}</span>
                    <span v-if="file.detail.stages.extraction.running_batches"> · 进行中 {{ file.detail.stages.extraction.running_batches }}</span>
                    <span v-if="file.detail.stages.extraction.total_candidate_chunks"> · 分片 {{ file.detail.stages.extraction.processed_chunks }}/{{ file.detail.stages.extraction.total_candidate_chunks }}</span>
                    <span v-if="file.detail.stages.extraction.entity_count"> · 实体 {{ file.detail.stages.extraction.entity_count }}</span>
                    <span v-if="file.detail.stages.extraction.relation_count"> · 关系 {{ file.detail.stages.extraction.relation_count }}</span>
                  </template>
                </div>
                <div class="stage-detail" v-else>等待中...</div>
              </div>

              <!-- Log stream (collapsed by default when processing) -->
              <details class="stage-logs" v-if="file.logs.length || file.status === 'failed'" open>
                <summary class="logs-toggle">终端日志 ({{ file.logs.length }})</summary>
                <div class="logs-body">
                  <div class="terminal-line" v-for="(log, index) in file.logs" :key="`${file.id}-${index}-${log.time}`">
                    <span class="term-prompt">$</span>
                    <span class="term-time">[{{ new Date(log.time).toLocaleTimeString() }}]</span>
                    <span class="term-level" :class="`level-${log.level}`">{{ log.level === 'error' ? 'ERR' : log.level === 'warning' ? 'WRN' : 'INF' }}</span>
                    <span class="term-msg">{{ log.message }}</span>
                  </div>
                  <!-- Error message in red when failed -->
                  <div class="terminal-line error-line" v-if="file.status === 'failed' && file.message">
                    <span class="term-prompt">$</span>
                    <span class="term-time">[{{ new Date().toLocaleTimeString() }}]</span>
                    <span class="term-level level-error">ERR</span>
                    <span class="term-msg error-msg">{{ file.message }}</span>
                  </div>
                </div>
              </details>
            </div>
          </div>
        </div>

      </div>
    </div>

    <div v-else class="empty-state">
      <div class="empty-icon">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
      </div>
      <div class="empty-title">暂无文件</div>
      <div class="empty-desc">上传文档开始使用</div>
    </div>

    <Teleport to="body">
      <div class="dialog-overlay" v-if="showProcessDialog" @click.self="showProcessDialog = false">
        <div class="dialog-card">
          <div class="dialog-head">
            <div class="dialog-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
                <polyline points="13 2 3 14 12 14 19 8" />
              </svg>
            </div>
            <div>
              <div class="dialog-title">选择处理模式</div>
              <div class="dialog-sub">{{ pendingFileName }}</div>
            </div>
          </div>
          <div class="dialog-body">
            <button class="mode-btn" @click="confirmProcess(true)">
              <div class="mode-icon">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                  <circle cx="6.5" cy="6.5" r="2.25" />
                  <circle cx="17.5" cy="6.5" r="2.25" />
                  <circle cx="12" cy="17.5" r="2.25" />
                  <path d="M8.75 6.5h6.5" />
                  <path d="M8.2 8.1 10.3 15.2" />
                  <path d="m15.8 8.1-2.1 7.1" />
                </svg>
              </div>
              <div class="mode-text">
                <strong>{{ pendingProcessMode === 'reprocess' ? '重新分片 + 抽取图谱' : '分片 + 抽取图谱' }}</strong>
                <span>切分文本、生成向量，并调用 LLM 抽取实体与关系写入图数据库</span>
              </div>
              <span class="mode-arrow">&rarr;</span>
            </button>
            <button class="mode-btn mode-simple" @click="confirmProcess(false)">
              <div class="mode-icon">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                </svg>
              </div>
              <div class="mode-text">
                <strong>{{ pendingProcessMode === 'reprocess' ? '重新分片（更快）' : '仅分片（更快）' }}</strong>
                <span>只切分文本并生成向量，不调用 LLM，速度更快</span>
              </div>
              <span class="mode-arrow">&rarr;</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Confirm Dialog -->
      <div class="dialog-overlay" v-if="showConfirmDialog" @click.self="confirmDialogCancel">
        <div class="dialog-card confirm-card">
          <div class="confirm-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </div>
          <div class="confirm-title">{{ confirmDialogTitle }}</div>
          <div class="confirm-message">{{ confirmDialogMessage }}</div>
          <div class="confirm-actions">
            <button class="confirm-btn cancel" @click="confirmDialogCancel">{{ confirmDialogCancelText }}</button>
            <button class="confirm-btn ok" @click="confirmDialogOk">{{ confirmDialogConfirmText }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.page-head { display: flex; align-items: center; gap: 8px; margin-bottom: 20px; }
.back-btn { background: none; border: none; cursor: pointer; color: var(--c-secondary); padding: 4px; border-radius: 6px; display: flex; transition: all 150ms; }
.back-btn:hover { color: var(--c-fg); background: var(--c-muted); }
.head-title { display: flex; align-items: center; gap: 8px; color: var(--c-fg); }
h1 { font-size: 18px; font-weight: 700; }

.dropzone {
  border: 2px dashed var(--c-border);
  border-radius: 16px;
  padding: 28px;
  text-align: center;
  cursor: pointer;
  background: var(--c-muted);
  transition: border-color 150ms, background 150ms;
  margin-bottom: 20px;
}
.dropzone:hover, .dropzone.drag { border-color: var(--c-fg); background: var(--c-muted-hover); }
.dz-icon { color: var(--c-secondary); margin-bottom: 8px; }
.dz-title { font-size: 14px; font-weight: 600; }
.dz-hint { font-size: 12px; color: var(--c-secondary); margin-top: 4px; }

.sec-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.sec-title { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700; color: var(--c-secondary); text-transform: uppercase; letter-spacing: 0.5px; flex: 1; }
.batch-wrap { display: flex; gap: 6px; }
.batch-btn { display: inline-flex; align-items: center; gap: 5px; padding: 4px 12px; font-size: 11px; font-weight: 600; border-radius: 6px; border: 1px solid #6366f1; background: transparent; color: #6366f1; cursor: pointer; transition: all 150ms; }
.batch-btn:hover { background: #6366f1; color: #fff; }
.batch-btn.batch-fast { border-color: #64748b; color: #64748b; }
.batch-btn.batch-fast:hover { background: #64748b; color: #fff; }

.file-list { display: flex; flex-direction: column; gap: 10px; }
.file-card { border-radius: 18px; border: 1px solid var(--c-border); background: var(--c-panel); overflow: hidden; }
.file-main { display: flex; align-items: center; gap: 10px; padding: 10px 14px; }
/* === 3D效果状态灯 === */
.status-lamp {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  flex-shrink: 0;
  cursor: help;
  position: relative;
  background: linear-gradient(135deg, #3a3a3a 0%, #1a1a1a 100%);
  box-shadow: 
    0 2px 4px rgba(0, 0, 0, 0.4),
    inset 0 1px 2px rgba(255, 255, 255, 0.1);
  transition: all 0.3s ease;
}

.status-lamp::before {
  content: '';
  position: absolute;
  top: 3px;
  left: 3px;
  right: 3px;
  bottom: 3px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(255,255,255,0.2) 0%, transparent 50%);
  pointer-events: none;
}

/* 处理中/上传中 - 绿灯呼吸效果 */
.status-lamp.processing,
.status-lamp.uploading {
  background: linear-gradient(135deg, #86efac 0%, #4ade80 30%, #22c55e 70%, #16a34a 100%);
  box-shadow: 
    0 0 0 2px rgba(74, 222, 128, 0.15),
    0 0 15px rgba(74, 222, 128, 0.4),
    0 0 30px rgba(74, 222, 128, 0.2),
    0 0 50px rgba(74, 222, 128, 0.1),
    0 3px 6px rgba(0, 0, 0, 0.3);
  animation: lamp-breathe-green 3s ease-in-out infinite;
}

/* 已完成 - 绿灯常亮 */
.status-lamp.indexed {
  background: linear-gradient(135deg, #6ee7b7 0%, #34d399 50%, #10b981 100%);
  box-shadow: 
    0 0 0 2px rgba(74, 222, 128, 0.2),
    0 0 15px rgba(74, 222, 128, 0.5),
    0 3px 6px rgba(0, 0, 0, 0.3);
}

/* 失败 - 红灯快速闪烁 */
.status-lamp.failed {
  background: linear-gradient(135deg, #fca5a5 0%, #f87171 50%, #ef4444 100%);
  box-shadow: 
    0 0 0 3px rgba(248, 113, 113, 0.3),
    0 0 25px rgba(248, 113, 113, 0.8),
    0 0 50px rgba(248, 113, 113, 0.4),
    0 4px 8px rgba(0, 0, 0, 0.3);
  animation: lamp-blink-red 0.4s ease-in-out infinite;
}

/* 等待处理 - 黄灯微弱常亮 */
.status-lamp.uploaded {
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 50%, #fbbf24 100%);
  box-shadow: 
    0 0 0 2px rgba(251, 191, 36, 0.2),
    0 0 10px rgba(251, 191, 36, 0.4),
    0 3px 6px rgba(0, 0, 0, 0.3);
  opacity: 0.7;
}

@keyframes lamp-breathe-green {
  0%, 100% { 
    box-shadow: 
      0 0 0 1px rgba(74, 222, 128, 0.1),
      0 0 10px rgba(74, 222, 128, 0.25),
      0 0 25px rgba(74, 222, 128, 0.15),
      0 0 45px rgba(74, 222, 128, 0.08),
      0 3px 6px rgba(0, 0, 0, 0.3);
    transform: scale(0.98);
    opacity: 0.75;
  }
  50% { 
    box-shadow: 
      0 0 0 4px rgba(74, 222, 128, 0.3),
      0 0 20px rgba(74, 222, 128, 0.6),
      0 0 45px rgba(74, 222, 128, 0.35),
      0 0 75px rgba(74, 222, 128, 0.15),
      0 0 100px rgba(74, 222, 128, 0.08),
      0 4px 8px rgba(0, 0, 0, 0.35);
    transform: scale(1.08);
    opacity: 1;
  }
}

@keyframes lamp-blink-red {
  0%, 100% { 
    box-shadow: 
      0 0 0 3px rgba(248, 113, 113, 0.3),
      0 0 25px rgba(248, 113, 113, 0.8),
      0 0 50px rgba(248, 113, 113, 0.4),
      0 4px 8px rgba(0, 0, 0, 0.3);
    opacity: 1;
  }
  50% { 
    box-shadow: 
      0 0 0 1px rgba(248, 113, 113, 0.1),
      0 0 8px rgba(248, 113, 113, 0.3),
      0 0 15px rgba(248, 113, 113, 0.15),
      0 2px 4px rgba(0, 0, 0, 0.2);
    opacity: 0.4;
  }
}
@keyframes breathe-green {
  0%, 100% { opacity: 0.4; box-shadow: 0 0 4px rgba(74, 222, 128, 0.3); }
  50% { opacity: 1; box-shadow: 0 0 14px rgba(74, 222, 128, 0.9); }
}
@keyframes blink-red {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.2; }
}
@keyframes breathe-blue {
  0%, 100% { opacity: 0.4; box-shadow: 0 0 4px rgba(96, 165, 250, 0.3); }
  50% { opacity: 1; box-shadow: 0 0 14px rgba(96, 165, 250, 0.9); }
}

/* === 方案一回退代码备份 === */
/* 
.status-light {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-light.processing {
  background: #4ADE80;
  box-shadow: 0 0 8px rgba(74, 222, 128, 0.5);
  animation: breathe-green 2s ease-in-out infinite;
}
.status-light.indexed {
  background: #4ADE80;
  box-shadow: 0 0 6px rgba(74, 222, 128, 0.4);
}
.status-light.failed {
  background: #F87171;
  box-shadow: 0 0 8px rgba(248, 113, 113, 0.5);
  animation: blink-red 0.5s ease-in-out infinite;
}
.status-light.uploading {
  background: #60A5FA;
  box-shadow: 0 0 8px rgba(96, 165, 250, 0.5);
  animation: breathe-blue 2s ease-in-out infinite;
}
.status-light.uploaded {
  background: #FBBF24;
  box-shadow: 0 0 6px rgba(251, 191, 36, 0.4);
}
*/
.ft-icon { color: var(--c-secondary); flex-shrink: 0; }
.file-info { flex: 1; min-width: 0; }
.file-name { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.file-size { font-size: 11px; color: var(--c-secondary); }

.mini-bar { width: 52px; height: 3px; background: var(--c-border); border-radius: 999px; overflow: hidden; flex-shrink: 0; }
.mini-fill { height: 100%; background: var(--c-fg); border-radius: 999px; transition: width 220ms ease; }

.tag { font-size: 11px; font-weight: 600; flex-shrink: 0; }
.tag-up { color: var(--c-accent); }
.tag-proc { color: #6366f1; }
.tag-ok { color: var(--c-success); }
.tag-err { color: var(--c-danger); }

.proc-btn { display: inline-flex; align-items: center; gap: 4px; padding: 4px 12px; font-size: 11px; font-weight: 600; border-radius: 6px; border: 1px solid #6366f1; background: transparent; color: #6366f1; cursor: pointer; transition: all 150ms; }
.proc-btn:hover { background: #6366f1; color: #fff; }
.proc-btn-retry { border-color: #64748b; color: #64748b; }
.proc-btn-retry:hover { background: #64748b; color: #fff; }

.rm-btn, .cancel-btn { 
  background: none; 
  border: 1px solid #ef4444; 
  cursor: pointer; 
  color: #ef4444; 
  padding: 4px 8px; 
  border-radius: 4px; 
  display: flex; 
  align-items: center; 
  justify-content: center; 
  transition: all 150ms; 
  flex-shrink: 0; 
}
.rm-btn:hover, .cancel-btn:hover { 
  background: #ef4444; 
  color: #fff; 
}

.process-panel {
  padding: 0 14px 14px 44px;
}

.terminal {
  border-radius: 14px;
  overflow: hidden;
  background: #0d1117;
  border: 1px solid #21262d;
  box-shadow: 0 4px 24px rgba(0,0,0,0.3);
}

.terminal-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #161b22;
  border-bottom: 1px solid #21262d;
}

.terminal-time-display {
  padding: 2px 8px;
  font-size: 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: #58a6ff;
  background: rgba(88,166,255,0.1);
  border-radius: 4px;
  flex-shrink: 0;
}

.terminal-time-display.done {
  color: #3fb950;
  background: rgba(63,185,80,0.1);
}

.terminal-title {
  flex: 1;
  font-size: 11px;
  color: #8b949e;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.terminal-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  flex-shrink: 0;
}

.terminal-pill {
  padding: 2px 8px;
  font-size: 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: #8b949e;
  background: #21262d;
  border-radius: 4px;
}

.terminal-body.stages-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}

/* ---- stage rows ---- */
.stage-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stage-overall {
  margin-bottom: 2px;
}

.stage-head {
  display: flex;
  align-items: center;
  gap: 6px;
}

.stage-icon {
  width: 16px;
  height: 16px;
  font-size: 12px;
  text-align: center;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stage-icon.icon-done { 
  color: #3fb950; 
}
.stage-icon.icon-active { 
  color: #4ade80; 
  animation: pulse-glow-green 1.5s ease-in-out infinite;
}
.stage-icon.icon-pending { color: #484f58; }

@keyframes pulse-glow-green {
  0%, 100% { 
    text-shadow: 0 0 2px rgba(74, 222, 128, 0.2); 
    opacity: 0.3;
  }
  50% { 
    text-shadow: 0 0 15px rgba(74, 222, 128, 1), 0 0 30px rgba(74, 222, 128, 0.6), 0 0 50px rgba(74, 222, 128, 0.3); 
    opacity: 1;
  }
}

.stage-label {
  font-size: 12px;
  font-weight: 600;
  color: #c9d1d9;
  flex: 1;
}

.stage-pct {
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: #8b949e;
  flex-shrink: 0;
  min-width: 32px;
  text-align: right;
}

.stage-pct--main {
  font-size: 13px;
  font-weight: 700;
  color: #c9d1d9;
}

.stage-time {
  font-size: 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: #8b949e;
  flex-shrink: 0;
}

/* ---- stage progress bars ---- */
.stage-bar-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.stage-bar-track {
  flex: 1;
  height: 4px;
  background: #21262d;
  border-radius: 999px;
  overflow: hidden;
}

.stage-track--main {
  height: 6px;
}

.stage-track--sub {
  height: 3px;
}

.stage-bar-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 400ms ease;
}

.stage-fill--main {
  background: linear-gradient(90deg, #3fb950, #58a6ff);
}

.stage-fill--chunk {
  background: #3fb950;
}

.stage-fill--extract {
  background: linear-gradient(90deg, #58a6ff, #a371f7);
}

/* ---- stage detail ---- */
.stage-detail {
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: #8b949e;
  padding-left: 22px;
}

/* ---- collapsible logs ---- */
.stage-logs {
  margin-top: 4px;
  border-top: 1px solid #21262d;
  padding-top: 10px;
}

.logs-toggle {
  font-size: 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: #484f58;
  cursor: pointer;
  user-select: none;
}

.logs-toggle:hover { color: #8b949e; }

.logs-body {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-height: 200px;
  overflow: auto;
}

/* ---- keep old terminal-log styles ---- */

.terminal-line {
  display: flex;
  gap: 8px;
  align-items: baseline;
}

.term-prompt {
  color: #3fb950;
  flex-shrink: 0;
  font-weight: 700;
}

.term-prompt.blink {
  animation: term-blink 1s step-end infinite;
}

@keyframes term-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.term-time {
  color: #484f58;
  flex-shrink: 0;
}

.term-level {
  flex-shrink: 0;
  font-weight: 700;
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 3px;
  color: #58a6ff;
  background: rgba(88,166,255,0.12);
}

.term-level.level-error {
  color: #f85149;
  background: rgba(248,81,73,0.12);
}

.term-level.level-warning {
  color: #d29922;
  background: rgba(210,153,34,0.12);
}

.term-msg {
  color: #c9d1d9;
  word-break: break-word;
}

.term-msg.dim {
  color: #8b949e;
}

.term-msg.error-msg {
  color: #f85149;
  font-weight: 600;
}

/* Dialog */
.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,0.55);
  backdrop-filter: blur(4px);
}

.dialog-card {
  width: 440px;
  max-width: 92vw;
  background: var(--c-panel);
  border: 1px solid var(--c-border);
  border-radius: 20px;
  box-shadow: 0 24px 60px rgba(0,0,0,0.25);
  overflow: hidden;
}

.dialog-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 20px;
  border-bottom: 1px solid var(--c-border);
}

.dialog-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: var(--c-muted);
  color: #6366f1;
  flex-shrink: 0;
}

.dialog-title {
  font-size: 15px;
  font-weight: 700;
}

.dialog-sub {
  font-size: 12px;
  color: var(--c-secondary);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 280px;
}

.dialog-body {
  padding: 14px 20px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mode-btn {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 14px 16px;
  border: 1px solid var(--c-border);
  border-radius: 14px;
  background: var(--c-muted);
  cursor: pointer;
  text-align: left;
  transition: all 150ms;
  color: var(--c-fg);
}

.mode-btn:hover {
  border-color: #6366f1;
  background: rgba(99,102,241,0.06);
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(99,102,241,0.12);
}

.mode-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: rgba(99,102,241,0.1);
  color: #6366f1;
  flex-shrink: 0;
}

.mode-simple .mode-icon {
  background: rgba(100,116,139,0.1);
  color: #64748b;
}

.mode-text {
  flex: 1;
  min-width: 0;
}

.mode-text strong {
  display: block;
  font-size: 13px;
  font-weight: 700;
}

.mode-text span {
  display: block;
  font-size: 11px;
  color: var(--c-secondary);
  margin-top: 3px;
  line-height: 1.4;
}

.mode-arrow {
  font-size: 18px;
  color: var(--c-secondary);
  flex-shrink: 0;
}

.file-sub.err {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 14px 14px 44px;
  color: var(--c-danger);
  font-size: 11px;
}

@media (max-width: 820px) {
  .process-panel {
    padding-left: 14px;
  }

  .terminal-meta {
    display: none;
  }

  .terminal-line {
    flex-wrap: wrap;
    gap: 4px;
  }
}

/* Confirm Dialog */
.confirm-card {
  width: 360px;
  max-width: 90vw;
  padding: 24px;
  text-align: center;
}

.confirm-icon {
  width: 56px;
  height: 56px;
  margin: 0 auto 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgba(239,68,68,0.1);
  color: #ef4444;
}

.confirm-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--c-fg);
  margin-bottom: 8px;
}

.confirm-message {
  font-size: 13px;
  color: var(--c-secondary);
  line-height: 1.5;
  margin-bottom: 20px;
}

.confirm-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
}

.confirm-btn {
  padding: 10px 24px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 150ms;
  border: none;
}

.confirm-btn.cancel {
  background: var(--c-muted);
  color: var(--c-secondary);
}

.confirm-btn.cancel:hover {
  background: var(--c-border);
  color: var(--c-fg);
}

.confirm-btn.ok {
  background: #ef4444;
  color: #fff;
}

.confirm-btn.ok:hover {
  background: #dc2626;
}
</style>
