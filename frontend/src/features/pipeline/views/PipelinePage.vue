<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { usePipeline } from '../composables/usePipeline.js'
import { useScenes } from '@/features/scenes/composables/useScenes.js'

defineOptions({ name: 'PipelinePage' })

const router = useRouter()
const {
  STEPS, VOICES,
  text, voice, speed, style, autoScenes, templates,
  running, stepStatus, log, globalStatus,
  jobs,
  start, loadFromHistory, randomStory, resetProgress,
  timeAgo,
} = usePipeline()

const { styleLabel, styleColor } = useScenes()

const logEl = ref(null)
const activeProjectId = ref('')

// Auto-scroll log
watch(log, async () => {
  await nextTick()
  if (logEl.value) {
    logEl.value.scrollTop = logEl.value.scrollHeight
  }
})

// Reset progress when form fields change
watch([text, voice, speed, style], () => {
  if (globalStatus.value && globalStatus.value !== 'running') {
    resetProgress()
  }
})

// Persist style to localStorage
watch(style, (val) => {
  localStorage.setItem('sts-pipeline-style', val)
})

const historyCount = computed(() => {
  const n = jobs.value.length
  return n ? `${n} job${n !== 1 ? 's' : ''}` : ''
})

const lastEvent = computed(() => {
  return log.value.length ? log.value[log.value.length - 1] : null
})

const showProgress = computed(() => globalStatus.value !== '')
const showLog = computed(() => log.value.length > 0)

function dotColor(stepId) {
  const s = stepStatus.value[stepId] || 'pending'
  if (s === 'running') return 'var(--accent)'
  if (s === 'done') return '#26DE81'
  if (s === 'skipped') return 'var(--text-muted)'
  if (s === 'error') return '#FF6B6B'
  return 'var(--border)'
}

function dotTextColor(stepId) {
  const s = stepStatus.value[stepId] || 'pending'
  if (s === 'running') return 'var(--accent)'
  if (s === 'done') return '#26DE81'
  if (s === 'skipped') return 'var(--text-muted)'
  if (s === 'error') return '#FF6B6B'
  return 'var(--text-muted)'
}

function dotIcon(step) {
  const s = stepStatus.value[step.id] || 'pending'
  if (s === 'done') return '\u2713'
  if (s === 'skipped') return '\u2014'
  if (s === 'error') return '\u2717'
  return step.icon
}

function dotAnimating(stepId) {
  return (stepStatus.value[stepId] || 'pending') === 'running'
}

function connectorColor(idx) {
  if (idx >= STEPS.length - 1) return 'var(--border)'
  const thisStatus = stepStatus.value[STEPS[idx].id] || 'pending'
  const nextStatus = stepStatus.value[STEPS[idx + 1]?.id] || 'pending'
  return (nextStatus === 'done' || thisStatus === 'done') ? '#26DE81' : 'var(--border)'
}

function logIcon(entry) {
  if (entry.step === 'error') return '\u2717'
  if (entry.status === 'done') return '\u2713'
  return '\u2192'
}

function logColor(entry) {
  if (entry.step === 'error') return '#FF6B6B'
  if (entry.status === 'done') return '#26DE81'
  return 'var(--text-muted)'
}

function statusColor(status) {
  if (status === 'done') return '#26DE81'
  if (status === 'error') return '#FF6B6B'
  return 'var(--accent)'
}

function onHistoryClick(index) {
  const j = jobs.value[index]
  if (!j) return
  activeProjectId.value = j.project_id
  loadFromHistory(index)
}

function openInScenes(projectId) {
  router.push('/scenes')
}

