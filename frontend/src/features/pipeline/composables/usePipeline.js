import { ref, readonly } from 'vue'
import { api } from '@/shared/api/client.js'
import { useToast } from '@/shared/composables/useToast.js'
import { useActivityFeed } from '@/shared/composables/useActivityFeed.js'
import { pickRandomStory } from '@/shared/composables/useRandomStory.js'
import { timeAgo } from '@/shared/utils/format.js'
import { useDoneSound } from '@/shared/composables/useDoneSound.js'
import { useProviderCatalogStore } from '@/features/providers/stores/providerCatalog.js'

import { ALL_STEPS } from '../constants/steps.js'
import { usePipelineForm } from './usePipelineForm.js'
import { useNiches } from './useNiches.js'
import { useProviderTabs } from './useProviderTabs.js'
import { usePipelineHistory } from './usePipelineHistory.js'

/** Canonical selected id for a domain, loaded from the provider catalog. */
function _selectedProviderId(domain) {
  const catalog = useProviderCatalogStore()
  catalog.loadCatalog()
  return catalog.selectedProvider(domain)?.id || ''
}

// ── Execution state (singleton) ──

const running = ref(false)
const stopping = ref(false)
const jobId = ref(null)
const stepStatus = ref({})
const log = ref([])
const globalStatus = ref('')

const failedStep = ref(null)
const failedProjectId = ref(null)
const stoppedStep = ref(null)
const stoppedProjectId = ref(null)
const sceneNotifications = ref([])
const batchMode = ref(false)  // true when job queue is running — suppresses per-job done sound

let eventSource = null
let initialized = false
let _lastSceneReady = 0

// ── SSE ──

function _closeSSE() {
  if (eventSource) { eventSource.close(); eventSource = null }
  running.value = false
  stopping.value = false
  jobId.value = null
}

function startSSE(id) {
  const { _openInProviderTab } = useProviderTabs()
  const { loadHistory, lastCompletedProjectId, lastCompletedExportFilename, inferResumeStep } = usePipelineHistory()

  if (eventSource) { eventSource.close(); eventSource = null }
  running.value = true
  jobId.value = id
  eventSource = new EventSource(`/api/pipeline/progress/${id}`)

  const activity = useActivityFeed()

  eventSource.onmessage = (e) => {
    const event = JSON.parse(e.data)
    log.value = [...log.value, event]

    const step = event.step
    const status = event.status

    if (event.open_url) {
      try { _openInProviderTab(event.open_url, step) } catch {}
    }

    if (step === 'done') {
      const summary = event.summary || {}
      globalStatus.value = 'done'
      _closeSSE()
      stoppedStep.value = null
      stoppedProjectId.value = null
      lastCompletedProjectId.value = summary.scenes?.project_id || event.project_id || null
      lastCompletedExportFilename.value = summary.export?.filename || null
      activity.push('Pipeline complete', 'success', { source: 'pipeline' })
      if (!batchMode.value) useDoneSound().play()
      setTimeout(() => loadHistory(), 500)
      return
    }
    if (step === 'stopped') {
      globalStatus.value = 'stopped'
      _closeSSE()
      failedStep.value = null
      failedProjectId.value = null
      stoppedStep.value = event.resume_from
        || event.stopped_step
        || inferResumeStep(stepStatus.value)
        || null
      stoppedProjectId.value = event.project_id || stoppedProjectId.value || null
      activity.push(`Pipeline stopped at ${stoppedStep.value || 'unknown step'}`, 'warning', { source: 'pipeline' })
      setTimeout(() => loadHistory(), 500)
      return
    }
    if (step === 'error') {
      globalStatus.value = 'error'
      _closeSSE()
      stoppedStep.value = null
      stoppedProjectId.value = null

      const errorStep = event.error_step
        || Object.entries(stepStatus.value).find(([, s]) => s === 'running')?.[0]
        || null
      if (errorStep) {
        failedStep.value = errorStep
        stepStatus.value = { ...stepStatus.value, [errorStep]: 'error' }
      }

      failedProjectId.value = event.project_id || failedProjectId.value || null
      if (!failedProjectId.value) {
        const pidMatch = (event.message || '').match(/\[(pp_\w+)\]/)
        if (pidMatch) failedProjectId.value = pidMatch[1]
      }

      activity.push(event.message || `Pipeline error at ${errorStep || 'unknown step'}`, 'error', { source: 'pipeline' })
      setTimeout(() => usePipelineHistory().loadHistory(), 500)
      return
    }

    // Track per-scene completions (no sound — sound only on final export done)
    if ((step === 'assets' || step === 'storyboard') && event.scene_ready != null) {
      const ready = event.scene_ready
      const total = event.scene_total || 0
      if (event.scene_new && ready > _lastSceneReady) {
        const label = step === 'assets' ? 'Video' : 'Image'
        sceneNotifications.value = [...sceneNotifications.value, {
          id: Date.now(),
          type: 'success',
          step,
          scene: ready,
          total,
          message: `${label} ${ready}/${total} ready`,
          time: new Date(),
        }]
        activity.push(`${label} ${ready}/${total} ready`, 'success', { source: 'pipeline', step })
      }
      _lastSceneReady = ready
    }

    // Push step progress to activity feed
    if (event.message) {
      activity.push(event.message, 'pipeline', { source: 'pipeline', step })
    }

    stepStatus.value = { ...stepStatus.value, [step]: status }
    globalStatus.value = 'running'
  }

  eventSource.onerror = () => {
    const wasRunning = globalStatus.value === 'running'
    _closeSSE()
    if (wasRunning) {
      globalStatus.value = 'error'
      activity.push('Pipeline connection lost', 'error', { source: 'pipeline' })
    }
  }
}

