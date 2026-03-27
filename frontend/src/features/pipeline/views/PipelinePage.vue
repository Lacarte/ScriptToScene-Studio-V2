<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/shared/api/client.js'
import { usePipeline } from '../composables/usePipeline.js'
import { CATEGORY_COLORS, withAlpha, categoryColor, statusColor, stepColor, stepTextColor, logEntryIcon, logEntryColor } from '../constants/colors.js'
import NichePicker from '../components/NichePicker.vue'
import ProgressStepper from '../components/ProgressStepper.vue'
import PipelineLog from '../components/PipelineLog.vue'
import PipelineHistory from '../components/PipelineHistory.vue'
import { useScenes } from '@/features/scenes/composables/useScenes.js'
import { useAssets } from '@/features/assets/composables/useAssets.js'
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
  if (tmpl) setStyle(styleId)
}

// Category and Style are now independent (decoupled in Phase 3)
function setCategory(id) {
  story.storyCategory.value = id
  setNicheCategory(id)
}
function setStyle(id) {
  setVisualStyleOverride(id)
}

function handleNicheSelect(preset) {
  if (!preset) {
    clearNiche()
    return
  }
  selectNiche(preset)
  story.storyCategory.value = preset.category || story.storyCategory.value
  if (preset.duration) story.storyDuration.value = preset.duration
}

async function handleNicheSave(presetData) {
  const result = await saveNichePreset(presetData)
  if (result.ok) toast.success(`Niche "${presetData.label}" saved`)
  else toast.error(result.error || 'Failed to save niche')
}

async function handleNicheDelete(presetId) {
  const result = await deleteNichePreset(presetId)
  if (result.ok) toast.success('Niche deleted')
  else toast.error(result.error || 'Failed to delete niche')
}

const detecting = ref(false)
const detectedStyle = ref(null) // { style_id, confidence, reason }
const showGenHistory = ref(false)

async function detectStyle() {
  const t = text.value.trim()
  if (!t) { toast.error('Paste some text first'); return }
  detecting.value = true
  detectedStyle.value = null
  try {
    const webhookUrl = story.webhookUrl.value?.trim()
    const result = await api.post('/api/story/classify-style', {
      body: {
        text: t,
        webhook_url: webhookUrl || undefined,
      },
      timeout: 35000,
    })
    if (result.error) { toast.error(result.error); return }
    detectedStyle.value = result
    setStyle(result.style_id)
    const tmpl = templates.value.find(tp => tp.id === result.style_id)
    const label = tmpl?.name || result.style_id
    const pct = Math.round((result.confidence || 0) * 100)
    toast.success(`Detected: ${label} (${pct}%) — ${result.reason || ''}`)
  } catch (e) {
    toast.error(e.message || 'Style detection failed')
  } finally {
    detecting.value = false
  }
}

// ── Audio preview (cached WAV or stream TTS) ──
const previewing = ref(false)
const previewLabel = ref('')
let _previewAbort = null
let _previewCtx = null
let _previewAudioEl = null

async function previewAudio() {
  const t = text.value.trim()
  if (!t) { toast.error('Enter story text first'); return }
  if (previewing.value) { stopPreview(); return }

  previewing.value = true
  previewLabel.value = 'Checking cache...'
  const ctrl = new AbortController()
  _previewAbort = ctrl

  try {
    // 1. Check if cached WAV exists
    const cacheResp = await fetch('/api/tts/cache/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: t, voice: voice.value, speed: speed.value }),
      signal: ctrl.signal,
    })
    const cacheData = await cacheResp.json()

    if (cacheData.cached) {
      // Play cached WAV directly — instant playback
      previewLabel.value = 'Playing (cached)'
      const audio = new Audio(`/api/tts/cache/${cacheData.key}`)
      _previewAudioEl = audio
      // Wait for playback to finish OR user stop (pause event)
      await new Promise((resolve, reject) => {
        audio.onended = resolve
        audio.onpause = resolve
        audio.onerror = () => reject(new Error('Cached audio playback failed'))
        audio.play().catch(reject)
      })
      return
    }

    // 2. Not cached — stream from TTS and let backend cache it
    //    Retry on 429 (another stream in progress) with backoff
    previewLabel.value = 'Generating...'
    let resp
    const MAX_RETRIES = 10
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      resp = await fetch('/api/tts/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'kokoro',
          voice: voice.value,
          speed: speed.value,
          prompt: t,
        }),
        signal: ctrl.signal,
      })
      if (resp.status !== 429) break
      if (attempt === MAX_RETRIES) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.error || 'TTS busy — try again shortly')
      }
      previewLabel.value = 'Waiting for TTS...'
      await new Promise(r => setTimeout(r, 2000))
    }

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error(err.error || `TTS failed (${resp.status})`)
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 })
    _previewCtx = audioCtx
    let nextPlayTime = audioCtx.currentTime
    let buf = ''
    let chunks = 0

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const d = JSON.parse(line.slice(6))
        if (d.phase === 'audio') {
          chunks++
          const pcm = Uint8Array.from(atob(d.samples), c => c.charCodeAt(0))
          const float32 = new Float32Array(pcm.buffer)
          const audioBuf = audioCtx.createBuffer(1, float32.length, d.sample_rate)
          audioBuf.getChannelData(0).set(float32)
          const source = audioCtx.createBufferSource()
          source.buffer = audioBuf
          source.connect(audioCtx.destination)
          if (nextPlayTime < audioCtx.currentTime) nextPlayTime = audioCtx.currentTime
          source.start(nextPlayTime)
          nextPlayTime += audioBuf.duration
          previewLabel.value = `Playing · chunk ${chunks}`
        } else if (d.phase === 'done') {
          previewLabel.value = `Playing · ${chunks} chunks`
        } else if (d.phase === 'error') {
          throw new Error(d.message)
        }
      }
    }

    // Wait for playback to finish
    const remaining = nextPlayTime - audioCtx.currentTime
    if (remaining > 0) {
      await new Promise(r => setTimeout(r, remaining * 1000 + 300))
    }
  } catch (e) {
    if (e.name !== 'AbortError') toast.error(e.message || 'Preview failed')
  } finally {
    stopPreview()
  }
}

function stopPreview() {
  if (_previewAbort) { _previewAbort.abort(); _previewAbort = null }
  if (_previewCtx) { try { _previewCtx.close() } catch {} _previewCtx = null }
  if (_previewAudioEl) {
    _previewAudioEl.pause()
    _previewAudioEl.removeAttribute('src')
    _previewAudioEl.load()  // release the connection
    _previewAudioEl = null
  }
  previewing.value = false
  previewLabel.value = ''
}

onUnmounted(stopPreview)

// ── Jobs Pane ──
const jobPaneTab = ref('queue') // 'queue' | 'saved'
const showJobPane = ref(false)

// ── Auto-generated Job Queue ──
const JOB_QUEUE_KEY = 'sts-job-queue'
const jobQueue = ref(JSON.parse(localStorage.getItem(JOB_QUEUE_KEY) || '[]'))
const jobQueueRunning = ref(false)
const jobQueueCurrent = ref(null) // { presetId, index, total }

function _persistJobQueue() {
  localStorage.setItem(JOB_QUEUE_KEY, JSON.stringify(jobQueue.value))
}

function addToQueue(presetId) {
  const existing = jobQueue.value.find(q => q.presetId === presetId)
  if (existing) {
    existing.count++
  } else {
    const preset = nichePresets.value[presetId]
    if (!preset) return
    jobQueue.value.push({ presetId, count: 1, label: preset.label || presetId })
  }
  _persistJobQueue()
}

function removeFromQueue(presetId) {
  const existing = jobQueue.value.find(q => q.presetId === presetId)
  if (!existing) return
  existing.count--
  if (existing.count <= 0) {
    jobQueue.value = jobQueue.value.filter(q => q.presetId !== presetId)
  }
  _persistJobQueue()
}

function deleteFromQueue(presetId) {
  jobQueue.value = jobQueue.value.filter(q => q.presetId !== presetId)
  _persistJobQueue()
}

function clearQueue() {
  jobQueue.value = []
  _persistJobQueue()
}

const totalQueuedJobs = computed(() => jobQueue.value.reduce((sum, q) => sum + q.count, 0))

async function runJobQueue() {
  if (jobQueueRunning.value || running.value) return
  if (!jobQueue.value.length) { toast.error('Queue is empty'); return }

  jobQueueRunning.value = true
  const queue = [...jobQueue.value] // snapshot
  let jobIndex = 0

  for (const item of queue) {
    const preset = nichePresets.value[item.presetId]
    if (!preset) continue

    for (let i = 0; i < item.count; i++) {
      jobIndex++
      jobQueueCurrent.value = { presetId: item.presetId, index: jobIndex, total: totalQueuedJobs.value, label: item.label }

      // Apply preset settings
      selectNiche(preset)
      story.storyCategory.value = preset.category || story.storyCategory.value
      if (preset.duration) story.storyDuration.value = preset.duration

      // Generate a story for this preset
      try {
        const generated = await handleGenerateStory({ notifySuccess: false })
        if (!generated.ok) {
          toast.error(`Queue job ${jobIndex} failed to generate story`)
          continue
        }
        // Run the pipeline
        await start()
        // Wait for pipeline to finish (watch globalStatus)
        await new Promise((resolve) => {
          const unwatch = watch(globalStatus, (status) => {
            if (status === 'done' || status === 'error' || status === 'stopped') {
              unwatch()
              resolve()
            }
          })
          // Safety: if not running after start, resolve immediately
          if (!running.value) { unwatch(); resolve() }
        })
      } catch (e) {
        toast.error(`Queue job ${jobIndex} error: ${e.message || 'unknown'}`)
      }
    }
  }

  jobQueueRunning.value = false
  jobQueueCurrent.value = null
  clearQueue()
  toast.success(`Job queue complete — ${jobIndex} jobs processed`)
}

