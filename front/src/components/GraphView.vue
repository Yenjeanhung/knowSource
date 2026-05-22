<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { fetchGraphRelationTypes, fetchGraphView, fetchKbs, getKb } from '../api'

const ENTITY_COLORS = [
  '#5b7fbc', '#7a9e7e', '#b8a45c', '#c08b7a', '#7b8db0',
  '#8aa88a', '#bc9a5e', '#c48b6e', '#6b90b5', '#8a9e8a',
  '#ab8d5c', '#b8887a', '#728da8', '#87a387', '#a88a5e',
]

const kbs = ref([])
const kbFiles = ref([])
const relationTypes = ref([])

const selectedKbId = ref('')
const selectedFileId = ref('')
const entityQuery = ref('')
const relationType = ref('')
const viewMode = ref('graph')
const showChunkList = ref(false)

const loading = ref(false)
const error = ref('')
const graphData = ref(null)
const selectedNodeId = ref('')
const selectedChunkId = ref('')

// Canvas dimensions (fixed world space)
const WORLD_W = 1600
const WORLD_H = 1000

// Pan & zoom
const viewBox = ref({ x: 0, y: 0, w: WORLD_W, h: WORLD_H })
const defaultViewBox = { x: 0, y: 0, w: WORLD_W, h: WORLD_H }
const zoomLevel = ref(1)
const MIN_ZOOM = 0.25
const MAX_ZOOM = 3

// Force simulation
const svgRef = ref(null)
const nodes = ref([])
const edges = ref([])
const isDragging = ref(false)
const isPanning = ref(false)
const dragNode = ref(null)
const dragOffset = ref({ x: 0, y: 0 })
const panStart = ref({ x: 0, y: 0 })
const panViewBoxStart = ref({ x: 0, y: 0 })
const colorMap = ref({})
const simSettled = ref(false)

const summary = computed(() => graphData.value?.summary || {
  provider: '--', entity_total: 0, relation_total: 0,
  file_count: 0, chunk_count: 0, filtered_result_count: 0,
})

const records = computed(() => graphData.value?.records || [])

const sortedRecords = computed(() => {
  const arr = [...records.value]
  arr.sort((a, b) => String(a.file_name || '').localeCompare(String(b.file_name || '')))
  return arr
})

const selectedChunk = computed(() => records.value.find(item => item.chunk_id === selectedChunkId.value) || null)
const selectedNode = computed(() => nodes.value.find(n => n.id === selectedNodeId.value) || null)

const nodeMap = computed(() => {
  const map = {}
  for (const n of nodes.value) map[n.id] = n
  return map
})

const edgeRenderList = computed(() => {
  const map = nodeMap.value
  return edges.value.map(edge => {
    const sx = map[edge.source]?.x || 0
    const sy = map[edge.source]?.y || 0
    const tx = map[edge.target]?.x || 0
    const ty = map[edge.target]?.y || 0
    const mx = (sx + tx) / 2
    const my = (sy + ty) / 2
    const dx = tx - sx
    const dy = ty - sy
    const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
    const cx = mx - (dy / dist) * dist * 0.15
    const cy = my + (dx / dist) * dist * 0.15
    return { ...edge, sx, sy, tx, ty, mx, my, cx, cy }
  })
})

const selectedNodeEdges = computed(() => {
  if (!selectedNodeId.value) return []
  return edges.value.filter(e => e.source === selectedNodeId.value || e.target === selectedNodeId.value)
})

const groupedRecords = computed(() => {
  const groups = {}
  for (const r of sortedRecords.value) {
    const key = r.file_name || r.file_id
    if (!groups[key]) groups[key] = { file_name: key, rows: [] }
    groups[key].rows.push(r)
  }
  return Object.values(groups)
})

// ======================= Force simulation =======================

function assignColors() {
  const types = new Set()
  for (const r of records.value) {
    for (const e of (r.entities || [])) types.add(e.entity_type || 'UNKNOWN')
  }
  const map = {}
  let i = 0
  for (const t of types) map[t] = ENTITY_COLORS[i++ % ENTITY_COLORS.length]
  colorMap.value = map
}