// ── Actions ──

function resetProgress() {
  stepStatus.value = {}
  log.value = []
  globalStatus.value = ''
  jobId.value = null
  stopping.value = false
  sceneNotifications.value = []
  _lastSceneReady = 0
  const hist = usePipelineHistory()
  hist.lastCompletedProjectId.value = null
  hist.lastCompletedExportFilename.value = null
  failedStep.value = null
  failedProjectId.value = null
  stoppedStep.value = null
  stoppedProjectId.value = null
}

async function start() {
  const toast = useToast()
  const form = usePipelineForm()
  const niches = useNiches()

  const t = form.text.value.trim()
  if (!t) { toast.error('Enter story text'); return false }
  if (form.speed.value < 0.5 || form.speed.value > 2.0) {
    toast.error('Speed must be between 0.5 and 2.0'); return false
  }

  // Preflight: check extension connectivity before starting. Selections come
  // from the provider catalog (step 16.1) — never from the retired app-config keys.
  const storyboardProvider = _selectedProviderId('storyboard')
  const assetProvider = _selectedProviderId('animator')
  const stopValue = form.stopAfter.value || undefined

  // Stay focused on STS at start. Each provider tab is activated only when
  // its step actually emits an open_url SSE event, gated by the activate-tab
  // endpoint's WS handshake-with-retry.
  try {
    const preflight = await api.post('/api/pipeline/preflight', {
      body: {
        stop_after: stopValue || '',
        storyboard_provider: storyboardProvider,
        asset_provider: assetProvider,
      },
    })
    if (preflight.warnings?.length) {
      for (const warning of preflight.warnings) {
        const detail = warning.queued
          ? `run will queue and continue when the ${warning.target} tab reconnects`
          : 'run may wait for the provider tab'
        toast.warning(`${warning.message} — ${detail}`, 7000)
      }
    }
    if (!preflight.ok && preflight.issues?.length) {
      for (const issue of preflight.issues) {
        toast.error(`${issue.message} — open the ${issue.target} tab first`, 6000)
      }
      return false
    }
  } catch {
    // Preflight endpoint unavailable — proceed anyway
  }

  resetProgress()
  running.value = true
  stopping.value = false
  globalStatus.value = 'running'
  stepStatus.value = { [ALL_STEPS[0].id]: 'running' }

  const webhookUrl = localStorage.getItem('sts-scenes-webhook-url') || ''
  const config = {
    text: t,
    voice: form.kokoroVoice.value,
    speed: form.speed.value,
    style: form.style.value,
    ...niches._buildNicheConfig(),
    tts_provider: form.ttsProvider.value || _selectedProviderId('tts') || undefined,
    tts_voice: form.voice.value,
    auto_scenes: true,
    auto_storyboard: true,
    stop_after: stopValue,
    webhook_url: webhookUrl || undefined,
    image_model: form.imageModel.value || undefined,
    storyboard_provider: storyboardProvider || undefined,
    prompt_prefix: localStorage.getItem('sts-prompt-prefix') ?? 'generate an image ',
    provider: assetProvider || undefined,
    auto_type: true,
  }

  try {
    const res = await api.post('/api/pipeline/run', { body: config })
    jobId.value = res.job_id
    failedProjectId.value = res.project_id
    stoppedProjectId.value = null
    stoppedStep.value = null
    globalStatus.value = 'running'
    toast.success('Pipeline started')
    startSSE(res.job_id)
    return true
  } catch (e) {
    toast.error(e.message || 'Pipeline failed to start')
    running.value = false
    stopping.value = false
    return false
  }
}

