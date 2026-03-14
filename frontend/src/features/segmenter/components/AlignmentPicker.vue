<script setup>
defineOptions({ name: 'AlignmentPicker' })

defineProps({
  show: { type: Boolean, required: true },
  items: { type: Array, default: () => [] },
})

const emit = defineEmits(['select', 'close'])

function formatDuration(seconds) {
  if (seconds == null) return '--'
  const m = Math.floor(seconds / 60)
  const s = (seconds % 60).toFixed(1)
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

function relativeTime(ts) {
  if (!ts) return ''
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

function formatDate(ts) {
  return relativeTime(ts)
}

function truncate(str, max = 60) {
  if (!str) return ''
  return str.length > max ? str.slice(0, max) + '…' : str
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
            <div class="item-body">
              <p v-if="item.transcript" class="item-transcript">{{ truncate(item.transcript) }}</p>
              <div class="item-meta">
                <span class="item-project">{{ item.project_id || item.folder }}</span>
                <span class="meta-dot">&middot;</span>
                <span v-if="item.word_count != null">{{ item.word_count }} words</span>
                <span v-else-if="item.alignment">{{ item.alignment.length }} words</span>
                <template v-if="item.duration != null">
                  <span class="meta-dot">&middot;</span>
                  <span>{{ formatDuration(item.duration) }}</span>
                </template>
                <template v-if="item.timestamp || item.created_at">
                  <span class="meta-dot">&middot;</span>
                  <span>{{ relativeTime(item.timestamp || item.created_at) }}</span>
                </template>
              </div>
            </div>
            <span v-if="item.source_file" class="item-file-badge">{{ item.source_file }}</span>
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
  align-items: center;
  justify-content: space-between;
  gap: 12px;
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

.item-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.item-transcript {
  font-size: 13px;
  color: var(--text);
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-muted);
}

.item-project {
  color: var(--accent);
  font-weight: 600;
}

.meta-dot {
  color: var(--text-muted);
  opacity: 0.5;
}

.item-file-badge {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-secondary);
  background: var(--bg-darkest);
  padding: 3px 8px;
  border-radius: 6px;
  white-space: nowrap;
  flex-shrink: 0;
}
</style>
