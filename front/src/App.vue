<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const isSidebarCollapsed = ref(false)
const SIDEBAR_STORAGE_KEY = 'knowsource.sidebar.collapsed'

const menuItems = computed(() => [
  { to: '/', label: '知识库', exact: true, hint: '知识库' },
  { to: '/query', label: '问答', exact: false, hint: '问答' },
  { to: '/vectors', label: '向量', exact: false, hint: '向量' },
])

function toggleSidebar() {
  isSidebarCollapsed.value = !isSidebarCollapsed.value
  localStorage.setItem(SIDEBAR_STORAGE_KEY, String(isSidebarCollapsed.value))
}

function isExact(item) {
  return item.exact ? 'is-active' : undefined
}

onMounted(() => {
  const saved = localStorage.getItem(SIDEBAR_STORAGE_KEY)
  if (saved !== null) {
    isSidebarCollapsed.value = saved === 'true'
  }
})
</script>

<template>
  <div class="app-shell" :class="{ 'is-collapsed': isSidebarCollapsed }">
    <aside class="sidebar">
      <div class="sidebar-top">
        <button
          class="sidebar-toggle"
          type="button"
          :aria-label="isSidebarCollapsed ? '展开菜单' : '收起菜单'"
          @click="toggleSidebar"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.85" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="3.75" y="5" width="16.5" height="14" rx="3" />
            <path d="M9 5v14" />
          </svg>
        </button>
      </div>

      <nav class="side-nav">
        <router-link
          v-for="item in menuItems"
          :key="item.to"
          :to="item.to"
          class="side-item"
          active-class="is-active"
          :exact-active-class="isExact(item)"
        >
          <span class="side-icon-wrap" aria-hidden="true">
            <svg
              v-if="item.to === '/'"
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M3.75 7.25A2.25 2.25 0 0 1 6 5h4.25c.57 0 1.12.22 1.54.62l1.14 1.1c.42.4.97.63 1.55.63H18A2.25 2.25 0 0 1 20.25 9.6v7.15A2.25 2.25 0 0 1 18 19H6a2.25 2.25 0 0 1-2.25-2.25Z" />
              <path d="M3.75 9.25h16.5" />
            </svg>
            <svg
              v-else-if="item.to === '/query'"
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M12 3.25 18.75 7v7.75L12 18.5l-6.75-3.75V7L12 3.25Z" />
              <path d="M9 9.25h6" />
              <path d="M9 12.75h3.5" />
            </svg>
            <svg
              v-else
              width="22"
              height="22"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.8"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <rect x="4.25" y="4.25" width="15.5" height="15.5" rx="2.25" />
              <path d="M8 8.5h8" />
              <path d="M8 12h8" />
              <path d="M8 15.5h5" />
            </svg>
          </span>

          <span class="side-label">{{ item.label }}</span>
          <span class="side-hint">{{ item.hint }}</span>
        </router-link>
      </nav>

      <div class="side-brand" @click="router.push('/')">
        <span class="side-icon-wrap brand-icon" aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 2.75 18.5 8.25 12 21.25 5.5 8.25 12 2.75Z" />
            <path d="M12 2.75v18.5" stroke-width="1.1" opacity="0.45" />
            <path d="M8.75 10.25h6.5" stroke-width="1.1" opacity="0.45" />
          </svg>
        </span>
        <span class="brand-text">KnowSource</span>
        <span class="side-hint">KnowSource</span>
      </div>
    </aside>

    <main class="main-area">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100dvh;
  max-width: 1152px;
  margin: 0;
}

.sidebar {
  width: 118px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  padding: 12px 10px;
  position: sticky;
  top: 0;
  height: 100dvh;
  border-right: 1px solid var(--c-border);
  background: #fff;
  transition: width 180ms ease, padding 180ms ease;
}

.sidebar-top {
  display: flex;
  justify-content: flex-start;
  padding-bottom: 10px;
}

.sidebar-toggle {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: var(--c-secondary);
  cursor: pointer;
  transition: background 150ms ease, color 150ms ease;
}

.sidebar-toggle:hover {
  background: var(--c-muted);
  color: var(--c-fg);
}

.side-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 8px;
}

.side-item,
.side-brand {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 48px;
  padding: 0 12px;
  border-radius: 14px;
  color: var(--c-secondary);
  text-decoration: none;
  transition: background 150ms ease, color 150ms ease;
}

.side-item:hover,
.side-brand:hover {
  background: var(--c-muted);
  color: var(--c-fg);
}

.side-item.is-active {
  background: var(--c-muted);
  color: var(--c-fg);
  font-weight: 600;
}

.side-icon-wrap {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: currentColor;
}

.brand-icon {
  color: var(--c-fg);
}

.side-label,
.brand-text {
  font-size: 14px;
  font-weight: inherit;
  white-space: nowrap;
}

.side-brand {
  margin-top: 8px;
  padding-top: 14px;
  cursor: pointer;
  user-select: none;
  border-top: 1px solid var(--c-border);
}

.brand-text {
  font-size: 13px;
  font-weight: 700;
  color: var(--c-fg);
}

.side-hint {
  position: absolute;
  left: calc(100% + 10px);
  top: 50%;
  transform: translateY(-50%) translateX(-4px);
  padding: 7px 10px;
  border: 1px solid #ece7df;
  border-radius: 12px;
  background: rgba(255, 252, 247, 0.98);
  color: #5f5548;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  box-shadow: 0 12px 28px rgba(92, 78, 58, 0.12);
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
  transition: opacity 140ms ease, transform 140ms ease, visibility 140ms ease;
  z-index: 12;
}

.side-hint::before {
  content: '';
  position: absolute;
  left: -6px;
  top: 50%;
  width: 10px;
  height: 10px;
  border-left: 1px solid #ece7df;
  border-bottom: 1px solid #ece7df;
  background: rgba(255, 252, 247, 0.98);
  transform: translateY(-50%) rotate(45deg);
}

.main-area {
  flex: 1;
  min-width: 0;
  padding: 28px 32px 48px;
}

.is-collapsed .sidebar {
  width: 72px;
  padding-left: 8px;
  padding-right: 8px;
}

.is-collapsed .sidebar-top {
  justify-content: center;
}

.is-collapsed .side-item,
.is-collapsed .side-brand {
  justify-content: center;
  padding-left: 0;
  padding-right: 0;
}

.is-collapsed .side-label,
.is-collapsed .brand-text {
  display: none;
}

.is-collapsed .side-item:hover .side-hint,
.is-collapsed .side-item:focus-visible .side-hint,
.is-collapsed .side-brand:hover .side-hint,
.is-collapsed .side-brand:focus-visible .side-hint {
  opacity: 1;
  visibility: visible;
  transform: translateY(-50%) translateX(0);
}

@media (max-width: 640px) {
  .sidebar {
    width: 72px;
    padding-left: 8px;
    padding-right: 8px;
  }

  .sidebar-top {
    justify-content: center;
  }

  .side-item,
  .side-brand {
    justify-content: center;
    padding-left: 0;
    padding-right: 0;
  }

  .side-label,
  .brand-text {
    display: none;
  }

  .main-area {
    padding: 20px 16px 40px;
  }
}
</style>
