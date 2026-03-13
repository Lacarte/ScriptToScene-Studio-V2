import { ref, computed, readonly, shallowRef } from 'vue'
import { api } from '@/shared/api/client.js'

// ---- Provider config ----
const PROVIDER_URLS = {
  midjourney: 'https://www.midjourney.com/imagine',
  grok: 'https://grok.com/imagine',
  'meta-ai': 'https://www.meta.ai/media',
}

const TYPE_COLORS = {
  video: '#4ECDC4',
  image: '#A78BFA',
  text: '#FFB347',
}

// ---- Singleton state ----
const scenes = ref([])
const provider = ref('grok')
const arguments_ = ref('')
const aspectRatio = ref('16:9')
const providerOptions = ref({
  grok_mode: 'default',
  grok_quality: 'standard',
  grok_duration: '5',
  model: 'default',
  resolution: '1024x1024',
  output_format: 'png',
  auto_type: false,
})

const grabberRunning = ref(false)
const grabberJobId = ref(null)
const sceneStatuses = ref({})
const selectedScenes = ref(new Set())
const history = ref([])
const analysisData = ref(null)

// Audio
const audioUrl = ref(null)
const isPlaying = ref(false)
const currentTime = ref(0)

// Lightbox
const lightboxOpen = ref(false)
const lightboxScene = ref(null)
const lightboxFile = ref(null)

let pollTimer = null

// ---- Derived ----
const sceneCount = computed(() => scenes.value.length)
const selectedCount = computed(() => selectedScenes.value.size)

const progress = computed(() => {
  const total = scenes.value.length
  if (!total) return { total: 0, ready: 0, error: 0, pending: 0, percent: 0 }
  let ready = 0
  let error = 0
  for (const s of scenes.value) {
    const st = sceneStatuses.value[s.index]
    if (st?.status === 'ready') ready++
    else if (st?.status === 'error') error++
  }
  return {
    total,
    ready,
    error,
    pending: total - ready - error,
    percent: Math.round((ready / total) * 100),
  }
})

