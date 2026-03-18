<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { usePipeline } from '../composables/usePipeline.js'
import { useScenes } from '@/features/scenes/composables/useScenes.js'
import { useStory } from '../composables/useStory.js'
import { useProjectSync } from '@/shared/composables/useProjectSync.js'
import { lastPickedStory } from '@/shared/composables/useRandomStory.js'
import { formatElapsed } from '@/shared/utils/format.js'
import { useToast } from '@/shared/composables/useToast.js'

defineOptions({ name: 'PipelinePage' })

const toast = useToast()
const story = useStory()

// Source mode: 'manual' (paste/random) or 'generate' (AI story)
const sourceMode = ref(localStorage.getItem('sts-pipeline-source-mode') || 'manual')
watch(sourceMode, (v) => localStorage.setItem('sts-pipeline-source-mode', v))

function applyRecommendedStyle(styleId) {
  const tmpl = templates.value.find(t => t.id === styleId)
  if (tmpl) style.value = styleId
}

// Link Category ↔ Style: they share the same template list
function setCategory(id) {
  story.storyCategory.value = id
  style.value = id  // sync style to match
}
function setStyle(id) {
  style.value = id
  story.storyCategory.value = id  // sync category to match
}

async function handleGenerateStory() {
  try {
    const data = await story.generateStory(style.value)
    // Strip section labels for clean pipeline text
    const plain = data.story_text
      .replace(/^(Hook|Build|Climax|CTA):\s*/gim, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim()
    text.value = plain
    toast.success('Story generated and applied')
  } catch (e) {
    toast.error(e.message || 'Story generation failed')
  }
}

const router = useRouter()
const {
  ALL_STEPS, VOICES,
  text, voice, speed, style, autoScenes, stopAfter, templates,
  running, stepStatus, log, globalStatus,
  jobs, lastCompletedProjectId, lastCompletedExportFilename,
  failedStep, failedProjectId,
  start, retry, regenerateAssets, loadFromHistory, randomStory, resetProgress,
  timeAgo,
} = usePipeline()

const STEPS = computed(() => {
  const stop = stopAfter.value
  if (!stop) return ALL_STEPS
  const idx = ALL_STEPS.findIndex(s => s.id === stop)
  return idx >= 0 ? ALL_STEPS.slice(0, idx + 1) : ALL_STEPS
})

const { styleLabel, styleColor } = useScenes()

// Sync category to match current style on init
story.storyCategory.value = style.value || 'cinematic'

const logEl = ref(null)
const activeProjectId = ref('')
useProjectSync(activeProjectId)

// Auto-scroll log
watch(log, async () => {
  await nextTick()
  if (logEl.value) {
    logEl.value.scrollTop = logEl.value.scrollHeight
  }
})

const canRun = computed(() => text.value.trim().length > 0 && !running.value)

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

// Auto-navigate when pipeline completes — destination depends on stop_after
watch(globalStatus, (status) => {
  if (status === 'done' && lastCompletedProjectId.value) {
    const stop = stopAfter.value
    const pid = lastCompletedProjectId.value
    // Map stop_after to the appropriate page
    const destinations = {
      tts: '/tts',
      timing: '/alignment',
      segment: '/segmenter',
      scenes: '/scenes',
      assets: '/assets',
      assemble: '/editor',
    }
    const dest = destinations[stop] || '/export-library'
    const query = { project: pid }
    if (dest === '/export-library' && lastCompletedExportFilename.value) {
      query.export = lastCompletedExportFilename.value
    }
    setTimeout(() => {
      router.push({ path: dest, query })
    }, 1500)
  }
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
  const steps = STEPS.value
  if (idx >= steps.length - 1) return 'var(--border)'
  const thisStatus = stepStatus.value[steps[idx].id] || 'pending'
  const nextStatus = stepStatus.value[steps[idx + 1]?.id] || 'pending'
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
  router.push({ path: '/scenes', query: { project: projectId } })
}

function esc(str) {
  if (!str) return ''
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

const HISTORY_STEP_LABELS = {
  tts: 'TTS',
  timing: 'Alignment',
  segment: 'Segment',
  scenes: 'Scenes',
  assets: 'Assets',
  assemble: 'Build',
  export: 'Export',
}

function historyTimings(job) {
  const timings = job?.pipeline_timing || {}
  return Object.entries(HISTORY_STEP_LABELS)
    .filter(([key]) => timings[key] != null)
    .map(([key, label]) => ({ key, label, duration: timings[key] }))
}

function logStepLabel(step) {
  if (step === 'timing') return 'alignment'
  return step || ''
}
</script>

<template>
  <div class="pipeline-page">

    <!-- Header -->
    <div class="header">
      <div>
        <h2 class="page-title">Pipeline</h2>
        <p class="page-subtitle">Run the full TTS &rarr; Alignment &rarr; Segment &rarr; Scenes pipeline</p>
      </div>
    </div>

    <!-- Input -->
    <section class="card input-card">
      <!-- Source mode header -->
      <div class="source-header">
        <label class="field-label">Story Text</label>
        <div class="source-header-right">
          <span v-if="text.trim()" class="word-count">{{ text.trim().split(/\s+/).length }} words</span>
          <div class="mode-toggle">
            <button
              class="mode-btn"
              :class="{ active: sourceMode === 'manual' }"
              @click="sourceMode = 'manual'"
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-1px"><rect x="2" y="2" width="20" height="20" rx="3"/><circle cx="8" cy="8" r="1.5" fill="currentColor"/><circle cx="16" cy="8" r="1.5" fill="currentColor"/><circle cx="8" cy="16" r="1.5" fill="currentColor"/><circle cx="16" cy="16" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/></svg>
              Random
            </button>
            <button
              class="mode-btn"
              :class="{ active: sourceMode === 'generate' }"
              @click="sourceMode = 'generate'"
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-1px"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
              Generate
            </button>
          </div>
        </div>
      </div>

      <!-- Random mode: action row + recommended styles -->
      <div v-if="sourceMode === 'manual'" class="source-random">
        <button class="random-action-btn" @click="randomStory">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="3"/><circle cx="8" cy="8" r="1.5" fill="currentColor"/><circle cx="16" cy="8" r="1.5" fill="currentColor"/><circle cx="8" cy="16" r="1.5" fill="currentColor"/><circle cx="16" cy="16" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/></svg>
          Roll Random Story
        </button>
        <span v-if="lastPickedStory?.type" class="story-type-badge">{{ lastPickedStory.type }}</span>
        <div v-if="lastPickedStory?.styles?.length" class="story-recommended-styles">
          <span class="rec-label">Recommended:</span>
          <button
            v-for="sid in lastPickedStory.styles"
            :key="sid"
            class="rec-style-tag"
            :class="{ active: style === sid }"
            @click="applyRecommendedStyle(sid)"
          >{{ templates.find(t => t.id === sid)?.name || sid }}</button>
        </div>
      </div>

      <!-- Generate mode: inline story form -->
      <div v-if="sourceMode === 'generate'" class="source-generate">
        <div class="gen-form">
          <div class="gen-group">
            <label class="control-label">Category / Style</label>
            <select :value="style" class="input-field control-select" @change="setCategory($event.target.value)">
              <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}</option>
            </select>
          </div>
          <div class="gen-group">
            <label class="control-label">Language</label>
            <select v-model="story.storyLanguage.value" class="input-field control-select">
              <option v-for="lang in story.LANGUAGES" :key="lang.id" :value="lang.id">{{ lang.label }}</option>
            </select>
          </div>
          <div class="gen-group">
            <label class="control-label">Duration</label>
            <input v-model.number="story.storyDuration.value" type="number" class="input-field control-number" min="15" max="180" step="5">
          </div>
          <div class="gen-group gen-group--action">
            <button class="gen-story-btn" :disabled="story.isGenerating.value" @click="handleGenerateStory">
              <span v-if="story.isGenerating.value" class="gen-spinner"></span>
              <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
              {{ story.isGenerating.value ? 'Generating...' : 'Generate Story' }}
            </button>
          </div>
        </div>
        <p v-if="story.error.value" class="gen-error">{{ story.error.value }}</p>
        <!-- Generation result stats -->
        <div v-if="story.result.value" class="gen-result-bar">
          <span class="gen-result-id">{{ story.result.value.project_id }}</span>
          <span class="gen-sep">&middot;</span>
          <span>{{ story.result.value.word_count }} words</span>
          <span class="gen-sep">&middot;</span>
          <span>~{{ story.result.value.estimated_duration }}s</span>
          <span class="gen-sep">&middot;</span>
          <span>{{ styleLabel(story.result.value.story_category || story.result.value.preset_style || '') || story.result.value.story_category }}</span>
          <span class="gen-sep">&middot;</span>
          <span class="gen-result-muted">{{ (story.result.value.generation_time || 0).toFixed(1) }}s gen</span>
        </div>
      </div>

      <!-- Textarea (always visible) -->
      <textarea
        v-model="text"
        class="input-field textarea"
        :class="{ 'textarea--empty': !text.trim() }"
        rows="5"
        :placeholder="sourceMode === 'generate' ? 'Click Generate Story above, or type your own text...' : 'Paste your story, script, or narration text here...'"
      ></textarea>

      <!-- Controls strip -->
      <div class="controls-strip">
        <div class="control-group">
          <label class="control-label">Voice</label>
          <select v-model="voice" class="input-field control-select">
            <option v-for="v in VOICES" :key="v.id" :value="v.id">{{ v.label }}</option>
          </select>
        </div>
        <div class="control-group">
          <label class="control-label">Speed</label>
          <input
            v-model.number="speed"
            type="number"
            class="input-field control-number"
            min="0.5"
            max="2.0"
            step="0.1"
          >
        </div>
        <div class="control-group">
          <label class="control-label">Style</label>
          <select :value="style" class="input-field control-select" @change="setStyle($event.target.value)">
            <option v-for="t in templates" :key="t.id" :value="t.id">{{ t.name }}</option>
          </select>
        </div>
        <div class="control-group">
          <label class="control-label">Run Until</label>
          <select v-model="stopAfter" class="input-field control-select control-select--sm">
            <option value="">All steps (→ Export)</option>
            <option value="tts">TTS only</option>
            <option value="timing">→ Alignment</option>
            <option value="segment">→ Segment</option>
            <option value="scenes">→ Scenes</option>
            <option value="assets">→ Assets</option>
            <option value="assemble">→ Assemble</option>
            <option value="export">→ Export</option>
          </select>
        </div>
        <div class="control-group control-group--auto">
          <label class="auto-toggle" for="pipeline-auto-scenes" :class="{ disabled: stopAfter }">
            <input id="pipeline-auto-scenes" v-model="autoScenes" type="checkbox" class="auto-check" :disabled="!!stopAfter">
            <span class="auto-text">Auto-scenes</span>
          </label>
        </div>
      </div>

      <!-- Action row -->
      <div class="action-row">
        <button class="run-btn" :class="{ 'run-btn--disabled': !canRun }" :disabled="!canRun" @click="start">
          <span class="run-icon" aria-hidden="true">
            <svg v-if="!running" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
              <path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>
            </svg>
            <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spinner-svg">
              <circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-dashoffset="12"></circle>
            </svg>
          </span>
          <span class="run-label">{{ running ? 'Running...' : 'Run Pipeline' }}</span>
        </button>
        <!-- Retry button — appears when pipeline failed -->
        <button
          v-if="globalStatus === 'error' && failedStep && failedProjectId && !running"
          class="retry-btn"
          @click="retry"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
          Retry from {{ failedStep }}
        </button>
        <span v-if="!text.trim() && !running && globalStatus !== 'error'" class="run-hint">{{ sourceMode === 'generate' ? 'Generate a story or type text to get started' : 'Paste text or click Random to get started' }}</span>
      </div>
    </section>

    <!-- Progress -->
    <section v-if="showProgress" class="card progress-card">
      <div class="progress-header">
        <label class="field-label progress-label">Progress</label>
        <span v-if="activeProjectId" class="progress-project font-mono">{{ activeProjectId }}</span>
      </div>
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
          <span class="log-step">{{ logStepLabel(entry.step) }}</span>
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
          :class="{ active: j.project_id === activeProjectId, 'hist-item--error': j.status === 'error' }"
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
                <template v-if="j.status === 'error'">
                  <span class="hist-sep">&middot;</span>
                  <span class="hist-error-badge">error at {{ j.error_step || '?' }}</span>
                </template>
              </div>
              <div v-if="j.pipeline_timing && Object.keys(j.pipeline_timing).length" class="hist-timings">
                <span v-if="formatElapsed(j.pipeline_timing.total)" class="hist-timing hist-timing--total">
                  total {{ formatElapsed(j.pipeline_timing.total) }}
                </span>
                <span
                  v-for="step in historyTimings(j)"
                  :key="step.key"
                  class="hist-timing"
                >
                  {{ step.label }} {{ formatElapsed(step.duration) }}
                </span>
              </div>
            </div>
            <!-- Action buttons -->
            <div class="hist-actions">
              <!-- Retry button for errored pipelines -->
              <button
                v-if="j.status === 'error' && j.error_step"
                class="hist-action-btn hist-action-btn--retry"
                title="Retry from failed step"
                @click.stop="onHistoryClick(i)"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                Retry
              </button>
              <!-- Regenerate assets button for completed pipelines with scenes -->
              <button
                v-if="j.status === 'done' && j.scene_count > 0"
                class="hist-action-btn hist-action-btn--regen"
                title="Regenerate assets with provider"
                @click.stop="regenerateAssets(j.project_id)"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
                Regen Assets
              </button>
              <!-- Open in scenes -->
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

  </div>
</template>

<style scoped>
.pipeline-page {
  max-width: 780px;
  margin: 0 auto;
  padding: 32px 24px;
}

/* ---- Header ---- */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  letter-spacing: -0.02em;
}

/* ---- Card ---- */
.card {
  padding: 24px;
}

.input-card {
  margin-bottom: 16px;
}

.progress-card,
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
  font-size: 8px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--text-muted);
  margin-bottom: 5px;
}