function esc(str) {
  if (!str) return ''
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
</script>

<template>
  <div class="pipeline-page">

    <!-- Header -->
    <div class="header">
      <div>
        <h2 class="page-title">Pipeline</h2>
        <p class="page-subtitle">Run the full TTS &rarr; Timing &rarr; Segment &rarr; Scenes pipeline</p>
      </div>
    </div>

    <!-- Input -->
    <section class="card input-card">
      <div class="field-row">
        <label class="field-label">Story Text</label>
        <button class="random-btn" title="Load a random story excerpt" @click="randomStory">&#x1F3B2; Random</button>
      </div>
      <textarea
        v-model="text"
        class="input-field textarea"
        rows="6"
        placeholder="Enter your story text..."
      ></textarea>
      <div class="controls-row">
        <div>
          <label class="control-label">Voice</label>
          <select v-model="voice" class="input-field select-voice">
            <option v-for="v in VOICES" :key="v.id" :value="v.id">{{ v.label }}</option>
          </select>
        </div>
        <div>
          <label class="control-label">Speed</label>
          <input
            v-model.number="speed"
            type="number"
            class="input-field select-speed"
            min="0.5"
            max="2.0"
            step="0.1"
          >
        </div>
        <div>
          <label class="control-label">Style</label>
          <select v-model="style" class="input-field select-style">
            <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}</option>
          </select>
        </div>
      </div>
      <div class="auto-scenes-row">
        <input
          id="pipeline-auto-scenes"
          v-model="autoScenes"
          type="checkbox"
          class="auto-scenes-check"
        >
        <label for="pipeline-auto-scenes" class="auto-scenes-label">
          Auto-generate scenes <span class="auto-scenes-note">&mdash; run scene generation with the selected style after pipeline completes</span>
        </label>
      </div>
      <div class="run-row">
        <button class="run-btn" :disabled="running" @click="start">
          <span class="run-icon" aria-hidden="true">
            <svg v-if="!running" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="6" cy="12" r="1.75" fill="currentColor" stroke="none"></circle>
              <path d="M9 12h8"></path>
              <path d="M13.5 7.5L18 12l-4.5 4.5"></path>
            </svg>
            <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spinner-svg">
              <circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-dashoffset="12"></circle>
            </svg>
          </span>
          <span class="run-label">{{ running ? 'Running...' : 'Run Pipeline' }}</span>
        </button>
      </div>
    </section>

    <!-- Progress -->
    <section v-if="showProgress" class="card progress-card">
      <label class="field-label progress-label">Progress</label>
      <div class="steps-row">
        <template v-for="(step, i) in STEPS" :key="step.id">
          <div class="step-col">
            <div
              class="step-dot"
              :class="{ 'step-pulse': dotAnimating(step.id) }"
              :style="{
                background: dotColor(step.id) + '15',
                borderColor: dotColor(step.id),
              }"
            >{{ dotIcon(step) }}</div>
            <span class="step-label" :style="{ color: dotTextColor(step.id) }">{{ step.label }}</span>
          </div>
          <div
            v-if="i < STEPS.length - 1"
            class="step-connector"
            :style="{ background: connectorColor(i) }"
          ></div>
        </template>
      </div>
      <div v-if="lastEvent" class="current-step">
        <div class="current-step-inner">
          <div v-if="globalStatus === 'running'" class="step-spinner"></div>
          <span class="current-step-msg" :class="{ 'is-error': lastEvent.step === 'error' }">
            {{ lastEvent.step === 'done' ? 'Pipeline complete' : lastEvent.message || '' }}
          </span>
        </div>
      </div>
    </section>

    <!-- Log -->
    <section v-if="showLog" class="card log-card">
      <label class="field-label log-label">Log</label>
      <div ref="logEl" class="log-container">
        <div v-for="(entry, i) in log" :key="i" class="log-entry" :style="{ color: logColor(entry) }">
          <span class="log-icon">{{ logIcon(entry) }}</span>
          <span class="log-step">{{ entry.step || '' }}</span>
          {{ entry.message || '' }}
        </div>
      </div>
    </section>

    <!-- History -->
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
          :class="{ active: j.project_id === activeProjectId }"
          @click="onHistoryClick(i)"
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
              </div>
            </div>
            <button
              class="hist-open-btn"
              title="Open in Scene Generator"
              @click.stop="openInScenes(j.project_id)"
            >
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
.pipeline-page {
  max-width: 780px;
  margin: 0 auto;
  padding: 24px 24px 32px;
}

/* ---- Header ---- */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-title {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text);
}

.page-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin-top: 4px;
}

/* ---- Card ---- */
.card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}

.card:hover {
  border-color: var(--border-hover);
}

.input-card {
  margin-bottom: 16px;
}

.progress-card {
  margin-bottom: 16px;
}

.log-card {
  margin-bottom: 16px;
}

/* ---- Labels ---- */
.field-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--text-muted);
}

.control-label {
  display: block;
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--text-muted);
  margin-bottom: 4px;
}

/* ---- Input Field ---- */
.input-field {
  background: var(--bg-darkest);
  border: 1.5px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  padding: 8px 12px;
  outline: none;
}

.input-field:focus {
  border-color: var(--accent);
}

.textarea {
  width: 100%;
  resize: vertical;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.6;
}

.select-voice {
  width: 140px;
  font-size: 12px;
}

.select-speed {
  width: 80px;
  font-size: 12px;
}

.select-style {
  width: 140px;
  font-size: 12px;
}

/* ---- Field Row ---- */
.field-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

/* ---- Random Button ---- */
.random-btn {
  padding: 2px 8px;
  border-radius: 5px;
  font-size: 9px;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s;
}

.random-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

/* ---- Controls Row ---- */
.controls-row {
  display: flex;
  gap: 12px;
  margin-top: 12px;
  flex-wrap: wrap;
}

/* ---- Auto-scenes ---- */
.auto-scenes-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--bg-darkest);
  border: 1px solid var(--border);
}

.auto-scenes-check {
  accent-color: var(--accent);
  cursor: pointer;
}