async function startResumedRun(resumeStep, resumeProject, { idleStatus = '', successMessage, failureMessage } = {}) {
  const toast = useToast()
  const form = usePipelineForm()
  const niches = useNiches()

  if (running.value) { toast.error('Pipeline is already running'); return }
  if (!resumeStep || !resumeProject) { toast.error('No pipeline step to resume'); return }

  const t = form.text.value.trim()
  if (!t) { toast.error('Enter story text'); return }

  const previousStatus = globalStatus.value
  const previousStepStatus = { ...stepStatus.value }
  running.value = true
  stopping.value = false
  globalStatus.value = 'running'
  stepStatus.value = { ...stepStatus.value, [resumeStep]: 'running' }

  const webhookUrl = localStorage.getItem('sts-scenes-webhook-url') || ''
  const config = {
    text: t,
    voice: form.kokoroVoice.value,
    speed: form.speed.value,
    style: form.style.value,
    ...niches._buildNicheConfig(),
    tts_provider: form.ttsProvider.value || _selectedProviderId('tts') || undefined,
    tts_voice: form.voice.value,
    auto_scenes: true,
    auto_storyboard: true,
    stop_after: form.stopAfter.value || undefined,
    webhook_url: webhookUrl || undefined,
    image_model: form.imageModel.value || undefined,
    storyboard_provider: _selectedProviderId('storyboard') || undefined,
    prompt_prefix: localStorage.getItem('sts-prompt-prefix') ?? 'generate an image ',
    provider: _selectedProviderId('animator') || undefined,
    auto_type: true,
    resume_from: resumeStep,
    resume_project_id: resumeProject,
  }

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
  if (!running.value || !jobId.value) { toast.error('No running pipeline to stop'); return }
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

async function regenerateAssets(projectId) {
  const toast = useToast()
  const { _openInProviderTab } = useProviderTabs()
  if (!projectId) { toast.error('No project to regenerate assets for'); return }
  try {
    const res = await api.post(`/api/pipeline/${projectId}/regenerate-assets`)
    if (res.open_url) {
      try { _openInProviderTab(res.open_url, 'assets') } catch {}
    }
    toast.success(`Asset regeneration started (${res.scene_count} scenes)`)
    return res
  } catch (e) {
    toast.error(e.message || 'Failed to start asset regeneration')
    throw e
  }
}

async function randomStory() {
  const toast = useToast()
  const { text } = usePipelineForm()
  try {
    const story = await pickRandomStory()
    if (!story) return
    text.value = story
    toast.success('Random story loaded')
  } catch (e) {
    toast.error(e.message || 'Failed to load random story')
  }
}

function loadFromHistory(index) {
  const form = usePipelineForm()
  const niches = useNiches()
  const hist = usePipelineHistory()
  const j = hist.jobs.value[index]
  if (!j) return

  if (j.text) form.text.value = j.text
  if (j.voice) form.kokoroVoice.value = j.voice
  if (j.speed) form.speed.value = j.speed
  if (j.niche_preset && niches.nichePresets.value[j.niche_preset]) {
    niches.selectNiche({ id: j.niche_preset, ...niches.nichePresets.value[j.niche_preset] })
  } else {
    niches.clearNiche()
  }
  if (j.style) {
    const tmpl = form.templates.value.find(t => t.id === j.style)
    if (tmpl) form.style.value = tmpl.id
    else form.style.value = j.style
  }
  if (j.visual_style || j.style) niches.setVisualStyleOverride(j.visual_style || j.style)
  if (Object.prototype.hasOwnProperty.call(j, 'story_tone')) niches.setStoryTone(j.story_tone || '')
  if (Object.prototype.hasOwnProperty.call(j, 'category')) niches.setNicheCategory(j.category || '')
  if (j.stop_after !== undefined) form.stopAfter.value = j.stop_after || ''

  if (j.step_statuses && Object.keys(j.step_statuses).length) {
    stepStatus.value = { ...j.step_statuses }
  } else {
    stepStatus.value = {}
  }

  running.value = false
  stopping.value = false
  jobId.value = null

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
    stoppedStep.value = j.resume_from || j.stopped_step || hist.inferResumeStep(j.step_statuses) || null
    stoppedProjectId.value = j.project_id
  } else {
    failedStep.value = null
    failedProjectId.value = null
    stoppedStep.value = null
    stoppedProjectId.value = null
    globalStatus.value = j.status === 'done' ? 'done' : ''
  }
}

