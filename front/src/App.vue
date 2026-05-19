<script setup>
import { ref } from 'vue'
import KbList from './components/KbList.vue'
import KbDetail from './components/KbDetail.vue'
import QueryView from './components/QueryView.vue'
import CreateKbModal from './components/CreateKbModal.vue'

const tab = ref('kb')
const selectedKbId = ref(null)
const showCreateModal = ref(false)
const refreshKey = ref(0)

function switchToKb() {
  tab.value = 'kb'
  selectedKbId.value = null
}

function openKb(kbId) {
  selectedKbId.value = kbId
}

function backToList() {
  selectedKbId.value = null
  refreshKey.value++
}

function onKbCreated(kbId) {
  showCreateModal.value = false
  selectedKbId.value = kbId
}

async function deleteKb(kbId) {
  selectedKbId.value = null
  refreshKey.value++
}
</script>

<template>
  <div class="shell">
    <!-- Header -->
    <header class="header">
      <div class="logo">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="2" y="2" width="20" height="20" rx="4"/><line x1="8" y1="8" x2="16" y2="8"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="8" y1="16" x2="12" y2="16"/>
        </svg>
        <h1>MiniRAG</h1>
        <div class="dot"></div>
      </div>
    </header>

    <!-- Tabs -->
    <div class="tabs">
      <button class="tab" :class="{ active: tab === 'kb' }" @click="switchToKb">Knowledge Base</button>
      <button class="tab" :class="{ active: tab === 'query' }" @click="tab = 'query'">Query</button>
    </div>

    <!-- KB Tab -->
    <template v-if="tab === 'kb'">
      <KbList v-if="!selectedKbId" :key="refreshKey" @open="openKb" @create="showCreateModal = true" @deleted="deleteKb" />
      <KbDetail v-else :kb-id="selectedKbId" @back="backToList" @deleted="deleteKb(selectedKbId)" />
    </template>

    <!-- Query Tab -->
    <QueryView v-if="tab === 'query'" />

    <!-- Create KB Modal -->
    <CreateKbModal v-if="showCreateModal" @close="showCreateModal = false" @created="onKbCreated" />
  </div>
</template>

<style scoped>
.shell { max-width: 640px; margin: 0 auto; padding: 0 20px; min-height: 100dvh; display: flex; flex-direction: column; }

.header { display: flex; align-items: center; gap: 10px; padding: 20px 0 16px; border-bottom: 1px solid var(--c-border); margin-bottom: 24px; }
.header .logo { display: flex; align-items: center; gap: 8px; }
.header h1 { font-size: 18px; font-weight: 700; letter-spacing: -0.3px; }
.header .dot { width: 5px; height: 5px; border-radius: 50%; background: var(--c-accent); }

.tabs { display: flex; gap: 0; margin-bottom: 24px; }
.tab {
  padding: 8px 0; margin-right: 24px; font-size: 14px; font-weight: 500;
  color: var(--c-secondary); cursor: pointer; border: none; background: none;
  border-bottom: 2px solid transparent; transition: color 150ms, border-color 150ms;
  font-family: var(--font);
}
.tab:hover { color: var(--c-fg); }
.tab.active { color: var(--c-fg); border-bottom-color: var(--c-fg); font-weight: 700; }

@media (max-width: 480px) {
  .shell { padding: 0 14px; }
  .header { padding: 16px 0 12px; margin-bottom: 16px; }
}
</style>
