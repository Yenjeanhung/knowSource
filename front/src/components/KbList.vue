<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchKbs, updateKb, deleteKb as apiDeleteKb } from '../api'
import CreateKbModal from './CreateKbModal.vue'

const router = useRouter()
const kbSearch = ref('')
const kbs = ref([])
const viewMode = ref('list')
const showCreateModal = ref(false)

const showEditModal = ref(false)
const editId = ref('')
const editName = ref('')
const editDesc = ref('')

const filteredKbs = computed(() => {
  const q = kbSearch.value.toLowerCase().trim()
  if (!q) return kbs.value
  return kbs.value.filter(kb => kb.name.toLowerCase().includes(q) || (kb.description || '').toLowerCase().includes(q))
})

async function loadKbs() { try { kbs.value = await fetchKbs() } catch {} }

async function removeKb(kbId, e) {
  e && e.stopPropagation()
  const kb = kbs.value.find(k => k.id === kbId)
  if (!confirm(`确定删除「${kb?.name}」及其所有文件？`)) return
  try { await apiDeleteKb(kbId) } catch {}
  await loadKbs()
}

function openEdit(kb, e) {
  e && e.stopPropagation()
  editId.value = kb.id
  editName.value = kb.name
  editDesc.value = kb.description || ''
  showEditModal.value = true
}

async function saveEdit() {
  if (!editName.value.trim()) return
  try {
    await updateKb(editId.value, { name: editName.value, description: editDesc.value })
    const kb = kbs.value.find(k => k.id === editId.value)
    if (kb) { kb.name = editName.value; kb.description = editDesc.value }
  } catch {}
  showEditModal.value = false
}

function onKbCreated(kbId) { showCreateModal.value = false; router.push('/kb/' + kbId) }

const typeColor = (t) => ({ pdf:'#ef4444', docx:'#3b82f6', txt:'#6b7280', md:'#8b5cf6', csv:'#10b981', json:'#f59e0b', html:'#f97316' }[t] || '#6b7280')

onMounted(loadKbs)
</script>

<template>
  <div>
    <!-- Toolbar -->
    <div class="toolbar">
      <div class="search-wrap">
        <svg class="search-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input type="text" v-model="kbSearch" placeholder="搜索知识库...">
      </div>
      <div class="view-toggle">
        <button :class="{ on: viewMode === 'list' }" @click="viewMode = 'list'">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/></svg>
        </button>
        <button :class="{ on: viewMode === 'card' }" @click="viewMode = 'card'">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>
        </button>
      </div>
      <button class="btn primary" @click="showCreateModal = true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        新建
      </button>
    </div>

    <!-- === LIST VIEW === -->
    <template v-if="viewMode === 'list'">
      <div class="kb-list" v-if="filteredKbs.length">
        <div class="kb-row" v-for="kb in filteredKbs" :key="kb.id" @click="router.push('/kb/' + kb.id)">
          <div class="kb-icon-box">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/></svg>
            <span class="kb-badge" v-if="kb.file_count">{{ kb.file_count }}</span>
          </div>
          <div class="kb-body">
            <div class="kb-title">{{ kb.name }}</div>
            <div class="kb-meta">
              <span v-for="t in kb.file_types?.slice(0, 4)" :key="t" class="tag" :style="{ color: typeColor(t), background: typeColor(t) + '15' }">{{ t }}</span>
              <span class="kb-desc" v-if="kb.description">{{ kb.description }}</span>
            </div>
          </div>
          <div class="kb-hover-actions">
            <button class="icon-btn" @click="openEdit(kb, $event)" title="编辑">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
            </button>
            <button class="icon-btn danger" @click="removeKb(kb.id, $event)" title="删除">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          </div>
        </div>
      </div>
      <div class="empty-state" v-else>
        <div class="empty-icon">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"><path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/></svg>
        </div>
        <div class="empty-title">{{ kbSearch ? '没有匹配的知识库' : '暂无知识库' }}</div>
        <div class="empty-desc" v-if="!kbSearch">点击「新建」创建第一个知识库</div>
      </div>
    </template>

    <!-- === CARD VIEW === -->
    <template v-if="viewMode === 'card'">
      <div class="kb-cards" v-if="filteredKbs.length">
        <div class="kb-card" v-for="kb in filteredKbs" :key="kb.id" @click="router.push('/kb/' + kb.id)">
          <div class="card-top-row">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/></svg>
            <div class="card-actions">
              <button class="icon-btn" @click="openEdit(kb, $event)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg></button>
              <button class="icon-btn danger" @click="removeKb(kb.id, $event)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>
            </div>
          </div>
          <div class="card-name">{{ kb.name }}</div>
          <div class="card-desc" v-if="kb.description">{{ kb.description }}</div>
          <div class="card-foot">
            <span>{{ kb.file_count }} 个文件</span>
            <span v-for="t in kb.file_types?.slice(0, 3)" :key="t" class="tag" :style="{ color: typeColor(t), background: typeColor(t) + '15' }">{{ t }}</span>
          </div>
        </div>
      </div>
      <div class="empty-state" v-else>
        <div class="empty-icon"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/></svg></div>
        <div class="empty-title">{{ kbSearch ? '没有匹配的知识库' : '暂无知识库' }}</div>
        <div class="empty-desc" v-if="!kbSearch">点击「新建」创建第一个知识库</div>
      </div>
    </template>

    <!-- Edit Modal -->
    <div class="modal-mask" v-if="showEditModal" @click.self="showEditModal = false">
      <div class="modal" @click.stop>
        <h3>编辑知识库</h3>
        <div class="field"><label>名称</label><input type="text" v-model="editName" placeholder="知识库名称" @keydown.enter="saveEdit" autofocus></div>
        <div class="field"><label>描述</label><textarea v-model="editDesc" placeholder="简要描述知识库内容" rows="3"></textarea></div>
        <div class="modal-btns"><button class="btn" @click="showEditModal = false">取消</button><button class="btn primary" @click="saveEdit" :disabled="!editName.trim()">保存</button></div>
      </div>
    </div>

    <CreateKbModal v-if="showCreateModal" @close="showCreateModal = false" @created="onKbCreated" />
  </div>