/* ---- Input Field ---- */
.input-field {
  background: var(--bg-darkest);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  padding: 8px 12px;
  outline: none;
  transition: border-color 0.15s;
}

.input-field:focus {
  border-color: var(--accent);
}

.textarea {
  width: 100%;
  resize: vertical;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.7;
  min-height: 120px;
}

.textarea--empty {
  color: var(--text-muted);
}

/* ---- Source Header ---- */
.source-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.source-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.word-count {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--accent);
  font-weight: 600;
}

/* ---- Mode Toggle ---- */
.mode-toggle {
  display: flex;
  border: 1px solid var(--border);
  border-radius: 7px;
  overflow: hidden;
  background: var(--bg-darkest);
}

.mode-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  font-size: 10px;
  font-weight: 600;
  font-family: var(--font-mono);
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.mode-btn:first-child {
  border-right: 1px solid var(--border);
}

.mode-btn:hover:not(.active) {
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.02);
}

.mode-btn.active {
  color: var(--accent);
  background: rgba(78, 205, 196, 0.1);
}

/* ---- Random Mode ---- */
.source-random {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.random-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  border-radius: 7px;
  font-size: 11px;
  font-weight: 600;
  font-family: var(--font-mono);
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.random-action-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(78, 205, 196, 0.06);
}