function buildGraph() {
  const entityMap = new Map()
  const edgeList = []

  for (const record of records.value) {
    for (const entity of (record.entities || [])) {
      const key = (entity.name || '').toLowerCase()
      if (!entityMap.has(key)) {
        entityMap.set(key, {
          id: key, name: entity.name,
          entityType: entity.entity_type || 'UNKNOWN',
          description: entity.description || '',
          chunkIds: [], degree: 0,
        })
      }
      const e = entityMap.get(key)
      if (!e.chunkIds.includes(record.chunk_id)) e.chunkIds.push(record.chunk_id)
    }
  }

  for (const record of records.value) {
    for (const relation of (record.relations || [])) {
      const sKey = (relation.source_name || '').toLowerCase()
      const tKey = (relation.target_name || '').toLowerCase()
      if (!entityMap.has(sKey)) {
        entityMap.set(sKey, { id: sKey, name: relation.source_name, entityType: relation.source_type || 'UNKNOWN', description: '', chunkIds: [], degree: 0 })
      }
      if (!entityMap.has(tKey)) {
        entityMap.set(tKey, { id: tKey, name: relation.target_name, entityType: relation.target_type || 'UNKNOWN', description: '', chunkIds: [], degree: 0 })
      }
      const edgeKey = `${sKey}|||${relation.relation_type}|||${tKey}`
      if (!edgeList.some(e => e.key === edgeKey)) {
        edgeList.push({ key: edgeKey, source: sKey, target: tKey, label: relation.relation_type })
        entityMap.get(sKey).degree++
        entityMap.get(tKey).degree++
      }
    }
  }

  const entityList = Array.from(entityMap.values())
  entityList.sort((a, b) => b.degree - a.degree)

  const cx = WORLD_W / 2
  const cy = WORLD_H / 2
  const radius = Math.min(WORLD_W, WORLD_H) * 0.38

  const nodeList = entityList.map((e, index) => {
    let x, y
    if (entityList.length === 1) {
      x = cx; y = cy
    } else if (index < 5) {
      const angle = (index / 5) * Math.PI * 2
      x = cx + Math.cos(angle) * radius * 0.15
      y = cy + Math.sin(angle) * radius * 0.15
    } else {
      const angle = ((index - 5) / (entityList.length - 5)) * Math.PI * 2
      const r = radius * (0.55 + Math.random() * 0.45)
      x = cx + Math.cos(angle) * r
      y = cy + Math.sin(angle) * r
    }
    return { ...e, x, y, vx: 0, vy: 0 }
  })

  nodes.value = nodeList
  edges.value = edgeList
  simSettled.value = false
  viewBox.value = { ...defaultViewBox }
  zoomLevel.value = 1
}

function simulationStep() {
  const nodeArr = nodes.value
  const edgeArr = edges.value
  if (!nodeArr.length) return 0

  const repulsion = 4000
  const attraction = 0.002
  const gravity = 0.003
  const damping = 0.8
  const minDist = 50

  const neighbors = new Map()
  for (const n of nodeArr) neighbors.set(n.id, new Set())
  for (const e of edgeArr) {
    if (neighbors.has(e.source)) neighbors.get(e.source).add(e.target)
    if (neighbors.has(e.target)) neighbors.get(e.target).add(e.source)
  }

  let maxSpeed = 0

  for (let i = 0; i < nodeArr.length; i++) {
    const a = nodeArr[i]
    if (a === dragNode.value) continue

    let fx = 0, fy = 0

    for (let j = 0; j < nodeArr.length; j++) {
      if (i === j) continue
      const b = nodeArr[j]
      const dx = a.x - b.x
      const dy = a.y - b.y
      const dist = Math.max(minDist, Math.sqrt(dx * dx + dy * dy))
      const force = repulsion / (dist * dist)
      fx += (dx / dist) * force
      fy += (dy / dist) * force
    }

    const myNeighbors = neighbors.get(a.id) || new Set()
    for (const nid of myNeighbors) {
      const b = nodeArr.find(n => n.id === nid)
      if (!b) continue
      fx += (b.x - a.x) * attraction
      fy += (b.y - a.y) * attraction
    }

    fx += (WORLD_W / 2 - a.x) * gravity
    fy += (WORLD_H / 2 - a.y) * gravity

    a.vx = (a.vx + fx) * damping
    a.vy = (a.vy + fy) * damping
    a.x += a.vx
    a.y += a.vy

    a.x = Math.max(40, Math.min(WORLD_W - 40, a.x))
    a.y = Math.max(40, Math.min(WORLD_H - 40, a.y))

    const speed = Math.sqrt(a.vx * a.vx + a.vy * a.vy)
    if (speed > maxSpeed) maxSpeed = speed
  }

  return maxSpeed
}

function getNodeColor(node) {
  return colorMap.value[node.entityType] || '#8899aa'
}

function getNodeRadius(node) {
  if (node.id === selectedNodeId.value) return 24
  const base = 14
  const extra = Math.min(node.degree * 4, 22)
  return base + extra
}