</template>

<style scoped>
.toolbar { display: flex; gap: 10px; margin-bottom: 20px; align-items: center; }
.search-wrap { flex: 1; position: relative; }
.search-icon { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); color: var(--c-secondary); pointer-events: none; }
.search-wrap input { padding-left: 34px; }

.view-toggle { display: flex; border: 1px solid var(--c-border); border-radius: var(--radius-sm); overflow: hidden; }
.view-toggle button { background: none; border: none; padding: 7px 9px; cursor: pointer; color: var(--c-secondary); display: flex; transition: all 150ms; }
.view-toggle button.on { background: var(--c-fg); color: var(--c-bg); }
.view-toggle button:hover:not(.on) { background: var(--c-muted); color: var(--c-fg); }

/* List */
.kb-list { display: flex; flex-direction: column; gap: 2px; }
.kb-row { display: flex; align-items: center; gap: 14px; padding: 14px 16px; border-radius: var(--radius); cursor: pointer; transition: background 150ms; border: 1px solid transparent; }
.kb-row:hover { background: var(--c-muted); border-color: var(--c-border); }
.kb-icon-box { position: relative; width: 40px; height: 40px; border-radius: 10px; background: var(--c-muted); display: flex; align-items: center; justify-content: center; color: var(--c-secondary); flex-shrink: 0; }
.kb-badge { position: absolute; top: -4px; right: -6px; background: var(--c-fg); color: var(--c-bg); font-size: 10px; font-weight: 700; min-width: 17px; height: 17px; border-radius: 9px; display: flex; align-items: center; justify-content: center; padding: 0 5px; }
.kb-body { flex: 1; min-width: 0; }
.kb-title { font-size: 14px; font-weight: 600; margin-bottom: 3px; }
.kb-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.kb-desc { font-size: 12px; color: var(--c-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 240px; }
.kb-hover-actions { display: flex; gap: 2px; opacity: 0; transition: opacity 150ms; flex-shrink: 0; }
.kb-row:hover .kb-hover-actions { opacity: 1; }

.tag { font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 4px; text-transform: uppercase; letter-spacing: 0.3px; }

.icon-btn { background: none; border: none; cursor: pointer; color: var(--c-secondary); padding: 5px; border-radius: 6px; display: flex; transition: all 150ms; }
.icon-btn:hover { color: var(--c-fg); background: var(--c-muted); }
.icon-btn.danger:hover { color: #ef4444; background: #fef2f2; }

/* Cards */
.kb-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
.kb-card { border: 1px solid var(--c-border); border-radius: var(--radius); padding: 18px; cursor: pointer; transition: all 200ms; display: flex; flex-direction: column; gap: 10px; }
.kb-card:hover { border-color: #aaa; box-shadow: 0 2px 12px rgba(0,0,0,0.05); transform: translateY(-1px); }
.card-top-row { display: flex; justify-content: space-between; align-items: center; color: var(--c-secondary); }
.card-actions { display: flex; gap: 2px; opacity: 0; transition: opacity 150ms; }
.kb-card:hover .card-actions { opacity: 1; }
.card-name { font-size: 15px; font-weight: 600; }
.card-desc { font-size: 12px; color: var(--c-secondary); line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card-foot { display: flex; justify-content: space-between; align-items: center; margin-top: auto; padding-top: 8px; border-top: 1px solid var(--c-border); font-size: 11px; color: var(--c-secondary); gap: 6px; }

/* Empty */
.empty-icon { color: var(--c-border); margin-bottom: 10px; }

/* Modal */
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.35); display: flex; align-items: center; justify-content: center; z-index: 200; }
.modal { background: var(--c-bg); border-radius: 12px; padding: 24px; width: 420px; max-width: 90vw; box-shadow: 0 12px 40px rgba(0,0,0,0.15); }
h3 { font-size: 16px; font-weight: 700; margin-bottom: 18px; }
.field { margin-bottom: 14px; }
.field label { display: block; font-size: 12px; font-weight: 600; color: var(--c-secondary); margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
.field input, .field textarea { width: 100%; padding: 9px 12px; font-size: 14px; font-family: var(--font); border: 1px solid var(--c-border); border-radius: 8px; background: var(--c-bg); color: var(--c-fg); outline: none; transition: border-color 150ms; resize: vertical; }
.field input:focus, .field textarea:focus { border-color: var(--c-fg); }
.modal-btns { display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px; }
</style>
