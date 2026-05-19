<script setup>
import { ref, computed, onMounted } from 'vue'
import { fetchKbs, updateKb, deleteKb as apiDeleteKb } from '../api'

const emit = defineEmits(['open', 'create', 'deleted'])

const kbSearch = ref('')
const kbs = ref([])
const viewMode = ref('list')

// 编辑弹窗
const showEditModal = ref(false)
const editId = ref('')
const editName = ref('')
const editDesc = ref('')

const filteredKbs = computed(() => {
  const q = kbSearch.value.toLowerCase().trim()
  if (!q) return kbs.value
  return kbs.value.filter(kb => kb.name.toLowerCase().includes(q) || (kb.description || '').toLowerCase().includes(q))
})

async function loadKbs() {
  try { kbs.value = await fetchKbs() } catch {}
}

async function deleteKb(kbId, e) {
  e && e.stopPropagation()
  const kb = kbs.value.find(k => k.id === kbId)
  if (!confirm(`确定删除「${kb?.name}」及其所有文件？`)) return
  try { await apiDeleteKb(kbId) } catch {}
  await loadKbs()
  emit('deleted', kbId)
}

function openEditModal(kb, e) {
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

// 文件类型颜色
const typeColor = (t) => {
  const m = { pdf: '#ef4444', docx: '#3b82f6', txt: '#6b7280', md: '#8b5cf6', csv: '#10b981', json: '#f59e0b', html: '#f97316' }
  return m[t] || '#6b7280'
}

onMounted(loadKbs)
</script>

<template>
  <div>
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="search-box">
        <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input type="text" v-model="kbSearch" placeholder="搜索知识库...">
      </div>
      <div class="view-toggle">
        <button :class="{ active: viewMode === 'list' }" @click="viewMode = 'list'">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/></svg>
        </button>
        <button :class="{ active: viewMode === 'card' }" @click="viewMode = 'card'">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>
        </button>
      </div>
      <button class="btn primary" @click="emit('create')">+ 新建</button>
    </div>

    <!-- ====== 列表视图 ====== -->
    <template v-if="viewMode === 'list'">
      <div v-if="filteredKbs.length" class="kb-list">
        <div class="kb-item" v-for="kb in filteredKbs" :key="kb.id" @click="emit('open', kb.id)">
          <div class="item-icon">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
            </svg>
            <span class="item-badge" v-if="kb.file_count">{{ kb.file_count }}</span>
          </div>
          <div class="item-body">
            <div class="item-name">{{ kb.name }}</div>
            <div class="item-sub">
              <span v-for="t in kb.file_types.slice(0, 5)" :key="t" class="type-badge" :style="{ color: typeColor(t), background: typeColor(t) + '14' }">{{ t }}</span>
              <span class="item-dot" v-if="kb.description">·</span>
              <span class="item-desc-inline" v-if="kb.description">{{ kb.description }}</span>
            </div>
          </div>
          <div class="item-actions">
            <button class="act-btn" @click="openEditModal(kb, $event)" title="编辑">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
            </button>
            <button class="act-btn danger" @click="deleteKb(kb.id, $event)" title="删除">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          </div>
        </div>
      </div>
      <div v-else class="empty-state">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--c-border);margin-bottom:8px">
          <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
        </svg>
        <div class="empty-title">{{ kbSearch ? '没有匹配的知识库' : '暂无知识库' }}</div>
        <div class="empty-desc" v-if="!kbSearch">点击「+ 新建」创建第一个知识库</div>
      </div>
    </template>

    <!-- ====== 卡片视图 ====== -->
    <template v-if="viewMode === 'card'">
      <div v-if="filteredKbs.length" class="kb-cards">
        <div class="kb-card" v-for="kb in filteredKbs" :key="kb.id" @click="emit('open', kb.id)">
          <div class="card-top">
            <div class="card-icon-wrap">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
              </svg>
            </div>
            <div class="card-menu">
              <button class="act-btn" @click="openEditModal(kb, $event)" title="编辑">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
              </button>
              <button class="act-btn danger" @click="deleteKb(kb.id, $event)" title="删除">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
          </div>
          <div class="card-name">{{ kb.name }}</div>
          <div class="card-desc" v-if="kb.description">{{ kb.description }}</div>
          <div class="card-bottom">
            <span class="card-stat">{{ kb.file_count }} 个文件</span>
            <div class="card-types" v-if="kb.file_types?.length">
              <span v-for="t in kb.file_types.slice(0, 5)" :key="t" class="type-badge" :style="{ color: typeColor(t), background: typeColor(t) + '14' }">{{ t }}</span>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="empty-state">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--c-border);margin-bottom:8px">
          <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
        </svg>
        <div class="empty-title">{{ kbSearch ? '没有匹配的知识库' : '暂无知识库' }}</div>
        <div class="empty-desc" v-if="!kbSearch">点击「+ 新建」创建第一个知识库</div>
      </div>
    </template>

    <!-- 编辑弹窗 -->
    <div class="modal-mask" v-if="showEditModal" @click.self="showEditModal = false">
      <div class="modal" @click.stop>
        <h3>编辑知识库</h3>
        <div class="field">
          <label>名称</label>
          <input type="text" v-model="editName" placeholder="知识库名称" @keydown.enter="saveEdit" autofocus>
        </div>
        <div class="field">
          <label>描述</label>
          <textarea v-model="editDesc" placeholder="简要描述知识库内容（选填）" rows="3" @keydown.enter.ctrl="saveEdit"></textarea>
        </div>
        <div class="modal-actions">
          <button class="btn" @click="showEditModal = false">取消</button>
          <button class="btn primary" @click="saveEdit" :disabled="!editName.trim()">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 工具栏 */