.story-type-badge {
  font-size: 9px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(167, 139, 250, 0.12);
  color: var(--accent-secondary, #A78BFA);
  white-space: nowrap;
}

.story-recommended-styles {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
}

.rec-label {
  font-size: 9px;
  color: var(--text-muted);
  font-weight: 600;
}

.rec-style-tag {
  font-size: 9px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.rec-style-tag:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(78, 205, 196, 0.08);
}

.rec-style-tag.active {
  border-color: var(--accent);
  background: rgba(78, 205, 196, 0.15);
  color: var(--accent);
}

/* ---- Generate Mode ---- */
.source-generate {
  margin-bottom: 10px;
}

.gen-form {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.gen-group {
  flex-shrink: 1;
  min-width: 0;
}

.gen-group--action {
  flex-shrink: 0;
  margin-left: auto;
}

.gen-story-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border-radius: 8px;
  font-size: 11px;
  font-weight: 700;
  font-family: var(--font-mono);
  border: none;
  cursor: pointer;
  color: white;
  background: linear-gradient(135deg, #A78BFA, #7C3AED);
  box-shadow: 0 2px 12px rgba(167, 139, 250, 0.25);
  transition: all 0.2s;
  white-space: nowrap;
}

.gen-story-btn:hover:not(:disabled) {
  box-shadow: 0 4px 16px rgba(167, 139, 250, 0.4);
  transform: translateY(-1px);
}

.gen-story-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.gen-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

.gen-error {
  margin-top: 6px;
  font-size: 11px;
  color: #FF6B6B;
  font-family: var(--font-mono);
}

.gen-result-bar {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  margin-top: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  background: var(--bg-darkest);
  border: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-secondary);
}

.gen-result-id {
  color: var(--accent);
  font-weight: 600;
}

.gen-sep {
  color: var(--text-muted);
  opacity: 0.4;
}

.gen-result-muted {
  color: var(--text-muted);
}

/* ---- Controls Strip ---- */
.controls-strip {
  display: flex;
  align-items: flex-end;
  gap: 14px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}

.control-group {
  flex-shrink: 1;
  min-width: 0;
}

.control-group--auto {
  margin-left: auto;
  flex-shrink: 0;
  align-self: flex-end;
}

.control-select {
  width: 100%;
  min-width: 100px;
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
}

.control-select--sm {
  width: 170px;
  font-size: 11px;
}

.control-number {
  width: 72px;
  font-size: 12px;
  font-family: var(--font-mono);
  text-align: center;
}

/* ---- Auto-scenes ---- */
.auto-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 8px 12px;
  height: 34px;
  box-sizing: border-box;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg-darkest);
  transition: all 0.15s;
}