function stopJobQueue() {
  jobQueueRunning.value = false
  jobQueueCurrent.value = null
  if (running.value) stop()
}

// ── Saved Stories (Job Histories) ──
const SAVED_STORIES_KEY = 'sts-saved-stories'
const savedStories = ref(JSON.parse(localStorage.getItem(SAVED_STORIES_KEY) || '[]'))

function _persistSavedStories() {
  localStorage.setItem(SAVED_STORIES_KEY, JSON.stringify(savedStories.value))
}

function saveCurrentStory() {
  const t = text.value.trim()
  if (!t) { toast.error('No story text to save'); return }

  const entry = {
    id: Date.now(),
    text: t,
    title: t.slice(0, 60).replace(/\n/g, ' ') + (t.length > 60 ? '...' : ''),
    style: style.value || '',
    visualStyle: visualStyle.value || '',
    storyTone: storyTone.value || '',
    category: nicheCategory.value || '',
    voice: voice.value || '',
    speed: speed.value || 1.0,
    savedAt: new Date().toISOString(),
  }
  savedStories.value.unshift(entry)
  if (savedStories.value.length > 50) savedStories.value = savedStories.value.slice(0, 50)
  _persistSavedStories()
  toast.success('Story saved')
}

function loadSavedStory(entry) {
  text.value = entry.text
  if (entry.voice) voice.value = entry.voice
  if (entry.speed) speed.value = entry.speed
  if (entry.style) style.value = entry.style
  if (entry.visualStyle) setVisualStyleOverride(entry.visualStyle)
  if (entry.storyTone) setStoryTone(entry.storyTone)
  if (entry.category) setNicheCategory(entry.category)
  showJobPane.value = false
  toast.success('Story loaded')
}

async function runSavedStory(entry) {
  if (running.value || jobQueueRunning.value) { toast.error('Pipeline is already running'); return }
  loadSavedStory(entry)
  showJobPane.value = false
  await nextTick()
  await start()
}

const savedQueueRunning = ref(false)
const savedQueueCurrent = ref(null) // { index, total, title }

async function runAllSavedStories() {
  if (running.value || jobQueueRunning.value || savedQueueRunning.value) { toast.error('Pipeline is already running'); return }
  if (!savedStories.value.length) { toast.error('No saved stories'); return }

  savedQueueRunning.value = true
  const stories = [...savedStories.value]

  for (let i = 0; i < stories.length; i++) {
    if (!savedQueueRunning.value) break // stopped

    const entry = stories[i]
    savedQueueCurrent.value = { index: i + 1, total: stories.length, title: entry.title }

    // Load story settings
    text.value = entry.text
    if (entry.voice) voice.value = entry.voice
    if (entry.speed) speed.value = entry.speed
    if (entry.style) style.value = entry.style
    if (entry.visualStyle) setVisualStyleOverride(entry.visualStyle)
    if (entry.storyTone) setStoryTone(entry.storyTone)
    if (entry.category) setNicheCategory(entry.category)

    await nextTick()

    try {
      await start()
      // Wait for pipeline to finish
      await new Promise((resolve) => {
        const unwatch = watch(globalStatus, (status) => {
          if (status === 'done' || status === 'error' || status === 'stopped') {
            unwatch()
            resolve()
          }
        })
        if (!running.value) { unwatch(); resolve() }
      })
    } catch (e) {
      toast.error(`Saved job ${i + 1} error: ${e.message || 'unknown'}`)
    }
  }

  savedQueueRunning.value = false
  savedQueueCurrent.value = null
  if (savedQueueRunning.value !== false) toast.success(`All ${stories.length} saved stories processed`)
}

function stopSavedQueue() {
  savedQueueRunning.value = false
  savedQueueCurrent.value = null
  if (running.value) stop()
}

function deleteSavedStory(id) {
  savedStories.value = savedStories.value.filter(s => s.id !== id)
  _persistSavedStories()
}

