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

onMounted(loadKbs)
</script>

<template>
  <div>
    <!-- 工具栏：搜索 + 新建 -->
    <div class="kb-toolbar">
      <input type="text" v-model="kbSearch" placeholder="搜索知识库...">
      <button class="btn primary" @click="emit('create')">+ 新建</button>
    </div>

    <!-- 列表视图 -->
    <template v-if="viewMode === 'list'">
      <div v-if="filteredKbs.length" class="kb-list">
        <div class="kb-item" v-for="kb in filteredKbs" :key="kb.id" @click="emit('open', kb.id)">
          <svg class="kb-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
          </svg>
          <div class="kb-info">
            <div class="kb-name">{{ kb.name }}</div>
            <div class="kb-meta">
              <span>{{ kb.file_count }} 个文件</span>
              <span v-if="kb.file_types?.length"> · </span>
              <span class="type-tag" v-for="t in kb.file_types.slice(0, 4)" :key="t">{{ t }}</span>
            </div>
            <div class="kb-desc" v-if="kb.description">{{ kb.description }}</div>
          </div>
          <div class="kb-actions">
            <button class="icon-btn" @click="openEditModal(kb, $event)" title="编辑">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
            </button>
            <button class="icon-btn danger" @click="deleteKb(kb.id, $event)" title="删除">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </div>
      </div>
      <div v-else class="empty-state">
        <div class="icon">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
          </svg>
        </div>
        <div class="title" v-if="kbSearch">没有匹配的知识库</div>
        <div class="title" v-else>暂无知识库</div>
        <div class="desc" v-if="!kbSearch">点击「+ 新建」创建第一个知识库</div>
      </div>
    </template>

    <!-- 卡片视图 -->
    <template v-if="viewMode === 'card'">
      <div v-if="filteredKbs.length" class="kb-cards">
        <div class="kb-card" v-for="kb in filteredKbs" :key="kb.id" @click="emit('open', kb.id)">
          <div class="card-header">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
            </svg>
            <div class="card-actions">
              <button class="icon-btn" @click="openEditModal(kb, $event)" title="编辑">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>
              </button>
              <button class="icon-btn danger" @click="deleteKb(kb.id, $event)" title="删除">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
          </div>
          <div class="card-name">{{ kb.name }}</div>
          <div class="card-desc" v-if="kb.description">{{ kb.description }}</div>
          <div class="card-footer">
            <span class="card-count">{{ kb.file_count }} 个文件</span>
            <div class="card-types" v-if="kb.file_types?.length">
              <span class="type-tag" v-for="t in kb.file_types.slice(0, 5)" :key="t">{{ t }}</span>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="empty-state">
        <div class="icon">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
          </svg>
        </div>
        <div class="title" v-if="kbSearch">没有匹配的知识库</div>
        <div class="title" v-else>暂无知识库</div>
        <div class="desc" v-if="!kbSearch">点击「+ 新建」创建第一个知识库</div>
      </div>
    </template>

    <!-- 右下角视图切换 -->
    <div class="view-fab">
      <button :class="{ active: viewMode === 'list' }" @click="viewMode = 'list'" title="列表视图">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>
        </svg>
      </button>
      <button :class="{ active: viewMode === 'card' }" @click="viewMode = 'card'" title="卡片视图">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
        </svg>
      </button>
    </div>

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
          <textarea v-model="editDesc" placeholder="简要描述知识库内容（选填）" rows="2" @keydown.enter.ctrl="saveEdit"></textarea>
        </div>
        <div class="actions">
          <button class="btn" @click="showEditModal = false">取消</button>
          <button class="btn primary" @click="saveEdit" :disabled="!editName.trim()">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.kb-toolbar { display: flex; gap: 8px; margin-bottom: 16px; }
.kb-toolbar input { flex: 1; }

