import { ref, watch, computed } from 'vue'
import { api } from '@/shared/api/client.js'
import { useSettings } from '@/features/settings/composables/useSettings.js'

// ── Singleton state ──

const text = ref('')
const kokoroVoice = ref(localStorage.getItem('sts-pipeline-voice') || 'af_heart')
const inworldVoice = ref(localStorage.getItem('sts-pipeline-inworld-voice') || 'Carter')
const speed = ref(parseFloat(localStorage.getItem('sts-pipeline-speed')) || 1.0)
watch(kokoroVoice, (v) => {
  if (v) localStorage.setItem('sts-pipeline-voice', v)
  else localStorage.removeItem('sts-pipeline-voice')
})
watch(inworldVoice, (v) => {
  if (v) localStorage.setItem('sts-pipeline-inworld-voice', v)
  else localStorage.removeItem('sts-pipeline-inworld-voice')
})
watch(speed, (v) => {
  if (v != null) localStorage.setItem('sts-pipeline-speed', String(v))
  else localStorage.removeItem('sts-pipeline-speed')
})
const style = ref('cinematic')
const stopAfter = ref(localStorage.getItem('sts-pipeline-stop-after') || '')
watch(stopAfter, (v) => {
  if (v) localStorage.setItem('sts-pipeline-stop-after', v)
  else localStorage.removeItem('sts-pipeline-stop-after')
})
const templates = ref([])
const imageModel = ref(localStorage.getItem('sts-image-model') || '')
watch(imageModel, (v) => {
  if (v) localStorage.setItem('sts-image-model', v)
  else localStorage.removeItem('sts-image-model')
})
const imageModelsConfig = ref({})

// ── TTS Provider & Voices ──

const kokoroVoices = ref([
  { id: 'af_heart', label: 'af_heart' },
  { id: 'af_bella', label: 'af_bella' },
  { id: 'am_adam', label: 'am_adam' },
  { id: 'am_michael', label: 'am_michael' },
  { id: 'bf_emma', label: 'bf_emma' },
])
const inworldVoices = ref([])
const inworldVoicesLoaded = ref(false)

// ── Favorites (persisted in localStorage) ──
const FAVORITES_KEY = 'sts-inworld-voice-favorites'

function _loadFavorites() {
  try {
    return JSON.parse(localStorage.getItem(FAVORITES_KEY) || '[]')
  } catch { return [] }
}

const favorites = ref(_loadFavorites())

function toggleFavorite(voiceId) {
  const idx = favorites.value.indexOf(voiceId)
  if (idx >= 0) favorites.value.splice(idx, 1)
  else favorites.value.push(voiceId)
  localStorage.setItem(FAVORITES_KEY, JSON.stringify(favorites.value))
}

function isFavorite(voiceId) {
  return favorites.value.includes(voiceId)
}

// Load Kokoro voices on init
api.get('/api/tts/voices').then(voices => {
  if (Array.isArray(voices) && voices.length) {
    kokoroVoices.value = voices.map(v => ({ id: v, label: v }))
  }
}).catch(() => {})

function loadInworldVoices() {
  if (inworldVoicesLoaded.value) return
  inworldVoicesLoaded.value = true
  api.get('/api/tts/voices?provider=inworld').then(voices => {
    if (Array.isArray(voices) && voices.length) {
      inworldVoices.value = voices
    }
  }).catch(() => {
    inworldVoicesLoaded.value = false
  })
}

// Computed: active provider from settings
const ttsProvider = computed(() => {
  const { settings } = useSettings()
  return settings.value['sts-tts-provider'] || 'kokoro'
})

// Computed: voice getter/setter that delegates to the active provider's ref
const voice = computed({
  get: () => ttsProvider.value === 'inworld' ? inworldVoice.value : kokoroVoice.value,
  set: (v) => {
    if (ttsProvider.value === 'inworld') inworldVoice.value = v
    else kokoroVoice.value = v
  },
})

// Computed: voices for the active provider (favorites first)
const VOICES = computed(() => {
  if (ttsProvider.value === 'inworld') {
    loadInworldVoices()
    const list = inworldVoices.value.length
      ? inworldVoices.value
      : [
          { id: 'Dennis', label: 'Dennis', description: 'Middle-aged man with a smooth, calm and friendly voice' },
          { id: 'Alex', label: 'Alex', description: 'Energetic and expressive mid-range male voice' },
          { id: 'Ashley', label: 'Ashley', description: 'A warm, natural female voice' },
        ]
    // Sort: favorites first, then alphabetical
    const favSet = new Set(favorites.value)
    return [...list].sort((a, b) => {
      const aFav = favSet.has(a.id) ? 0 : 1
      const bFav = favSet.has(b.id) ? 0 : 1
      if (aFav !== bFav) return aFav - bFav
      return a.label.localeCompare(b.label)
    })
  }
  return kokoroVoices.value
})

let _formInitialized = false

async function initForm() {
  if (_formInitialized) return
  _formInitialized = true

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
    const { settings } = useSettings()
    const defaultStyle = settings.value['sts-default-style']
    if (defaultStyle && templates.value.find(t => t.id === defaultStyle)) {
      style.value = defaultStyle
    }
  }

  // Pre-load Inworld voices if that's the active provider
  if (ttsProvider.value === 'inworld') {
    loadInworldVoices()
  }

  try {
    imageModelsConfig.value = await api.get('/api/storyboard/image-models')
  } catch (e) {
    console.warn('[Pipeline] Failed to load image models:', e.message)
  }
}

export function usePipelineForm() {
  initForm()

  return {
    VOICES,
    ttsProvider,
    favorites,
    toggleFavorite,
    isFavorite,
    text,
    voice,
    kokoroVoice,
    inworldVoice,
    speed,
    style,
    stopAfter,
    imageModel,
    imageModelsConfig,
    templates,
  }
}
