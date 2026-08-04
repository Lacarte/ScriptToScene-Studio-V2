<script setup>
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'
import { useWorkflowStore } from '../stores/workflow.js'
import { PORT_COLORS } from '../constants.js'
import NodeIcon from './NodeIcon.vue'

// Generic card for every node type — rendering is driven entirely by the
// registry definition carried in `data` (Automa BlockBasic pattern).
const props = defineProps({
  id: { type: String, required: true },
  data: { type: Object, required: true },
  selected: { type: Boolean, default: false },
})

const store = useWorkflowStore()

const def = computed(() => store.nodeTypes[props.data.nodeType] || {})
const category = computed(() => store.categories[def.value.category] || {})
const color = computed(() => category.value.color || '#9CA3AF')

const inputs = computed(() => def.value.inputs || [])
const outputs = computed(() => def.value.outputs || [])

function portColor(port) {
  return PORT_COLORS[port.type] || PORT_COLORS.generic_json
}

function handleStyle(port, index, total) {
  return {
    top: `${((index + 1) / (total + 1)) * 100}%`,
    background: portColor(port),
    border: port.type === 'control' ? '1.5px dashed rgba(255,255,255,0.6)' : '1.5px solid rgba(0,0,0,0.45)',
  }
}
</script>

<template>
  <div class="node-card" :class="{ selected, disabled: data.disabled }">
    <span class="node-strip" :style="{ background: color }" />

    <Handle
      v-for="(port, i) in inputs"
      :id="port.id"
      :key="`in-${port.id}`"
      type="target"
      :position="Position.Left"
      class="node-handle"
      :style="handleStyle(port, i, inputs.length)"
      :title="`${port.id} (${port.type})${port.required ? ' — required' : ''}`"
    />

    <div class="node-body">
      <span class="node-icon" :style="{ color }">
        <NodeIcon :icon="def.icon" />
      </span>
      <div class="node-text">
        <span class="node-name">{{ data.label }}</span>
        <span class="node-type">{{ def.display_name }}</span>
      </div>
    </div>

    <Handle
      v-for="(port, i) in outputs"
      :id="port.id"
      :key="`out-${port.id}`"
      type="source"
      :position="Position.Right"
      class="node-handle"
      :style="handleStyle(port, i, outputs.length)"
      :title="`${port.id} (${port.type})`"
    />
  </div>
</template>

<style scoped>
.node-card {
  position: relative;
  min-width: 172px;
  max-width: 220px;
  background: var(--bg-darkest, #101418);
  border: 1px solid var(--border, #2a3138);
  border-radius: 10px;
  color: var(--text, #e5e7eb);
  font-size: 12px;
  transition: border-color 0.15s, box-shadow 0.15s;
}

.node-card.selected {
  border-color: var(--accent, #4ecdc4);
  box-shadow: 0 0 0 1px var(--accent, #4ecdc4), 0 4px 18px rgba(0, 0, 0, 0.35);
}

.node-card.disabled {
  opacity: 0.45;
}

.node-strip {
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 0 3px 3px 0;
}

.node-body {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 10px 14px;
}

.node-icon {
  width: 20px;
  height: 20px;
  min-width: 20px;
}

.node-icon svg {
  width: 100%;
  height: 100%;
}

.node-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.node-name {
  font-weight: 600;
  line-height: 1.25;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-type {
  font-size: 10px;
  color: var(--text-muted, #8b949e);
  line-height: 1.3;
}

.node-handle {
  width: 10px;
  height: 10px;
}
</style>
