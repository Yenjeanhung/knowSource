<script setup>
import { useRouter, useRoute } from 'vue-router'
const router = useRouter()
const route = useRoute()
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <nav class="side-nav">
        <router-link to="/" class="side-item" exact-active-class="is-active">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3.75 7.25A2.25 2.25 0 0 1 6 5h4.2c.6 0 1.16.24 1.58.66l1.06 1.09c.42.42.98.66 1.58.66H18A2.25 2.25 0 0 1 20.25 9.66v7.09A2.25 2.25 0 0 1 18 19H6a2.25 2.25 0 0 1-2.25-2.25V7.25Z"/>
            <path d="M3.75 9.25h16.5"/>
          </svg>
          <span class="side-label">知识库</span>
        </router-link>
        <router-link to="/query" class="side-item" active-class="is-active">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 3.25 18.75 7v7.75L12 18.5l-6.75-3.75V7L12 3.25Z"/>
            <path d="M9 9.25h6"/>
            <path d="M9 12.75h3.5"/>
          </svg>
          <span class="side-label">问答</span>
        </router-link>
      </nav>

      <div class="side-brand" @click="router.push('/')">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 2.75 18.5 8.25 12 21.25 5.5 8.25 12 2.75Z"/>
          <path d="M12 2.75v18.5" stroke-width="1.1" opacity="0.45"/>
          <path d="M8.75 10.25h6.5" stroke-width="1.1" opacity="0.45"/>
        </svg>
        <span class="brand-text">KnowSource</span>
      </div>
    </aside>

    <main class="main-area">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex; min-height: 100dvh; max-width: 1152px; margin: 0;
}

.sidebar {
  width: 96px; flex-shrink: 0;
  display: flex; flex-direction: column;
  border-right: 1px solid var(--c-border);
  padding: 0 8px; position: sticky; top: 0; height: 100dvh;
}

.side-nav {
  flex: 1; display: flex; flex-direction: column; gap: 6px; padding-top: 24px;
}

.side-item {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 12px 6px; border-radius: 12px;
  text-decoration: none; color: var(--c-secondary);
  transition: all 150ms; cursor: pointer;
  position: relative;
}
.side-item:hover { color: var(--c-fg); background: var(--c-muted); }
.side-item.is-active {
  color: var(--c-fg); background: var(--c-muted); font-weight: 600;
}
.side-item.is-active::before {
  content: ''; position: absolute; left: -8px; top: 10px; bottom: 10px;
  width: 3px; background: var(--c-fg); border-radius: 0 2px 2px 0;
}

.side-label { font-size: 11px; font-weight: inherit; letter-spacing: 0.2px; }

.side-brand {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 14px 4px 22px; cursor: pointer; user-select: none;
  color: var(--c-fg); border-top: 1px solid var(--c-border);
  transition: opacity 150ms;
}
.side-brand:hover { opacity: 0.7; }
.brand-text { font-size: 10px; font-weight: 700; letter-spacing: 0.2px; line-height: 1.1; }

.main-area { flex: 1; min-width: 0; padding: 28px 32px 48px; }

@media (max-width: 640px) {
  .sidebar { width: 56px; padding: 0 6px; }
  .side-item { padding: 14px 6px; }
  .side-label { display: none; }
  .brand-text { display: none; }
  .side-brand { border-top: 0; padding: 12px 6px; }
  .main-area { padding: 20px 16px 40px; }
}
</style>
