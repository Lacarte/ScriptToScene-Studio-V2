<script setup>
import { ref, watch, nextTick } from 'vue'
import { logEntryIcon, logEntryColor } from '../constants/colors.js'
import { ALL_STEPS } from '../constants/steps.js'

const props = defineProps({
  log: { type: Array, default: () => [] },
})

const logEl = ref(null)

const STEP_LABELS = {}
for (const s of ALL_STEPS) STEP_LABELS[s.id] = s.label

function logStepLabel(step) {
  return STEP_LABELS[step] || step || ''
}

watch(() => props.log.length, async () => {
  await nextTick()
  if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
})
</script>

<template>
  <div ref="logEl" class="log-container">
    <div v-for="(entry, i) in log" :key="i" class="log-entry" :style="{ color: logEntryColor(entry) }">
      <span class="log-icon">{{ logEntryIcon(entry) }}</span>
      <span class="log-step">{{ logStepLabel(entry.step) }}</span>
      {{ entry.message || '' }}
    </div>
  </div>
</template>

<style scoped>
.log-container { max-height: 200px; overflow-y: auto; font-size: 11px; line-height: 1.6; padding: 8px 12px; background: var(--bg-darkest); border-radius: 8px; border: 1px solid var(--border); font-family: 'JetBrains Mono', monospace; }
.log-entry { padding: 3px 0; }
.log-icon { opacity: 0.6; }
.log-step { color: var(--accent); }
</style>
