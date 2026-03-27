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
