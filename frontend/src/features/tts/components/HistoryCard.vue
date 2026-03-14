<script setup>
import { computed } from 'vue'
import { VOICE_META } from '../composables/useTts.js'

const props = defineProps({
  item: { type: Object, required: true },
})

const emit = defineEmits(['play', 'delete', 'open-folder'])

const voiceMeta = computed(() => VOICE_META[props.item.voice] || {})
const voiceName = computed(() => voiceMeta.value.name || props.item.voice)
const excerpt = computed(() => {
  const text = props.item.prompt || ''
  return text.length > 60 ? text.slice(0, 60) + '...' : text
})
const durationLabel = computed(() => {
  return props.item.duration_seconds ? `${props.item.duration_seconds.toFixed(1)}s` : ''
})

function timeAgo(ts) {
  if (!ts) return ''
  const diff = (Date.now() - new Date(ts).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

const ago = computed(() => timeAgo(props.item.timestamp))
</script>

<template>
  <div class="card history-card" @click="emit('play', item)">
    <button class="play-btn" @click.stop="emit('play', item)" title="Play">
      <svg width="14" height="14" fill="currentColor" viewBox="0 0 24 24">
        <path d="M8 5v14l11-7z" />
      </svg>
    </button>

    <div class="card-info">
      <p class="card-text">{{ excerpt }}</p>
      <div class="card-meta">
        <span>{{ voiceName }}</span>
        <span class="sep">/</span>
        <span>{{ durationLabel }}</span>
        <span class="sep">/</span>
        <span>{{ ago }}</span>
      </div>
    </div>

    <div style="display:flex;gap:4px;align-items:center">
      <button class="icon-btn" @click.stop="emit('open-folder', item)" title="Open folder">
        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" />
        </svg>
      </button>
      <button class="delete-btn" @click.stop="emit('delete', item)" title="Delete">
      <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path d="M3 6h18" />
        <path d="M8 6V4h8v2" />
        <path d="M5 6v14a2 2 0 002 2h10a2 2 0 002-2V6" />
      </svg>
    </button>
    </div>
  </div>
</template>

<style scoped>
.history-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  margin-bottom: 6px;
  cursor: pointer;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.history-card:hover {
  border-color: var(--border-hover);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
}

.play-btn {
  width: 32px;
  height: 32px;
  min-width: 32px;
  border-radius: 8px;
  background: rgba(78, 205, 196, 0.1);
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent);
  margin-top: 2px;
  transition: background 0.15s;
}

.play-btn:hover {
  background: rgba(78, 205, 196, 0.2);
}

.card-info {
  flex: 1;
  min-width: 0;
}

.card-text {
  margin: 0;
  font-size: 12px;
  color: var(--text);
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin: 0;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  font-size: 10px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.sep {
  opacity: 0.3;
}

.icon-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-muted);
  padding: 4px;
  transition: color 0.15s;
}

.icon-btn:hover {
  color: var(--text);
}

.delete-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-muted);
  padding: 4px;
  transition: color 0.15s;
}

.delete-btn:hover {
  color: var(--coral);
}
</style>