function savedStoryAge(entry) {
  const ms = Date.now() - new Date(entry.savedAt).getTime()
  const mins = Math.floor(ms / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

async function handleGenerateStory({ notifySuccess = true } = {}) {
  const previousText = text.value
  try {
    const data = await story.generateStory(style.value, { storyTone: storyTone.value || undefined })
    // Strip section labels for clean pipeline text
    const plain = data.story_text
      .replace(/^(Hook|Build|Climax|CTA):\s*/gim, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim()
    text.value = plain
    if (notifySuccess) toast.success('Story generated and applied')
    return { ok: true, data, text: plain }
  } catch (e) {
    text.value = previousText
    toast.error(e.message || 'Story generation failed')
    return { ok: false, error: e }
  }
}

async function handleGenerateFromIdea() {
  const idea = text.value.trim()
  if (!idea) return
  const previousText = text.value
  try {
    const data = await story.generateStory(style.value, {
      storyTone: storyTone.value || undefined,
      idea,
    })
    const plain = data.story_text
      .replace(/^(Hook|Build|Climax|CTA):\s*/gim, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim()
    text.value = plain
    toast.success('Story generated from your idea')
  } catch (e) {
    text.value = previousText
    toast.error(e.message || 'Story generation failed')
  }
}

async function loadFromGenHistory(h) {
  try {
    const data = await story.loadStory(h.project_id)
    const plain = (data.story_text || '')
      .replace(/^(Hook|Build|Climax|CTA):\s*/gim, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim()
    text.value = plain
    if (h.preset_style) style.value = h.preset_style
    if (h.story_category) story.storyCategory.value = h.story_category
    showGenHistory.value = false
    toast.success(`Loaded story ${h.project_id}`)
  } catch (e) {
    toast.error(e.message || 'Failed to load story')
  }
}

const router = useRouter()
const {
  ALL_STEPS, VOICES,
  text, voice, speed, style, stopAfter, imageModel, imageModelsConfig, templates,
  running, stopping, stepStatus, log, globalStatus,
  jobs, lastCompletedProjectId, lastCompletedExportFilename,
  failedStep, failedProjectId, stoppedStep, stoppedProjectId,
  nichePreset, nichePresets, storyTone, storyTones, visualStyles, nicheCategories,
  visualStyle, nicheCategory,
  start, stop, retry, resumeStopped, loadFromHistory, randomStory, resetProgress,
  selectNiche, clearNiche, saveNichePreset, deleteNichePreset,
  setVisualStyleOverride, setStoryTone, setNicheCategory,
  pendingProviderUrl, openPendingProvider,
  timeAgo,
} = usePipeline()

const assets = useAssets()

const STEPS = computed(() => {
  const stop = stopAfter.value
  if (!stop) return ALL_STEPS
  const idx = ALL_STEPS.findIndex(s => s.id === stop)
  return idx >= 0 ? ALL_STEPS.slice(0, idx + 1) : ALL_STEPS
})

const { styleLabel, styleColor } = useScenes()

const availableImageModels = computed(() => {
  const cfg = imageModelsConfig.value || {}
  const styleCfg = cfg[style.value] || cfg['default'] || {}
  return styleCfg.models || []
})

function formatOptionLabel(value) {
  return String(value || '')
    .split('_')
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function firstSentence(value) {
  const text = String(value || '').trim()
  if (!text) return ''
  const match = text.match(/^[^.?!]+[.?!]?/)
  return (match?.[0] || text).trim()
}

// CATEGORY_COLORS, withAlpha, categoryColor imported from constants/colors.js

const jobCatalogSearch = ref('')
const CATALOG_CAT_COLORS = {
  test: '#00D4AA', horror: '#DC2626', psychology: '#8B5CF6', philosophy: '#6366F1',
  motivation: '#F59E0B', romance: '#EC4899', mystery: '#6D28D9',
  history: '#D97706', science: '#0EA5E9', nature: '#10B981',
  survival: '#EF4444', bible: '#A78BFA', other: '#6B7280',
}

const groupedCatalog = computed(() => {
  const q = jobCatalogSearch.value.toLowerCase().trim()
  const entries = Object.entries(nichePresets.value || {})
  const filtered = q
    ? entries.filter(([, p]) =>
        (p.label || '').toLowerCase().includes(q) ||
        (p.category || '').toLowerCase().includes(q) ||
        (p.visual_style || '').toLowerCase().includes(q) ||
        (p.description || '').toLowerCase().includes(q) ||
        (p.tags || []).some(t => t.toLowerCase().includes(q))
      )
    : entries
  const groups = {}
  for (const [id, p] of filtered) {
    const cat = p.category || 'other'
    if (!groups[cat]) groups[cat] = []
    groups[cat].push({ id, ...p })
  }
  return Object.keys(groups)
    .sort((a, b) => {
      if (a === 'test') return -1
      if (b === 'test') return 1
      if (a === 'other') return 1
      if (b === 'other') return -1
      return a.localeCompare(b)
    })
    .map(cat => ({ category: cat, presets: groups[cat] }))
})

const availableCategories = computed(() => {
  const base = nicheCategories.value?.length
    ? [...nicheCategories.value]
    : [...(story.categories.value || [])]
  const current = story.storyCategory.value
  if (current && !base.includes(current)) base.unshift(current)
  return base
})
const availableVisualStyles = computed(() => {
  const base = visualStyles.value?.length ? [...visualStyles.value] : [...templates.value]
  const current = style.value
  if (current && !base.some(item => item.id === current)) {
    const legacyTemplate = templates.value.find(item => item.id === current)
    if (legacyTemplate) base.unshift(legacyTemplate)
  }
  return base
})
const selectedNicheConfig = computed(() => nichePresets.value?.[nichePreset.value] || null)
const activeStyleTemplate = computed(() => (
  templates.value.find(item => item.id === style.value)
  || availableVisualStyles.value.find(item => item.id === style.value)
  || null
))
const activeToneDescription = computed(() => storyTones.value?.[storyTone.value] || '')
const activeToneHint = computed(() => firstSentence(activeToneDescription.value))
const currentCategoryColor = computed(() => categoryColor(story.storyCategory.value))
const currentNicheConfig = computed(() => {
  const selected = selectedNicheConfig.value
  const derivedNiche = selected && selected.category === story.storyCategory.value
    ? selected.niche
    : story.storyCategory.value
  return {
    visual_style: style.value,
    category: story.storyCategory.value,
    niche: derivedNiche || '',
    story_tone: storyTone.value || selected?.story_tone || '',
    voice: voice.value,
    speed: speed.value,
  }
})
const currentCategoryLabel = computed(() => formatOptionLabel(story.storyCategory.value) || 'Select category')

// -- Custom style dropdown logic --
const openDropdown = ref('')  // '' | 'category' | 'style'
function toggleDropdown(id) { openDropdown.value = openDropdown.value === id ? '' : id }
function selectFromDropdown(id, value) {
  if (id === 'category') setCategory(value)
  else setStyle(value)
  openDropdown.value = ''
}
function onClickOutside(e) {
  if (openDropdown.value && !e.target.closest('.style-dropdown')) openDropdown.value = ''
}
onMounted(() => document.addEventListener('mousedown', onClickOutside))
onBeforeUnmount(() => document.removeEventListener('mousedown', onClickOutside))

const logEl = ref(null)

// ── Collapsible sections ──
const creativeOpen = ref(localStorage.getItem('sts-section-creative') !== 'false')
const settingsOpen = ref(localStorage.getItem('sts-section-settings') !== 'false')
const logOpen = ref(false)
watch(creativeOpen, v => localStorage.setItem('sts-section-creative', String(v)))
watch(settingsOpen, v => localStorage.setItem('sts-section-settings', String(v)))

const settingsSummary = computed(() => {
  const parts = []
  parts.push(voice.value || 'af_heart')
  parts.push(speed.value + 'x')
  if (stopAfter.value) {
    const step = ALL_STEPS.find(s => s.id === stopAfter.value)
    parts.push('→ ' + (step?.label || stopAfter.value))
  } else {
    parts.push('All steps')
  }
  return parts.join(' / ')
})

const activeProjectId = ref('')
useProjectSync(activeProjectId)

// Auto-scroll log
watch(log, async () => {
  await nextTick()
  if (logEl.value) {
    logEl.value.scrollTop = logEl.value.scrollHeight
  }
})

const canRun = computed(() => {
  if (running.value || story.isGenerating.value) return false
  return text.value.trim().length > 0
})
const runLabel = computed(() => {
  if (stopping.value) return 'Stopping...'
  if (running.value) return 'Running...'
  return 'Run Pipeline'
})
const runHintText = computed(() => {
  return sourceMode.value === 'generate'
    ? 'Generate a story or type text to get started'
    : 'Paste text or click Random to get started'
})
const canResumeStopped = computed(() => (
  globalStatus.value === 'stopped'
  && !!stoppedStep.value
  && !!stoppedProjectId.value
  && !running.value
))

async function handleRunPipeline() {
  if (!canRun.value) return
  await start()
}


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
      storyboard: '/storyboard',
      assets: '/assets',
      assemble: '/editor',
      export: '/export-library',
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
  return stepColor(stepStatus.value[stepId])
}

function dotTextColor(stepId) {
  return stepTextColor(stepStatus.value[stepId])
}

function dotIcon(step) {
  const s = stepStatus.value[step.id] || 'pending'
  if (s === 'done') return '\u2713'
  if (s === 'stopped') return '\u23F8'
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

// logIcon, logColor, statusColor imported from constants/colors.js
function logIcon(entry) { return logEntryIcon(entry) }
function logColor(entry) { return logEntryColor(entry) }

function onHistoryClick(index) {
  const j = jobs.value[index]
  if (!j) return
  activeProjectId.value = j.project_id
  loadFromHistory(index)
}

function retryFromHistory(index) {
  const j = jobs.value[index]
  if (!j || !j.error_step) return
  activeProjectId.value = j.project_id
  loadFromHistory(index)
  // Auto-trigger retry after state is loaded
  nextTick(() => retry())
}

const PROVIDER_URLS = {
  grok: 'https://grok.com/imagine',
  midjourney: 'https://www.midjourney.com/imagine',
  'meta-ai': 'https://www.meta.ai/media',
}

async function handleRegenerateAssets(projectId) {
  // 1. Check if scenes exist for this project
  let sceneData
  try {
    sceneData = await api.get(`/api/scenes/${projectId}`)
  } catch {
    toast.error('No scenes found — run the Scene Blueprint for this project first')
    return
  }

  if (!sceneData?.scenes?.length) {
    toast.error('No scenes found — run the Scene Blueprint for this project first')
    return
  }

  // 2. Load scenes into the assets composable
  assets.loadScenes(sceneData)

  // 3. Start the grabber (same as Asset Manager's Start button)
  try {
    await assets.startGrabber(projectId)
    toast.success(`Grabber started for ${sceneData.scenes.length} scenes`)
  } catch (e) {
    toast.error(e.message || 'Failed to start grabber')
    return
  }

  // 4. Open the provider website
  const providerUrl = PROVIDER_URLS[assets.provider.value]
  if (providerUrl) window.open(providerUrl, 'sts-provider-tab')

  // 5. Navigate to the assets page
  router.push({ path: '/assets', query: { project: projectId } })
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
  <div class="pipeline-layout">
  <div class="pipeline-page">

    <!-- Background filmstrip watermark -->
    <svg class="bg-filmstrip" viewBox="0 0 80 520" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <defs>
        <linearGradient id="fs-fade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="white" stop-opacity="1"/>
          <stop offset="75%" stop-color="white" stop-opacity="0.6"/>
          <stop offset="100%" stop-color="white" stop-opacity="0"/>
        </linearGradient>
        <mask id="fs-mask"><rect width="80" height="520" fill="url(#fs-fade)"/></mask>
      </defs>
      <g mask="url(#fs-mask)">
        <!-- Outer strip -->
        <rect x="1" y="1" width="78" height="518" rx="4" stroke="currentColor" stroke-width="1.2" fill="none"/>
        <!-- Sprocket track borders -->
        <line x1="14" y1="0" x2="14" y2="520" stroke="currentColor" stroke-width="0.4"/>
        <line x1="66" y1="0" x2="66" y2="520" stroke="currentColor" stroke-width="0.4"/>
        <!-- Left sprocket holes -->
        <rect x="5" y="16" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="5" y="56" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="5" y="96" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="5" y="136" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="5" y="176" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="5" y="216" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="5" y="256" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="5" y="296" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="5" y="336" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="5" y="376" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="5" y="416" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="5" y="456" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="5" y="496" width="6" height="4" rx="1" fill="currentColor"/>
        <!-- Right sprocket holes -->
        <rect x="69" y="16" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="69" y="56" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="69" y="96" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="69" y="136" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="69" y="176" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="69" y="216" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="69" y="256" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="69" y="296" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="69" y="336" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="69" y="376" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="69" y="416" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="69" y="456" width="6" height="4" rx="1" fill="currentColor"/>
        <rect x="69" y="496" width="6" height="4" rx="1" fill="currentColor"/>
        <!-- Film frames (rounded) -->
        <rect x="17" y="5" width="46" height="30" rx="2" stroke="currentColor" stroke-width="0.6" fill="none"/>
        <rect x="17" y="45" width="46" height="30" rx="2" stroke="currentColor" stroke-width="0.6" fill="none"/>
        <rect x="17" y="85" width="46" height="30" rx="2" stroke="currentColor" stroke-width="0.6" fill="none"/>
        <rect x="17" y="125" width="46" height="30" rx="2" stroke="currentColor" stroke-width="0.6" fill="none"/>
        <rect x="17" y="165" width="46" height="30" rx="2" stroke="currentColor" stroke-width="0.6" fill="none"/>
        <rect x="17" y="205" width="46" height="30" rx="2" stroke="currentColor" stroke-width="0.6" fill="none"/>
        <rect x="17" y="245" width="46" height="30" rx="2" stroke="currentColor" stroke-width="0.6" fill="none"/>
        <rect x="17" y="285" width="46" height="30" rx="2" stroke="currentColor" stroke-width="0.6" fill="none"/>
        <rect x="17" y="325" width="46" height="30" rx="2" stroke="currentColor" stroke-width="0.6" fill="none"/>
        <rect x="17" y="365" width="46" height="30" rx="2" stroke="currentColor" stroke-width="0.6" fill="none"/>
        <rect x="17" y="405" width="46" height="30" rx="2" stroke="currentColor" stroke-width="0.6" fill="none"/>
        <rect x="17" y="445" width="46" height="30" rx="2" stroke="currentColor" stroke-width="0.6" fill="none"/>
        <rect x="17" y="485" width="46" height="30" rx="2" stroke="currentColor" stroke-width="0.6" fill="none"/>
      </g>
    </svg>

    <!-- Header -->
    <div class="header">
      <div>
        <h2 class="page-title">Pipeline</h2>
        <p class="page-subtitle">TTS &rarr; Alignment &rarr; Segment &rarr; Scenes &rarr; Storyboard &rarr; Animator &rarr; Build &rarr; Export</p>
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
              :disabled="running"
              @click="sourceMode = 'manual'"
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-1px"><rect x="2" y="2" width="20" height="20" rx="3"/><circle cx="8" cy="8" r="1.5" fill="currentColor"/><circle cx="16" cy="8" r="1.5" fill="currentColor"/><circle cx="8" cy="16" r="1.5" fill="currentColor"/><circle cx="16" cy="16" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/></svg>
              Random
            </button>
            <button
              class="mode-btn"
              :class="{ active: sourceMode === 'generate' }"
              :disabled="running"
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

      <div class="creative-panel">
        <button class="section-toggle" @click="creativeOpen = !creativeOpen">
          <div class="creative-copy">
            <span class="creative-kicker">Creative Setup</span>
            <h3 class="creative-title">Set the creative direction</h3>
          </div>
          <svg class="section-chevron" :class="{ open: creativeOpen }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
        <div v-show="creativeOpen" class="section-body">

        <NichePicker
          :presets="nichePresets"
          :selected="nichePreset"
          :templates="templates"
          :current-config="currentNicheConfig"
          @select="handleNicheSelect"
          @save="handleNicheSave"
          @delete="handleNicheDelete"
        />

        <div class="creative-grid">
          <div class="creative-group creative-group--style">
            <label class="control-label">Visual Style</label>
            <div class="style-dropdown" :class="{ open: openDropdown === 'style' }">
              <button class="style-dropdown-trigger input-field control-select creative-trigger" @click="toggleDropdown('style')">
                <span class="style-dropdown-dot" :style="{ background: styleColor(style) }"></span>
                <span class="style-dropdown-label">{{ styleLabel(style) || 'Select style' }}</span>
                <svg class="style-dropdown-chevron" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
              </button>
              <div v-show="openDropdown === 'style'" class="style-dropdown-menu">
                <div
                  v-for="v in availableVisualStyles" :key="v.id"
                  class="style-dropdown-item" :class="{ selected: v.id === style }"
                  :style="v.id === style ? { background: v.color + '18', borderColor: v.color } : {}"
                  @click="selectFromDropdown('style', v.id)"
                >
                  <span class="style-dropdown-dot" :style="{ background: v.color }"></span>
                  <span class="style-dropdown-item-label">{{ v.name }}</span>
                </div>
              </div>
            </div>
            <p v-if="activeStyleTemplate?.description" class="creative-detail">{{ activeStyleTemplate.description }}</p>
          </div>

          <div class="creative-group">
            <label class="control-label">Category</label>
            <div class="style-dropdown" :class="{ open: openDropdown === 'category' }">
              <button
                class="style-dropdown-trigger input-field control-select"
                :style="{ borderColor: withAlpha(currentCategoryColor, '66'), background: withAlpha(currentCategoryColor, '0A') }"
                @click="toggleDropdown('category')"
              >
                <span class="style-dropdown-dot" :style="{ background: currentCategoryColor }"></span>
                <span class="style-dropdown-label">{{ currentCategoryLabel }}</span>
                <svg class="style-dropdown-chevron" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
              </button>
              <div v-show="openDropdown === 'category'" class="style-dropdown-menu">
                <div
                  v-for="categoryId in availableCategories" :key="categoryId"
                  class="style-dropdown-item" :class="{ selected: categoryId === story.storyCategory.value }"
                  :style="categoryId === story.storyCategory.value ? { background: withAlpha(categoryColor(categoryId), '18'), borderColor: categoryColor(categoryId) } : {}"
                  @click="selectFromDropdown('category', categoryId)"
                >
                  <span class="style-dropdown-dot" :style="{ background: categoryColor(categoryId) }"></span>
                  <span class="style-dropdown-item-label" :style="{ color: categoryId === story.storyCategory.value ? categoryColor(categoryId) : '' }">{{ formatOptionLabel(categoryId) }}</span>
                </div>
              </div>
            </div>
          </div>

          <div class="creative-group">
            <label class="control-label">Story Tone</label>
            <select v-model="storyTone" class="input-field control-select" @change="setStoryTone(storyTone)">
              <option value="">Auto / None</option>
              <option v-for="(description, toneId) in storyTones" :key="toneId" :value="toneId">
                {{ formatOptionLabel(toneId) }}
              </option>
            </select>
            <p class="creative-detail">{{ activeToneHint || 'How the narration should feel.' }}</p>
          </div>
        </div>
        </div><!-- /section-body -->
      </div>

      <!-- Generate mode: inline story form -->
      <div v-if="sourceMode === 'generate'" class="source-generate">
        <div class="story-generator-panel">
          <div class="story-generator-header">
            <div>
              <span class="creative-kicker">Story Generator</span>
              <h3 class="story-generator-title">Generate text from your current creative setup</h3>
            </div>
            <!-- "Run Pipeline generates first" toggle removed -->
          </div>
          <div class="gen-form">
            <div class="gen-group">
            <label class="control-label">Language</label>
            <select v-model="story.storyLanguage.value" class="input-field control-select">
              <option v-for="lang in story.LANGUAGES" :key="lang.id" :value="lang.id">{{ lang.label }}</option>
            </select>
            </div>
            <div class="gen-group">
            <label class="control-label">Level</label>
            <select v-model="story.storyLanguageLevel.value" class="input-field control-select">
              <option v-for="lvl in story.LANGUAGE_LEVELS" :key="lvl.id" :value="lvl.id">{{ lvl.label }}</option>
            </select>
            </div>
            <div class="gen-group">
            <label class="control-label">Duration</label>
            <input v-model.number="story.storyDuration.value" type="number" class="input-field control-number" min="15" max="180" step="5">
            </div>
            <div class="gen-group gen-group--action">
              <div class="gen-btn-group">
                <button class="gen-story-btn" :disabled="story.isGenerating.value" @click="handleGenerateStory">
                  <span v-if="story.isGenerating.value" class="gen-spinner"></span>
                  <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                  {{ story.isGenerating.value ? 'Generating...' : 'Generate' }}
                </button>
                <button v-if="text.trim()" class="gen-story-btn gen-idea-btn" :disabled="story.isGenerating.value" @click="handleGenerateFromIdea" title="Use current text as idea seed for a new story">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a7 7 0 0 1 5 11.9V16a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1v-2.1A7 7 0 0 1 12 2z"/><path d="M9 21h6"/><path d="M10 17v1"/><path d="M14 17v1"/></svg>
                  from Idea
                </button>
              </div>
            </div>
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
          <span>{{ formatOptionLabel(story.result.value.story_category || story.result.value.preset_style || '') }}</span>
          <span class="gen-sep">&middot;</span>
          <span class="gen-result-muted">{{ (story.result.value.generation_time || 0).toFixed(1) }}s gen</span>
        </div>
      </div>

      <!-- Generate History (collapsible) -->
      <div v-if="sourceMode === 'generate'" class="gen-history-section">
        <button class="gen-history-toggle" @click="showGenHistory = !showGenHistory">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          Generate History
          <span v-if="story.history.value.length" class="gen-history-count">({{ story.history.value.length }})</span>
          <svg class="gen-history-chevron" :class="{ rotated: showGenHistory }" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
        <div v-if="showGenHistory && story.history.value.length" class="gen-history-list">
          <div v-for="h in story.history.value" :key="h.project_id" class="gen-history-item" @click="loadFromGenHistory(h)">
            <span class="gen-history-preview">{{ h.preview || h.project_id }}</span>
            <span class="gen-history-meta">
              <span v-if="h.preset_style" class="gen-history-tag" :style="{ color: styleColor(h.preset_style) }">{{ styleLabel(h.preset_style) }}</span>
              <span v-if="h.story_category" class="gen-history-tag gen-history-tag--cat">{{ formatOptionLabel(h.story_category) }}</span>
              <span class="gen-history-words">{{ h.word_count || '?' }}w</span>
              <span class="gen-history-age">{{ timeAgo(h.timestamp) }}</span>
            </span>
          </div>
        </div>
        <p v-else-if="showGenHistory" class="gen-history-empty">No generated stories yet</p>
      </div>

      <!-- Textarea (always visible) -->
      <textarea
        v-model="text"
        class="input-field textarea"
        :class="{ 'textarea--empty': !text.trim() }"
        rows="5"
        :placeholder="sourceMode === 'generate' ? 'Click Generate Story above, or type your own text...' : 'Paste your story, script, or narration text here...'"
      ></textarea>

      <!-- Detect style bar + audio preview -->
      <div v-if="text.trim()" class="detect-style-bar">
        <button class="detect-style-btn" :disabled="detecting" @click="detectStyle">
          <span v-if="detecting" class="detect-spinner"></span>
          <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
          {{ detecting ? 'Detecting...' : 'Detect Style' }}
        </button>
        <button class="detect-style-btn preview-audio-btn" :class="{ 'preview-audio-btn--active': previewing }" :disabled="running" @click="previewAudio">
          <svg v-if="!previewing" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
          {{ previewing ? 'Stop' : 'Preview Audio' }}
        </button>
        <span v-if="previewLabel" class="preview-status">{{ previewLabel }}</span>
        <span v-if="detectedStyle" class="detect-result">
          <span class="detect-dot" :style="{ background: styleColor(detectedStyle.style_id) }"></span>
          <span :style="{ color: styleColor(detectedStyle.style_id), fontWeight: 600 }">{{ styleLabel(detectedStyle.style_id) }}</span>
          <span class="detect-confidence">{{ Math.round((detectedStyle.confidence || 0) * 100) }}%</span>
          <span v-if="detectedStyle.reason" class="detect-reason">{{ detectedStyle.reason }}</span>
        </span>
      </div>

      <!-- Controls strip -->
      <button class="section-toggle section-toggle--compact" @click="settingsOpen = !settingsOpen">
        <span class="controls-strip-label">Pipeline Settings</span>
        <span v-if="!settingsOpen" class="section-summary">{{ settingsSummary }}</span>
        <svg class="section-chevron" :class="{ open: settingsOpen }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
      </button>
      <div v-show="settingsOpen" class="controls-strip">
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
          <label class="control-label">Run Until</label>
          <select v-model="stopAfter" class="input-field control-select control-select--sm">
            <option value="">All steps (→ Export)</option>
            <option value="tts">TTS only</option>
            <option value="timing">→ Alignment</option>
            <option value="segment">→ Segment</option>
            <option value="scenes">→ Scenes</option>
            <option value="storyboard">→ Storyboard</option>
            <option value="assets">→ Animator</option>
            <option value="assemble">→ Assemble</option>
            <option value="export">→ Export</option>
          </select>
        </div>
        <!-- auto-scenes and auto-storyboard toggles removed — always enabled -->
        <!-- Image Model moved to Storyboard page webhook section -->
      </div>

      <!-- Action row -->
      <div class="action-row">
        <button class="run-btn" :class="{ 'run-btn--disabled': !canRun, 'run-btn--running': running }" :disabled="!canRun" @click="handleRunPipeline">
          <span class="run-icon" aria-hidden="true">
            <svg v-if="!running" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
              <path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>
            </svg>
            <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spinner-svg">
              <circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-dashoffset="12"></circle>
            </svg>
          </span>
          <span class="run-label">{{ runLabel }}</span>
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
        <span v-if="!text.trim() && !running && globalStatus !== 'error'" class="run-hint">{{ runHintText }}</span>
      </div>
    </section>

    <!-- Pending provider URL banner -->
    <div v-if="pendingProviderUrl" class="provider-redirect-banner" @click="openPendingProvider()">
      <span class="provider-redirect-icon">&#x1F517;</span>
      <span>Click to open provider tab: <b>{{ pendingProviderUrl }}</b></span>
    </div>

    <!-- Progress -->
    <ProgressStepper
      v-if="showProgress"
      :steps="STEPS"
      :step-status="stepStatus"
      :global-status="globalStatus"
      :running="running"
      :stopping="stopping"
      :last-event="lastEvent"
      :active-project-id="activeProjectId"
      :can-resume="canResumeStopped"
      @stop="stop"
      @resume="resumeStopped"
    />

    <!-- Log (expandable) -->
    <section v-if="log.length" class="card log-card">
      <button class="section-toggle section-toggle--compact" @click="logOpen = !logOpen">
        <label class="field-label log-label">Log</label>
        <span class="section-summary">{{ log.length }} entries</span>
        <svg class="section-chevron" :class="{ open: logOpen }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
      </button>
      <PipelineLog v-show="logOpen" :log="log" />
    </section>

    <!-- History -->
    <PipelineHistory
      :jobs="jobs"
      :active-project-id="activeProjectId"
      :templates="templates"
      @select="onHistoryClick"
      @retry="retryFromHistory"
      @regenerate="handleRegenerateAssets"
      @open="openInScenes"
    />

  </div>

  <!-- Right sidebar: Jobs Pane -->
  <aside class="jobs-sidebar" :class="{ 'jobs-sidebar--open': showJobPane }">
    <button class="jobs-sidebar-toggle" :title="showJobPane ? '' : 'Jobs'" @click="showJobPane = !showJobPane">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="18" rx="2"/><path d="M8 3v18"/><path d="M16 3v18"/></svg>
      <span class="jobs-sidebar-label">Jobs</span>
      <span v-if="totalQueuedJobs" class="jobs-count">{{ totalQueuedJobs }}</span>
      <svg class="jobs-sidebar-chevron" :class="{ rotated: showJobPane }" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 6 15 12 9 18"/></svg>
    </button>

    <template v-if="showJobPane">
      <!-- Tab bar -->
      <div class="jobs-tabs">
        <button class="jobs-tab" :class="{ active: jobPaneTab === 'queue' }" @click="jobPaneTab = 'queue'">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          Auto Queue
          <span v-if="totalQueuedJobs" class="jobs-tab-badge">{{ totalQueuedJobs }}</span>
        </button>
        <button class="jobs-tab" :class="{ active: jobPaneTab === 'saved' }" @click="jobPaneTab = 'saved'">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/></svg>
          Saved
          <span v-if="savedStories.length" class="jobs-tab-badge jobs-tab-badge--muted">{{ savedStories.length }}</span>
        </button>
      </div>

      <!-- TAB 1: Auto Queue -->
      <div v-if="jobPaneTab === 'queue'" class="jobs-tab-content">

        <!-- Running status — cinematic progress bar -->
        <div v-if="jobQueueRunning && jobQueueCurrent" class="q-live">
          <div class="q-live-track">
            <div class="q-live-fill" :style="{ width: Math.round((jobQueueCurrent.index / jobQueueCurrent.total) * 100) + '%' }"></div>
          </div>
          <div class="q-live-info">
            <div class="q-live-left">
              <span class="q-live-pulse"></span>
              <span class="q-live-counter">{{ jobQueueCurrent.index }}<span class="q-live-sep">/</span>{{ jobQueueCurrent.total }}</span>
              <span class="q-live-name">{{ jobQueueCurrent.label }}</span>
            </div>
            <button class="q-live-stop" @click="stopJobQueue">
              <svg width="8" height="8" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>
              Abort
            </button>
          </div>
        </div>

        <!-- Dispatch: queued job cards -->
        <div class="q-dispatch">
          <div v-if="jobQueue.length" class="q-dispatch-header">
            <span class="q-dispatch-title">Dispatch</span>
            <span class="q-dispatch-total">{{ totalQueuedJobs }} job{{ totalQueuedJobs !== 1 ? 's' : '' }}</span>
          </div>

          <div v-if="!jobQueue.length" class="q-empty">
            <div class="q-empty-icon">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/><path d="M12 12v4"/><path d="M10 14h4"/></svg>
            </div>
            <span class="q-empty-text">Queue empty</span>
            <span class="q-empty-hint">Pick presets below to batch-produce videos</span>
          </div>

          <TransitionGroup name="q-card" tag="div" class="q-cards">
            <div
              v-for="item in jobQueue"
              :key="item.presetId"
              class="q-card"
              :style="{ '--q-color': styleColor(nichePresets[item.presetId]?.visual_style) || 'var(--accent)' }"
            >
              <div class="q-card-glow"></div>
              <div class="q-card-body">
                <div class="q-card-head">
                  <span class="q-card-dot"></span>
                  <span class="q-card-name">{{ item.label }}</span>
                </div>
                <div class="q-card-cat" v-if="nichePresets[item.presetId]?.category">{{ formatOptionLabel(nichePresets[item.presetId].category) }}</div>
              </div>
              <div class="q-card-stepper">
                <button class="q-step-btn" @click="removeFromQueue(item.presetId)" :disabled="item.count <= 1">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"/></svg>
                </button>
                <span class="q-step-val">{{ item.count }}</span>
                <button class="q-step-btn" @click="addToQueue(item.presetId)">
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                </button>
              </div>
              <button class="q-card-remove" @click="deleteFromQueue(item.presetId)" title="Remove">
                <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
          </TransitionGroup>

          <!-- Launch bar -->
          <div v-if="jobQueue.length" class="q-launch">
            <button class="q-launch-btn" :disabled="jobQueueRunning || running" @click="runJobQueue">
              <span class="q-launch-icon">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              </span>
              <span class="q-launch-text">Launch {{ totalQueuedJobs }}</span>
            </button>
            <button class="q-launch-clear" :disabled="jobQueueRunning" @click="clearQueue" title="Clear queue">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          </div>
        </div>

        <!-- Preset catalog — grouped with search -->
        <div class="q-catalog">
          <div class="q-catalog-header">
            <span class="q-catalog-label">Presets</span>
            <span class="q-catalog-total">{{ Object.keys(nichePresets).length }}</span>
          </div>
          <div class="q-catalog-search">
            <svg class="q-search-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input
              v-model="jobCatalogSearch"
              class="q-search-input"
              placeholder="Search presets..."
              @keydown.escape="jobCatalogSearch = ''"
            />
            <button v-if="jobCatalogSearch" type="button" class="q-search-clear" @click="jobCatalogSearch = ''">&times;</button>
          </div>
          <div class="q-catalog-groups">
            <div v-if="groupedCatalog.length === 0" class="q-catalog-empty">
              No presets match "{{ jobCatalogSearch }}"
            </div>
            <div v-for="group in groupedCatalog" :key="group.category" class="q-cat-group">
              <div class="q-group-header">
                <span class="q-group-dot" :style="{ background: CATALOG_CAT_COLORS[group.category] || '#6B7280' }"></span>
                <span class="q-group-label">{{ formatOptionLabel(group.category) }}</span>
                <span class="q-group-count">{{ group.presets.length }}</span>
              </div>
              <div class="q-catalog-grid">
                <button
                  v-for="p in group.presets"
                  :key="p.id"
                  class="q-cat-chip"
                  :class="{ 'q-cat-chip--queued': jobQueue.some(q => q.presetId === p.id) }"
                  :style="{ '--chip-color': styleColor(p.visual_style) }"
                  @click="addToQueue(p.id)"
                >
                  <span class="q-cat-bar" :style="{ background: styleColor(p.visual_style) }"></span>
                  <span class="q-cat-name">{{ p.label }}</span>
                  <span v-if="jobQueue.find(q => q.presetId === p.id)" class="q-cat-count">{{ jobQueue.find(q => q.presetId === p.id).count }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- TAB 2: Saved Stories (Job Histories) -->
      <div v-if="jobPaneTab === 'saved'" class="jobs-tab-content">

        <!-- Run-all live progress -->
        <div v-if="savedQueueRunning && savedQueueCurrent" class="q-live">
          <div class="q-live-track">
            <div class="q-live-fill" :style="{ width: Math.round((savedQueueCurrent.index / savedQueueCurrent.total) * 100) + '%' }"></div>
          </div>
          <div class="q-live-info">
            <div class="q-live-left">
              <span class="q-live-pulse"></span>
              <span class="q-live-counter">{{ savedQueueCurrent.index }}<span class="q-live-sep">/</span>{{ savedQueueCurrent.total }}</span>
              <span class="q-live-name">{{ savedQueueCurrent.title }}</span>
            </div>
            <button class="q-live-stop" @click="stopSavedQueue">
              <svg width="8" height="8" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>
              Abort
            </button>
          </div>
        </div>

        <!-- Save + Run All actions -->
        <div class="saved-actions-bar">
          <button v-if="text.trim()" class="saved-sidebar-save" @click="saveCurrentStory">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
            Save Current
          </button>
          <button v-if="savedStories.length >= 1" class="saved-run-all-btn" :disabled="running || jobQueueRunning || savedQueueRunning" @click="runAllSavedStories">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            Run All {{ savedStories.length }}
          </button>
        </div>

        <div class="saved-sidebar-list">
          <div v-if="!savedStories.length" class="saved-empty">No saved stories yet.</div>
          <div
            v-for="entry in savedStories"
            :key="entry.id"
            class="saved-story-item"
            :class="{ 'saved-story-item--active': savedQueueRunning && savedQueueCurrent && savedQueueCurrent.title === entry.title }"
            @click="loadSavedStory(entry)"
          >
            <div class="saved-story-main">
              <span class="saved-story-title">{{ entry.title }}</span>
              <span class="saved-story-meta">
                <span v-if="entry.style" class="saved-tag">
                  <span class="saved-tag-dot" :style="{ background: styleColor(entry.visualStyle || entry.style) }"></span>
                  {{ styleLabel(entry.visualStyle || entry.style) }}
                </span>
                <span v-if="entry.storyTone" class="saved-tag saved-tag--tone">{{ formatOptionLabel(entry.storyTone) }}</span>
                <span v-if="entry.category" class="saved-tag saved-tag--cat">{{ formatOptionLabel(entry.category) }}</span>
                <span class="saved-story-age">{{ savedStoryAge(entry) }}</span>
              </span>
            </div>
            <div class="saved-story-actions">
              <button class="saved-story-run" title="Run pipeline" :disabled="running || jobQueueRunning || savedQueueRunning" @click.stop="runSavedStory(entry)">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              </button>
              <button class="saved-story-delete" title="Delete" @click.stop="deleteSavedStory(entry.id)">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </aside>

  </div>
</template>

<style scoped>
/* ── Collapsible Sections ── */
.section-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 0;
  margin-bottom: 12px;
  background: none;
  border: none;
  cursor: pointer;
  color: inherit;
  text-align: left;
  gap: 8px;
}
.section-toggle:hover .section-chevron { color: var(--accent); }
.section-toggle--compact {
  padding: 4px 0;
  margin-bottom: 8px;
}
.section-chevron {
  color: var(--text-muted);
  transition: transform 0.2s ease, color 0.15s;
  flex-shrink: 0;
}
.section-chevron.open { transform: rotate(180deg); }
.section-summary {
  font-size: 11px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.02em;
  margin-left: auto;
  padding: 2px 8px;
  background: rgba(255,255,255,0.03);
  border-radius: 4px;
  white-space: nowrap;
}
.section-body {
  animation: sectionFadeIn 0.15s ease-out;
}
@keyframes sectionFadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.pipeline-layout {
  display: flex;
  gap: 0;
  max-width: 1200px;
  margin: 0 auto;
}

.pipeline-page {
  flex: 1;
  min-width: 0;
  max-width: 780px;
  margin: 0 auto;
  padding: 32px 24px;
  position: relative;
}

.bg-filmstrip {
  position: fixed;
  top: -30px;
  right: 60px;
  height: 110vh;
  width: auto;
  color: rgba(255, 255, 255, 0.04);
  pointer-events: none;
  z-index: 0;
  transform: rotate(8deg);
}

/* ---- Header ---- */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.page-title {
  letter-spacing: -0.02em;
}

.header-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.progress-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.progress-stop-btn,
.progress-resume-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
  font-family: var(--font-mono);
  border: 1px solid;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
  white-space: nowrap;
}

.progress-stop-btn {
  border-color: rgba(255, 107, 107, 0.4);
  color: #FF9C9C;
  background: rgba(255, 107, 107, 0.08);
}

.progress-stop-btn:hover:not(:disabled) {
  border-color: #FF6B6B;
  box-shadow: 0 4px 12px rgba(255, 107, 107, 0.2);
}

.progress-stop-btn:disabled {
  cursor: wait;
  opacity: 0.7;
}

.progress-resume-btn {
  border-color: rgba(255, 179, 71, 0.35);
  color: #FFD37A;
  background: rgba(255, 179, 71, 0.1);
}

.progress-resume-btn:hover {
  border-color: #FFB347;
  box-shadow: 0 4px 12px rgba(255, 179, 71, 0.2);
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

/* ---- Detect Style ---- */
.detect-style-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
}

.detect-style-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 12px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.detect-style-btn:hover:not(:disabled) {
  color: var(--accent);
  border-color: var(--accent);
  background: rgba(78, 205, 196, 0.06);
}

.detect-style-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}


.preview-audio-btn--active {
  color: var(--accent) !important;
  border-color: var(--accent) !important;
  background: rgba(78, 205, 196, 0.1) !important;
}

.preview-status {
  font-size: 11px;
  color: var(--accent);
  font-weight: 500;
  letter-spacing: 0.03em;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(78, 205, 196, 0.08);
  white-space: nowrap;
}

/* ── Jobs Sidebar ── */
.jobs-sidebar {
  position: fixed;
  top: 0;
  right: 0;
  height: 100vh;
  width: 52px;
  flex-shrink: 0;
  padding: 32px 0 32px 0;
  transition: width 0.2s ease;
  overflow: hidden;
  z-index: 100;
  background: var(--bg-surface, #0f1117);
}
.jobs-sidebar--open {
  width: 320px;
  border-left: 1px solid var(--border);
  padding: 32px 16px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,0.08) transparent;
}
.jobs-sidebar--open::-webkit-scrollbar { width: 4px; }
.jobs-sidebar--open::-webkit-scrollbar-track { background: transparent; }
.jobs-sidebar--open::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.08); border-radius: 2px; }

.jobs-sidebar-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  background: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
  width: 100%;
}
.jobs-sidebar-toggle:hover { color: var(--accent); border-color: var(--accent); }
.jobs-sidebar--open .jobs-sidebar-toggle { margin-bottom: 10px; }

.jobs-sidebar-label { display: none; }
.jobs-sidebar--open .jobs-sidebar-label { display: inline; }
.jobs-sidebar--open .jobs-count { display: inline-flex; }

.jobs-sidebar-chevron {
  margin-left: auto;
  transition: transform 0.2s;
  display: none;
}
.jobs-sidebar--open .jobs-sidebar-chevron { display: block; }
.jobs-sidebar-chevron.rotated { transform: rotate(180deg); }

.jobs-count {
  display: none;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  background: var(--accent);
  border-radius: 9px;
}

/* ── Jobs Tabs ── */
.jobs-tabs {
  display: flex;
  gap: 2px;
  margin-bottom: 12px;
  padding: 2px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.jobs-tab {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 6px 8px;
  font-size: 10px;
  font-weight: 600;
  font-family: var(--font-mono);
  color: var(--text-muted);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.jobs-tab:hover:not(.active) { color: var(--text-secondary); }
.jobs-tab.active {
  color: var(--accent);
  background: rgba(78, 205, 196, 0.08);
  border-color: rgba(78, 205, 196, 0.2);
}

.jobs-tab-badge {
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  font-size: 9px;
  font-weight: 700;
  color: #fff;
  background: var(--accent);
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.jobs-tab-badge--muted {
  background: rgba(255, 255, 255, 0.12);
  color: var(--text-muted);
}

.jobs-tab-content {
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* ── Live Progress ── */
.q-live {
  margin-bottom: 14px;
  border-radius: 10px;
  overflow: hidden;
  background: linear-gradient(135deg, rgba(78, 205, 196, 0.06), rgba(78, 205, 196, 0.02));
  border: 1px solid rgba(78, 205, 196, 0.18);
}

.q-live-track {
  height: 3px;
  background: rgba(78, 205, 196, 0.1);
  position: relative;
  overflow: hidden;
}

.q-live-fill {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, var(--accent), #5edfd6);
  transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 0 12px rgba(78, 205, 196, 0.5);
}
.q-live-fill::after {
  content: '';
  position: absolute;
  right: 0;
  top: -2px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 0 8px var(--accent), 0 0 20px rgba(78, 205, 196, 0.4);
  animation: q-dot-glow 1.5s ease-in-out infinite;
}

@keyframes q-dot-glow {
  0%, 100% { opacity: 0.7; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1.2); }
}

.q-live-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
}

.q-live-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.q-live-pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
  animation: q-pulse 1.2s ease-in-out infinite;
  box-shadow: 0 0 6px var(--accent);
}

@keyframes q-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.7); }
}

