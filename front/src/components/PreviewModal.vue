<script setup>
import { ref, watch, nextTick, computed, onBeforeUnmount } from 'vue'
import * as pdfjsLib from 'pdfjs-dist'
import { getFilePreviewUrl, fetchFileContent } from '../api'

pdfjsLib.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs'

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
const previewBodyRef = ref(null)
const canvasRef = ref(null)
const textLayerRef = ref(null)
const pdfScale = ref(1.5)
const pdfCurrentPage = ref(1)
const pdfTotalPages = ref(0)

let pdfDoc = null
let renderTask = null

const normalizedExt = computed(() => {
  const ext = (props.fileExt || '').trim().toLowerCase()
  if (ext) return ext.startsWith('.') ? ext : `.${ext}`

  const name = (props.fileName || '').trim().toLowerCase()
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.slice(dot) : ''
})

const isPdf = computed(() => normalizedExt.value === '.pdf')

/* ---- PDF preview ---- */

async function loadPdf() {
  if (renderTask) { try { renderTask.cancel() } catch {}; renderTask = null }
  if (pdfDoc) { try { pdfDoc.destroy() } catch {}; pdfDoc = null }

  loading.value = true
  error.value = ''
  pdfCurrentPage.value = props.pageNumber || 1

  try {
    const url = getFilePreviewUrl(props.fileId)
    pdfDoc = await pdfjsLib.getDocument(url).promise
    pdfTotalPages.value = pdfDoc.numPages
    if (pdfCurrentPage.value > pdfTotalPages.value) pdfCurrentPage.value = 1
    await nextTick()
    await renderPdfPage(pdfCurrentPage.value)
  } catch (err) {
    error.value = `PDF 加载失败: ${err.message}`
  }
  loading.value = false
}

async function renderPdfPage(pageNum) {
  if (!pdfDoc) return
  if (renderTask) { try { renderTask.cancel() } catch {}; renderTask = null }

  const page = await pdfDoc.getPage(pageNum)
  const viewport = page.getViewport({ scale: pdfScale.value })

  const canvas = canvasRef.value
  if (!canvas) {
    await nextTick()
    if (!canvasRef.value) return
  }
  const c = canvasRef.value
  const dpr = window.devicePixelRatio || 1
  c.width = viewport.width * dpr
  c.height = viewport.height * dpr
  c.style.width = viewport.width + 'px'
  c.style.height = viewport.height + 'px'
  const ctx = c.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

  renderTask = page.render({ canvasContext: ctx, viewport })
  await renderTask.promise

  const tld = textLayerRef.value
  if (tld) {
    tld.innerHTML = ''
    tld.style.width = viewport.width + 'px'
    tld.style.height = viewport.height + 'px'

    const textContent = await page.getTextContent()
    const textLayer = new pdfjsLib.TextLayer({
      textContentSource: textContent,
      container: tld,
      viewport,
    })
    await textLayer.render()

    await nextTick()
    highlightInTextLayer(tld)
  }

  pdfCurrentPage.value = pageNum
}

