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

<style scoped>
.history-section { margin-top: 16px; }
.history-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.history-title { font-family: var(--font-display); font-size: 18px; font-weight: 700; color: var(--text); }
.history-count { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--text-muted); }
.history-list { display: flex; flex-direction: column; gap: 8px; max-height: 500px; overflow-y: auto; padding: 2px; }
.history-empty { text-align: center; padding: 24px; font-size: 12px; color: var(--text-muted); }

.hist-item { background: var(--bg-surface); border: 1px solid var(--border); border-radius: 10px; cursor: pointer; transition: border-color 0.2s, box-shadow 0.2s; }
.hist-item:hover { border-color: var(--border-hover); box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2); }
.hist-item.active { border-color: var(--accent-active); box-shadow: inset 3px 0 0 var(--accent-active), 0 0 12px rgba(255, 159, 67, 0.15); }
.hist-item--error { border-color: rgba(255, 107, 107, 0.25); }
.hist-item--error .hist-excerpt { color: var(--text-secondary); }

.hist-inner { display: flex; align-items: center; gap: 12px; padding: 12px 16px; }
.hist-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.hist-content { flex: 1; min-width: 0; }
.hist-excerpt { font-size: 13px; font-weight: 500; color: var(--text); line-height: 1.5; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 4px; }

.hist-meta { display: flex; align-items: center; gap: 8px; font-size: 10px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; }
.hist-sep { opacity: 0.3; }
.hist-scenes { color: #4ECDC4; }
.hist-time { color: var(--text-muted); }
.hist-style { display: inline-flex; align-items: center; gap: 3px; }
.hist-style-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }

.hist-timings { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.hist-timing { display: inline-flex; align-items: center; padding: 2px 6px; border-radius: 999px; background: var(--bg-darkest); color: var(--text-muted); font-family: 'JetBrains Mono', monospace; font-size: 9px; line-height: 1.4; }
.hist-timing--total { color: var(--accent); border: 1px solid rgba(78, 205, 196, 0.22); }

.hist-error-badge { font-size: 9px; font-weight: 700; color: #FF6B6B; background: rgba(255, 107, 107, 0.1); padding: 1px 6px; border-radius: 3px; }

.hist-actions { display: flex; align-items: center; gap: 4px; flex-shrink: 0; margin-left: auto; }
.hist-action-btn { display: inline-flex; align-items: center; gap: 4px; padding: 4px 8px; border-radius: 5px; font-size: 9px; font-weight: 600; font-family: var(--font-mono); border: 1px solid var(--border); background: transparent; cursor: pointer; transition: all 0.15s; white-space: nowrap; }
.hist-action-btn--retry { color: #FF6B6B; border-color: rgba(255, 107, 107, 0.3); }
.hist-action-btn--retry:hover { background: rgba(255, 107, 107, 0.1); border-color: #FF6B6B; }
.hist-action-btn--regen { color: var(--text-muted); }
.hist-action-btn--regen:hover { color: var(--accent); border-color: var(--accent); background: rgba(78, 205, 196, 0.06); }

.hist-open-btn { background: none; border: none; cursor: pointer; color: var(--text-muted); padding: 4px; flex-shrink: 0; transition: color 0.2s; }
.hist-open-btn:hover { color: var(--accent); }
</style>