.q-live-counter {
  font: 700 13px/1 var(--font-mono);
  color: var(--accent);
  letter-spacing: -0.02em;
}

.q-live-sep { opacity: 0.4; margin: 0 1px; }

.q-live-name {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.q-live-stop {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  font: 700 9px/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--coral);
  background: rgba(255, 107, 107, 0.06);
  border: 1px solid rgba(255, 107, 107, 0.25);
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}
.q-live-stop:hover {
  background: rgba(255, 107, 107, 0.14);
  border-color: var(--coral);
  box-shadow: 0 0 10px rgba(255, 107, 107, 0.15);
}

/* ── Dispatch Section ── */
.q-dispatch {
  margin-bottom: 14px;
}

.q-dispatch-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
}

.q-dispatch-title {
  font: 700 9px/1 var(--font-mono);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.q-dispatch-total {
  font: 600 10px/1 var(--font-mono);
  color: var(--accent);
  opacity: 0.8;
}

/* ── Empty State ── */
.q-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 28px 16px 20px;
  text-align: center;
}

.q-empty-icon {
  color: var(--border-hover);
  opacity: 0.5;
  margin-bottom: 2px;
}

.q-empty-text {
  font: 600 12px/1 var(--font-display);
  color: var(--text-muted);
}

.q-empty-hint {
  font-size: 10px;
  color: var(--text-muted);
  opacity: 0.6;
  line-height: 1.4;
  max-width: 200px;
}

