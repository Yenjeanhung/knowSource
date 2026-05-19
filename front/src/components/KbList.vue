<script setup>
import { ref, computed, onMounted } from 'vue'
import { fetchKbs, deleteKb as apiDeleteKb } from '../api'

const emit = defineEmits(['open', 'create', 'deleted'])

const kbSearch = ref('')
const kbs = ref([])

const filteredKbs = computed(() => {
  const q = kbSearch.value.toLowerCase().trim()
  if (!q) return kbs.value
  return kbs.value.filter(kb => kb.name.toLowerCase().includes(q))
})

async function loadKbs() {
  try { kbs.value = await fetchKbs() } catch {}
}

async function deleteKb(kbId, e) {
  e && e.stopPropagation()
  const kb = kbs.value.find(k => k.id === kbId)
  if (!confirm(`Delete "${kb?.name}" and all its files?`)) return
  try { await apiDeleteKb(kbId) } catch {}
  await loadKbs()
  emit('deleted', kbId)
}

onMounted(loadKbs)
</script>

<template>
  <div>
    <div class="kb-toolbar">
      <input type="text" v-model="kbSearch" placeholder="Search knowledge bases...">
      <button class="btn primary" @click="emit('create')">+ New</button>
    </div>

    <div v-if="filteredKbs.length" class="kb-list">
      <div class="kb-item" v-for="kb in filteredKbs" :key="kb.id" @click="emit('open', kb.id)">
        <svg class="kb-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
        </svg>
        <div class="kb-info">
          <div class="kb-name">{{ kb.name }}</div>
          <div class="kb-meta">{{ kb.file_count }} file{{ kb.file_count !== 1 ? 's' : '' }}</div>
        </div>
        <span class="kb-count">{{ kb.file_count }}</span>
        <div class="kb-actions">
          <button class="btn danger sm" @click="deleteKb(kb.id, $event)">Delete</button>
        </div>
      </div>
    </div>

    <div v-else class="empty-state">
      <div class="icon">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z"/>
        </svg>
      </div>
      <div class="title" v-if="kbSearch">No matching knowledge bases</div>
      <div class="title" v-else>No knowledge bases yet</div>
      <div class="desc" v-if="!kbSearch">Click "+ New" to create your first one</div>
    </div>
  </div>
</template>

<style scoped>
.kb-toolbar { display: flex; gap: 8px; margin-bottom: 16px; }
.kb-toolbar input { flex: 1; }

.kb-list { display: flex; flex-direction: column; gap: 4px; }
.kb-item {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 14px; border-radius: var(--radius-sm);
  cursor: pointer; transition: background 150ms;
  border: 1px solid transparent;
}
.kb-item:hover { background: var(--c-muted); }
.kb-icon { color: var(--c-secondary); flex-shrink: 0; }
.kb-info { flex: 1; min-width: 0; }
.kb-name { font-size: 14px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kb-meta { font-size: 12px; color: var(--c-secondary); }
.kb-count { font-size: 12px; color: var(--c-secondary); background: var(--c-muted); padding: 2px 8px; border-radius: 10px; flex-shrink: 0; }
.kb-actions { display: flex; gap: 4px; opacity: 0; transition: opacity 150ms; }
.kb-item:hover .kb-actions { opacity: 1; }
.sm { padding: 4px 8px; font-size: 12px; }
</style>
