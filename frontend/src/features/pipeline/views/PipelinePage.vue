<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/shared/api/client.js'
import { usePipeline } from '../composables/usePipeline.js'
import NichePicker from '../components/NichePicker.vue'
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
const generateBeforeRun = ref(localStorage.getItem('sts-pipeline-generate-before-run') === 'true')

// Source mode: 'manual' (paste/random) or 'generate' (AI story)
const sourceMode = ref(localStorage.getItem('sts-pipeline-source-mode') || 'manual')
watch(sourceMode, (v) => localStorage.setItem('sts-pipeline-source-mode', v))
watch(generateBeforeRun, (v) => localStorage.setItem('sts-pipeline-generate-before-run', String(v)))

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
    previewLabel.value = 'Generating...'
    const resp = await fetch('/api/tts/stream', {
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

// ── Saved Stories ──
const SAVED_STORIES_KEY = 'sts-saved-stories'
const savedStories = ref(JSON.parse(localStorage.getItem(SAVED_STORIES_KEY) || '[]'))
const showSavedStories = ref(false)

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
  showSavedStories.value = false
  toast.success('Story loaded')
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
  text, voice, speed, style, autoScenes, stopAfter, templates,
  running, stopping, stepStatus, log, globalStatus,
  jobs, lastCompletedProjectId, lastCompletedExportFilename,
  failedStep, failedProjectId, stoppedStep, stoppedProjectId,
  nichePreset, nichePresets, storyTone, storyTones, visualStyles, nicheCategories,
  visualStyle, nicheCategory,
  start, stop, retry, resumeStopped, loadFromHistory, randomStory, resetProgress,
  selectNiche, clearNiche, saveNichePreset, deleteNichePreset,
  setVisualStyleOverride, setStoryTone, setNicheCategory,
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

const CATEGORY_COLORS = {
  psychology: '#8B5CF6',
  crime: '#EF4444',
  horror: '#FF6B6B',
  motivation: '#FACC15',
  philosophy: '#94A3B8',
  religion: '#D4AF37',
  mystery: '#7C3AED',
  science: '#38BDF8',
  history: '#C08457',
  nature: '#22C55E',
  romance: '#F472B6',
  comedy: '#F97316',
  children: '#F9A8D4',
  anecdote: '#FB7185',
  politics: '#DC2626',
  survival: '#84CC16',
  curiosity: '#2DD4BF',
  space: '#60A5FA',
}

function withAlpha(hex, alpha = '18') {
  if (!hex || typeof hex !== 'string') return `rgba(78, 205, 196, 0.${alpha})`
  if (hex.startsWith('#') && hex.length === 7) return `${hex}${alpha}`
  return hex
}

function categoryColor(categoryId) {
  return CATEGORY_COLORS[categoryId] || '#4ECDC4'
}

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
const shouldGenerateBeforeRun = computed(() => sourceMode.value === 'generate' && generateBeforeRun.value)
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
  if (shouldGenerateBeforeRun.value) return !!story.webhookUrl.value?.trim()
  return text.value.trim().length > 0
})
const runLabel = computed(() => {
  if (stopping.value) return 'Stopping...'
  if (running.value) return 'Running...'
  return 'Run Pipeline'
})
const runHintText = computed(() => {
  if (shouldGenerateBeforeRun.value) {
    return story.webhookUrl.value?.trim()
      ? 'Run Pipeline will generate fresh text first using your current setup'
      : 'Configure the story webhook to generate text before running'
  }
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
  if (shouldGenerateBeforeRun.value) {
    const generated = await handleGenerateStory({ notifySuccess: false })
    if (!generated.ok) return
  }
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
  const s = stepStatus.value[stepId] || 'pending'
  if (s === 'running') return 'var(--accent)'
  if (s === 'done') return '#26DE81'
  if (s === 'stopped') return '#FFB347'
  if (s === 'skipped') return 'var(--text-muted)'
  if (s === 'error') return '#FF6B6B'
  return 'var(--border)'
}

function dotTextColor(stepId) {
  const s = stepStatus.value[stepId] || 'pending'
  if (s === 'running') return 'var(--accent)'
  if (s === 'done') return '#26DE81'
  if (s === 'stopped') return '#FFB347'
  if (s === 'skipped') return 'var(--text-muted)'
  if (s === 'error') return '#FF6B6B'
  return 'var(--text-muted)'
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
  if (status === 'stopped') return '#FFB347'
  if (status === 'error') return '#FF6B6B'
  return 'var(--accent)'
}

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
    toast.error('No scenes found — run the Scene Generator for this project first')
    return
  }

  if (!sceneData?.scenes?.length) {
    toast.error('No scenes found — run the Scene Generator for this project first')
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
        <div class="creative-panel-header">
          <div class="creative-copy">
            <span class="creative-kicker">Creative Setup</span>
            <h3 class="creative-title">Set the creative direction</h3>
            <p class="creative-note">Choose a niche preset or set the visual style, category, and tone yourself.</p>
          </div>
        </div>

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
      </div>

      <!-- Generate mode: inline story form -->
      <div v-if="sourceMode === 'generate'" class="source-generate">
        <div class="story-generator-panel">
          <div class="story-generator-header">
            <div>
              <span class="creative-kicker">Story Generator</span>
              <h3 class="story-generator-title">Generate text from your current creative setup</h3>
            </div>
            <label class="generate-first-toggle">
              <input v-model="generateBeforeRun" type="checkbox" class="generate-first-check">
              <span class="generate-first-text">Run Pipeline generates first</span>
            </label>
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
      <span class="controls-strip-label">Pipeline Settings</span>
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
        <button class="run-btn" :class="{ 'run-btn--disabled': !canRun }" :disabled="!canRun" @click="handleRunPipeline">
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
        <span v-if="(!text.trim() || shouldGenerateBeforeRun) && !running && globalStatus !== 'error'" class="run-hint">{{ runHintText }}</span>
      </div>
    </section>

    <!-- Progress -->
    <section v-if="showProgress" class="card progress-card">
      <div class="progress-header">
        <label class="field-label progress-label">Progress</label>
        <div class="progress-header-right">
          <span v-if="activeProjectId" class="progress-project font-mono">{{ activeProjectId }}</span>
          <button
            v-if="running || stopping"
            class="progress-stop-btn"
            :disabled="stopping"
            @click="stop"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>
            {{ stopping ? 'Stopping...' : 'Stop' }}
          </button>
          <button
            v-else-if="canResumeStopped"
            class="progress-resume-btn"
            @click="resumeStopped"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            Resume
          </button>
        </div>
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
          <span class="current-step-msg" :class="{ 'is-error': lastEvent.step === 'error', 'is-stopped': lastEvent.step === 'stopped' || lastEvent.status === 'stopped' }">
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
                @click.stop="retryFromHistory(i)"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                Retry
              </button>
              <!-- Regenerate assets button for completed pipelines with scenes -->
              <button
                v-if="j.status === 'done' && j.scene_count > 0"
                class="hist-action-btn hist-action-btn--regen"
                title="Regenerate assets with provider"
                @click.stop="handleRegenerateAssets(j.project_id)"
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

  <!-- Right sidebar: Saved Stories -->
  <aside class="saved-sidebar" :class="{ 'saved-sidebar--open': showSavedStories }">
    <button class="saved-sidebar-toggle" @click="showSavedStories = !showSavedStories">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
      <span class="saved-sidebar-label">My Stories</span>
      <span v-if="savedStories.length" class="saved-count">({{ savedStories.length }})</span>
      <svg class="saved-sidebar-chevron" :class="{ rotated: showSavedStories }" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 6 15 12 9 18"/></svg>
    </button>
    <button v-if="showSavedStories && text.trim()" class="saved-sidebar-save" @click="saveCurrentStory">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
      Save Current Story
    </button>
    <div v-if="showSavedStories" class="saved-sidebar-list">
      <div v-if="!savedStories.length" class="saved-empty">No saved stories yet.</div>
      <div v-for="entry in savedStories" :key="entry.id" class="saved-story-item" @click="loadSavedStory(entry)">
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
        <button class="saved-story-delete" title="Delete" @click.stop="deleteSavedStory(entry.id)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
    </div>
  </aside>

  </div>
</template>

<style scoped>
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

/* ── Saved Stories Sidebar ── */
.saved-sidebar {
  width: 52px;
  flex-shrink: 0;
  padding: 32px 0 32px 0;
  transition: width 0.2s ease;
  overflow: hidden;
}
.saved-sidebar--open {
  width: 300px;
  border-left: 1px solid var(--border);
  padding: 32px 16px;
}

.saved-sidebar-toggle {
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
.saved-sidebar-toggle:hover { color: var(--accent); border-color: var(--accent); }
.saved-sidebar--open .saved-sidebar-toggle { margin-bottom: 8px; }

.saved-sidebar-save {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 7px 12px;
  margin-bottom: 12px;
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

.saved-sidebar-label {
  display: none;
}
.saved-sidebar--open .saved-sidebar-label { display: inline; }
.saved-sidebar--open .saved-count { display: inline; }

.saved-sidebar-chevron {
  margin-left: auto;
  transition: transform 0.2s;
  display: none;
}
.saved-sidebar--open .saved-sidebar-chevron { display: block; }
.saved-sidebar-chevron.rotated { transform: rotate(180deg); }

.saved-count {
  opacity: 0.6;
  font-size: 10px;
  display: none;
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

.saved-story-delete {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  opacity: 0;
  transition: all 0.12s;
}
.saved-story-item:hover .saved-story-delete { opacity: 0.6; }
.saved-story-delete:hover { opacity: 1 !important; color: #ef4444; }

@media (max-width: 900px) {
  .pipeline-layout { flex-direction: column; }
  .saved-sidebar {
    width: 100% !important;
    border-left: none !important;
    border-top: 1px solid var(--border);
    padding: 16px 24px !important;
  }
  .saved-sidebar-label { display: inline !important; }
  .saved-sidebar-chevron { display: block !important; }
  .saved-count { display: inline !important; }
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

.generate-first-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
  cursor: pointer;
  flex-shrink: 0;
}

.generate-first-check {
  margin: 0;
  accent-color: var(--accent);
}

.generate-first-text {
  font: 600 10px/1 var(--font-mono);
  letter-spacing: 0.03em;
  color: var(--text-secondary);
  white-space: nowrap;
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

/* ---- Custom style dropdown (matches Scene Generator StylePicker) ---- */
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

  .gen-group--action,
  .control-group--auto {
    margin-left: 0;
    align-self: stretch;
  }

  .story-generator-header {
    flex-direction: column;
    align-items: stretch;
  }

  .generate-first-toggle {
    width: fit-content;
  }
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
</style>