/* ── Queue Cards ── */
.q-cards {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.q-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border-radius: 8px;
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--q-color) 4%, transparent), transparent 60%);
  border: 1px solid color-mix(in srgb, var(--q-color) 14%, transparent);
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.15s;
  overflow: hidden;
}
.q-card:hover {
  border-color: color-mix(in srgb, var(--q-color) 30%, transparent);
  box-shadow: 0 2px 12px color-mix(in srgb, var(--q-color) 8%, transparent);
}

/* Subtle left-edge accent stripe */
.q-card-glow {
  position: absolute;
  left: 0;
  top: 4px;
  bottom: 4px;
  width: 2px;
  border-radius: 1px;
  background: var(--q-color);
  opacity: 0.5;
  transition: opacity 0.2s;
}
.q-card:hover .q-card-glow { opacity: 0.9; }

.q-card-body {
  flex: 1;
  min-width: 0;
  padding-left: 4px;
}

.q-card-head {
  display: flex;
  align-items: center;
  gap: 6px;
}

.q-card-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--q-color);
  flex-shrink: 0;
  box-shadow: 0 0 5px color-mix(in srgb, var(--q-color) 40%, transparent);
}

.q-card-name {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.q-card-cat {
  font-size: 9px;
  font-weight: 500;
  color: var(--text-muted);
  margin-top: 2px;
  padding-left: 13px;
  letter-spacing: 0.02em;
}

/* Stepper control */
.q-card-stepper {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.2);
}

