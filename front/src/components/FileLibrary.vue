<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import FolderTreeNode from './FolderTreeNode.vue'
import {
  attachAssetsToKb,
  createCrawlJob,
  createDirectory,
  deleteDirectory,
  updateDirectory,
  deleteAsset as apiDeleteAsset,
  fetchAssetContent,
  fetchAssets,
  fetchDirectories,
  fetchKbs,
  getAssetPreviewUrl,
  getCrawlJob,
  getLatestCrawlJob,
  uploadAssetChunk,
} from '../api'

const CHUNK_SIZE = 512 * 1024
const uuid = () => ([1e7] + -1e3 + -4e3 + -8e3 + -1e11).replace(
  /[018]/g,
  c => (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16),
)

const directories = ref([])
const assets = ref([])
const kbs = ref([])
const selectedDirectoryId = ref('')
const expandedDirectories = ref(new Set(['']))
const search = ref('')
const uploading = ref({})
const selectedAssets = ref(new Set())
const selectedKbId = ref('')

// 文件夹编辑相关状态
const showFolderModal = ref(false)
const folderModalMode = ref('create')
const editingFolderId = ref('')
const editingFolderName = ref('')
const processingFolder = ref(false)

// 确认对话框
const showConfirmDialog = ref(false)
const confirmDialogTitle = ref('')
const confirmDialogMessage = ref('')
const confirmDialogConfirmText = ref('确定')
const confirmDialogCancelText = ref('取消')
let confirmDialogCallback = null

// 采集相关
const crawlKeyword = ref('')
const crawlMaxPages = ref(5)
const crawlDepth = ref('medium')
const crawlJob = ref(null)

// 预览相关
const previewAsset = ref(null)
const previewText = ref('')
const previewLoading = ref(false)

let crawlTimer = null

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

// 构建文件夹树
const directoryTree = computed(() => {
  const children = new Map()
  for (const item of directories.value) {
    const key = item.parent_id || ''
    if (!children.has(key)) children.set(key, [])
    children.get(key).push(item)
  }
  const build = (parentId) => {
    return (children.get(parentId) || []).map(item => ({
      ...item,
      children: build(item.id)
    }))
  }
  return build('')
})

const selectedCount = computed(() => selectedAssets.value.size)
const readyAssets = computed(() => assets.value.filter(item => item.status === 'ready'))