function getNodeLabel(node) {
  return node.name.length > 22 ? node.name.slice(0, 20) + '..' : node.name
}

// ======================= Pan & Zoom =======================

function zoomIn() {
  const newZoom = Math.min(MAX_ZOOM, zoomLevel.value * 1.4)
  applyZoom(newZoom)
}

function zoomOut() {
  const newZoom = Math.max(MIN_ZOOM, zoomLevel.value / 1.4)
  applyZoom(newZoom)
}

function zoomReset() {
  viewBox.value = { ...defaultViewBox }
  zoomLevel.value = 1
}

function applyZoom(newZoom) {
  const vb = viewBox.value
  const centerX = vb.x + vb.w / 2
  const centerY = vb.y + vb.h / 2
  const newW = WORLD_W / newZoom
  const newH = WORLD_H / newZoom
  viewBox.value = {
    x: centerX - newW / 2,
    y: centerY - newH / 2,
    w: newW,
    h: newH,
  }
  zoomLevel.value = newZoom
}

function onWheel(event) {
  event.preventDefault()
  const delta = event.deltaY > 0 ? 0.85 : 1.15
  const newZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoomLevel.value * delta))
  // Zoom toward mouse position
  const svg = svgRef.value
  if (!svg) { applyZoom(newZoom); return }
  const rect = svg.getBoundingClientRect()
  const mouseX = event.clientX - rect.left
  const mouseY = event.clientY - rect.top
  const svgW = rect.width
  const svgH = rect.height
  const vb = viewBox.value
  const worldX = vb.x + (mouseX / svgW) * vb.w
  const worldY = vb.y + (mouseY / svgH) * vb.h

  const newW = WORLD_W / newZoom
  const newH = WORLD_H / newZoom
  viewBox.value = {
    x: worldX - (mouseX / svgW) * newW,
    y: worldY - (mouseY / svgH) * newH,
    w: newW,
    h: newH,
  }
  zoomLevel.value = newZoom
}

// ======================= Mouse Events =======================

function getSvgPoint(event) {
  const svg = svgRef.value
  if (!svg) return { x: 0, y: 0 }
  const pt = svg.createSVGPoint()
  pt.x = event.clientX
  pt.y = event.clientY
  const ctm = svg.getScreenCTM()
  if (!ctm) return { x: event.clientX, y: event.clientY }
  const transformed = pt.matrixTransform(ctm.inverse())
  return { x: transformed.x, y: transformed.y }
}

function onNodeMouseDown(event, node) {
  event.stopPropagation()
  event.preventDefault()
  isDragging.value = true
  dragNode.value = node
  const pt = getSvgPoint(event)
  dragOffset.value = { x: pt.x - node.x, y: pt.y - node.y }
}

function onSvgBackgroundMouseDown(event) {
  // Only pan if clicking on empty canvas (not a node)
  if (event.target === svgRef.value || event.target.classList.contains('bg-rect')) {
    isPanning.value = true
    panStart.value = { x: event.clientX, y: event.clientY }
    panViewBoxStart.value = { x: viewBox.value.x, y: viewBox.value.y }
  }
}

function onSvgMouseMove(event) {
  if (isDragging.value && dragNode.value) {
    const pt = getSvgPoint(event)
    dragNode.value.x = pt.x - dragOffset.value.x
    dragNode.value.y = pt.y - dragOffset.value.y
    dragNode.value.vx = 0
    dragNode.value.vy = 0
    return
  }
  if (isPanning.value) {
    const dx = event.clientX - panStart.value.x
    const dy = event.clientY - panStart.value.y
    const svg = svgRef.value
    if (!svg) return
    const rect = svg.getBoundingClientRect()
    const scaleX = viewBox.value.w / rect.width
    const scaleY = viewBox.value.h / rect.height
    viewBox.value = {
      ...viewBox.value,
      x: panViewBoxStart.value.x - dx * scaleX,
      y: panViewBoxStart.value.y - dy * scaleY,
    }
  }
}

function onSvgMouseUp() {
  if (isDragging.value && dragNode.value) {
    dragNode.value.vx = 0
    dragNode.value.vy = 0
  }
  isDragging.value = false
  dragNode.value = null
  isPanning.value = false
}

function onNodeClick(node) {
  selectedNodeId.value = node.id
  selectedChunkId.value = node.chunkIds[0] || ''
}

// ======================= Simulation loop =======================

let simTimer = null
let settleCounter = 0