.q-step-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.12s;
}
.q-step-btn:hover:not(:disabled) {
  color: var(--accent);
  background: rgba(78, 205, 196, 0.08);
}
.q-step-btn:disabled { opacity: 0.25; cursor: default; }
.q-step-btn:first-child { border-right: 1px solid var(--border); }
.q-step-btn:last-child { border-left: 1px solid var(--border); }

.q-step-val {
  width: 26px;
  text-align: center;
  font: 700 12px/24px var(--font-mono);
  color: var(--q-color, var(--accent));
  letter-spacing: -0.03em;
}

/* Remove button */
.q-card-remove {
  position: absolute;
  top: 3px;
  right: 3px;
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: 4px;
  opacity: 0;
  transition: all 0.12s;
}
.q-card:hover .q-card-remove { opacity: 0.5; }
.q-card-remove:hover { opacity: 1 !important; color: var(--coral); background: rgba(255, 107, 107, 0.08); }

/* Card enter/leave transitions */
.q-card-enter-active { animation: q-card-in 0.25s ease-out; }
.q-card-leave-active { animation: q-card-out 0.2s ease-in forwards; }
.q-card-move { transition: transform 0.25s ease; }

@keyframes q-card-in {
  from { opacity: 0; transform: translateX(12px) scale(0.96); }
  to { opacity: 1; transform: translateX(0) scale(1); }
}
@keyframes q-card-out {
  from { opacity: 1; transform: translateX(0) scale(1); }
  to { opacity: 0; transform: translateX(-12px) scale(0.96); }
}