function fmtSize(value = 0) {
  if (value < 1024) return `${value} B`
  if (value < 1048576) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1048576).toFixed(1)} MB`
}

function sourceLabel(source) {
  return { upload: '上传', kb_upload: '知识库上传', crawl: '网络采集', legacy: '历史文件' }[source] || source || '未知'
}

async function loadDirectories() {
  try { directories.value = await fetchDirectories() } catch {}
}

async function loadAssets() {
  try {
    assets.value = await fetchAssets({ directoryId: selectedDirectoryId.value, q: search.value })
    const ids = new Set(assets.value.map(item => item.id))
    selectedAssets.value = new Set([...selectedAssets.value].filter(id => ids.has(id)))
  } catch {}
}

async function loadKbs() {
  try { kbs.value = await fetchKbs() } catch {}
}

async function refreshAll() {
  await Promise.all([loadDirectories(), loadAssets(), loadKbs()])
}

function toggleDirectory(directoryId) {
  const next = new Set(expandedDirectories.value)
  if (next.has(directoryId)) {
    next.delete(directoryId)
  } else {
    next.add(directoryId)
  }
  expandedDirectories.value = next
}

function selectDirectory(id) {
  selectedDirectoryId.value = id
  loadAssets()
}

// 文件夹操作
function openCreateFolder() {
  folderModalMode.value = 'create'
  editingFolderId.value = ''
  editingFolderName.value = ''
  showFolderModal.value = true
}

function openEditFolder(folder) {
  folderModalMode.value = 'edit'
  editingFolderId.value = folder.id
  editingFolderName.value = folder.name
  showFolderModal.value = true
}

async function saveFolder() {
  const name = editingFolderName.value.trim()
  if (!name || processingFolder.value) return
  processingFolder.value = true
  try {
    if (folderModalMode.value === 'create') {
      await createDirectory({ name, parentId: selectedDirectoryId.value || null })
    } else {
      await updateDirectory(editingFolderId.value, { name })
    }
    showFolderModal.value = false
    await loadDirectories()
  } catch {
    window.alert('文件夹操作失败')
  }
  processingFolder.value = false
}

async function deleteFolder(folder) {
  const confirmed = await showConfirm(
    '删除文件夹',
    `确定要删除文件夹「${folder.name}」吗？`,
    '删除',
    '取消'
  )
  if (!confirmed) return
  try {
    await deleteDirectory(folder.id)
    if (selectedDirectoryId.value === folder.id) {
      selectedDirectoryId.value = ''
    }
    await loadDirectories()
    await loadAssets()
  } catch {
    window.alert('删除文件夹失败')
  }
}

// 文件操作
function triggerUpload() {
  const el = document.getElementById('assetFileInput')
  if (el) el.click()
}

async function handlePick(event) {
  await uploadFiles(event.target.files)
  event.target.value = ''
}

async function uploadFiles(fileList) {
  for (const file of fileList) {
    const assetId = uuid()
    uploading.value = { ...uploading.value, [assetId]: { name: file.name, progress: 0 } }
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE) || 1
    try {
      for (let index = 0; index < totalChunks; index += 1) {
        const chunk = file.slice(index * CHUNK_SIZE, (index + 1) * CHUNK_SIZE)
        await uploadAssetChunk({
          assetId,
          fileName: file.name,
          fileSize: file.size,
          directoryId: selectedDirectoryId.value || null,
          chunkIndex: index,
          totalChunks,
          chunk,
        })
        uploading.value = {
          ...uploading.value,
          [assetId]: { ...uploading.value[assetId], progress: Math.round(((index + 1) / totalChunks) * 100) }
        }
      }
    } catch {
      // upload failed
    }
    const next = { ...uploading.value }
    delete next[assetId]
    uploading.value = next
    await loadAssets()
  }
}

async function deleteAsset(asset) {
  const confirmed = await showConfirm(
    '删除文件',
    `确认要删除「${asset.name}」吗？`,
    '删除',
    '取消'
  )
  if (!confirmed) return
  try {
    await apiDeleteAsset(asset.id)
  } catch {
    window.alert('删除文件失败')
  }
  await loadAssets()
}

async function openPreview(asset) {
  previewAsset.value = asset
  previewLoading.value = true
  try {
    if (asset.ext !== 'pdf') {
      previewText.value = await fetchAssetContent(asset.id)
    }
  } catch {
    previewText.value = ''
  }
  previewLoading.value = false
}

function toggleAssetSelection(id) {
  const next = new Set(selectedAssets.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedAssets.value = next
}

async function attachSelected() {
  if (!selectedKbId.value || selectedCount.value === 0) return
  try {
    await attachAssetsToKb(selectedKbId.value, [...selectedAssets.value])
    window.alert(`已添加 ${selectedCount.value} 个文件`)
    selectedAssets.value = new Set()
  } catch {
    window.alert('添加失败')
  }
}

// 采集相关
async function startCrawl() {
  if (!crawlKeyword.value.trim()) return
  try {
    const job = await createCrawlJob({
      keyword: crawlKeyword.value.trim(),
      directoryId: selectedDirectoryId.value || null,
      maxPages: crawlMaxPages.value,
      analysisDepth: crawlDepth.value,
    })
    crawlJob.value = job
    startCrawlPolling()
  } catch {
    window.alert('创建采集任务失败')
  }
}

function startCrawlPolling() {
  if (crawlTimer) clearInterval(crawlTimer)
  crawlTimer = setInterval(async () => {
    if (!crawlJob.value) return
    try {
      const job = await getCrawlJob(crawlJob.value.id)
      crawlJob.value = job
      if (job.status === 'completed' || job.status === 'failed') {
        clearInterval(crawlTimer)
        crawlTimer = null
        await loadAssets()
      }
    } catch {}
  }, 1500)
}

async function restoreCrawlJob() {
  try {
    const job = await getLatestCrawlJob()
    if (job && (job.status === 'pending' || job.status === 'running' || job.status === 'queued')) {
      crawlJob.value = job
      startCrawlPolling()
    }
  } catch {}
}

onMounted(async () => {
  await refreshAll()
  await restoreCrawlJob()
})

onUnmounted(() => {
  if (crawlTimer) clearInterval(crawlTimer)
})
</script>

<template>
  <div class="library-page">
    <div class="library-toolbar">
      <div class="search-wrap">
        <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
        <input type="text" v-model="search" placeholder="搜索文件、来源、摘要..." @input="loadAssets">
      </div>
      <button class="icon-btn refresh-btn" @click="refreshAll" title="刷新">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 21h5v-5"/></svg>
      </button>
      <button class="btn primary" @click="triggerUpload">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        上传
      </button>
      <input type="file" id="assetFileInput" multiple style="display: none" @change="handlePick">
    </div>

    <div class="library-layout">
      <!-- 左侧文件夹树 -->
      <aside class="folder-panel">
        <div class="folder-tree-header">
          <span class="tree-title">文件夹</span>
          <button class="tree-action-btn" @click="openCreateFolder" title="新建文件夹">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 20V4"/>
              <path d="M4 12h16"/>
            </svg>
          </button>
        </div>
        <div class="folder-tree">
          <div
            :class="['tree-root-item', { active: selectedDirectoryId === '' }]"
            @click="selectDirectory('')"
          >
            <svg class="folder-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            <span class="folder-name">全部文件</span>
          </div>
          
          <FolderTreeNode
            v-for="node in directoryTree"
            :key="node.id"
            :node="node"
            :expanded="expandedDirectories"
            :selected-id="selectedDirectoryId"
            @toggle="toggleDirectory"
            @select="selectDirectory"
            @edit="openEditFolder"
            @delete="deleteFolder"
          />
        </div>
      </aside>

      <!-- 右侧文件列表 -->
      <main class="asset-panel">
        <!-- 采集区域 -->
        <div class="crawl-band">
          <div class="crawl-fields">
            <input type="text" v-model="crawlKeyword" placeholder="输入关键词联网采集资料">
            <input type="number" class="small-input" v-model.number="crawlMaxPages" :min="1" placeholder="页数">
            <select v-model="crawlDepth" class="depth-select">
              <option value="low">分析维度：低</option>
              <option value="medium">分析维度：中</option>
              <option value="high">分析维度：高</option>
            </select>
            <button class="btn primary crawl-btn" @click="startCrawl" :disabled="!crawlKeyword.trim()">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>
              开始采集
            </button>
          </div>
          <div class="crawl-hint">
            <span class="hint-item">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
              页数：要采集的网页数量
            </span>
            <span class="hint-item">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              分析维度：越高分析越详细，内容越多
            </span>
          </div>
          <div v-if="crawlJob" class="crawl-status">
            <span class="status-dot" :class="crawlJob.status === 'running' ? 'running' : (crawlJob.status === 'completed' ? 'done' : 'failed')"></span>
            <span>{{ crawlJob.keyword }} · {{ crawlJob.status === 'running' ? '采集中' : (crawlJob.status === 'completed' ? '完成' : '失败') }}</span>
            <span v-if="crawlJob.status === 'running' && crawlJob.progress != null">{{ crawlJob.progress }}%</span>
            <div v-if="crawlJob.status === 'running' && crawlJob.progress != null" class="crawl-progress">
              <div :style="{ width: `${crawlJob.progress}%` }"></div>
            </div>
            <div v-if="crawlJob.status === 'failed' && crawlJob.message" class="crawl-error">
              {{ crawlJob.message }}
            </div>
          </div>
        </div>

        <!-- 上传进度 -->
        <div v-if="Object.keys(uploading).length > 0" class="uploading-list">
          <div v-for="([assetId, upload], index) in Object.entries(uploading)" :key="assetId" class="uploading-item">
            <span>{{ upload.name }}</span>
            <div class="mini-bar"><div class="mini-fill" :style="{ width: `${upload.progress}%` }"></div></div>
            <span>{{ upload.progress }}%</span>
          </div>
        </div>

        <!-- 批量操作区域 -->
        <div v-if="selectedCount > 0" class="attach-bar">
          <span>已选 {{ selectedCount }} 个文件</span>
          <select v-model="selectedKbId">
            <option value="">选择知识库...</option>
            <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
          </select>
          <button class="btn primary" @click="attachSelected" :disabled="!selectedKbId">添加到知识库</button>
        </div>

        <!-- 文件列表 -->
        <div class="asset-table">
          <div class="table-head">
            <div></div>
            <div>文件</div>
            <div>来源</div>
            <div>知识库</div>
            <div>操作</div>
          </div>
          <div v-if="assets.length > 0">
            <div v-for="asset in assets" :key="asset.id" :class="['asset-row', { selected: selectedAssets.has(asset.id) }]">
              <button class="check-btn" @click.stop="toggleAssetSelection(asset.id)" :disabled="asset.status !== 'ready'">
                {{ selectedAssets.has(asset.id) ? '✓' : '' }}
              </button>
              <div class="asset-main" @click="openPreview(asset)">
                <div class="asset-name">{{ asset.name }}</div>
                <div class="asset-meta">
                  <span>{{ fmtSize(asset.size) }}</span>
                  <span v-if="asset.ext">{{ asset.ext.toUpperCase() }}</span>
                  <span>{{ asset.status }}</span>
                </div>
                <div class="asset-summary" v-if="asset.summary">{{ asset.summary }}</div>
              </div>
              <div class="asset-source">
                <span class="source-chip">{{ sourceLabel(asset.source_type) }}</span>
                <a v-if="asset.source_url" :href="asset.source_url" target="_blank" rel="noreferrer">来源</a>
              </div>
              <div class="asset-kb">{{ asset.kb_file_count || 0 }}</div>
              <div class="asset-actions">
                <button class="icon-btn" title="预览" @click="openPreview(asset)">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
                </button>
                <button class="rm-btn" title="删除" @click="deleteAsset(asset)">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/></svg>
                </button>
              </div>
            </div>
          </div>
          <div v-else class="empty-state">
            <div class="empty-title">暂无文件</div>
            <div class="empty-desc">上传或采集后会出现在这里</div>
          </div>
        </div>
      </main>
    </div>

    <!-- 文件夹编辑弹窗 -->
    <div class="modal-mask" v-if="showFolderModal" @click.self="showFolderModal = false">
      <div class="create-dir-modal" @click.stop>
        <h3>{{ folderModalMode === 'create' ? '新建文件夹' : '编辑文件夹' }}</h3>
        <div class="field">
          <label>名称</label>
          <input
            v-model="editingFolderName"
            type="text"
            placeholder="例如：项目文档"
            autofocus
            @keydown.enter="saveFolder"
          >
        </div>
        <div class="actions">
          <button class="btn" @click="showFolderModal = false">取消</button>
          <button class="btn primary" :disabled="!editingFolderName.trim() || processingFolder" @click="saveFolder">
            {{ processingFolder ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 预览弹窗 -->
    <div class="modal-mask" v-if="previewAsset" @click.self="previewAsset = null">
      <div class="preview-modal">
        <div class="preview-head">
          <div>
            <div class="preview-title">{{ previewAsset.name }}</div>
            <div class="preview-sub">{{ sourceLabel(previewAsset.source_type) }} · {{ fmtSize(previewAsset.size) }}</div>
          </div>
          <button class="icon-btn" @click="previewAsset = null">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
          </button>
        </div>
        <div class="preview-body">
          <div v-if="previewLoading" class="empty-state">加载中...</div>
          <iframe v-else-if="previewAsset.ext === 'pdf'" :src="getAssetPreviewUrl(previewAsset.id)" class="pdf-frame"></iframe>
          <pre v-else class="preview-text">{{ previewText || '当前格式暂不支持文本预览' }}</pre>
        </div>
      </div>
    </div>

    <!-- 确认对话框 -->
    <div class="modal-mask" v-if="showConfirmDialog" @click.self="confirmDialogCancel">
      <div class="modal confirm-modal" @click.stop>
        <div class="confirm-icon warning">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2L2 20h20L12 2zm0 15l-.5-6h1l-.5 6zm0-8l-.5-3h1l-.5 3z"/>
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
  </div>
</template>

<style scoped>
.library-page { display: flex; flex-direction: column; gap: 16px; }
.library-toolbar { display: flex; gap: 10px; align-items: center; }
.search-wrap { flex: 1; position: relative; }
.search-icon { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); color: var(--c-secondary); }
.search-wrap input { padding-left: 34px; }
.icon-btn { background: none; border: none; cursor: pointer; color: var(--c-secondary); padding: 7px; border-radius: 6px; display: inline-flex; align-items: center; justify-content: center; }
.icon-btn:hover { color: var(--c-fg); background: var(--c-muted); }
.icon-btn.danger:hover { color: var(--c-danger); background: rgba(239, 68, 68, 0.08); }
.rm-btn { background: #ef4444; color: #fff; cursor: pointer; padding: 6px 12px; border-radius: 6px; display: flex; align-items: center; justify-content: center; transition: all 150ms; flex-shrink: 0; border: none; font-size: 13px; font-weight: 600; }
.rm-btn:hover { background: #dc2626; }
.library-layout { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 16px; align-items: start; }

/* 左侧文件夹树 */
.folder-panel { 
  border-right: 1px solid var(--c-border); 
  padding-right: 10px; 
  min-height: 70vh; 
  display: flex;
  flex-direction: column;
}

.folder-tree-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0 12px;
  border-bottom: 1px solid var(--c-border);
  margin-bottom: 8px;
}

.tree-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--c-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.tree-action-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 5px;
  border-radius: 4px;
  color: var(--c-secondary);
  transition: all 0.15s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.tree-action-btn:hover {
  background-color: var(--c-muted);
  color: var(--c-fg);
}

.folder-tree { 
  flex: 1;
  display: flex; 
  flex-direction: column; 
  gap: 1px;
  overflow-y: auto;
}

.tree-root-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.15s ease;
  color: var(--c-secondary);
}

.tree-root-item:hover {
  background-color: var(--c-muted);
  color: var(--c-fg);
}

.tree-root-item.active {
  background-color: var(--c-accent-muted);
  color: var(--c-fg);
}

.expand-placeholder {
  width: 20px;
  flex-shrink: 0;
}

.folder-icon { 
  width: 16px; 
  flex-shrink: 0; 
  color: #f59e0b;
}

.folder-name { 
  flex: 1;
  min-width: 0; 
  white-space: nowrap; 
  overflow: hidden; 
  text-overflow: ellipsis;
  font-size: 13px;
}

.asset-panel { min-width: 0; display: flex; flex-direction: column; gap: 12px; }
.crawl-band, .attach-bar, .uploading-list { border: 1px solid var(--c-border); border-radius: 8px; background: var(--c-panel); padding: 12px; }
.crawl-fields { display: flex; gap: 12px; align-items: center; }
.crawl-options { display: flex; gap: 16px; align-items: center; }
.option-item { display: flex; align-items: center; gap: 6px; }
.option-label { font-size: 12px; color: var(--c-secondary); white-space: nowrap; }
.small-input { width: 60px !important; text-align: center; }
.depth-select { padding: 6px 10px; border: 1px solid var(--c-border); border-radius: 6px; font-size: 12px; background: var(--c-bg); min-width: 120px; }
.crawl-btn { padding: 8px 16px !important; gap: 6px; }
.crawl-hint { display: flex; gap: 16px; margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--c-border); }
.hint-item { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--c-secondary); }
.crawl-status { display: grid; grid-template-columns: auto 1fr auto; gap: 8px; align-items: center; margin-top: 10px; color: var(--c-secondary); font-size: 12px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--c-secondary); }
.status-dot.running { background: #22c55e; box-shadow: 0 0 12px rgba(34, 197, 94, 0.5); }
.status-dot.done { background: var(--c-success); }
.status-dot.failed { background: var(--c-danger); }
.crawl-progress { grid-column: 1 / -1; height: 4px; background: var(--c-muted); border-radius: 999px; overflow: hidden; }
.crawl-progress div { height: 100%; background: var(--c-fg); transition: width 220ms ease; }
.crawl-error { grid-column: 2 / -1; margin-top: 4px; padding: 8px 12px; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 6px; color: #ef4444; font-size: 12px; }
.attach-bar { display: flex; gap: 10px; align-items: center; }
.attach-bar span { flex: 1; font-size: 13px; font-weight: 600; }
.attach-bar select { min-width: 180px; padding: 7px 10px; border: 1px solid var(--c-border); border-radius: 6px; }
.uploading-list { display: flex; flex-direction: column; gap: 8px; }
.uploading-item { display: grid; grid-template-columns: minmax(0, 1fr) 120px 44px; align-items: center; gap: 10px; font-size: 12px; color: var(--c-secondary); }
.mini-bar { height: 4px; background: var(--c-muted); border-radius: 999px; overflow: hidden; }
.mini-bar div { height: 100%; background: var(--c-accent); }
.asset-table { border: 1px solid var(--c-border); border-radius: 8px; overflow: hidden; background: var(--c-panel); }
.table-head, .asset-row { display: grid; grid-template-columns: 44px minmax(260px, 1fr) 140px 80px 92px; align-items: center; gap: 10px; padding: 10px 12px; }
.table-head { background: var(--c-muted); color: var(--c-secondary); font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px; }
.asset-row + .asset-row { border-top: 1px solid var(--c-border); }
.asset-row:hover, .asset-row.selected { background: var(--c-muted); }
.check-btn { width: 22px; height: 22px; border: 1px solid var(--c-border); border-radius: 6px; background: var(--c-panel); color: var(--c-fg); cursor: pointer; }
.check-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.asset-main { min-width: 0; cursor: pointer; }
.asset-name { font-size: 13px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.asset-meta { display: flex; gap: 8px; color: var(--c-secondary); font-size: 11px; margin-top: 2px; }
.asset-summary { color: var(--c-secondary); font-size: 12px; margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.asset-source { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.source-chip { padding: 2px 7px; border-radius: 999px; background: var(--c-muted); color: var(--c-secondary); font-weight: 600; }
.asset-source a { color: var(--c-accent); text-decoration: none; }
.asset-kb { font-size: 13px; color: var(--c-secondary); }
.asset-actions { display: flex; gap: 4px; }

.modal-mask { position: fixed; inset: 0; z-index: 300; display: flex; align-items: center; justify-content: center; background: var(--c-overlay); padding: 24px; }
.modal { background: var(--c-panel); border: 1px solid var(--c-border); border-radius: 12px; padding: 24px; max-width: 420px; width: 100%; }
.create-dir-modal h3 { font-size: 16px; font-weight: 700; margin-bottom: 16px; }
.field { margin-bottom: 16px; }
.field label { display: block; font-size: 13px; font-weight: 600; color: var(--c-secondary); margin-bottom: 6px; }
.actions { display: flex; justify-content: flex-end; gap: 8px; }
.preview-modal { width: min(860px, 94vw); max-height: 86vh; background: var(--c-panel); border: 1px solid var(--c-border); border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; }
.preview-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--c-border); }
.preview-title { font-weight: 700; font-size: 14px; }
.preview-sub { color: var(--c-secondary); font-size: 12px; margin-top: 2px; }
.preview-body { min-height: 360px; overflow: auto; }
.preview-text { padding: 16px; white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; line-height: 1.65; color: var(--c-fg); }
.pdf-frame { width: 100%; height: 70vh; border: 0; }
.empty-state { padding: 40px 24px; text-align: center; color: var(--c-secondary); }
.empty-title { font-size: 14px; font-weight: 700; margin-bottom: 4px; }
.empty-desc { font-size: 12px; }

/* 确认对话框 */
.confirm-modal { text-align: center; }
.confirm-icon { width: 56px; height: 56px; margin: 0 auto 16px; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: rgba(239, 68, 68, 0.1); color: #ef4444; }
.confirm-icon.warning { background: rgba(251, 191, 36, 0.1); color: #fbbf24; }
.confirm-title { font-size: 16px; font-weight: 700; color: var(--c-fg); margin-bottom: 8px; }
.confirm-message { font-size: 13px; color: var(--c-secondary); line-height: 1.5; margin-bottom: 20px; }
.confirm-actions { display: flex; gap: 10px; justify-content: center; }
.confirm-btn { padding: 10px 24px; border-radius: 10px; font-size: 13px; font-weight: 600; cursor: pointer; transition: all 150ms; border: none; }
.confirm-btn.cancel { background: var(--c-muted); color: var(--c-secondary); }
.confirm-btn.cancel:hover { background: var(--c-border); color: var(--c-fg); }
.confirm-btn.ok { background: #ef4444; color: #fff; }
.confirm-btn.ok:hover { background: #dc2626; }

@media (max-width: 820px) {
  .library-toolbar, .crawl-fields, .attach-bar { flex-wrap: wrap; }
  .library-layout { grid-template-columns: 1fr; }
  .folder-panel { border-right: 0; border-bottom: 1px solid var(--c-border); padding-right: 0; padding-bottom: 10px; min-height: auto; }
  .table-head { display: none; }
  .asset-row { grid-template-columns: 32px minmax(0, 1fr) auto; }
  .asset-source, .asset-kb { display: none; }
}
</style>
