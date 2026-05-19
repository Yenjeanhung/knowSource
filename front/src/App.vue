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
        <svg class="logo-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="12 2 20 9 12 22 4 9"/>
          <line x1="12" y1="2" x2="12" y2="22" stroke-width="1.2" opacity="0.4"/>
          <line x1="4" y1="9" x2="20" y2="9" stroke-width="1.2" opacity="0.4"/>
        </svg>
        <h1>知源</h1>
        <span class="logo-sub">KnowSource</span>
      </div>
    </header>

    <!-- Tabs -->
    <div class="tabs">
      <button class="tab" :class="{ active: tab === 'kb' }" @click="switchToKb">知识库</button>
      <button class="tab" :class="{ active: tab === 'query' }" @click="tab = 'query'">问答</button>
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
.shell { max-width: 1024px; margin: 0 auto; padding: 0 24px; min-height: 100dvh; display: flex; flex-direction: column; }

.header { display: flex; align-items: center; gap: 10px; padding: 20px 0 16px; border-bottom: 1px solid var(--c-border); margin-bottom: 24px; }
.header .logo { display: flex; align-items: center; gap: 8px; }
.header h1 { font-size: 18px; font-weight: 700; letter-spacing: 1px; }
.header .logo-icon { color: var(--c-fg); }
.header .logo-sub { font-size: 11px; color: var(--c-secondary); font-weight: 500; letter-spacing: 0.5px; margin-left: -2px; }

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