export function useAssets() {
  // ---- Load scenes from scene generator result ----
  function loadScenes(data) {
    if (!data || !Array.isArray(data.scenes)) return
    scenes.value = data.scenes.map((s, i) => ({ ...s, index: s.index ?? i }))
    analysisData.value = data.analysis ?? null
    audioUrl.value = data.audio_url ?? null
    sceneStatuses.value = {}
    selectedScenes.value = new Set()
  }

  function setProvider(p) {
    provider.value = p
  }

  function setArguments(a) {
    arguments_.value = a
  }

  function setAspectRatio(ar) {
    aspectRatio.value = ar
  }

  function setProviderOption(key, value) {
    providerOptions.value = { ...providerOptions.value, [key]: value }
  }

  // ---- Grabber ----
  async function startGrabber(projectId) {
    if (!scenes.value.length) return

    const payload = {
      project_id: projectId || `project_${Date.now()}`,
      scenes: scenes.value.map(s => ({
        prompt: s.image_prompt || s.text_content || '',
        scene: s.index,
      })),
      provider: provider.value,
      arguments: arguments_.value,
      aspect_ratio: aspectRatio.value,
      ...providerOptions.value,
    }

    try {
      const res = await api.post('/api/assets/grabber/start', { body: payload })
      grabberRunning.value = true
      grabberJobId.value = res.grabber_id || payload.project_id
      startPolling(payload.project_id)
      return res
    } catch (err) {
      grabberRunning.value = false
      throw err
    }
  }

  async function stopGrabber() {
    grabberRunning.value = false
    stopPolling()
  }

  function startPolling(projectId) {
    stopPolling()
    pollTimer = setInterval(() => pollStatus(projectId), 3000)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function pollStatus(projectId) {
    try {
      const res = await api.get(`/api/assets/grabber/status/${projectId}`)
      if (res.scene_statuses) {
        sceneStatuses.value = { ...res.scene_statuses }
      }
      if (res.status === 'completed' || res.status === 'error') {
        grabberRunning.value = false
        stopPolling()
      }
    } catch {
      // keep polling on transient errors
    }
  }

  async function redownload(projectId) {
    return api.post(`/api/assets/redownload/${projectId}`)
  }

  // ---- History ----
  async function loadHistory() {
    try {
      history.value = await api.get('/api/assets/history')
    } catch {
      history.value = []
    }
  }

  async function loadFromHistory(projectId) {
    try {
      const data = await api.get(`/api/assets/project/${projectId}`)
      if (data.scenes) {
        scenes.value = data.scenes
        sceneStatuses.value = data.scene_statuses || {}
        analysisData.value = data.analysis || null
        audioUrl.value = data.audio_url || null
        selectedScenes.value = new Set()
      }
      return data
    } catch (err) {
      throw err
    }
  }

  async function reconcile(projectId) {
    return api.post(`/api/assets/reconcile/${projectId}`)
  }

  // ---- Scene card actions ----
  function editPrompt(idx) {
    const scene = scenes.value.find(s => s.index === idx)
    if (scene) scene._editing = true
  }

  function savePrompt(idx, newPrompt) {
    const scene = scenes.value.find(s => s.index === idx)
    if (scene) {
      scene.image_prompt = newPrompt
      scene._editing = false
    }
  }

  function copyPrompt(idx) {
    const scene = scenes.value.find(s => s.index === idx)
    if (!scene) return
    const text = scene.image_prompt || scene.text_content || ''
    navigator.clipboard.writeText(text).catch(() => {})
  }

  async function openFolder(idx, projectId) {
    return api.post(`/api/assets/open-folder/${projectId}/${idx}`)
  }

  async function downloadScene(idx, projectId) {
    const status = sceneStatuses.value[idx]
    if (!status?.local_files?.length) return
    for (const file of status.local_files) {
      const link = document.createElement('a')
      link.href = `/output/assets/${file}`
      link.download = file.split('/').pop()
      link.click()
    }
  }

  function downloadAll(projectId) {
    for (const scene of scenes.value) {
      downloadScene(scene.index, projectId)
    }
  }

  // ---- Selection ----
  function toggleSelect(idx) {
    const next = new Set(selectedScenes.value)
    if (next.has(idx)) next.delete(idx)
    else next.add(idx)
    selectedScenes.value = next
  }

  function selectAll() {
    selectedScenes.value = new Set(scenes.value.map(s => s.index))
  }

  function selectNone() {
    selectedScenes.value = new Set()
  }

  function selectPending() {
    const pending = new Set()
    for (const scene of scenes.value) {
      const st = sceneStatuses.value[scene.index]
      if (!st || st.status === 'pending' || st.status === 'error') {
        pending.add(scene.index)
      }
    }
    selectedScenes.value = pending
  }

  async function resendSelected(projectId) {
    const selected = scenes.value.filter(s => selectedScenes.value.has(s.index))
    if (!selected.length) return

    const payload = {
      project_id: projectId || `project_${Date.now()}`,
      scenes: selected.map(s => ({
        prompt: s.image_prompt || s.text_content || '',
        scene: s.index,
      })),
      provider: provider.value,
      arguments: arguments_.value,
      aspect_ratio: aspectRatio.value,
      ...providerOptions.value,
    }

    const res = await api.post('/api/assets/grabber/start', { body: payload })
    grabberRunning.value = true
    grabberJobId.value = res.grabber_id || payload.project_id
    startPolling(payload.project_id)
    return res
  }

  // ---- Lightbox ----
  function openLightbox(scene, file) {
    lightboxScene.value = scene
    lightboxFile.value = file
    lightboxOpen.value = true
  }

  function closeLightbox() {
    lightboxOpen.value = false
    lightboxScene.value = null
    lightboxFile.value = null
  }

  // ---- Scene history picker ----
  async function loadSceneHistory() {
    return api.get('/api/scenes/history')
  }

  // ---- Thumbnails ----
  async function generateThumbnails(projectId) {
    return api.post(`/api/assets/thumbnails/${projectId}`)
  }

  return {
    // State
    scenes: readonly(scenes),
    provider,
    arguments: arguments_,
    aspectRatio,
    providerOptions,
    grabberRunning: readonly(grabberRunning),
    grabberJobId: readonly(grabberJobId),
    sceneStatuses,
    selectedScenes,
    history: readonly(history),
    analysisData: readonly(analysisData),

    // Audio
    audioUrl: readonly(audioUrl),
    isPlaying,
    currentTime,

    // Lightbox
    lightboxOpen,
    lightboxScene: readonly(lightboxScene),
    lightboxFile: readonly(lightboxFile),

    // Derived
    sceneCount,
    selectedCount,
    progress,

    // Constants
    PROVIDER_URLS,
    TYPE_COLORS,

    // Functions
    loadScenes,
    setProvider,
    setArguments,
    setAspectRatio,
    setProviderOption,
    startGrabber,
    stopGrabber,
    pollStatus,
    redownload,
    loadHistory,
    loadFromHistory,
    reconcile,
    editPrompt,
    savePrompt,
    copyPrompt,
    openFolder,
    downloadScene,
    downloadAll,
    toggleSelect,
    selectAll,
    selectNone,
    selectPending,
    resendSelected,
    openLightbox,
    closeLightbox,
    loadSceneHistory,
    generateThumbnails,
  }
}
