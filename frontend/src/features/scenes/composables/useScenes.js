import { ref, readonly, computed } from 'vue'
import { api } from '@/shared/api/client.js'
import { useAudioRegistry } from '@/shared/composables/useAudioRegistry.js'

const { register: audioRegister, unregister: audioUnregister } = useAudioRegistry()

// ---- Singleton state ----
const segData = ref(null)
const templates = ref([])
const selectedStyle = ref('cinematic')
const webhookEnabled = ref(true)
const webhookUrl = ref('')
const defaultWebhookUrl = ref('')
const payload = ref(null)
const result = ref(null)
const isGenerating = ref(false)
const history = ref([])
const forkPerStyle = ref(false)

// Audio playback
const audioUrl = ref(null)
const audioEl = ref(null)
const isPlaying = ref(false)
const currentTime = ref(0)
const activeSceneIdx = ref(-1)
let animFrame = null

// Segmenter history for picker
const segHistory = ref([])

let templatesLoaded = false
let webhookLoaded = false
const initializing = ref(false)

// Computed timings from segmenter data
const segTimings = computed(() => {
  const scenes = result.value?.scenes || []
  if (!scenes.length) return []

  const timings = []
  const sd = segData.value

  if (sd?.segments) {
    const allSegs = sd.segments
    const speechSegs = allSegs.filter(s => !s.is_filler)
    const totalEnd = sd.metadata?.total_duration || allSegs[allSegs.length - 1]?.end || 0

    for (let i = 0; i < scenes.length; i++) {
      const seg = speechSegs[i]
      if (seg) {
        const start = i === 0 ? 0 : seg.start
        const nextSeg = speechSegs[i + 1]
        const end = nextSeg ? nextSeg.start : totalEnd
        timings.push({ start, end, sceneIdx: i })
      } else {
        const prev = timings[i - 1]
        const start = prev ? prev.end : 0
        const dur = scenes[i].duration || 0
        timings.push({ start, end: start + dur, sceneIdx: i })
      }
    }
  } else {
    // Fallback: cumulative from scene durations
    let t = 0
    for (let i = 0; i < scenes.length; i++) {
      const dur = scenes[i].duration || 0
      timings.push({ start: t, end: t + dur, sceneIdx: i })
      t += dur
    }
  }
  return timings
})

const totalDuration = computed(() => {
  const t = segTimings.value
  return t.length ? t[t.length - 1].end : 0
})

const selectedTemplate = computed(() => {
  return templates.value.find(t => t.id === selectedStyle.value) || null
})