function startSimulation() {
  stopSimulation()
  settleCounter = 0
  function tick() {
    let maxSpeed = 0
    for (let i = 0; i < 3; i++) {
      const speed = simulationStep()
      if (speed > maxSpeed) maxSpeed = speed
    }
    if (!isDragging.value && maxSpeed < 0.03) {
      settleCounter++
      if (settleCounter > 120) {
        simSettled.value = true
        simTimer = null
        return
      }
    } else {
      settleCounter = 0
      simSettled.value = false
    }
    simTimer = requestAnimationFrame(tick)
  }
  simTimer = requestAnimationFrame(tick)
}

function stopSimulation() {
  if (simTimer) { cancelAnimationFrame(simTimer); simTimer = null }
}

// ======================= Data loading =======================

async function loadKbs() {
  try { kbs.value = await fetchKbs() } catch { kbs.value = [] }
}

async function loadKbFiles() {
  if (!selectedKbId.value) { kbFiles.value = []; return }
  try { const kb = await getKb(selectedKbId.value); kbFiles.value = kb.files || [] } catch { kbFiles.value = [] }
}

async function loadRelationTypes() {
  if (!selectedKbId.value) { relationTypes.value = []; return }
  try {
    const data = await fetchGraphRelationTypes({ kbId: selectedKbId.value, fileId: selectedFileId.value })
    relationTypes.value = data.items || []
  } catch { relationTypes.value = [] }
}

async function loadView() {
  if (!selectedKbId.value) { graphData.value = null; return }
  loading.value = true; error.value = ''
  try {
    const data = await fetchGraphView({
      kbId: selectedKbId.value, fileId: selectedFileId.value,
      entityQuery: entityQuery.value.trim(), relationType: relationType.value,
    })
    graphData.value = data
    assignColors(); buildGraph(); startSimulation()
    selectedNodeId.value = ''
    selectedChunkId.value = records.value[0]?.chunk_id || ''
  } catch (err) {
    error.value = err.message || '加载图谱失败'
    graphData.value = null; stopSimulation()
  } finally { loading.value = false }
}

async function onKbChange() {
  selectedFileId.value = ''; relationType.value = ''; entityQuery.value = ''
  await loadKbFiles(); await loadRelationTypes(); await loadView()
}
async function onFileChange() { relationType.value = ''; await loadRelationTypes(); await loadView() }
async function submitFilters() { await loadView() }

function selectChunk(record) {
  selectedChunkId.value = record.chunk_id
}

onMounted(async () => {
  await loadKbs()
  if (kbs.value.length) { selectedKbId.value = kbs.value[0].id; await onKbChange() }
})
onUnmounted(() => stopSimulation())
</script>