.auto-toggle:hover {
  border-color: var(--border-hover);
}

.auto-toggle.disabled {
  opacity: 0.4;
  cursor: not-allowed;
  pointer-events: none;
}

.auto-check {
  accent-color: var(--accent);
  cursor: pointer;
}

.auto-text {
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
}

/* ---- Action Row ---- */
.action-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid var(--border);
}

.run-hint {
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  opacity: 0.7;
}

/* ---- Retry Button ---- */
.retry-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 20px;
  height: 42px;
  font-size: 12px;
  font-weight: 700;
  font-family: var(--font-mono);
  border-radius: 10px;
  border: 1.5px solid #FF6B6B;
  background: rgba(255, 107, 107, 0.08);
  color: #FF6B6B;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}

.retry-btn:hover {
  background: rgba(255, 107, 107, 0.16);
  box-shadow: 0 4px 16px rgba(255, 107, 107, 0.2);
  transform: translateY(-1px);
}

.retry-btn:active {
  transform: translateY(0);
}

/* ---- Run Button ---- */
.run-btn {
  position: relative;
  border: 1px solid rgba(255, 163, 77, 0.45);
  background:
    radial-gradient(circle at top left, rgba(255, 226, 150, 0.22), transparent 42%),
    linear-gradient(135deg, #ff7a18 0%, var(--accent-active) 52%, #ffd166 100%);
  color: #1f1307;
  box-shadow:
    0 10px 26px rgba(255, 122, 24, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.28);
  overflow: hidden;
  padding: 0 28px;
  height: 42px;
  font-size: 13px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  border-radius: 10px;
  cursor: pointer;
  font-family: var(--font-mono);
  flex-shrink: 0;
  transition: transform 0.15s, box-shadow 0.15s;
}

.run-btn::before {
  content: "";
  position: absolute;
  inset: 1px;
  border-radius: inherit;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.14), transparent 55%);
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
}