/* ── Launch Bar ── */
.q-launch {
  display: flex;
  gap: 6px;
  margin-top: 10px;
}

.q-launch-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  background: linear-gradient(135deg, var(--accent), #3abfb7);
  color: #0a0e13;
  font: 700 11px/1 var(--font-mono);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  transition: all 0.2s;
  position: relative;
  overflow: hidden;
}
.q-launch-btn::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(255,255,255,0.12), transparent 50%);
  pointer-events: none;
}
.q-launch-btn:hover:not(:disabled) {
  box-shadow: 0 4px 20px rgba(78, 205, 196, 0.35), 0 0 40px rgba(78, 205, 196, 0.1);
  transform: translateY(-1px);
}
.q-launch-btn:active:not(:disabled) { transform: translateY(0); }
.q-launch-btn:disabled { opacity: 0.4; cursor: not-allowed; filter: saturate(0.5); }

.q-launch-icon {
  display: flex;
  align-items: center;
}

.q-launch-text {
  white-space: nowrap;
}

.q-launch-clear {
  width: 38px;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}
.q-launch-clear:hover:not(:disabled) {
  color: var(--coral);
  border-color: rgba(255, 107, 107, 0.3);
  background: rgba(255, 107, 107, 0.05);
}
.q-launch-clear:disabled { opacity: 0.3; cursor: not-allowed; }

/* ── Preset Catalog ── */
.q-catalog {
  border-top: 1px solid var(--border);
  padding-top: 10px;
}

.q-catalog-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.q-catalog-label {
  font: 700 9px/1 var(--font-mono);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.q-catalog-total {
  font: 500 9px/1 var(--font-mono);
  color: var(--text-muted);
  background: rgba(255,255,255,0.06);
  padding: 2px 5px;
  border-radius: 4px;
}

.q-catalog-search {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  position: relative;
}

.q-search-icon {
  color: var(--text-muted);
  opacity: 0.5;
  flex-shrink: 0;
}

.q-search-input {
  flex: 1;
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 26px 5px 8px;
  font: 400 11px/1.3 system-ui, sans-serif;
  color: var(--text);
  outline: none;
  transition: border-color 0.15s;
}

.q-search-input:focus {
  border-color: var(--accent);
}

.q-search-input::placeholder {
  color: var(--text-muted);
  opacity: 0.5;
}

.q-search-clear {
  position: absolute;
  right: 6px;
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 15px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}

.q-search-clear:hover {
  color: var(--text);
}

.q-catalog-groups {
  max-height: 340px;
  overflow-y: auto;
  padding-right: 2px;
}

.q-catalog-groups::-webkit-scrollbar { width: 4px; }
.q-catalog-groups::-webkit-scrollbar-track { background: transparent; }
.q-catalog-groups::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }

.q-catalog-empty {
  text-align: center;
  padding: 20px 0;
  font: 400 11px/1.4 system-ui, sans-serif;
  color: var(--text-muted);
  opacity: 0.6;
}

.q-cat-group {
  margin-bottom: 8px;
}

.q-cat-group:last-child {
  margin-bottom: 0;
}

.q-group-header {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 3px 0 5px;
}

.q-group-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.q-group-label {
  font: 600 9px/1 var(--font-mono);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.q-group-count {
  font: 500 8px/1 var(--font-mono);
  color: var(--text-muted);
  opacity: 0.5;
}

.q-catalog-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 4px;
}

.q-cat-chip {
  display: flex;
  align-items: center;
  gap: 0;
  padding: 0;
  font-size: 10px;
  font-weight: 500;
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
  position: relative;
  overflow: hidden;
}
.q-cat-chip:hover {
  color: var(--text);
  border-color: color-mix(in srgb, var(--chip-color) 40%, var(--border));
  background: color-mix(in srgb, var(--chip-color) 5%, transparent);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}
.q-cat-chip--queued {
  border-color: color-mix(in srgb, var(--chip-color) 35%, transparent);
  background: color-mix(in srgb, var(--chip-color) 8%, transparent);
  color: var(--text);
}

.q-cat-bar {
  width: 3px;
  align-self: stretch;
  flex-shrink: 0;
  border-radius: 3px 0 0 3px;
  transition: width 0.15s;
}

.q-cat-chip:hover .q-cat-bar {
  width: 4px;
}

.q-cat-name {
  padding: 5px 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
  min-width: 0;
}

.q-cat-count {
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  font: 700 9px/16px var(--font-mono);
  text-align: center;
  color: #fff;
  background: var(--chip-color, var(--accent));
  border-radius: 8px;
  margin-right: 6px;
  flex-shrink: 0;
}

/* ── Saved Stories (in Jobs pane) ── */
.saved-actions-bar {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
}

.saved-sidebar-save {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  font-size: 11px;
  font-weight: 500;
  color: var(--accent);
  background: rgba(78, 205, 196, 0.06);
  border: 1px dashed rgba(78, 205, 196, 0.3);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.saved-sidebar-save:hover {
  background: rgba(78, 205, 196, 0.12);
  border-color: var(--accent);
}

.saved-run-all-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  font: 700 10px/1 var(--font-mono);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #0a0e13;
  background: linear-gradient(135deg, var(--accent), #3abfb7);
  border: none;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  flex-shrink: 0;
  position: relative;
  overflow: hidden;
}
.saved-run-all-btn::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(255,255,255,0.12), transparent 50%);
  pointer-events: none;
}
.saved-run-all-btn:hover:not(:disabled) {
  box-shadow: 0 4px 16px rgba(78, 205, 196, 0.3);
  transform: translateY(-1px);
}
.saved-run-all-btn:disabled { opacity: 0.4; cursor: not-allowed; filter: saturate(0.5); }

.saved-story-item--active {
  background: rgba(78, 205, 196, 0.06);
  border-left: 2px solid var(--accent);
  padding-left: 8px;
}

.saved-sidebar-list {
  overflow-y: auto;
  max-height: calc(100vh - 140px);
}

.saved-empty {
  padding: 20px 8px;
  text-align: center;
  color: var(--text-muted);
  font-size: 12px;
}

.saved-story-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 10px;
  cursor: pointer;
  border-bottom: 1px solid var(--border);
  border-radius: 6px;
  transition: background 0.12s;
}
.saved-story-item:last-child { border-bottom: none; }
.saved-story-item:hover { background: rgba(255, 255, 255, 0.04); }

.saved-story-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.saved-story-title {
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.saved-story-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
}