function highlightInTextLayer(textLayerDiv) {
  const chunkText = props.chunkText
  if (!chunkText || chunkText.length < 10) return

  const spans = Array.from(textLayerDiv.querySelectorAll('span'))
  if (spans.length === 0) return

  const spanData = []
  let charOffset = 0
  const allText = []
  for (const span of spans) {
    const t = span.textContent || ''
    if (!t) continue
    spanData.push({ span, start: charOffset, end: charOffset + t.length, text: t })
    allText.push(t)
    charOffset += t.length
  }

  if (spanData.length === 0) return
  const fullText = allText.join('')

  const clean = s => s.replace(/\s+/g, '')
  const needleClean = clean(chunkText)
  const haystackClean = clean(fullText)

  let matchCleanStart = haystackClean.indexOf(needleClean)
  let matchCleanEnd

  if (matchCleanStart === -1) {
    const sub = chunkText.substring(10, Math.min(90, chunkText.length))
    const subClean = clean(sub)
    matchCleanStart = haystackClean.indexOf(subClean)
    if (matchCleanStart === -1) {
      const prefix = clean(chunkText.substring(0, 60))
      matchCleanStart = haystackClean.indexOf(prefix)
      if (matchCleanStart === -1) return
      matchCleanEnd = matchCleanStart + prefix.length
    } else {
      matchCleanEnd = matchCleanStart + subClean.length
    }
  } else {
    matchCleanEnd = matchCleanStart + needleClean.length
  }
  if (matchCleanEnd === undefined) matchCleanEnd = matchCleanStart + needleClean.length

  const matchOrigStart = mapCleanToOrig(fullText, matchCleanStart)
  const matchOrigEnd = mapCleanToOrig(fullText, matchCleanEnd)

  // Collect Y positions of matched spans for full-line highlight
  const wrap = textLayerDiv.parentElement
  const wrapRect = wrap.getBoundingClientRect()

  const lineYs = new Map()
  for (const sd of spanData) {
    if (sd.start < matchOrigEnd && sd.end > matchOrigStart) {
      const rect = sd.span.getBoundingClientRect()
      const y = Math.round(rect.top - wrapRect.top)
      if (!lineYs.has(y)) {
        lineYs.set(y, rect.height)
      }
    }
  }

  // Create highlight overlay with full-width line bars
  let hl = wrap.querySelector('.pdf-hl')
  if (!hl) {
    hl = document.createElement('div')
    hl.className = 'pdf-hl'
    hl.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:1;'
    wrap.insertBefore(hl, textLayerDiv)
  }
  hl.innerHTML = ''

  for (const [y, h] of lineYs) {
    const bar = document.createElement('div')
    bar.style.cssText = `position:absolute;left:-4px;right:-4px;top:${y - 1}px;height:${h + 2}px;background:rgba(59,130,246,0.13);border-radius:2px;`
    hl.appendChild(bar)
  }

  const firstBar = hl.firstElementChild
  const previewBody = previewBodyRef.value
  if (firstBar && previewBody) {
    const targetTop = wrap.offsetTop + firstBar.offsetTop - Math.max(40, previewBody.clientHeight * 0.2)
    previewBody.scrollTop = Math.max(0, targetTop)
  }
}

function mapCleanToOrig(origText, cleanPos) {
  let ci = 0
  for (let oi = 0; oi < origText.length; oi++) {
    if (/\s/.test(origText[oi])) continue
    if (ci === cleanPos) return oi
    ci++
  }
  return origText.length
}

function pdfPrevPage() {
  if (pdfCurrentPage.value > 1) {
    loading.value = true
    renderPdfPage(pdfCurrentPage.value - 1).finally(() => { loading.value = false })
  }
}

function pdfNextPage() {
  if (pdfCurrentPage.value < pdfTotalPages.value) {
    loading.value = true
    renderPdfPage(pdfCurrentPage.value + 1).finally(() => { loading.value = false })
  }
}

function pdfZoomIn() {
  pdfScale.value = Math.min(3, pdfScale.value + 0.25)
  renderPdfPage(pdfCurrentPage.value)
}

function pdfZoomOut() {
  pdfScale.value = Math.max(0.5, pdfScale.value - 0.25)
  renderPdfPage(pdfCurrentPage.value)
}

/* ---- TXT/MD preview ---- */

async function loadText() {
  loading.value = true
  error.value = ''
  try {
    textContent.value = await fetchFileContent(props.fileId)
    await nextTick()
    if (highlightRef.value) {
      const pre = highlightRef.value
      const targetScroll = Math.max(0, (props.startOffset || 0) * 0.6 - 100)
      pre.scrollTop = targetScroll

      if (props.chunkText) {
        const escaped = props.chunkText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
        const firstPart = escaped.substring(0, 80)
        const highlightHtml = textContent.value.replace(
          new RegExp(firstPart, 'g'),
          m => `<mark>${m}</mark>`
        )
        if (highlightHtml !== textContent.value) {
          pre.innerHTML = highlightHtml
        }
      }
    }
  } catch (err) {
    error.value = `无法加载文件预览: ${err.message}`
  }
  loading.value = false
}

watch([() => props.visible, () => props.fileId], async ([visible, fileId]) => {
  if (!visible || !fileId) {
    textContent.value = ''
    return
  }
  if (isPdf.value) {
    textContent.value = ''
    await loadPdf()
  } else {
    await loadText()
  }
})

