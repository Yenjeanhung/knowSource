<script setup>
const props = defineProps({
  node: { type: Object, required: true },
  expanded: { type: Set, required: true },
  selectedId: { type: String, default: '' }
})

const emit = defineEmits(['toggle', 'select'])
</script>

<template>
  <div class="picker-folder-node">
    <div
      :class="['folder-tree-item', { active: selectedId === node.id }]"
      @click="() => emit('select', node.id)"
    >
      <button
        v-if="node.children.length > 0"
        class="expand-btn"
        @click.stop="emit('toggle', node.id)"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :style="{ transform: expanded.has(node.id) ? 'rotate(90deg)' : '' }">
          <polyline points="9 18 15 12 9 6"/>
        </svg>
      </button>
      <span v-else class="expand-spacer"></span>
      <div class="icon-wrapper">
        <svg class="folder-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
        </svg>
        <span v-if="(node.file_count || 0) > 0" class="file-badge">{{ node.file_count }}</span>
      </div>
      <span class="folder-name">{{ node.name }}</span>
    </div>
    <div v-if="node.children.length > 0 && expanded.has(node.id)" class="folder-children">
      <AssetPickerTreeNode
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :expanded="expanded"
        :selected-id="selectedId"
        @toggle="emit('toggle', $event)"
        @select="emit('select', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.picker-folder-node .folder-tree-item { padding-left: 0; }
.picker-folder-node .folder-children { margin-left: 16px; }

.icon-wrapper {
  position: relative;
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

.folder-icon {
  width: 18px;
  height: 18px;
  color: #f59e0b;
}

.file-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 14px;
  height: 14px;
  padding: 0 4px;
  background-color: #374151;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  border: 1px solid #4b5563;
}
</style>