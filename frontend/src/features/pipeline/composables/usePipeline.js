import { ref, readonly } from 'vue'
import { api } from '@/shared/api/client.js'
import { useToast } from '@/shared/composables/useToast.js'
import { pickRandomStory } from '@/shared/composables/useRandomStory.js'
import { timeAgo } from '@/shared/utils/format.js'
import { useDoneSound } from '@/shared/composables/useDoneSound.js'

// ── Constants ──

const ALL_STEPS = [
  { id: 'tts', label: 'TTS', icon: '\uD83C\uDFA4' },
  { id: 'timing', label: 'Timing', icon: '\u23F1' },
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
const jobId = ref(null)
const stepStatus = ref({})
const log = ref([])
const globalStatus = ref('')

const jobs = ref([])
const lastCompletedProjectId = ref(null)
const lastCompletedExportFilename = ref(null)

let eventSource = null
let initialized = false

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

  running.value = true
  resetProgress()

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

  // Pre-open a named tab on user click if pipeline will reach assets step
  // (browsers block popups from async/SSE handlers, so we open now and navigate later via SSE open_url)
  const stopVal = config.stop_after
  const reachesAssets = !stopVal || ['assets', 'assemble', 'export'].includes(stopVal)
  if (reachesAssets) {
    try { window.open('about:blank', 'sts-provider-tab') } catch {}
  }

  try {
    const res = await api.post('/api/pipeline/run', { body: config })
    jobId.value = res.job_id
    globalStatus.value = 'running'
    toast.success('Pipeline started')
    startSSE(res.job_id)
  } catch (e) {
    toast.error(e.message || 'Pipeline failed to start')
    running.value = false
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
      lastCompletedProjectId.value = summary.scenes?.project_id || event.project_id || null
      lastCompletedExportFilename.value = summary.export?.filename || null
      useDoneSound().play()
      setTimeout(() => loadHistory(), 500)
      return
    }
    if (step === 'error') {
      globalStatus.value = 'error'
      eventSource.close()
      eventSource = null
      running.value = false
      return
    }

    stepStatus.value = { ...stepStatus.value, [step]: status }
    globalStatus.value = 'running'
  }

  eventSource.onerror = () => {
    eventSource.close()
    eventSource = null
    running.value = false
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
    const tmpl = templates.value.find(t => j.style.toLowerCase().includes(t.id))
    if (tmpl) style.value = tmpl.id
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
  lastCompletedProjectId.value = null
  lastCompletedExportFilename.value = null
}

function dispose() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
  running.value = false
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
    jobId: readonly(jobId),
    stepStatus: readonly(stepStatus),
    log: readonly(log),
    globalStatus: readonly(globalStatus),

    jobs: readonly(jobs),
    lastCompletedProjectId: readonly(lastCompletedProjectId),
    lastCompletedExportFilename: readonly(lastCompletedExportFilename),

    // Actions
    start,
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