export function useScenes() {
  // ---- Templates ----
  async function loadTemplates() {
    try {
      templates.value = await api.get('/api/scenes/templates')
    } catch (e) {
      console.warn('[Scenes] Failed to load templates:', e.message)
      templates.value = [
        { id: 'cinematic', name: 'Cinematic', description: 'Default', color: '#4ECDC4', style_prompt: '' },
      ]
    }
    templatesLoaded = true
  }

  function selectStyle(id) {
    selectedStyle.value = id
    // Rebuild payload preview when style changes
    if (segData.value) buildPayload()
  }

  // ---- Webhook ----
  async function initWebhook() {
    if (webhookLoaded) return
    try {
      const data = await api.get('/api/scenes/webhook-url')
      defaultWebhookUrl.value = data.url || ''
    } catch (e) {
      console.warn('[Scenes] Failed to load webhook URL:', e.message)
      defaultWebhookUrl.value = ''
    }
    // Restore from localStorage, fall back to server default
    const saved = localStorage.getItem('sts-scenes-webhook-url')
    webhookUrl.value = saved !== null ? saved : defaultWebhookUrl.value

    const savedToggle = localStorage.getItem('sts-scenes-webhook-enabled')
    if (savedToggle === 'false') {
      webhookEnabled.value = false
    }
    webhookLoaded = true
  }

  function toggleWebhook() {
    webhookEnabled.value = !webhookEnabled.value
    localStorage.setItem('sts-scenes-webhook-enabled', webhookEnabled.value)
  }

  function resetWebhookUrl() {
    webhookUrl.value = defaultWebhookUrl.value
    localStorage.removeItem('sts-scenes-webhook-url')
  }

  function saveWebhookUrl(url) {
    webhookUrl.value = url
    localStorage.setItem('sts-scenes-webhook-url', url)
  }

  // ---- Payload ----
  function buildPayload() {
    const sd = segData.value
    if (!sd?.segments) {
      payload.value = null
      return null
    }

    const meta = sd.metadata || {}
    const allSegments = sd.segments || []
    const segments = allSegments
      .filter(s => !s.is_filler)
      .map(s => ({ index: s.index, words: s.words }))

    const tmpl = selectedTemplate.value || {}
    const built = {
      script: meta.transcript || '',
      style: selectedStyle.value,
      style_prompt: tmpl.style_prompt || '',
      segments,
    }

    // Include full segments for chapter-based generation (>20 speech segments)
    const speechCount = allSegments.filter(s => !s.is_filler).length
    if (speechCount > 20) {
      built.full_segments = allSegments
    }

    payload.value = built
    return built
  }

  // ---- Generate / Send ----
  async function sendToWebhook(aspectRatio = '9:16') {
    const sd = segData.value
    if (!sd?.segments) throw new Error('No segmentation data loaded')

    const url = webhookUrl.value?.trim()
    if (!url) throw new Error('Enter a webhook URL before sending')

    // Save webhook URL
    saveWebhookUrl(url)

    isGenerating.value = true
    stopAudio()
    result.value = null

    try {
      const meta = sd.metadata || {}
      const originalId = meta.project_id || ''
      const sendPayload = {
        ...buildPayload(),
        project_id: forkPerStyle.value ? '' : originalId,
        parent_id: forkPerStyle.value ? originalId : '',
        source_folder: meta.source_folder || '',
        aspect_ratio: aspectRatio,
        webhook_url: url,
      }

      const data = await api.post('/api/scenes/generate', {
        body: sendPayload,
        timeout: 600000,
      })

      result.value = data
      // Load audio for playback
      await loadAudio()
      // Refresh history
      await loadHistory()

      return data
    } finally {
      isGenerating.value = false
    }
  }

  // ---- History ----
  async function loadHistory() {
    try {
      history.value = await api.get('/api/scenes/history')
    } catch (e) {
      console.warn('[Scenes] Failed to load history:', e.message)
      history.value = []
    }
  }

  async function loadProject(projectId) {
    const data = await api.get(`/api/scenes/${projectId}`)
    result.value = data

    // Restore segmenter data if missing
    if (!segData.value && data.source_folder) {
      try {
        const hist = await api.get('/api/segmenter/history')
        const match = hist.find(h => h.source_folder === data.source_folder)
        if (match) {
          segData.value = await api.get(`/api/segmenter/${encodeURIComponent(match.folder)}`)
        }
      } catch (e) {
        console.warn('[Scenes] Failed to load segmenter data:', e.message)
        /* segment text won't show */
      }
    }

    // Sync style
    if (data.style) selectStyle(data.style)

    // Load audio
    await loadAudio()

    return data
  }

  // ---- Segmenter source ----
  function setSegData(data) {
    stopAudio()
    result.value = null
    segData.value = data
    buildPayload()
  }

  async function loadSegHistory() {
    try {
      segHistory.value = await api.get('/api/segmenter/history')
    } catch (e) {
      console.warn('[Scenes] Failed to load seg history:', e.message)
      segHistory.value = []
    }
    return segHistory.value
  }

  async function loadSegProject(folder) {
    const data = await api.get(`/api/segmenter/${encodeURIComponent(folder)}`)
    setSegData(data)
    return data
  }

  // ---- Audio ----
  async function loadAudio() {
    stopAudio()
    const sf = result.value?.source_folder || segData.value?.metadata?.source_folder
    if (!sf) {
      audioUrl.value = null
      return
    }
    try {
      const res = await api.get(`/api/scenes/audio/${encodeURIComponent(sf)}`)
      if (res?.url) {
        audioUrl.value = res.url
        const audio = new Audio(res.url)
        audio.onended = () => resetPlayback()
        audio.onerror = () => { audioUrl.value = null }
        audioEl.value = audio
        audioRegister('Scenes', audio)
      }
    } catch (e) {
      console.warn('[Scenes] Failed to load audio:', e.message)
      audioUrl.value = null
    }
  }

  function togglePlay() {
    const audio = audioEl.value
    if (!audio) return
    if (audio.paused) {
      audio.play().then(() => {
        isPlaying.value = true
        animFrame = requestAnimationFrame(tick)
      }).catch(() => {})
    } else {
      audio.pause()
      isPlaying.value = false
      if (animFrame) { cancelAnimationFrame(animFrame); animFrame = null }
    }
  }

  function seekTo(time) {
    const audio = audioEl.value
    if (!audio) return
    audio.currentTime = time
    updatePlayhead()
  }

  function playBlock(idx) {
    const audio = audioEl.value
    if (!audio) return
    const timing = segTimings.value[idx]
    if (!timing) return
    audio.currentTime = timing.start
    updatePlayhead()
    if (audio.paused) {
      audio.play().then(() => {
        isPlaying.value = true
        animFrame = requestAnimationFrame(tick)
      }).catch(() => {})
    }
  }

  function stopAudio() {
    const audio = audioEl.value
    if (audio) {
      audio.pause()
      audio.currentTime = 0
      audio.onended = null
      audio.onerror = null
    }
    audioUnregister('Scenes')
    audioEl.value = null
    audioUrl.value = null
    isPlaying.value = false
    currentTime.value = 0
    activeSceneIdx.value = -1
    if (animFrame) { cancelAnimationFrame(animFrame); animFrame = null }
  }

  function resetPlayback() {
    const audio = audioEl.value
    if (audio) {
      audio.pause()
      audio.currentTime = 0
    }
    isPlaying.value = false
    currentTime.value = 0
    activeSceneIdx.value = -1
    if (animFrame) { cancelAnimationFrame(animFrame); animFrame = null }
  }

  function tick() {
    const audio = audioEl.value
    if (!audio || audio.paused) return
    updatePlayhead()
    animFrame = requestAnimationFrame(tick)
  }

  function updatePlayhead() {
    const audio = audioEl.value
    if (!audio) return
    const t = audio.currentTime
    currentTime.value = t

    // Find active scene
    let idx = -1
    for (const timing of segTimings.value) {
      if (t >= timing.start && t < timing.end) { idx = timing.sceneIdx; break }
    }
    activeSceneIdx.value = idx
  }

  // ---- Style helpers ----
  function styleLabel(styleId) {
    if (!styleId) return ''
    const tmpl = templates.value.find(t => t.id === styleId)
    return tmpl ? tmpl.name : ''
  }

  function styleColor(styleId) {
    const tmpl = templates.value.find(t => t.id === styleId)
    return tmpl ? tmpl.color : 'var(--text-muted)'
  }

  // ---- Init ----
  if (!templatesLoaded) {
    initializing.value = true
    Promise.all([loadTemplates(), initWebhook()])
      .finally(() => { initializing.value = false })
  }

  return {
    initializing: readonly(initializing),
    // State
    segData: readonly(segData),
    templates: readonly(templates),
    selectedStyle: readonly(selectedStyle),
    selectedTemplate: readonly(selectedTemplate),
    webhookEnabled: readonly(webhookEnabled),
    webhookUrl: readonly(webhookUrl),
    payload: readonly(payload),
    result: readonly(result),
    isGenerating: readonly(isGenerating),
    history: readonly(history),
    forkPerStyle,
    segHistory: readonly(segHistory),

    // Audio
    audioUrl: readonly(audioUrl),
    isPlaying: readonly(isPlaying),
    currentTime: readonly(currentTime),
    activeSceneIdx: readonly(activeSceneIdx),
    segTimings: readonly(segTimings),
    totalDuration,

    // Functions
    loadTemplates,
    selectStyle,
    toggleWebhook,
    resetWebhookUrl,
    saveWebhookUrl,
    buildPayload,
    sendToWebhook,
    loadHistory,
    loadProject,
    setSegData,
    loadSegHistory,
    loadSegProject,
    loadAudio,
    togglePlay,
    seekTo,
    playBlock,
    stopAudio,
    styleLabel,
    styleColor,
  }
}
