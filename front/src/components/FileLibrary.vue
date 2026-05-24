<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  attachAssetsToKb,
  createCrawlJob,
  createDirectory,
  deleteAsset as apiDeleteAsset,
  fetchAssetContent,
  fetchAssets,
  fetchDirectories,
  fetchKbs,
  getAssetPreviewUrl,
  getCrawlJob,
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
const search = ref('')
const uploading = ref({})
const selectedAssets = ref(new Set())
const selectedKbId = ref('')
const crawlKeyword = ref('')
const crawlMaxPages = ref(5)
const crawlJob = ref(null)
const previewAsset = ref(null)
const previewText = ref('')
const previewLoading = ref(false)
const showDirectoryModal = ref(false)
const directoryName = ref('')
const creatingDirectory = ref(false)
let crawlTimer = null

const directoryRows = computed(() => {
  const children = new Map()
  for (const item of directories.value) {
    const key = item.parent_id || ''
    if (!children.has(key)) children.set(key, [])
    children.get(key).push(item)
  }
  const rows = []
  const walk = (parentId, depth) => {
    for (const item of children.get(parentId) || []) {
      rows.push({ ...item, depth })
      walk(item.id, depth + 1)
    }
  }
  walk('', 0)
  return rows
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

function selectDirectory(id) {
  selectedDirectoryId.value = id
  loadAssets()
}

function openDirectoryModal() {
  directoryName.value = ''
  showDirectoryModal.value = true
}

async function addDirectory() {
  const name = directoryName.value.trim()
  if (!name || creatingDirectory.value) return
  creatingDirectory.value = true
  try {
    await createDirectory({ name, parentId: selectedDirectoryId.value || null })
    showDirectoryModal.value = false
    await loadDirectories()
  } catch {
    window.alert('目录创建失败')
  }
  creatingDirectory.value = false
}

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
          [assetId]: { name: file.name, progress: Math.round(((index + 1) / totalChunks) * 100) },
        }
      }
    } catch {
      window.alert(`上传失败：${file.name}`)
    }
    const next = { ...uploading.value }
    delete next[assetId]
    uploading.value = next
  }
  await loadAssets()
}

function toggleAsset(assetId) {
  const next = new Set(selectedAssets.value)
  if (next.has(assetId)) next.delete(assetId)
  else next.add(assetId)
  selectedAssets.value = next
}

function toggleAll() {
  if (selectedAssets.value.size === readyAssets.value.length) {
    selectedAssets.value = new Set()
  } else {
    selectedAssets.value = new Set(readyAssets.value.map(item => item.id))
  }
}

async function attachSelected() {
  if (!selectedKbId.value || !selectedAssets.value.size) return
  try {
    await attachAssetsToKb(selectedKbId.value, [...selectedAssets.value])
    selectedAssets.value = new Set()
    await loadAssets()
    window.alert('已加入知识库')
  } catch {
    window.alert('加入知识库失败')
  }
}

async function startCrawl() {
  if (!crawlKeyword.value.trim()) return
  try {
    crawlJob.value = await createCrawlJob({
      keyword: crawlKeyword.value.trim(),
      directoryId: selectedDirectoryId.value || null,
      maxPages: crawlMaxPages.value,
    })
    if (crawlTimer) clearInterval(crawlTimer)
    crawlTimer = setInterval(syncCrawlJob, 800)
    syncCrawlJob()
  } catch {
    window.alert('采集任务创建失败，请检查后端 .env 与网络配置')
  }
}

async function syncCrawlJob() {
  if (!crawlJob.value?.id) return
  try {
    crawlJob.value = await getCrawlJob(crawlJob.value.id)
    if (crawlJob.value.status === 'done' || crawlJob.value.status === 'failed') {
      clearInterval(crawlTimer)
      crawlTimer = null
      await refreshAll()
    }
  } catch {}
}

async function openPreview(asset) {
  previewAsset.value = asset
  previewText.value = ''
  previewLoading.value = true
  try {
    if (['txt', 'md', 'csv', 'json', 'html'].includes(asset.ext)) {
      previewText.value = await fetchAssetContent(asset.id)
    }
  } catch {
    previewText.value = '预览失败'
  }
  previewLoading.value = false
}