onBeforeUnmount(() => {
  if (renderTask) { try { renderTask.cancel() } catch {} }
  if (pdfDoc) { try { pdfDoc.destroy() } catch {} }
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
        <button class="preview-close" @click="onClose">&times;</button>
      </div>

      <!-- PDF controls -->
      <div class="pdf-controls" v-if="isPdf && !loading && !error">
        <button class="pdf-ctrl-btn" @click="pdfPrevPage" :disabled="pdfCurrentPage <= 1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
        <span class="pdf-page-info">{{ pdfCurrentPage }} / {{ pdfTotalPages }}</span>
        <button class="pdf-ctrl-btn" @click="pdfNextPage" :disabled="pdfCurrentPage >= pdfTotalPages">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
        <span class="pdf-zoom-sep"></span>
        <button class="pdf-ctrl-btn" @click="pdfZoomOut" title="缩小">-</button>
        <span class="pdf-zoom-pct">{{ Math.round(pdfScale * 100) }}%</span>
        <button class="pdf-ctrl-btn" @click="pdfZoomIn" title="放大">+</button>
      </div>

      <div class="preview-body" ref="previewBodyRef">
        <!-- PDF -->
        <template v-if="isPdf">
          <div class="pdf-viewport">
            <div class="pdf-canvas-wrap">
              <canvas ref="canvasRef"></canvas>
              <div class="pdf-text-layer" ref="textLayerRef"></div>
            </div>
          </div>
          <div class="preview-loading-overlay" v-if="loading">
            <span class="spinner"></span> 加载中...
          </div>
          <div class="preview-error-overlay" v-if="error">{{ error }}</div>
        </template>

        <!-- TXT/MD -->
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
  width: min(900px, 90vw); height: min(88vh, 750px);
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

/* PDF controls */
.pdf-controls {
  display: flex; align-items: center; gap: 4px;
  padding: 8px 14px;
  border-bottom: 1px solid #e5e5e5;
  flex-shrink: 0; user-select: none;
}
.pdf-ctrl-btn {
  background: none; border: 1px solid transparent;
  border-radius: 4px; cursor: pointer;
  padding: 4px 6px; color: #555;
  display: flex; align-items: center;
  transition: background 120ms, border-color 120ms;
}
.pdf-ctrl-btn:hover:not(:disabled) {
  background: #f5f5f5; border-color: #ddd;
}
.pdf-ctrl-btn:disabled { opacity: 0.3; cursor: default; }
.pdf-page-info {
  font-size: 12px; color: #555; min-width: 58px; text-align: center;
  font-weight: 500;
}
.pdf-zoom-sep {
  width: 1px; height: 18px; background: #e5e5e5; margin: 0 6px;
}
.pdf-zoom-pct {
  font-size: 11px; color: #888; min-width: 32px; text-align: center;
}

.preview-body {
  flex: 1; overflow: auto;
  position: relative;
  background: #f0f0f0;
}
.pdf-viewport {
  min-height: 100%;
  display: flex; justify-content: center;
}
.pdf-canvas-wrap {
  position: relative;
  margin: 12px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.3);
}
.pdf-canvas-wrap canvas {
  display: block;
  background: #fff;
}
.pdf-text-layer {
  position: absolute; left: 0; top: 0; right: 0; bottom: 0;
  overflow: hidden; line-height: 1; pointer-events: none;
}
.pdf-text-layer :deep(span) {
  color: transparent;
  position: absolute;
  white-space: pre;
  cursor: text;
  transform-origin: 0% 0%;
}

.preview-loading-overlay {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  background: rgba(240,240,240,0.7);
  color: #666; font-size: 14px; gap: 8px;
  z-index: 10;
}
.preview-error-overlay {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  background: rgba(240,240,240,0.9);
  color: #dc2626; font-size: 14px;
  z-index: 10;
}

@keyframes spin { to { transform: rotate(360deg); } }
.spinner {
  width: 18px; height: 18px;
  border: 2px solid #ddd; border-top-color: #666;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  display: inline-block;
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
  color: #444; background: #fff;
}
.preview-text :deep(mark) {
  background: #fef08a; color: #333;
  padding: 1px 0; border-radius: 2px;
}
</style>
