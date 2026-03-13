<script setup>
defineOptions({ name: 'AlignmentPicker' })

defineProps({
  show: { type: Boolean, required: true },
  items: { type: Array, default: () => [] },
})

const emit = defineEmits(['select', 'close'])

function formatDate(ts) {
  if (!ts) return '--'
  const d = new Date(ts)
  return d.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatDuration(seconds) {
  if (seconds == null) return '--'
  const m = Math.floor(seconds / 60)
  const s = (seconds % 60).toFixed(1)
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="picker-overlay" @click.self="emit('close')">
      <div class="picker-dialog">
        <div class="picker-header">
          <h3 class="picker-title">Pick Alignment</h3>
          <button class="picker-close" @click="emit('close')">&times;</button>
        </div>

        <div v-if="!items.length" class="picker-empty">
          No alignment history found. Run timing first.
        </div>

        <div v-else class="picker-list">
          <button
            v-for="item in items"
            :key="item.folder"
            class="picker-item"
            @click="emit('select', item)"
          >
            <div class="item-top">
              <span class="item-project">{{ item.project_id || item.folder }}</span>
              <span class="item-date">{{ formatDate(item.timestamp || item.created_at) }}</span>
            </div>
            <div class="item-meta">
              <span v-if="item.source_file" class="item-file">{{ item.source_file }}</span>
              <span v-if="item.word_count != null" class="item-detail">{{ item.word_count }} words</span>
              <span v-else-if="item.alignment" class="item-detail">{{ item.alignment.length }} words</span>
              <span v-if="item.duration != null" class="item-detail">{{ formatDuration(item.duration) }}</span>
            </div>
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.picker-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.picker-dialog {
  width: 100%;
  max-width: 520px;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
}

.picker-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
  border-bottom: 1px solid var(--border);
}

.picker-title {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
}

.picker-close {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  font-size: 20px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background 0.15s;
}

.picker-close:hover {
  background: rgba(255, 255, 255, 0.1);
}

.picker-empty {
  padding: 32px 20px;
  text-align: center;
  font-size: 13px;
  color: var(--text-secondary);
}

.picker-list {
  overflow-y: auto;
  padding: 8px;
}

.picker-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  text-align: left;
  padding: 14px 16px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  color: var(--text);
  font-family: inherit;
  font-size: inherit;
}

.picker-item:hover {
  background: rgba(255, 255, 255, 0.03);
  border-color: var(--border);
}

.item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.item-project {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-date {
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.item-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.item-file {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-detail {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-muted);
  flex-shrink: 0;
}
</style>