.toolbar {
  display: flex; align-items: center; gap: 10px; margin-bottom: 20px;
}
.search-box {
  flex: 1; position: relative; display: flex; align-items: center;
}
.search-icon {
  position: absolute; left: 10px; color: var(--c-secondary); pointer-events: none;
}
.search-box input {
  width: 100%; padding: 8px 12px 8px 34px; font-size: 13px;
  border: 1px solid var(--c-border); border-radius: var(--radius);
  background: var(--c-bg); color: var(--c-fg); outline: none;
  transition: border-color 150ms, box-shadow 150ms;
}
.search-box input:focus { border-color: var(--c-fg); box-shadow: 0 0 0 2px rgba(0,0,0,0.04); }
.search-box input::placeholder { color: var(--c-secondary); }

/* 视图切换 */
.view-toggle {
  display: flex; border: 1px solid var(--c-border); border-radius: var(--radius-sm);
  overflow: hidden; flex-shrink: 0;
}
.view-toggle button {
  background: none; border: none; padding: 7px 9px; cursor: pointer;
  color: var(--c-secondary); display: flex; transition: all 150ms;
}
.view-toggle button.active { background: var(--c-fg); color: var(--c-bg); }
.view-toggle button:hover:not(.active) { color: var(--c-fg); background: var(--c-muted); }

/* ====== 列表 ====== */
.kb-list { display: flex; flex-direction: column; gap: 2px; }
.kb-item {
  display: flex; align-items: center; gap: 14px;
  padding: 14px 16px; border-radius: var(--radius);
  cursor: pointer; transition: background 150ms, box-shadow 150ms;
  border: 1px solid transparent;
}
.kb-item:hover { background: var(--c-muted); border-color: var(--c-border); }
.item-icon {
  position: relative; width: 40px; height: 40px; border-radius: 10px;
  background: var(--c-muted); display: flex; align-items: center; justify-content: center;
  color: var(--c-secondary); flex-shrink: 0;
}
.item-badge {
  position: absolute; top: -4px; right: -4px;
  background: var(--c-fg); color: var(--c-bg); font-size: 10px; font-weight: 700;
  min-width: 16px; height: 16px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center; padding: 0 4px;
}
.item-body { flex: 1; min-width: 0; }
.item-name { font-size: 14px; font-weight: 600; margin-bottom: 3px; }
.item-sub {
  display: flex; align-items: center; gap: 5px; flex-wrap: wrap;
  font-size: 12px; color: var(--c-secondary);
}
.item-dot { opacity: 0.4; }
.item-desc-inline { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 260px; }
.type-badge {
  font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 4px;
  text-transform: uppercase; letter-spacing: 0.3px;
}
.item-actions { display: flex; gap: 4px; opacity: 0; transition: opacity 150ms; flex-shrink: 0; }
.kb-item:hover .item-actions { opacity: 1; }