async function deleteAsset(asset) {
  if (!window.confirm(`确定删除「${asset.name}」？已加入知识库的文件需要先从知识库移除。`)) return
  try {
    await apiDeleteAsset(asset.id)
    await loadAssets()
  } catch {
    window.alert('删除失败：文件可能仍被知识库使用')
  }
}

onMounted(refreshAll)
onUnmounted(() => {
  if (crawlTimer) clearInterval(crawlTimer)
})
</script>

<template>
  <div class="library-page">
    <div class="library-toolbar">
      <div class="search-wrap">
        <svg class="search-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
        <input v-model="search" type="text" placeholder="搜索文件、来源、摘要..." @keydown.enter="loadAssets">
      </div>
      <button class="icon-btn" title="刷新" @click="refreshAll">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 0 0-15.74-6.26L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 15.74 6.26L21 16"/><path d="M16 16h5v5"/></svg>
      </button>
      <button class="btn" @click="openDirectoryModal">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
        新建目录
      </button>
      <button class="btn primary" @click="triggerUpload">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/></svg>
        上传
      </button>
      <input id="assetFileInput" type="file" multiple accept=".txt,.pdf,.md,.csv,.json,.docx,.html" style="display:none" @change="handlePick">
    </div>

    <div class="library-layout">
      <aside class="dir-panel">
        <button class="dir-row" :class="{ active: selectedDirectoryId === '' }" @click="selectDirectory('')">
          <span class="dir-icon">⌂</span>
          <span>全部文件</span>
        </button>
        <button
          v-for="dir in directoryRows"
          :key="dir.id"
          class="dir-row"
          :class="{ active: selectedDirectoryId === dir.id }"
          :style="{ paddingLeft: `${12 + dir.depth * 16}px` }"
          @click="selectDirectory(dir.id)"
        >
          <span class="dir-icon">▸</span>
          <span>{{ dir.name }}</span>
        </button>
      </aside>

      <main class="asset-panel">
        <section class="crawl-band">
          <div class="crawl-fields">
            <input v-model="crawlKeyword" type="text" placeholder="输入关键字联网采集资料">
            <input v-model.number="crawlMaxPages" class="small-input" type="text" placeholder="页数">
            <button class="btn" :disabled="!crawlKeyword.trim() || crawlJob?.status === 'running'" @click="startCrawl">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 0 20"/><path d="M12 2a15.3 15.3 0 0 0 0 20"/></svg>
              采集
            </button>
          </div>
          <div class="crawl-status" v-if="crawlJob">
            <span :class="['status-dot', crawlJob.status]"></span>
            <span>{{ crawlJob.message }}</span>
            <span>{{ crawlJob.progress }}%</span>
            <div class="crawl-progress"><div :style="{ width: `${crawlJob.progress}%` }"></div></div>
          </div>
        </section>

        <section class="attach-bar" v-if="selectedCount">
          <span>已选 {{ selectedCount }} 个文件</span>
          <select v-model="selectedKbId">
            <option value="">选择知识库</option>
            <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
          </select>
          <button class="btn primary" :disabled="!selectedKbId" @click="attachSelected">加入知识库</button>
        </section>

        <div class="uploading-list" v-if="Object.keys(uploading).length">
          <div v-for="item in uploading" :key="item.name" class="uploading-item">
            <span>{{ item.name }}</span>
            <div class="mini-bar"><div :style="{ width: `${item.progress}%` }"></div></div>
            <span>{{ item.progress }}%</span>
          </div>
        </div>

        <div class="asset-table" v-if="assets.length">
          <div class="table-head">
            <button class="check-btn" @click="toggleAll">{{ selectedAssets.size === readyAssets.length ? '✓' : '' }}</button>
            <span>文件</span>
            <span>来源</span>
            <span>知识库</span>
            <span>操作</span>
          </div>
          <div class="asset-row" v-for="asset in assets" :key="asset.id">
            <button class="check-btn" :disabled="asset.status !== 'ready'" @click="toggleAsset(asset.id)">
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
              <button class="icon-btn danger" title="删除" @click="deleteAsset(asset)">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/></svg>
              </button>
            </div>
          </div>
        </div>

        <div class="empty-state" v-else>
          <div class="empty-title">暂无文件</div>
          <div class="empty-desc">上传或采集后会出现在这里</div>
        </div>
      </main>
    </div>

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

    <div class="modal-mask" v-if="showDirectoryModal" @click.self="showDirectoryModal = false">
      <div class="create-dir-modal" @click.stop>
        <h3>新建目录</h3>
        <div class="field">
          <label>名称</label>
          <input
            v-model="directoryName"
            type="text"
            placeholder="例如：项目文档"
            autofocus
            @keydown.enter="addDirectory"
          >
        </div>
        <div class="actions">
          <button class="btn" @click="showDirectoryModal = false">取消</button>
          <button class="btn primary" :disabled="!directoryName.trim() || creatingDirectory" @click="addDirectory">
            {{ creatingDirectory ? '创建中...' : '创建' }}
          </button>
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
.library-layout { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 16px; align-items: start; }
.dir-panel { border-right: 1px solid var(--c-border); padding-right: 10px; min-height: 70vh; }
.dir-row { width: 100%; display: flex; align-items: center; gap: 8px; padding: 8px 10px; border: 0; border-radius: 8px; background: transparent; color: var(--c-secondary); cursor: pointer; text-align: left; font-size: 13px; }
.dir-row:hover, .dir-row.active { background: var(--c-muted); color: var(--c-fg); }
.dir-icon { width: 14px; color: var(--c-secondary); }
.asset-panel { min-width: 0; display: flex; flex-direction: column; gap: 12px; }
.crawl-band, .attach-bar, .uploading-list { border: 1px solid var(--c-border); border-radius: 8px; background: var(--c-panel); padding: 12px; }
.crawl-fields { display: flex; gap: 8px; align-items: center; }
.small-input { width: 70px !important; text-align: center; }
.crawl-status { display: grid; grid-template-columns: auto 1fr auto; gap: 8px; align-items: center; margin-top: 10px; color: var(--c-secondary); font-size: 12px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--c-secondary); }
.status-dot.running { background: #22c55e; box-shadow: 0 0 12px rgba(34, 197, 94, 0.5); }
.status-dot.done { background: var(--c-success); }
.status-dot.failed { background: var(--c-danger); }
.crawl-progress { grid-column: 1 / -1; height: 4px; background: var(--c-muted); border-radius: 999px; overflow: hidden; }
.crawl-progress div { height: 100%; background: var(--c-fg); transition: width 220ms ease; }
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
.asset-row:hover { background: var(--c-muted); }
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
.preview-modal { width: min(860px, 94vw); max-height: 86vh; background: var(--c-panel); border: 1px solid var(--c-border); border-radius: 12px; overflow: hidden; display: flex; flex-direction: column; }
.create-dir-modal { background: var(--c-bg); border-radius: var(--radius); padding: 24px; width: 360px; max-width: 90vw; box-shadow: 0 8px 30px rgba(0,0,0,0.12); }
.create-dir-modal h3 { font-size: 16px; font-weight: 700; margin-bottom: 16px; }
.field { margin-bottom: 16px; }
.field label { display: block; font-size: 13px; font-weight: 600; color: var(--c-secondary); margin-bottom: 6px; }
.actions { display: flex; justify-content: flex-end; gap: 8px; }
.preview-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--c-border); }
.preview-title { font-weight: 700; font-size: 14px; }
.preview-sub { color: var(--c-secondary); font-size: 12px; margin-top: 2px; }
.preview-body { min-height: 360px; overflow: auto; }
.preview-text { padding: 16px; white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; line-height: 1.65; color: var(--c-fg); }
.pdf-frame { width: 100%; height: 70vh; border: 0; }
@media (max-width: 820px) {
  .library-toolbar, .crawl-fields, .attach-bar { flex-wrap: wrap; }
  .library-layout { grid-template-columns: 1fr; }
  .dir-panel { border-right: 0; border-bottom: 1px solid var(--c-border); padding-right: 0; padding-bottom: 10px; min-height: auto; }
  .table-head { display: none; }
  .asset-row { grid-template-columns: 32px minmax(0, 1fr) auto; }
  .asset-source, .asset-kb { display: none; }
}
</style>