.auto-scenes-label {
  font-size: 11px;
  color: var(--text-secondary);
  cursor: pointer;
}

.auto-scenes-note {
  color: var(--text-muted);
}

/* ---- Run Button ---- */
.run-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}

.run-btn {
  position: relative;
  border: 1px solid rgba(255, 163, 77, 0.45);
  background:
    radial-gradient(circle at top left, rgba(255, 226, 150, 0.22), transparent 42%),
    linear-gradient(135deg, #ff7a18 0%, #ff9f43 52%, #ffd166 100%);
  color: #1f1307;
  box-shadow:
    0 10px 26px rgba(255, 122, 24, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.28);
  overflow: hidden;
  padding: 0 24px;
  height: 44px;
  font-size: 13px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  border-radius: 6px;
  cursor: pointer;
  font-family: 'JetBrains Mono', monospace;
}

.run-btn::before {
  content: "";
  position: absolute;
  inset: 1px;
  border-radius: inherit;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.12), transparent 55%);
  pointer-events: none;
}

.run-btn .run-icon,
.run-btn .run-label {
  position: relative;
  z-index: 1;
}

.run-btn .run-icon {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.18);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22);
}

.run-btn .run-label {
  letter-spacing: 0.02em;
}

.run-btn:hover:not(:disabled) {
  color: #120b04;
  border-color: rgba(255, 209, 102, 0.9);
  box-shadow:
    0 14px 34px rgba(255, 138, 61, 0.38),
    inset 0 1px 0 rgba(255, 255, 255, 0.34);
  transform: translateY(-1px);
}

.run-btn:active:not(:disabled) {
  transform: translateY(0);
  box-shadow:
    0 8px 18px rgba(255, 122, 24, 0.22),
    inset 0 1px 0 rgba(255, 255, 255, 0.24);
}

.run-btn:disabled {
  opacity: 0.9;
  cursor: wait;
}

.spinner-svg {
  animation: spin 0.8s linear infinite;
}

/* ---- Progress ---- */
.progress-label {
  display: block;
  margin-bottom: 16px;
}

.steps-row {
  display: flex;
  align-items: center;
  width: 100%;
  margin-bottom: 16px;
}

.step-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 60px;
}

.step-dot {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 2px solid;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  transition: all 0.3s;
}

.step-pulse {
  animation: pulse 1.5s infinite;
}

.step-label {
  font-size: 10px;
  font-weight: 600;
  margin-top: 4px;
}

.step-connector {
  flex: 1;
  height: 2px;
  margin: 0 4px;
}

.current-step {
  min-height: 24px;
}

.current-step-inner {
  display: flex;
  align-items: center;
  gap: 8px;
}

.step-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(78, 205, 196, 0.3);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  flex-shrink: 0;
}

.current-step-msg {
  font-size: 12px;
  color: var(--text-secondary);
}

.current-step-msg.is-error {
  color: #FF6B6B;
}

/* ---- Log ---- */
.log-label {
  display: block;
  margin-bottom: 12px;
}

.log-container {
  max-height: 200px;
  overflow-y: auto;
  font-size: 11px;
  line-height: 1.6;
  padding: 8px 12px;
  background: var(--bg-darkest);
  border-radius: 8px;
  border: 1px solid var(--border);
  font-family: 'JetBrains Mono', monospace;
}

.log-entry {
  padding: 3px 0;
}

.log-icon {
  opacity: 0.6;
}

.log-step {
  color: var(--accent);
}

/* ---- History ---- */
.history-section {
  margin-top: 28px;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.history-title {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
}

.history-count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--text-muted);
}

.history-list {
  max-height: 400px;
  overflow-y: auto;
}

.history-empty {
  text-align: center;
  padding: 24px;
  font-size: 12px;
  color: var(--text-muted);
}

.hist-item {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.hist-item:hover {
  border-color: var(--border-hover);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
}

.hist-item.active {
  border-color: #ff9f43;
  box-shadow: inset 3px 0 0 #ff9f43, 0 0 12px rgba(255, 159, 67, 0.15);
}

.hist-inner {
  display: flex;
  align-items: start;
  gap: 10px;
  padding: 10px 12px 10px 14px;
}

.hist-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 5px;
}

.hist-content {
  flex: 1;
  min-width: 0;
}

.hist-excerpt {
  font-size: 12px;
  color: var(--text);
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hist-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 10px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
}

.hist-sep {
  opacity: 0.3;
}

.hist-scenes {
  color: #4ECDC4;
}

.hist-time {
  color: var(--text-muted);
}

.hist-style {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.hist-style-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}

.hist-open-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-muted);
  padding: 4px;
  flex-shrink: 0;
  transition: color 0.2s;
}

.hist-open-btn:hover {
  color: var(--accent);
}

/* ---- Animations ---- */
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}
</style>