<template>
  <div class="graph-page">
    <div class="graph-toolbar">
      <div>
        <div class="toolbar-title">图谱</div>
        <div class="toolbar-subtitle">实体关系图谱 &mdash; 滚轮缩放，拖拽画布/节点，点击节点查看详情</div>
      </div>
      <div class="toolbar-right">
        <div class="view-toggle">
          <button class="toggle-btn" :class="{ on: viewMode === 'graph' }" @click="viewMode = 'graph'">图谱视图</button>
          <button class="toggle-btn" :class="{ on: viewMode === 'list' }" @click="viewMode = 'list'">列表视图</button>
        </div>
        <div class="toolbar-meta">
          <span class="meta-chip">实体 {{ nodes.length }}</span>
          <span class="meta-chip">关系 {{ edges.length }}</span>
          <span v-if="viewMode === 'graph'" class="meta-chip">{{ Math.round(zoomLevel * 100) }}%</span>
        </div>
      </div>
    </div>

    <section class="graph-card filter-card">
      <div class="graph-filters">
        <select v-model="selectedKbId" @change="onKbChange">
          <option value="">选择知识库</option>
          <option v-for="kb in kbs" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
        </select>
        <select v-model="selectedFileId" :disabled="!selectedKbId" @change="onFileChange">
          <option value="">全部文件</option>
          <option v-for="file in kbFiles" :key="file.id" :value="file.id">{{ file.name }}</option>
        </select>
        <input v-model="entityQuery" type="text" placeholder="搜索实体关键词..." :disabled="!selectedKbId" @keydown.enter="submitFilters">
        <select v-model="relationType" :disabled="!selectedKbId">
          <option value="">全部关系类型</option>
          <option v-for="item in relationTypes" :key="item" :value="item">{{ item }}</option>
        </select>
        <button class="btn primary" :disabled="!selectedKbId || loading" @click="submitFilters">查询</button>
      </div>
    </section>

    <!-- ====== GRAPH VIEW ====== -->
    <section v-if="viewMode === 'graph'" class="graph-card main-card graph-mode">
      <div v-if="!selectedKbId" class="empty-state">
        <div class="title">先选择一个知识库</div>
        <div class="desc">图谱页会基于当前知识库和文件范围加载实体与关系。</div>
      </div>
      <div v-else-if="loading" class="loading-row"><span class="spinner"></span>加载图谱中...</div>
      <div v-else-if="error" class="error-text">{{ error }}</div>
      <div v-else-if="!records.length" class="empty-state">
        <div class="title">当前筛选条件下没有图谱结果</div>
        <div class="desc">可以换一个文件、清空关系筛选，或尝试更宽松的实体关键词。</div>
      </div>
      <div v-else class="graph-main">
        <div class="graph-canvas-wrap">
          <div class="graph-legend">
            <span v-for="(color, etype) in colorMap" :key="etype" class="legend-chip">
              <span class="legend-dot" :style="{ background: color }"></span>{{ etype }}
            </span>
          </div>
          <div class="graph-canvas" :class="{ panning: isPanning }">
            <svg
              ref="svgRef"
              :viewBox="`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`"
              class="graph-svg"
              preserveAspectRatio="xMidYMid meet"
              @mousedown="onSvgBackgroundMouseDown"
              @mousemove="onSvgMouseMove"
              @mouseup="onSvgMouseUp"
              @mouseleave="onSvgMouseUp"
              @wheel.prevent="onWheel"
            >
              <defs>
                <radialGradient id="nodeGrad" cx="38%" cy="32%">
                  <stop offset="0%" stop-color="white" stop-opacity="0.5" />
                  <stop offset="60%" stop-color="white" stop-opacity="0.06" />
                  <stop offset="100%" stop-color="black" stop-opacity="0.15" />
                </radialGradient>
                <filter id="nodeShadow">
                  <feDropShadow dx="0" dy="1.5" stdDeviation="2.5" flood-color="#000" flood-opacity="0.35" />
                </filter>
                <filter id="nodeGlow">
                  <feGaussianBlur stdDeviation="5" result="blur" />
                  <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
                </filter>
                <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                  <polygon points="0 0, 8 3, 0 6" fill="rgba(255,255,255,0.18)" />
                </marker>
              </defs>

              <!-- Background rect for panning -->
              <rect class="bg-rect" x="0" y="0" :width="WORLD_W" :height="WORLD_H" fill="transparent" />

              <!-- Edges -->
              <g class="graph-edges">
                <path
                  v-for="edge in edgeRenderList"
                  :key="edge.key"
                  :d="`M ${edge.sx} ${edge.sy} Q ${edge.cx} ${edge.cy} ${edge.tx} ${edge.ty}`"
                  class="graph-edge"
                  :class="{ 'edge-highlight': selectedNodeId && (edge.source === selectedNodeId || edge.target === selectedNodeId) }"
                  fill="none"
                  marker-end="url(#arrowhead)"
                />
              </g>

              <!-- Edge labels -->
              <g class="edge-labels">
                <text
                  v-for="edge in edgeRenderList"
                  :key="'el-' + edge.key"
                  :x="edge.mx" :y="edge.my"
                  class="edge-label"
                  :class="{ 'edge-label-hl': selectedNodeId && (edge.source === selectedNodeId || edge.target === selectedNodeId) }"
                >{{ edge.label }}</text>
              </g>

              <!-- Nodes -->
              <g class="graph-nodes">
                <g
                  v-for="node in nodes"
                  :key="node.id"
                  class="graph-node"
                  :class="{ selected: node.id === selectedNodeId }"
                  :transform="`translate(${node.x}, ${node.y})`"
                  @mousedown.prevent="onNodeMouseDown($event, node)"
                  @click="onNodeClick(node)"
                >
                  <circle
                    :r="getNodeRadius(node) + 8"
                    class="node-glow-ring"
                    :class="{ active: node.id === selectedNodeId }"
                    :stroke="getNodeColor(node)"
                    fill="none"
                  />
                  <circle
                    :r="getNodeRadius(node)"
                    :fill="getNodeColor(node)"
                    class="node-circle"
                    :filter="node.id === selectedNodeId ? 'url(#nodeGlow)' : 'url(#nodeShadow)'"
                  />
                  <circle
                    :r="getNodeRadius(node)"
                    fill="url(#nodeGrad)"
                    class="node-highlight"
                    pointer-events="none"
                  />
                  <text
                    :y="getNodeRadius(node) + 18"
                    class="node-label"
                    :class="{ bold: node.id === selectedNodeId }"
                  >{{ getNodeLabel(node) }}</text>
                </g>
              </g>
            </svg>

            <!-- Zoom controls -->
            <div class="zoom-controls">
              <button class="zoom-btn" @click="zoomIn" title="放大">+</button>
              <button class="zoom-btn" @click="zoomReset" title="重置">{{ Math.round(zoomLevel * 100) }}%</button>
              <button class="zoom-btn" @click="zoomOut" title="缩小">&minus;</button>
            </div>
          </div>
        </div>

        <aside class="graph-inspector">
          <div class="inspector-title">详情</div>
          <template v-if="selectedNode">
            <div class="inspector-card">
              <div class="inspector-name">
                <span class="entity-dot" :style="{ background: getNodeColor(selectedNode) }"></span>
                {{ selectedNode.name }}
              </div>
              <div class="inspector-sub">{{ selectedNode.entityType }}</div>
              <div v-if="selectedNode.description" class="inspector-desc">{{ selectedNode.description }}</div>
              <div class="detail-section">
                <div class="detail-label">关联关系 ({{ selectedNodeEdges.length }})</div>
                <div class="relation-list">
                  <div v-for="edge in selectedNodeEdges" :key="edge.key" class="relation-item">
                    <span class="rel-source">{{ edge.source === selectedNode.id ? selectedNode.name : (nodeMap[edge.source] || {}).name || edge.source }}</span>
                    <span class="rel-type">{{ edge.label }}</span>
                    <span class="rel-target">{{ edge.target === selectedNode.id ? selectedNode.name : (nodeMap[edge.target] || {}).name || edge.target }}</span>
                  </div>
                  <div v-if="!selectedNodeEdges.length" class="no-rels">无关联关系</div>
                </div>
              </div>
            </div>
          </template>
          <div v-else class="empty-inline">点击图中的实体节点查看关联关系和详细信息。</div>
        </aside>
      </div>
    </section>

    <!-- ====== LIST VIEW ====== -->
    <section v-if="viewMode === 'list'" class="graph-card main-card list-mode">
      <div v-if="!selectedKbId" class="empty-state"><div class="title">先选择一个知识库</div></div>
      <div v-else-if="loading" class="loading-row"><span class="spinner"></span> 加载中...</div>
      <div v-else-if="error" class="error-text">{{ error }}</div>
      <div v-else-if="!records.length" class="empty-state"><div class="title">没有图谱结果</div></div>
      <div v-else class="list-main">
        <section v-for="file in groupedRecords" :key="file.file_name" class="file-section">
          <div class="file-head">
            <div class="file-title">{{ file.file_name }}</div>
            <div class="file-sub">{{ file.rows.length }} 个分片</div>
          </div>
          <div class="record-grid">
            <article
              v-for="record in file.rows"
              :key="record.chunk_id"
              class="record-card"
              :class="{ active: selectedChunkId === record.chunk_id }"
              @click="selectChunk(record)"
            >
              <div class="record-head">
                <strong>Chunk {{ record.chunk_index }}</strong>
                <span>{{ record.entity_count }} 实体 · {{ record.relation_count }} 关系</span>
              </div>
              <div class="record-preview">{{ (record.content_preview || '').slice(0, 200) }}</div>
              <div class="chip-list" v-if="record.entities?.length">
                <span v-for="entity in record.entities.slice(0, 5)" :key="entity.entity_id" class="entity-chip">
                  {{ entity.name }}
                  <small>{{ entity.entity_type }}</small>
                </span>
              </div>
            </article>
          </div>
        </section>
      </div>
    </section>

    <!-- ====== Collapsible chunk list (graph mode) ====== -->
    <section v-if="viewMode === 'graph' && records.length" class="chunk-section">
      <button class="chunk-toggle" @click="showChunkList = !showChunkList">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline v-if="!showChunkList" points="6 9 12 15 18 9" />
          <polyline v-else points="18 15 12 9 6 15" />
        </svg>
        分片列表 ({{ records.length }})
        <span v-if="!showChunkList" class="chunk-toggle-hint">点击展开</span>
      </button>
      <div v-if="showChunkList" class="chunk-grid-compact">
        <article
          v-for="record in sortedRecords"
          :key="record.chunk_id"
          class="chunk-card"
          :class="{ active: selectedChunkId === record.chunk_id }"
          @click="selectedChunkId = record.chunk_id"
        >
          <div class="chunk-head">
            <strong>{{ record.file_name }} / Chunk {{ record.chunk_index }}</strong>
            <span>{{ record.entity_count }}E {{ record.relation_count }}R</span>
          </div>
          <div class="chunk-preview">{{ (record.content_preview || '').slice(0, 120) }}</div>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.graph-page { display: flex; flex-direction: column; gap: 14px; }