/* 视图切换 - 右下角浮动 */
.view-fab {
  position: fixed; bottom: 24px; right: 24px;
  display: flex; border: 1px solid var(--c-border); border-radius: var(--radius);
  overflow: hidden; background: var(--c-bg); box-shadow: 0 2px 8px rgba(0,0,0,0.08); z-index: 50;
}
.view-fab button {
  background: none; border: none; padding: 8px 10px; cursor: pointer;
  color: var(--c-secondary); display: flex; transition: background 150ms, color 150ms;
}
.view-fab button.active { background: var(--c-muted); color: var(--c-fg); }
.view-fab button:hover:not(.active) { color: var(--c-fg); }

/* List */
.kb-list { display: flex; flex-direction: column; gap: 2px; }
.kb-item {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 14px; border-radius: var(--radius-sm);
  cursor: pointer; transition: background 150ms;
}
.kb-item:hover { background: var(--c-muted); }
.kb-icon { color: var(--c-secondary); flex-shrink: 0; }
.kb-info { flex: 1; min-width: 0; }
.kb-name { font-size: 14px; font-weight: 600; }
.kb-meta { font-size: 12px; color: var(--c-secondary); display: flex; align-items: center; gap: 2px; }
.kb-desc { font-size: 12px; color: var(--c-secondary); margin-top: 2px; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.type-tag {
  font-size: 10px; color: var(--c-secondary); background: var(--c-muted);
  padding: 1px 6px; border-radius: 3px; font-weight: 500;
}
.kb-actions { display: flex; gap: 4px; opacity: 0; transition: opacity 150ms; flex-shrink: 0; }
.kb-item:hover .kb-actions { opacity: 1; }

.icon-btn {
  background: none; border: none; cursor: pointer; color: var(--c-secondary);
  padding: 4px; border-radius: 4px; display: flex; transition: color 150ms, background 150ms;
}
.icon-btn:hover { color: var(--c-fg); background: var(--c-muted); }
.icon-btn.danger:hover { color: var(--c-danger); }

/* Cards */
.kb-cards {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.kb-card {
  border: 1px solid var(--c-border); border-radius: var(--radius);
  padding: 16px; cursor: pointer; transition: border-color 150ms, box-shadow 150ms;
  display: flex; flex-direction: column; gap: 8px;
}
.kb-card:hover { border-color: var(--c-fg); box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.card-header { display: flex; justify-content: space-between; align-items: center; color: var(--c-secondary); }
.card-actions { display: flex; gap: 4px; opacity: 0; transition: opacity 150ms; }
.kb-card:hover .card-actions { opacity: 1; }
.card-name { font-size: 15px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.card-desc { font-size: 12px; color: var(--c-secondary); line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card-footer { display: flex; justify-content: space-between; align-items: center; margin-top: auto; padding-top: 4px; }
.card-count { font-size: 11px; color: var(--c-secondary); }
.card-types { display: flex; gap: 4px; flex-wrap: wrap; }

/* 编辑弹窗 */
.modal-mask {
  position: fixed; inset: 0; background: rgba(0,0,0,0.3);
  display: flex; align-items: center; justify-content: center;
  z-index: 100; animation: fadeIn 150ms;
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.modal {
  background: var(--c-bg); border-radius: var(--radius); padding: 24px;
  width: 400px; max-width: 90vw; box-shadow: 0 8px 30px rgba(0,0,0,0.12);
}
h3 { font-size: 16px; font-weight: 700; margin-bottom: 16px; }
.field { margin-bottom: 14px; }
.field label { display: block; font-size: 13px; font-weight: 600; color: var(--c-secondary); margin-bottom: 6px; }
.field input, .field textarea {
  width: 100%; padding: 8px 10px; font-size: 14px; font-family: var(--font);
  border: 1px solid var(--c-border); border-radius: var(--radius-sm);
  background: var(--c-bg); color: var(--c-fg); outline: none;
  transition: border-color 150ms; resize: vertical;
}
.field input:focus, .field textarea:focus { border-color: var(--c-fg); }
.actions { display: flex; justify-content: flex-end; gap: 8px; }
.sm { padding: 4px 8px; font-size: 12px; }
</style>