/* 操作按钮 */
.act-btn {
  background: none; border: none; cursor: pointer; color: var(--c-secondary);
  padding: 5px; border-radius: 6px; display: flex; align-items: center; justify-content: center;
  transition: color 150ms, background 150ms;
}
.act-btn:hover { color: var(--c-fg); background: var(--c-muted); }
.act-btn.danger:hover { color: #ef4444; background: #fef2f2; }

/* ====== 卡片 ====== */
.kb-cards {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px;
}
.kb-card {
  border: 1px solid var(--c-border); border-radius: var(--radius);
  padding: 18px; cursor: pointer; transition: all 200ms;
  display: flex; flex-direction: column; gap: 10px;
  background: var(--c-bg);
}
.kb-card:hover { border-color: #a0a0a0; box-shadow: 0 4px 16px rgba(0,0,0,0.06); transform: translateY(-1px); }
.card-top { display: flex; justify-content: space-between; align-items: flex-start; }
.card-icon-wrap {
  width: 36px; height: 36px; border-radius: 8px; background: var(--c-muted);
  display: flex; align-items: center; justify-content: center; color: var(--c-secondary);
}
.card-menu { display: flex; gap: 2px; opacity: 0; transition: opacity 150ms; }
.kb-card:hover .card-menu { opacity: 1; }
.card-name { font-size: 15px; font-weight: 600; line-height: 1.3; }
.card-desc {
  font-size: 12px; color: var(--c-secondary); line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.card-bottom {
  display: flex; justify-content: space-between; align-items: center;
  margin-top: auto; padding-top: 6px; border-top: 1px solid var(--c-border);
}
.card-stat { font-size: 11px; color: var(--c-secondary); }
.card-types { display: flex; gap: 4px; flex-wrap: wrap; }

/* 空状态 */
.empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 48px 24px; text-align: center;
}
.empty-title { font-size: 15px; font-weight: 600; color: var(--c-secondary); }
.empty-desc { font-size: 13px; color: var(--c-secondary); opacity: 0.7; margin-top: 4px; }

/* 弹窗 */
.modal-mask {
  position: fixed; inset: 0; background: rgba(0,0,0,0.35);
  display: flex; align-items: center; justify-content: center;
  z-index: 200; animation: fadeIn 150ms;
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.modal {
  background: var(--c-bg); border-radius: 12px; padding: 24px;
  width: 420px; max-width: 90vw; box-shadow: 0 12px 40px rgba(0,0,0,0.15);
}
h3 { font-size: 16px; font-weight: 700; margin-bottom: 18px; }
.field { margin-bottom: 14px; }
.field label { display: block; font-size: 12px; font-weight: 600; color: var(--c-secondary); margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
.field input, .field textarea {
  width: 100%; padding: 9px 12px; font-size: 14px; font-family: var(--font);
  border: 1px solid var(--c-border); border-radius: 8px;
  background: var(--c-bg); color: var(--c-fg); outline: none;
  transition: border-color 150ms, box-shadow 150ms; resize: vertical;
}
.field input:focus, .field textarea:focus { border-color: var(--c-fg); box-shadow: 0 0 0 3px rgba(0,0,0,0.04); }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px; }
</style>
