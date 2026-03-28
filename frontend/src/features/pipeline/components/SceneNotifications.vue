<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  notifications: { type: Array, default: () => [] },
})

const listEl = ref(null)

watch(() => props.notifications.length, async () => {
  await nextTick()
  if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
})

function icon(n) {
  return n.type === 'error' ? '\u2717' : '\u2713'
}

function color(n) {
  return n.type === 'error' ? '#FF6B6B' : '#26DE81'
}

function timeStr(t) {
  if (!t) return ''
  const d = t instanceof Date ? t : new Date(t)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function stepLabel(step) {
  if (step === 'assets') return 'Video'
  if (step === 'storyboard') return 'Image'
  return step
}
</script>

<template>
  <div ref="listEl" class="scene-notif-list">
    <div
      v-for="n in notifications"
      :key="n.id"
      class="scene-notif-item"
      :style="{ '--notif-color': color(n) }"
    >
      <span class="notif-icon" :style="{ color: color(n) }">{{ icon(n) }}</span>
      <span class="notif-badge">{{ stepLabel(n.step) }}</span>
      <span class="notif-msg">{{ n.message }}</span>
      <span class="notif-time">{{ timeStr(n.time) }}</span>
    </div>
    <div v-if="!notifications.length" class="scene-notif-empty">No scene events yet</div>
  </div>
</template>

<style scoped>
.scene-notif-list {
  max-height: 180px;
  overflow-y: auto;
  font-size: 11px;
  line-height: 1.5;
  padding: 8px 12px;
  background: var(--bg-darkest);
  border-radius: 8px;
  border: 1px solid var(--border);
  font-family: 'JetBrains Mono', monospace;
}
.scene-notif-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 40%, transparent);
}
.scene-notif-item:last-child { border-bottom: none; }
.notif-icon { flex-shrink: 0; font-size: 12px; }
.notif-badge {
  flex-shrink: 0;
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 1px 6px;
  border-radius: 3px;
  background: color-mix(in srgb, var(--notif-color) 15%, transparent);
  color: var(--notif-color);
}
.notif-msg { flex: 1; color: var(--text-secondary, #ccc); }
.notif-time { flex-shrink: 0; color: var(--text-muted); font-size: 10px; }
.scene-notif-empty { color: var(--text-muted); text-align: center; padding: 8px 0; }
</style>