function dispose() {
  if (eventSource) { eventSource.close(); eventSource = null }
  running.value = false
  stopping.value = false
}

async function init() {
  const niches = useNiches()
  const hist = usePipelineHistory()
  await niches.loadNiches()
  await hist.loadHistory()
}

// ── Composable (backward-compatible facade) ──

export function usePipeline() {
  if (!initialized) {
    initialized = true
    init()
  }

  const form = usePipelineForm()
  const niches = useNiches()
  const providerTabs = useProviderTabs()
  const hist = usePipelineHistory()

  return {
    // Constants
    ALL_STEPS,
    VOICES: form.VOICES,

    // Form state
    text: form.text,
    voice: form.voice,
    kokoroVoice: form.kokoroVoice,
    inworldVoice: form.inworldVoice,
    speed: form.speed,
    style: form.style,
    ttsProvider: form.ttsProvider,
    favorites: form.favorites,
    toggleFavorite: form.toggleFavorite,
    isFavorite: form.isFavorite,
    stopAfter: form.stopAfter,
    imageModel: form.imageModel,
    imageModelsConfig: readonly(form.imageModelsConfig),
    templates: readonly(form.templates),

    // Execution state
    running: readonly(running),
    batchMode,
    stopping: readonly(stopping),
    jobId: readonly(jobId),
    stepStatus: readonly(stepStatus),
    log: readonly(log),
    globalStatus: readonly(globalStatus),
    sceneNotifications: readonly(sceneNotifications),

    // History
    jobs: hist.jobs,
    lastCompletedProjectId: readonly(hist.lastCompletedProjectId),
    lastCompletedExportFilename: readonly(hist.lastCompletedExportFilename),
    failedStep: readonly(failedStep),
    failedProjectId: readonly(failedProjectId),
    stoppedStep: readonly(stoppedStep),
    stoppedProjectId: readonly(stoppedProjectId),

    // Niche state
    nichePreset: niches.nichePreset,
    visualStyle: niches.visualStyle,
    storyTone: niches.storyTone,
    nicheCategory: niches.nicheCategory,
    nichePresets: niches.nichePresets,
    storyTones: niches.storyTones,
    nicheCategories: niches.nicheCategories,
    visualStyles: niches.visualStyles,
    nichesLoaded: niches.nichesLoaded,

    // Actions
    start,
    stop,
    retry,
    resumeStopped,
    regenerateAssets,
    loadHistory: hist.loadHistory,
    loadFromHistory,
    randomStory,
    resetProgress,
    selectNiche: niches.selectNiche,
    clearNiche: niches.clearNiche,
    saveNichePreset: niches.saveNichePreset,
    deleteNichePreset: niches.deleteNichePreset,
    setVisualStyleOverride: niches.setVisualStyleOverride,
    setStoryTone: niches.setStoryTone,
    setNicheCategory: niches.setNicheCategory,
    init,

    // Provider tab
    pendingProviderUrl: providerTabs.pendingProviderUrl,
    openPendingProvider: providerTabs.openPendingProvider,

    // Helpers
    timeAgo,

    // Cleanup
    dispose,
  }
}