.saved-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 9px;
  color: var(--text-muted);
  background: rgba(255, 255, 255, 0.04);
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid var(--border);
}

.saved-tag-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}

.saved-tag--tone {
  color: var(--accent);
  border-color: rgba(78, 205, 196, 0.2);
}

.saved-tag--cat {
  color: #a78bfa;
  border-color: rgba(167, 139, 250, 0.2);
}

.saved-story-age {
  font-size: 9px;
  color: var(--text-muted);
  opacity: 0.5;
}

.saved-story-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.12s;
}
.saved-story-item:hover .saved-story-actions { opacity: 1; }

.saved-story-run {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  opacity: 0.7;
  transition: all 0.12s;
}
.saved-story-run:hover:not(:disabled) { opacity: 1; background: rgba(78, 205, 196, 0.1); }
.saved-story-run:disabled { opacity: 0.3; cursor: not-allowed; }

.saved-story-delete {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  opacity: 0.6;
  transition: all 0.12s;
}
.saved-story-delete:hover { opacity: 1 !important; color: #ef4444; }

@media (max-width: 900px) {
  .pipeline-layout { flex-direction: column; }
  .jobs-sidebar {
    position: fixed;
    top: auto;
    bottom: 0;
    right: 0;
    width: 100% !important;
    height: auto !important;
    max-height: 70vh;
    border-left: none !important;
    border-top: 1px solid var(--border);
    padding: 16px 24px !important;
  }
  .jobs-sidebar-label { display: inline !important; }
  .jobs-sidebar-chevron { display: block !important; }
  .jobs-count { display: inline-flex !important; }
}

.detect-spinner {
  width: 10px;
  height: 10px;
  border: 1.5px solid transparent;
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

.detect-result {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}

.detect-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.detect-confidence {
  color: var(--text-muted);
  font-size: 10px;
}

.detect-reason {
  color: var(--text-muted);
  font-size: 10px;
  font-style: italic;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
.creative-panel {
  margin: 12px 0 14px;
  padding: 12px;
  border: 1px solid rgba(78, 205, 196, 0.12);
  border-radius: 14px;
  background:
    radial-gradient(circle at top right, rgba(78, 205, 196, 0.05), transparent 28%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.02), rgba(255, 255, 255, 0));
}

.creative-panel-header {
  margin-bottom: 10px;
}

.creative-copy {
  min-width: 0;
}

.creative-kicker {
  display: inline-block;
  margin-bottom: 5px;
  font: 700 10px/1 var(--font-mono);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent);
}

.creative-title {
  margin: 0 0 3px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.creative-note {
  margin: 0;
  max-width: 560px;
  font-size: 11px;
  line-height: 1.45;
  color: var(--text-muted);
}

.creative-grid {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr;
  gap: 12px;
  margin-top: 10px;
}

.creative-group {
  min-width: 0;
}

.creative-group--style {
  grid-column: span 1;
}

.creative-trigger {
  min-height: 38px;
}

.creative-detail {
  margin: 6px 0 0;
  min-height: 16px;
  font-size: 10px;
  line-height: 1.4;
  color: var(--text-muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.source-generate {
  margin-bottom: 10px;
}

.story-generator-panel {
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.02);
}

.story-generator-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}


.story-generator-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
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

.gen-btn-group {
  display: inline-flex;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(167, 139, 250, 0.2);
}

.gen-story-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 7px 14px;
  font-size: 11px;
  font-weight: 700;
  font-family: var(--font-mono);
  border: none;
  cursor: pointer;
  color: white;
  background: linear-gradient(135deg, #A78BFA, #7C3AED);
  transition: all 0.15s;
  white-space: nowrap;
  border-radius: 0;
}

.gen-btn-group .gen-story-btn:first-child { border-radius: 8px 0 0 8px; }
.gen-btn-group .gen-story-btn:last-child { border-radius: 0 8px 8px 0; }
.gen-btn-group .gen-story-btn:only-child { border-radius: 8px; }

.gen-story-btn:hover:not(:disabled) {
  filter: brightness(1.15);
}

.gen-story-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.gen-idea-btn {
  background: rgba(124, 58, 237, 0.15);
  border-left: 1px solid rgba(167, 139, 250, 0.3);
  color: #C4B5FD;
}
.gen-idea-btn:hover:not(:disabled) {
  background: rgba(124, 58, 237, 0.3);
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

/* Generate History */
.gen-history-section { margin-top: 8px; }
.gen-history-toggle {
  display: flex; align-items: center; gap: 6px;
  background: none; border: none; color: var(--text-muted, #8892b0);
  font-size: 11px; font-family: var(--font-mono); cursor: pointer;
  padding: 4px 0; text-transform: uppercase; letter-spacing: 0.05em;
}
.gen-history-toggle:hover { color: var(--text-primary, #ccd6f6); }
.gen-history-count { color: var(--accent, #64ffda); font-weight: 600; }
.gen-history-chevron { transition: transform 0.2s; }
.gen-history-chevron.rotated { transform: rotate(180deg); }
.gen-history-list {
  max-height: 180px; overflow-y: auto; margin-top: 4px;
  border: 1px solid var(--border, #1e2d3d); border-radius: 6px;
  background: var(--bg-surface, #112240);
}
.gen-history-item {
  display: flex; flex-direction: column; gap: 2px;
  padding: 6px 10px; cursor: pointer;
  border-bottom: 1px solid var(--border, #1e2d3d);
  transition: background 0.15s;
}
.gen-history-item:last-child { border-bottom: none; }
.gen-history-item:hover { background: var(--bg-hover, #1a3a5c); }
.gen-history-preview {
  font-size: 11px; color: var(--text-primary, #ccd6f6);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.gen-history-meta {
  display: flex; align-items: center; gap: 6px;
  font-size: 10px; color: var(--text-muted, #8892b0);
}
.gen-history-tag { font-weight: 600; }
.gen-history-tag--cat { color: var(--accent, #64ffda); }
.gen-history-words { opacity: 0.7; }
.gen-history-age { opacity: 0.5; margin-left: auto; }
.gen-history-empty {
  font-size: 11px; color: var(--text-muted, #8892b0);
  padding: 8px 10px; margin: 0;
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
  flex-wrap: wrap;
}
.controls-strip-label {
  display: block;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
  margin-bottom: 6px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-muted);
  opacity: 0.6;
}

.control-group {
  flex-shrink: 1;
  min-width: 0;
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

/* ---- Custom style dropdown (matches Scene Blueprint StylePicker) ---- */
.style-dropdown {
  position: relative;
  width: 100%;
  min-width: 100px;
}
.style-dropdown-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  text-align: left;
  background: var(--bg-darkest);
  appearance: none;
  -webkit-appearance: none;
}
.style-dropdown-trigger:hover {
  border-color: var(--text-muted);
}
.style-dropdown-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.style-dropdown-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.style-dropdown-chevron {
  flex-shrink: 0;
  color: var(--text-muted);
  transition: transform 0.15s;
}
.style-dropdown.open .style-dropdown-chevron {
  transform: rotate(180deg);
}
.style-dropdown-menu {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  min-width: 200px;
  max-height: 320px;
  overflow-y: auto;
  z-index: 100;
  background: var(--bg-darkest);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}
.style-dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 6px;
  cursor: pointer;
  border: 1.5px solid transparent;
  transition: all 0.12s;
}
.style-dropdown-item:hover {
  background: var(--bg-surface);
}
.style-dropdown-item.selected {
  /* dynamic border + bg set via inline style */
}
.style-dropdown-item-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
  white-space: nowrap;
}

@media (max-width: 980px) {
  .creative-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 720px) {
  .creative-grid,
  .gen-form,
  .controls-strip {
    grid-template-columns: 1fr;
    flex-direction: column;
    align-items: stretch;
  }

  .gen-group--action {
    margin-left: 0;
    align-self: stretch;
  }

  .story-generator-header {
    flex-direction: column;
    align-items: stretch;
  }
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

/* ---- Running state ---- */
.run-btn--running {
  border-color: rgba(0, 200, 150, 0.5);
  background:
    linear-gradient(135deg, rgba(0, 200, 150, 0.15), rgba(0, 150, 200, 0.15));
  pointer-events: none;
  cursor: wait;
}

.run-btn--running::before {
  background: linear-gradient(135deg, rgba(0, 200, 150, 0.08), transparent);
}

.run-btn--running .run-icon {
  background: rgba(0, 200, 150, 0.2);
}

.run-btn--running .spinner-svg {
  animation: spin 1.2s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ---- Stop Button ---- */
.stop-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid rgba(255, 80, 80, 0.4);
  background: rgba(255, 60, 60, 0.12);
  color: #ff6b6b;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.stop-btn:hover:not(:disabled) {
  background: rgba(255, 60, 60, 0.25);
  border-color: rgba(255, 80, 80, 0.6);
}

.stop-btn:disabled {
  opacity: 0.5;
  cursor: wait;
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

.current-step-msg.is-stopped {
  color: #FFB347;
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

.provider-redirect-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 18px;
  margin: 8px 0;
  background: linear-gradient(135deg, rgba(45, 212, 191, 0.15), rgba(45, 212, 191, 0.05));
  border: 1px solid rgba(45, 212, 191, 0.4);
  border-radius: 8px;
  cursor: pointer;
  color: var(--text-primary);
  font-size: 13px;
  animation: pulse-border 2s ease-in-out infinite;
  transition: background 0.2s;
}
.provider-redirect-banner:hover {
  background: rgba(45, 212, 191, 0.2);
}
.provider-redirect-banner b {
  color: var(--accent);
  word-break: break-all;
}
.provider-redirect-icon {
  font-size: 18px;
}
@keyframes pulse-border {
  0%, 100% { border-color: rgba(45, 212, 191, 0.4); }
  50% { border-color: rgba(45, 212, 191, 0.8); }
}
</style>
