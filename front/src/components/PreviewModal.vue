<script setup>
import { ref, watch, nextTick, computed } from 'vue'
import { getFilePreviewUrl, fetchFileContent } from '../api'

const props = defineProps({
  visible: Boolean,
  fileId: String,
  fileName: String,
  fileExt: String,
  pageNumber: Number,
  startOffset: Number,
  endOffset: Number,
  chunkText: String,
})

const emit = defineEmits(['close'])

const loading = ref(false)
const error = ref('')
const textContent = ref('')
const highlightRef = ref(null)

const isPdf = computed(() => props.fileExt === '.pdf')
const previewUrl = computed(() => {
  let url = getFilePreviewUrl(props.fileId)
  if (isPdf.value && props.pageNumber) {
    url += `#page=${props.pageNumber}`
  }
  return url
})

watch([() => props.visible, () => props.fileId], async ([visible, fileId]) => {
  if (!visible || !fileId || isPdf.value) {
    textContent.value = ''
    return
  }
  loading.value = true
  error.value = ''
  try {
    textContent.value = await fetchFileContent(fileId)
    await nextTick()
    if (highlightRef.value) {
      const chunkStart = props.startOffset || 0
      // Scroll to chunk position
      const lineHeight = 20
      const targetScroll = Math.max(0, chunkStart * 0.6 - 100)
      highlightRef.value.scrollTop = targetScroll

      // Try to highlight the chunk text
      if (props.chunkText) {
        const pre = highlightRef.value
        const text = textContent.value
        const escaped = props.chunkText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
        const highlightHtml = text.replace(
          new RegExp(escaped.substring(0, 80), 'g'),
          m => `<mark>${m}</mark>`
        )
        // Only use innerHTML if text matches something
        if (highlightHtml !== text) {
          pre.innerHTML = highlightHtml
        }
      }
    }
  } catch (err) {
    error.value = `无法加载文件预览: ${err.message}`
  }
  loading.value = false
})

function onClose() {
  emit('close')
}
</script>

<template>
  <div class="preview-overlay" v-if="visible" @click.self="onClose">
    <div class="preview-modal">
      <div class="preview-header">
        <span class="preview-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          {{ fileName }}
        </span>
        <span class="preview-page" v-if="isPdf && pageNumber">第 {{ pageNumber }} 页</span>
        <button class="preview-close" @click="onClose">&times;</button>
      </div>

      <div class="preview-body">
        <!-- PDF: iframe -->
        <iframe v-if="isPdf" :src="previewUrl" class="preview-iframe" />

        <!-- TXT/MD: text -->
        <template v-else-if="loading">
          <div class="preview-loading">加载中...</div>
        </template>
        <template v-else-if="error">
          <div class="preview-error">{{ error }}</div>
        </template>
        <pre v-else class="preview-text" ref="highlightRef">{{ textContent }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.preview-overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0,0,0,0.45);
  display: flex; align-items: center; justify-content: center;
}
.preview-modal {
  background: #fff; border-radius: 10px;
  width: min(900px, 90vw); height: min(85vh, 700px);
  display: flex; flex-direction: column;
  box-shadow: 0 8px 40px rgba(0,0,0,0.18);
  overflow: hidden;
}
.preview-header {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 18px;
  border-bottom: 1px solid #e5e5e5;
  flex-shrink: 0;
}
.preview-title {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; font-weight: 600;
  color: #333; flex: 1;
  min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.preview-page {
  font-size: 12px; color: #7c3aed;
  background: #f0eaff; padding: 2px 10px; border-radius: 10px;
  font-weight: 600; flex-shrink: 0;
}
.preview-close {
  background: none; border: none;
  font-size: 22px; color: #999; cursor: pointer;
  padding: 0 4px; line-height: 1;
  flex-shrink: 0;
}
.preview-close:hover { color: #333; }
.preview-body {
  flex: 1; overflow: hidden;
  position: relative;
}
.preview-iframe {
  width: 100%; height: 100%; border: none;
}
.preview-loading, .preview-error {
  display: flex; align-items: center; justify-content: center;
  height: 100%; color: #999; font-size: 14px;
}
.preview-error { color: #dc2626; }
.preview-text {
  width: 100%; height: 100%;
  margin: 0; padding: 16px 20px;
  font-size: 13px; line-height: 1.75;
  font-family: var(--font-mono, 'Consolas', monospace);
  white-space: pre-wrap; word-break: break-word;
  overflow-y: auto; overflow-x: hidden;
  color: #444;
}
.preview-text :deep(mark) {
  background: #fef08a; color: #333;
  padding: 1px 0; border-radius: 2px;
}
</style>
