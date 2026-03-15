import { ref, readonly } from 'vue'
import { api } from '@/shared/api/client.js'
import { useToast } from '@/shared/composables/useToast.js'
import { RANDOM_STORIES } from '@/shared/data/stories.js'
import { timeAgo } from '@/shared/utils/format.js'
import { useDoneSound } from '@/shared/composables/useDoneSound.js'

// ── Constants ──

const STEPS = [
  { id: 'tts', label: 'TTS', icon: '\uD83C\uDFA4' },
  { id: 'timing', label: 'Timing', icon: '\u23F1' },
  { id: 'segment', label: 'Segment', icon: '\u2702' },
  { id: 'scenes', label: 'Scenes', icon: '\uD83C\uDFAC' },
]

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
const templates = ref([])

const running = ref(false)
const jobId = ref(null)
const stepStatus = ref({})
const log = ref([])
const globalStatus = ref('')

const jobs = ref([])
const lastCompletedProjectId = ref(null)

let eventSource = null
let lastStoryIdx = -1
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
    webhook_url: webhookUrl || undefined,
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

    if (step === 'done') {
      globalStatus.value = 'done'
      eventSource.close()
      eventSource = null
      running.value = false
      lastCompletedProjectId.value = event.summary?.scenes?.project_id || null
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
  if (!RANDOM_STORIES.length) return
  let idx
  do {
    idx = Math.floor(Math.random() * RANDOM_STORIES.length)
  } while (idx === lastStoryIdx && RANDOM_STORIES.length > 1)
  lastStoryIdx = idx
  text.value = RANDOM_STORIES[idx]
  toast.success('Random story loaded')
}

function resetProgress() {
  stepStatus.value = {}
  log.value = []
  globalStatus.value = ''
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
    STEPS,
    VOICES,

    // State
    text,
    voice,
    speed,
    style,
    autoScenes,
    templates: readonly(templates),

    running: readonly(running),
    jobId: readonly(jobId),
    stepStatus: readonly(stepStatus),
    log: readonly(log),
    globalStatus: readonly(globalStatus),

    jobs: readonly(jobs),
    lastCompletedProjectId: readonly(lastCompletedProjectId),

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
