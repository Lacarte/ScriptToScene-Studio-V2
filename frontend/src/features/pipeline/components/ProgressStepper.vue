<script setup>
import { computed } from 'vue'
import { stepColor, stepTextColor } from '../constants/colors.js'

const props = defineProps({
  steps: { type: Array, required: true },
  stepStatus: { type: Object, default: () => ({}) },
  globalStatus: { type: String, default: '' },
  running: { type: Boolean, default: false },
  stopping: { type: Boolean, default: false },
  lastEvent: { type: Object, default: null },
  activeProjectId: { type: String, default: null },
  canResume: { type: Boolean, default: false },
})

const emit = defineEmits(['stop', 'resume'])

function dotColor(stepId) { return stepColor(props.stepStatus[stepId]) }
function dotTextColor_(stepId) { return stepTextColor(props.stepStatus[stepId]) }
function dotAnimating(stepId) { return (props.stepStatus[stepId] || 'pending') === 'running' }
function dotIcon(step) {
  const s = props.stepStatus[step.id] || 'pending'
  if (s === 'done') return '\u2713'
  if (s === 'stopped') return '\u23F8'
  if (s === 'skipped') return '\u2014'
  if (s === 'error') return '\u2717'
  return step.icon
}
function connectorColor(idx) {
  if (idx >= props.steps.length - 1) return 'var(--border)'
  const thisS = props.stepStatus[props.steps[idx].id] || 'pending'
  const nextS = props.stepStatus[props.steps[idx + 1]?.id] || 'pending'
  return (nextS === 'done' || thisS === 'done') ? '#26DE81' : 'var(--border)'
}
</script>

<template>
  <section class="card progress-card">
    <div class="progress-header">
      <label class="field-label progress-label">Progress</label>
      <div class="progress-header-right">
        <span v-if="activeProjectId" class="progress-project font-mono">{{ activeProjectId }}</span>
        <button v-if="running || stopping" class="progress-stop-btn" :disabled="stopping" @click="emit('stop')">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>
          {{ stopping ? 'Stopping...' : 'Stop' }}
        </button>
        <button v-else-if="canResume" class="progress-resume-btn" @click="emit('resume')">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          Resume
        </button>
      </div>
    </div>
    <div class="steps-row">
      <template v-for="(step, i) in steps" :key="step.id">
        <div class="step-col">
          <div
            class="step-dot"
            :class="{ 'step-pulse': dotAnimating(step.id) }"
            :style="{ background: dotColor(step.id) + '15', borderColor: dotColor(step.id) }"
          >{{ dotIcon(step) }}</div>
          <span class="step-label" :style="{ color: dotTextColor_(step.id) }">{{ step.label }}</span>
        </div>
        <div v-if="i < steps.length - 1" class="step-connector" :style="{ background: connectorColor(i) }"></div>
      </template>
    </div>
    <div v-if="lastEvent" class="current-step">
      <div class="current-step-inner">
        <div v-if="globalStatus === 'running'" class="step-spinner"></div>
        <span class="current-step-msg" :class="{ 'is-error': lastEvent.step === 'error', 'is-stopped': lastEvent.step === 'stopped' || lastEvent.status === 'stopped' }">
          {{ lastEvent.step === 'done' ? 'Pipeline complete' : lastEvent.message || '' }}
        </span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.progress-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.progress-label { margin: 0; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-muted); }
.progress-header-right { display: flex; align-items: center; gap: 10px; }
.progress-project { font-size: 11px; color: var(--accent); }

.progress-stop-btn, .progress-resume-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 10px; font-size: 11px; font-weight: 600;
  border-radius: 6px; border: 1px solid var(--border);
  background: transparent; cursor: pointer; transition: all 0.15s;
}
.progress-stop-btn { color: #FF6B6B; border-color: rgba(255,107,107,0.3); }
.progress-stop-btn:hover:not(:disabled) { background: rgba(255,107,107,0.1); border-color: #FF6B6B; }
.progress-stop-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.progress-resume-btn { color: #26DE81; border-color: rgba(38,222,129,0.3); }
.progress-resume-btn:hover { background: rgba(38,222,129,0.1); border-color: #26DE81; }

.steps-row { display: flex; align-items: center; width: 100%; margin-bottom: 16px; }
.step-col { display: flex; flex-direction: column; align-items: center; min-width: 60px; }
.step-dot { width: 32px; height: 32px; border-radius: 50%; border: 2px solid; display: flex; align-items: center; justify-content: center; font-size: 14px; transition: all 0.3s; }
.step-pulse { animation: pulse 1.5s infinite; }
.step-label { font-size: 10px; font-weight: 600; margin-top: 4px; }
.step-connector { flex: 1; height: 2px; margin: 0 4px; }

.current-step { min-height: 24px; }
.current-step-inner { display: flex; align-items: center; gap: 8px; }
.step-spinner { width: 12px; height: 12px; border: 2px solid rgba(78,205,196,0.3); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.6s linear infinite; flex-shrink: 0; }
.current-step-msg { font-size: 12px; color: var(--text-secondary); }
.current-step-msg.is-error { color: #FF6B6B; }
.current-step-msg.is-stopped { color: #FFB347; }

@keyframes pulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(78,205,196,0.4); } 50% { box-shadow: 0 0 0 6px rgba(78,205,196,0); } }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