.run-btn .run-label {
  letter-spacing: 0.02em;
}

.run-btn:hover:not(:disabled):not(.run-btn--disabled) {
  transform: translateY(-1px);
  box-shadow:
    0 14px 34px rgba(255, 138, 61, 0.38),
    inset 0 1px 0 rgba(255, 255, 255, 0.34);
}

.run-btn:active:not(:disabled):not(.run-btn--disabled) {
  transform: translateY(0);
}

.run-btn:disabled {
  cursor: wait;
}

.run-btn--disabled {
  background: var(--bg-darkest) !important;
  border-color: var(--border) !important;
  color: var(--text-muted) !important;
  box-shadow: none !important;
  cursor: not-allowed !important;
  opacity: 0.5;
}

.run-btn--disabled::before {
  display: none;
}

.run-btn--disabled .run-icon {
  background: rgba(255, 255, 255, 0.05);
}

.spinner-svg {
  animation: spin 0.8s linear infinite;
}

/* ---- Progress ---- */
.progress-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.progress-label {
  margin: 0;
}

.progress-project {
  font-size: 11px;
  color: var(--accent);
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
  margin-top: 16px;
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
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 500px;
  overflow-y: auto;
  padding: 2px;
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
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.hist-item:hover {
  border-color: var(--border-hover);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
}

.hist-item.active {
  border-color: var(--accent-active);
  box-shadow: inset 3px 0 0 var(--accent-active), 0 0 12px rgba(255, 159, 67, 0.15);
}

.hist-inner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
}

