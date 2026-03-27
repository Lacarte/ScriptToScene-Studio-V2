<script setup>
import { computed } from 'vue'
import { statusColor } from '../constants/colors.js'
import { timeAgo, formatElapsed } from '@/shared/utils/format.js'
import { ALL_STEPS } from '../constants/steps.js'

const props = defineProps({
  jobs: { type: Array, default: () => [] },
  activeProjectId: { type: String, default: null },
  templates: { type: Array, default: () => [] },
})

const emit = defineEmits(['select', 'retry', 'regenerate', 'open'])

const historyCount = computed(() => {
  if (!props.jobs.length) return '0'
  return props.jobs.length + (props.jobs.length === 1 ? ' job' : ' jobs')
})

function styleColor(styleId) {
  const t = props.templates.find(t => t.id === styleId)
  return t?.color || '#4ECDC4'
}
function styleLabel(styleId) {
  const t = props.templates.find(t => t.id === styleId)
  return t?.name || styleId || ''
}

const STEP_LABELS = {}
for (const s of ALL_STEPS) STEP_LABELS[s.id] = s.label

function historyTimings(j) {
  if (!j.pipeline_timing) return []
  return Object.entries(j.pipeline_timing)
    .filter(([k]) => k !== 'total')
    .map(([k, v]) => ({ key: k, label: STEP_LABELS[k] || k, duration: v }))
    .filter(s => s.duration)
}
</script>

<template>
  <div class="history-section">
    <div class="history-header">
      <h3 class="history-title">History</h3>
      <span class="history-count">{{ historyCount }}</span>
    </div>
    <div class="history-list">
      <p v-if="!jobs.length" class="history-empty">No pipeline jobs yet</p>
      <div
        v-for="(j, i) in jobs"
        :key="j.project_id || i"
        class="hist-item"
        :class="{ active: j.project_id === activeProjectId, 'hist-item--error': j.status === 'error' }"
        @click="emit('select', i)"
      >
        <div class="hist-inner">
          <span class="hist-dot" :style="{ background: statusColor(j.status) }"></span>
          <div class="hist-content">
            <p class="hist-excerpt">{{ (j.text || '').slice(0, 60) + ((j.text || '').length > 60 ? '...' : '') || j.label || j.project_id }}</p>
            <div class="hist-meta">
              <span>{{ j.project_id }}</span>
              <template v-if="j.scene_count">
                <span class="hist-sep">/</span>
                <span class="hist-scenes">{{ j.scene_count }} scenes</span>
              </template>
              <span class="hist-sep">/</span>
              <span class="hist-time">{{ timeAgo(j.timestamp) }}</span>
              <template v-if="styleLabel(j.style)">
                <span class="hist-sep">&middot;</span>
                <span class="hist-style">
                  <span class="hist-style-dot" :style="{ background: styleColor(j.style) }"></span>
                  <span :style="{ color: styleColor(j.style), fontWeight: 600 }">{{ styleLabel(j.style) }}</span>
                </span>
              </template>
              <template v-if="j.status === 'error'">
                <span class="hist-sep">&middot;</span>
                <span class="hist-error-badge">error at {{ j.error_step || '?' }}</span>
              </template>
            </div>
            <div v-if="j.pipeline_timing && Object.keys(j.pipeline_timing).length" class="hist-timings">
              <span v-if="formatElapsed(j.pipeline_timing.total)" class="hist-timing hist-timing--total">
                total {{ formatElapsed(j.pipeline_timing.total) }}
              </span>
              <span v-for="step in historyTimings(j)" :key="step.key" class="hist-timing">
                {{ step.label }} {{ formatElapsed(step.duration) }}
              </span>
            </div>
          </div>
          <div class="hist-actions">
            <button v-if="j.status === 'error' && j.error_step" class="hist-action-btn hist-action-btn--retry" title="Retry from failed step" @click.stop="emit('retry', i)">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
              Retry
            </button>
            <button v-if="j.status === 'done' && j.scene_count > 0" class="hist-action-btn hist-action-btn--regen" title="Regenerate assets" @click.stop="emit('regenerate', j.project_id)">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
              Regen Assets
            </button>
            <button class="hist-open-btn" title="Open in Scene Blueprint" @click.stop="emit('open', j.project_id)">
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24">
                <path d="M4 11v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/>
                <path d="M4 11V7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v4"/>
                <path d="M4 11h16"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
