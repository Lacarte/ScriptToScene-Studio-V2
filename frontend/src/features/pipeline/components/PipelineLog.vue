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
  <section v-if="log.length" class="card log-card">
    <label class="field-label log-label">Log</label>
    <div ref="logEl" class="log-container">
      <div v-for="(entry, i) in log" :key="i" class="log-entry" :style="{ color: logEntryColor(entry) }">
        <span class="log-icon">{{ logEntryIcon(entry) }}</span>
        <span class="log-step">{{ logStepLabel(entry.step) }}</span>
        {{ entry.message || '' }}
      </div>
    </div>
  </section>
</template>