.hist-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.hist-content {
  flex: 1;
  min-width: 0;
}

.hist-excerpt {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 4px;
}

.hist-meta {
  display: flex;
  align-items: center;
  gap: 8px;
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

.hist-timings {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.hist-timing {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  border-radius: 999px;
  background: var(--bg-darkest);
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  line-height: 1.4;
}

.hist-timing--total {
  color: var(--accent);
  border: 1px solid rgba(78, 205, 196, 0.22);
}

.hist-style-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}

.hist-item--error {
  border-color: rgba(255, 107, 107, 0.25);
}

.hist-item--error .hist-excerpt {
  color: var(--text-secondary);
}

.hist-error-badge {
  font-size: 9px;
  font-weight: 700;
  color: #FF6B6B;
  background: rgba(255, 107, 107, 0.1);
  padding: 1px 6px;
  border-radius: 3px;
}

.hist-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  margin-left: auto;
}

.hist-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 5px;
  font-size: 9px;
  font-weight: 600;
  font-family: var(--font-mono);
  border: 1px solid var(--border);
  background: transparent;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.hist-action-btn--retry {
  color: #FF6B6B;
  border-color: rgba(255, 107, 107, 0.3);
}

.hist-action-btn--retry:hover {
  background: rgba(255, 107, 107, 0.1);
  border-color: #FF6B6B;
}

.hist-action-btn--regen {
  color: var(--text-muted);
}

.hist-action-btn--regen:hover {
  color: var(--accent);
  border-color: var(--accent);
  background: rgba(78, 205, 196, 0.06);
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