.graph-toolbar {
  display: flex; justify-content: space-between; align-items: flex-end;
  gap: 16px; flex-wrap: wrap;
}
.toolbar-title { font-size: 24px; font-weight: 700; letter-spacing: -0.02em; }
.toolbar-subtitle { margin-top: 4px; color: var(--c-secondary); font-size: 13px; }
.toolbar-right { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.toolbar-meta { display: flex; flex-wrap: wrap; gap: 8px; }
.meta-chip {
  padding: 5px 10px; border: 1px solid var(--c-border); border-radius: 999px;
  background: var(--c-panel); color: var(--c-secondary); font-size: 12px; font-weight: 500;
}

.view-toggle { display: inline-flex; border: 1px solid var(--c-border); border-radius: 10px; overflow: hidden; }
.toggle-btn {
  height: 36px; padding: 0 16px; border: 0; background: transparent;
  color: var(--c-secondary); font-weight: 600; font-size: 12px; cursor: pointer;
}
.toggle-btn.on { background: var(--c-fg); color: var(--c-bg); }

.graph-card { background: var(--c-panel); border: 1px solid var(--c-border); border-radius: 18px; }
.filter-card { padding: 16px; }

.graph-filters {
  display: grid;
  grid-template-columns: 160px 180px minmax(160px, 1fr) 150px 70px;
  gap: 10px; align-items: center;
}
.graph-filters select, .graph-filters input {
  height: 40px; padding: 0 12px; border: 1px solid var(--c-border);
  border-radius: 10px; background: var(--c-panel); color: var(--c-fg); font-size: 13px; outline: none;
}

/* Graph mode */
.graph-mode { padding: 16px; }
.graph-main { display: grid; grid-template-columns: minmax(0, 1fr) 290px; gap: 14px; align-items: start; }
.graph-canvas-wrap { min-width: 0; position: relative; }

.graph-legend { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.legend-chip {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px; font-weight: 600; color: var(--c-secondary);
}
.legend-dot { width: 10px; height: 10px; border-radius: 50%; }

.graph-canvas {
  position: relative;
  border: 1px solid var(--c-border); border-radius: 16px; overflow: hidden;
  background:
    radial-gradient(ellipse at 25% 25%, rgba(100,130,160,0.06), transparent 50%),
    radial-gradient(ellipse at 75% 70%, rgba(120,140,120,0.05), transparent 50%),
    #11161c;
  cursor: grab;
  min-height: 500px;
}
.graph-canvas.panning { cursor: grabbing; }
.graph-svg { width: 100%; display: block; }

/* Zoom controls */
.zoom-controls {
  position: absolute; bottom: 12px; right: 12px;
  display: flex; gap: 2px;
  background: rgba(22,27,34,0.92); border: 1px solid rgba(255,255,255,0.1);
  border-radius: 10px; padding: 3px; backdrop-filter: blur(8px);
}
.zoom-btn {
  width: 34px; height: 30px; display: inline-flex; align-items: center; justify-content: center;
  border: 0; border-radius: 7px; background: transparent;
  color: #c9d1d9; font-size: 12px; font-weight: 600; cursor: pointer;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  transition: background 120ms;
}
.zoom-btn:hover { background: rgba(255,255,255,0.08); }
.zoom-btn:nth-child(2) { width: auto; min-width: 44px; font-size: 10px; }

.graph-edge {
  stroke: rgba(255,255,255,0.09);
  stroke-width: 1.1;
  transition: stroke 250ms, stroke-width 250ms;
}
.graph-edge.edge-highlight { stroke: rgba(255,255,255,0.35); stroke-width: 2; }

.edge-label {
  fill: rgba(255,255,255,0.16); font-size: 10px; text-anchor: middle; pointer-events: none;
}
.edge-label-hl { fill: rgba(255,255,255,0.5); font-weight: 600; }

.graph-node { cursor: pointer; }

.node-glow-ring {
  stroke-width: 1.5; opacity: 0; transition: opacity 250ms;
}
.node-glow-ring.active { opacity: 0.25; }

.node-circle { transition: r 200ms ease; }
.node-highlight { pointer-events: none; }

.node-label {
  fill: rgba(255,255,255,0.7); font-size: 12px; text-anchor: middle;
  pointer-events: none; font-weight: 500;
  text-shadow: 0 1px 4px rgba(0,0,0,0.7);
}
.node-label.bold { fill: #fff; font-weight: 700; font-size: 13px; }

/* Inspector */
.graph-inspector {
  border: 1px solid var(--c-border); border-radius: 16px; padding: 14px;
  background: var(--c-panel); position: sticky; top: 16px;
  max-height: calc(100vh - 120px); overflow: auto;
}
.inspector-title { font-size: 14px; font-weight: 700; margin-bottom: 10px; }
.inspector-card { display: flex; flex-direction: column; gap: 10px; }
.inspector-name { font-size: 16px; font-weight: 700; display: flex; align-items: center; gap: 8px; }
.entity-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
.inspector-sub { color: var(--c-secondary); font-size: 12px; }
.inspector-desc { font-size: 12px; color: var(--c-secondary); line-height: 1.5; }
.detail-section { display: flex; flex-direction: column; gap: 6px; }
.detail-label { font-size: 11px; font-weight: 700; color: var(--c-secondary); text-transform: uppercase; letter-spacing: 0.04em; }
.relation-list { display: flex; flex-direction: column; gap: 4px; }
.relation-item {
  display: grid; grid-template-columns: 1fr auto 1fr; gap: 6px; align-items: center;
  padding: 6px 8px; border-radius: 8px; background: var(--c-muted); font-size: 12px;
}
.rel-source, .rel-target { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rel-type { color: var(--c-secondary); font-weight: 700; text-align: center; font-size: 10px; }
.no-rels { color: var(--c-secondary); font-size: 11px; font-style: italic; }
.empty-inline { color: var(--c-secondary); font-size: 13px; }

/* Chunk toggle */
.chunk-section { margin-top: 2px; }
.chunk-toggle {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 8px 14px; border: 1px solid var(--c-border); border-radius: 12px;
  background: var(--c-panel); color: var(--c-secondary); font-size: 12px; font-weight: 600; cursor: pointer;
  transition: all 150ms;
}
.chunk-toggle:hover { color: var(--c-fg); border-color: var(--c-fg); }
.chunk-toggle-hint { font-weight: 400; opacity: 0.5; font-size: 11px; }

.chunk-grid-compact {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 8px; margin-top: 10px;
}
.chunk-card {
  padding: 10px 12px; border: 1px solid var(--c-border); border-radius: 12px;
  cursor: pointer; transition: border-color 150ms;
}
.chunk-card.active { border-color: var(--c-accent); }
.chunk-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-size: 11px; }
.chunk-head span { color: var(--c-secondary); font-size: 10px; }
.chunk-preview {
  margin-top: 6px; font-size: 11px; color: var(--c-secondary); line-height: 1.5;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden;
}

/* List mode */
.list-mode { padding: 16px; }
.list-main { display: flex; flex-direction: column; gap: 14px; }
.file-section + .file-section { border-top: 1px solid var(--c-border); padding-top: 12px; }
.file-head { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; margin-bottom: 10px; }
.file-title { font-size: 14px; font-weight: 700; }
.file-sub { color: var(--c-secondary); font-size: 12px; }
.record-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }
.record-card {
  padding: 12px 14px; border: 1px solid var(--c-border); border-radius: 14px;
  cursor: pointer; transition: border-color 150ms;
}
.record-card.active { border-color: var(--c-accent); box-shadow: 0 0 0 3px rgba(161,98,7,0.08); }
.record-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; font-size: 12px; }
.record-head span { color: var(--c-secondary); }
.record-preview {
  margin-top: 8px; font-size: 13px; color: var(--c-fg); line-height: 1.6;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; overflow: hidden;
}
.chip-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.entity-chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 8px; border: 1px solid var(--c-border); border-radius: 999px;
  font-size: 11px; font-weight: 600;
}
.entity-chip small { opacity: 0.5; font-size: 10px; }

/* Shared */
.empty-state { text-align: center; padding: 32px 16px; color: var(--c-secondary); }
.empty-state .title { font-size: 15px; font-weight: 600; color: var(--c-fg); }
.empty-state .desc { margin-top: 6px; font-size: 13px; }
.loading-row { display: flex; align-items: center; gap: 8px; padding: 24px 0; color: var(--c-secondary); font-size: 14px; }
.error-text { color: var(--c-danger); padding: 12px 0; }

@media (max-width: 1100px) {
  .graph-filters { grid-template-columns: 1fr 1fr; }
  .graph-main { grid-template-columns: 1fr; }
  .graph-inspector { position: static; max-height: none; }
}

@media (max-width: 720px) {
  .graph-toolbar { flex-direction: column; align-items: stretch; }
  .toolbar-right { justify-content: space-between; }
  .graph-filters { grid-template-columns: 1fr; }
  .chunk-grid-compact { grid-template-columns: 1fr; }
  .record-grid { grid-template-columns: 1fr; }
  .graph-canvas { min-height: 360px; }
}
</style>
