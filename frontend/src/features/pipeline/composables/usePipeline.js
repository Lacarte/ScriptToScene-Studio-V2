import { ref, readonly } from 'vue'
import { api } from '@/shared/api/client.js'
import { useToast } from '@/shared/composables/useToast.js'
import { pickRandomStory } from '@/shared/composables/useRandomStory.js'
import { timeAgo } from '@/shared/utils/format.js'
import { useDoneSound } from '@/shared/composables/useDoneSound.js'
import { useSettings } from '@/features/settings/composables/useSettings.js'

// ── Provider tab loading screen ──

const providerTabLoadingHTML = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Waiting Assets</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:100%;height:100%;background:#000;overflow:hidden}
.c{display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:32px}
.frame{animation:pulse 5s ease-in-out infinite,colorShift 6s ease-in-out infinite}
.txt{animation:txtA 5s ease-in-out infinite,colorShift 6s ease-in-out infinite}
.img{animation:imgA 5s ease-in-out infinite,colorShift 6s ease-in-out infinite}
.d{opacity:0}
.d1{animation:pop 5s 1.0s ease-in-out infinite,colorShift 6s 0.0s ease-in-out infinite}
.d2{animation:pop 5s 1.15s ease-in-out infinite,colorShift 6s 0.3s ease-in-out infinite}
.d3{animation:pop 5s 1.3s ease-in-out infinite,colorShift 6s 0.6s ease-in-out infinite}
.d4{animation:pop 5s 1.45s ease-in-out infinite,colorShift 6s 0.9s ease-in-out infinite}
.d5{animation:pop 5s 1.1s ease-in-out infinite,colorShift 6s 0.2s ease-in-out infinite}
.d6{animation:pop 5s 1.35s ease-in-out infinite,colorShift 6s 0.7s ease-in-out infinite}
.d7{animation:pop 5s 1.25s ease-in-out infinite,colorShift 6s 0.5s ease-in-out infinite}
.d8{animation:pop 5s 1.5s ease-in-out infinite,colorShift 6s 1.0s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:.12}50%{opacity:.25}}
@keyframes txtA{0%,10%{opacity:.5}28%,72%{opacity:0}90%,100%{opacity:.5}}
@keyframes imgA{0%,20%{opacity:0}38%,62%{opacity:.45}80%,100%{opacity:0}}
@keyframes pop{0%,18%{opacity:0}28%{opacity:.7}40%{opacity:0}100%{opacity:0}}
@keyframes colorShift{0%,100%{fill:#4ECDC4;stroke:#4ECDC4}40%{fill:#2FB8AE;stroke:#2FB8AE}70%{fill:#ff7a18;stroke:#ff7a18}}
.lbl{animation:lblColor 6s ease-in-out infinite;font:500 11px/1 system-ui,sans-serif;letter-spacing:.1em;text-transform:uppercase}
@keyframes lblColor{0%,100%{color:#4ECDC4}40%{color:#2FB8AE}70%{color:#ff7a18}}
</style></head><body>
<div class="c">
  <svg width="128" height="128" viewBox="0 0 120 120" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect class="frame" x="22" y="12" width="76" height="96" rx="8" stroke-width="1.5" fill="none"/>
    <g class="txt">
      <rect x="34" y="28" width="32" height="2.5" rx="1.25"/>
      <rect x="34" y="36" width="52" height="2.5" rx="1.25"/>
      <rect x="34" y="44" width="42" height="2.5" rx="1.25"/>
      <rect x="34" y="52" width="48" height="2.5" rx="1.25"/>
      <rect x="34" y="60" width="30" height="2.5" rx="1.25"/>
      <rect x="34" y="68" width="44" height="2.5" rx="1.25"/>
      <rect x="34" y="76" width="36" height="2.5" rx="1.25"/>
      <rect x="34" y="84" width="22" height="2.5" rx="1.25"/>
    </g>
    <g class="img">
      <circle cx="74" cy="34" r="8" stroke-width="1.5" fill="none"/>
      <line x1="72" y1="30" x2="74" y2="28" stroke-width="1" stroke-linecap="round"/>
      <line x1="78" y1="31" x2="80" y2="29" stroke-width="1" stroke-linecap="round"/>
      <line x1="80" y1="36" x2="82.5" y2="36" stroke-width="1" stroke-linecap="round"/>
      <line x1="68" y1="36" x2="65.5" y2="36" stroke-width="1" stroke-linecap="round"/>
      <path d="M28 96 L48 58 L60 74 L72 48 L92 96" stroke-width="1.5" stroke-linejoin="round" fill="none"/>
    </g>
    <circle class="d d1" cx="48" cy="46" r="1.5"/>
    <circle class="d d2" cx="70" cy="56" r="1"/>
    <circle class="d d3" cx="54" cy="64" r="1.5"/>
    <circle class="d d4" cx="74" cy="72" r="1"/>
    <circle class="d d5" cx="42" cy="56" r="1"/>
    <circle class="d d6" cx="62" cy="78" r="1.2"/>
    <circle class="d d7" cx="78" cy="44" r="1"/>
    <circle class="d d8" cx="50" cy="82" r="1.2"/>
  </svg>
  <span class="lbl">Preparing provider\u2026</span>
</div>
</body></html>`

// ── Constants ──

const ALL_STEPS = [
  { id: 'tts', label: 'TTS', icon: '\uD83C\uDFA4' },
  { id: 'timing', label: 'Alignment', icon: '\u23F1' },
  { id: 'segment', label: 'Segment', icon: '\u2702' },
  { id: 'scenes', label: 'Scenes', icon: '\uD83C\uDFAC' },
  { id: 'assets', label: 'Assets', icon: '\uD83D\uDDBC' },
  { id: 'assemble', label: 'Build', icon: '\uD83D\uDD27' },
  { id: 'export', label: 'Export', icon: '\uD83D\uDCE4' },
]

// STEPS is now a computed exposed from the composable (see activeSteps below)

const VOICES = [
  { id: 'af_heart', label: 'af_heart' },
  { id: 'af_bella', label: 'af_bella' },
  { id: 'am_adam', label: 'am_adam' },
  { id: 'am_michael', label: 'am_michael' },
  { id: 'bf_emma', label: 'bf_emma' },
]

// ── Singleton state ──

const text = ref('')
const voice = ref('af_heart')
const speed = ref(1.0)
const style = ref('cinematic')
const autoScenes = ref(true)
const stopAfter = ref('')  // '', 'tts', 'timing', 'segment'
const templates = ref([])

const running = ref(false)
const stopping = ref(false)
const jobId = ref(null)
const stepStatus = ref({})
const log = ref([])
const globalStatus = ref('')

const jobs = ref([])
const lastCompletedProjectId = ref(null)
const lastCompletedExportFilename = ref(null)

// Retry state — tracks the failed step and project for resume
const failedStep = ref(null)
const failedProjectId = ref(null)
const stoppedStep = ref(null)
const stoppedProjectId = ref(null)

let eventSource = null
let initialized = false

function inferResumeStep(statuses = {}) {
  const stepIds = ALL_STEPS.map(step => step.id)
  for (const stepId of stepIds) {
    if (statuses?.[stepId] === 'stopped' || statuses?.[stepId] === 'running') {
      return stepId
    }
  }
  for (const stepId of stepIds) {
    if (!['done', 'skipped'].includes(statuses?.[stepId])) {
      return stepId
    }
  }
  return null
}

function maybeOpenProviderLoadingTab({ stopValue, resumeStep = null }) {
  const stepIds = ALL_STEPS.map(step => step.id)
  const assetsIdx = stepIds.indexOf('assets')
  const stopIdx = stopValue ? stepIds.indexOf(stopValue) : -1
  const resumeIdx = resumeStep ? stepIds.indexOf(resumeStep) : -1
  const reachesAssets = !stopValue || stopIdx >= assetsIdx
  const startsBeforeAssets = resumeStep == null || resumeIdx <= assetsIdx
  if (!reachesAssets || !startsBeforeAssets) return
  try {
    const w = window.open('about:blank', 'sts-provider-tab')
    if (w) {
      w.document.write(providerTabLoadingHTML)
      w.document.close()
    }
  } catch {}
}

// ── Actions ──

async function start() {
  const toast = useToast()
  const t = text.value.trim()
  if (!t) {
    toast.error('Enter story text')
    return
  }
  if (speed.value < 0.5 || speed.value > 2.0) {
    toast.error('Speed must be between 0.5 and 2.0')
    return
  }

  resetProgress()
  running.value = true
  stopping.value = false

  const webhookUrl = localStorage.getItem('sts-scenes-webhook-url') || ''
  const config = {
    text: t,
    voice: voice.value,
    speed: speed.value,
    style: style.value,
    auto_scenes: autoScenes.value,
    stop_after: stopAfter.value || undefined,
    webhook_url: webhookUrl || undefined,
    // Asset grabber options
    provider: localStorage.getItem('sts-asset-provider') || 'grok',
    auto_type: true,
  }

  // Browsers block popups from async/SSE handlers, so open the provider tab now if needed.
  maybeOpenProviderLoadingTab({ stopValue: config.stop_after })

  try {
    const res = await api.post('/api/pipeline/run', { body: config })
    jobId.value = res.job_id
    failedProjectId.value = res.project_id
    stoppedProjectId.value = null
    stoppedStep.value = null
    globalStatus.value = 'running'
    toast.success('Pipeline started')
    startSSE(res.job_id)
  } catch (e) {
    toast.error(e.message || 'Pipeline failed to start')
    running.value = false
    stopping.value = false
  }
}

function startSSE(id) {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  eventSource = new EventSource(`/api/pipeline/progress/${id}`)

  eventSource.onmessage = (e) => {
    const event = JSON.parse(e.data)
    log.value = [...log.value, event]

    const step = event.step
    const status = event.status

    // Open provider URL if the backend requests it
    if (event.open_url) {
      try { window.open(event.open_url, 'sts-provider-tab') } catch {}
    }

    if (step === 'done') {
      const summary = event.summary || {}
      globalStatus.value = 'done'
      eventSource.close()
      eventSource = null
      running.value = false
      stopping.value = false
      jobId.value = null
      stoppedStep.value = null
      stoppedProjectId.value = null
      lastCompletedProjectId.value = summary.scenes?.project_id || event.project_id || null
      lastCompletedExportFilename.value = summary.export?.filename || null
      useDoneSound().play()
      setTimeout(() => loadHistory(), 500)
      return
    }
    if (step === 'stopped') {
      globalStatus.value = 'stopped'
      eventSource.close()
      eventSource = null
      running.value = false
      stopping.value = false
      jobId.value = null
      failedStep.value = null
      failedProjectId.value = null

      const resumeStep = event.resume_from
        || event.stopped_step
        || inferResumeStep(stepStatus.value)
        || null
      stoppedStep.value = resumeStep

      stoppedProjectId.value = event.project_id || stoppedProjectId.value || null
      setTimeout(() => loadHistory(), 500)
      return
    }
    if (step === 'error') {
      globalStatus.value = 'error'
      eventSource.close()
      eventSource = null
      running.value = false
      stopping.value = false
      jobId.value = null
      stoppedStep.value = null
      stoppedProjectId.value = null

      // Use error_step from backend (authoritative) with fallback to last running step
      const errorStep = event.error_step
        || Object.entries(stepStatus.value).find(([, s]) => s === 'running')?.[0]
        || null
      if (errorStep) {
        failedStep.value = errorStep
        // Mark the failed step as 'error' in stepStatus
        stepStatus.value = { ...stepStatus.value, [errorStep]: 'error' }
      }

      // Resolve project_id: prefer event field, then extract from message
      failedProjectId.value = event.project_id || failedProjectId.value || null
      if (!failedProjectId.value) {
        const pidMatch = (event.message || '').match(/\[(pp_\w+)\]/)
        if (pidMatch) failedProjectId.value = pidMatch[1]
      }

      setTimeout(() => loadHistory(), 500)
      return
    }

    stepStatus.value = { ...stepStatus.value, [step]: status }
    globalStatus.value = 'running'
  }

  eventSource.onerror = () => {
    eventSource.close()
    eventSource = null
    running.value = false
    stopping.value = false
    if (globalStatus.value === 'running') {
      globalStatus.value = 'error'
    }
  }
}

async function loadHistory() {
  try {
    const data = await api.get('/api/pipeline/jobs')
    jobs.value = data
  } catch (e) {
    console.warn('[Pipeline] Failed to load history:', e.message)
    jobs.value = []
  }
}

function loadFromHistory(index) {
  const j = jobs.value[index]
  if (!j) return
  if (j.text) text.value = j.text
  if (j.voice) voice.value = j.voice
  if (j.speed) speed.value = j.speed
  if (j.style) {
    const tmpl = templates.value.find(t => t.id === j.style)
    if (tmpl) style.value = tmpl.id
    else style.value = j.style
  }
  // Restore pipeline settings from step_statuses if available
  if (j.stop_after !== undefined) stopAfter.value = j.stop_after || ''
  if (j.auto_scenes !== undefined) autoScenes.value = j.auto_scenes

  // Restore step statuses for progress display
  if (j.step_statuses && Object.keys(j.step_statuses).length) {
    stepStatus.value = { ...j.step_statuses }
  } else {
    stepStatus.value = {}
  }

  running.value = false
  stopping.value = false
  jobId.value = null

  // Restore error/stopped state for resume
  if (j.status === 'error' && j.error_step) {
    globalStatus.value = 'error'
    failedStep.value = j.error_step
    failedProjectId.value = j.project_id
    stoppedStep.value = null
    stoppedProjectId.value = null
  } else if (j.status === 'stopped') {
    globalStatus.value = 'stopped'
    failedStep.value = null
    failedProjectId.value = null
    stoppedStep.value = j.resume_from || j.stopped_step || inferResumeStep(j.step_statuses) || null
    stoppedProjectId.value = j.project_id
  } else {
    failedStep.value = null
    failedProjectId.value = null
    stoppedStep.value = null
    stoppedProjectId.value = null
    globalStatus.value = j.status === 'done' ? 'done' : ''
  }
}

async function regenerateAssets(projectId) {
  const toast = useToast()
  if (!projectId) {
    toast.error('No project to regenerate assets for')
    return
  }
  try {
    const res = await api.post(`/api/pipeline/${projectId}/regenerate-assets`)
    if (res.open_url) {
      try { window.open(res.open_url, 'sts-provider-tab') } catch {}
    }
    toast.success(`Asset regeneration started (${res.scene_count} scenes)`)
    return res
  } catch (e) {
    toast.error(e.message || 'Failed to start asset regeneration')
    throw e
  }
}

function randomStory() {
  const toast = useToast()
  const story = pickRandomStory()
  if (!story) return
  text.value = story
  toast.success('Random story loaded')
}

function resetProgress() {
  stepStatus.value = {}
  log.value = []
  globalStatus.value = ''
  jobId.value = null
  stopping.value = false
  lastCompletedProjectId.value = null
  lastCompletedExportFilename.value = null
  failedStep.value = null
  failedProjectId.value = null
  stoppedStep.value = null
  stoppedProjectId.value = null
}

async function startResumedRun(resumeStep, resumeProject, { idleStatus = '', successMessage, failureMessage } = {}) {
  const toast = useToast()
  if (running.value) {
    toast.error('Pipeline is already running')
    return
  }
  if (!resumeStep || !resumeProject) {
    toast.error('No pipeline step to resume')
    return
  }

  const t = text.value.trim()
  if (!t) {
    toast.error('Enter story text')
    return
  }

  const previousStatus = globalStatus.value
  const previousStepStatus = { ...stepStatus.value }
  running.value = true
  stopping.value = false
  globalStatus.value = 'running'
  const newStatus = { ...stepStatus.value }
  newStatus[resumeStep] = 'running'
  stepStatus.value = newStatus

  const webhookUrl = localStorage.getItem('sts-scenes-webhook-url') || ''
  const config = {
    text: t,
    voice: voice.value,
    speed: speed.value,
    style: style.value,
    auto_scenes: autoScenes.value,
    stop_after: stopAfter.value || undefined,
    webhook_url: webhookUrl || undefined,
    provider: localStorage.getItem('sts-asset-provider') || 'grok',
    auto_type: true,
    resume_from: resumeStep,
    resume_project_id: resumeProject,
  }

  maybeOpenProviderLoadingTab({ stopValue: config.stop_after, resumeStep })

  try {
    const res = await api.post('/api/pipeline/run', { body: config })
    jobId.value = res.job_id
    failedStep.value = null
    failedProjectId.value = null
    stoppedStep.value = null
    stoppedProjectId.value = null
    toast.success(successMessage || `Resuming from ${resumeStep}...`)
    startSSE(res.job_id)
  } catch (e) {
    toast.error(e.message || failureMessage || 'Resume failed to start')
    running.value = false
    stopping.value = false
    globalStatus.value = idleStatus || previousStatus
    stepStatus.value = previousStepStatus
  }
}

async function retry() {
  return startResumedRun(failedStep.value, failedProjectId.value, {
    idleStatus: 'error',
    successMessage: `Retrying from ${failedStep.value}...`,
    failureMessage: 'Retry failed to start',
  })
}

async function stop() {
  const toast = useToast()
  if (!running.value || !jobId.value) {
    toast.error('No running pipeline to stop')
    return
  }
  if (stopping.value) return

  try {
    const res = await api.post(`/api/pipeline/${jobId.value}/stop`)
    stopping.value = true
    toast.info(`Stopping after ${res.current_step || res.resume_from || 'the current step'}...`)
  } catch (e) {
    toast.error(e.message || 'Failed to stop pipeline')
  }
}

async function resumeStopped() {
  return startResumedRun(stoppedStep.value, stoppedProjectId.value, {
    idleStatus: 'stopped',
    successMessage: `Resuming from ${stoppedStep.value}...`,
    failureMessage: 'Resume failed to start',
  })
}

function dispose() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  running.value = false
  stopping.value = false
}

async function init() {
  try {
    const data = await api.get('/api/scenes/templates')
    templates.value = data
  } catch (e) {
    console.warn('[Pipeline] Failed to load templates:', e.message)
    templates.value = [{ id: 'cinematic', name: 'Cinematic', color: '#4ECDC4' }]
  }

  const saved = localStorage.getItem('sts-pipeline-style')
  if (saved) {
    const match = templates.value.find(t => t.id === saved)
    if (match) style.value = saved
  } else {
    // Fall back to the default style from settings
    const { settings } = useSettings()
    const defaultStyle = settings.value['sts-default-style']
    if (defaultStyle && templates.value.find(t => t.id === defaultStyle)) {
      style.value = defaultStyle
    }
  }

  await loadHistory()
}

// ── Composable ──

export function usePipeline() {
  if (!initialized) {
    initialized = true
    init()
  }

  return {
    // Constants
    ALL_STEPS,
    VOICES,

    // State
    text,
    voice,
    speed,
    style,
    autoScenes,
    stopAfter,
    templates: readonly(templates),

    running: readonly(running),
    stopping: readonly(stopping),
    jobId: readonly(jobId),
    stepStatus: readonly(stepStatus),
    log: readonly(log),
    globalStatus: readonly(globalStatus),

    jobs: readonly(jobs),
    lastCompletedProjectId: readonly(lastCompletedProjectId),
    lastCompletedExportFilename: readonly(lastCompletedExportFilename),
    failedStep: readonly(failedStep),
    failedProjectId: readonly(failedProjectId),
    stoppedStep: readonly(stoppedStep),
    stoppedProjectId: readonly(stoppedProjectId),

    // Actions
    start,
    stop,
    retry,
    resumeStopped,
    regenerateAssets,
    loadHistory,
    loadFromHistory,
    randomStory,
    resetProgress,
    init,

    // Helpers
    timeAgo,

    // Cleanup
    dispose,
  }
}
