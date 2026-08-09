import { ref, watch, computed } from 'vue'
import { api } from '@/shared/api/client.js'
import { useSettings } from '@/features/settings/composables/useSettings.js'
import { useDomainProvider } from '@/features/providers/composables/useDomainProvider.js'

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

/** `{id, label}` from either the reconciled shape or the historical bare ids. */
function asChoices(voices) {
  if (!Array.isArray(voices)) return []
  return voices
    .map(v => (typeof v === 'string' ? { id: v, label: v } : { ...v, label: v?.label || v?.id }))
    .filter(v => v.id)
}

// Load Kokoro voices on init
api.get('/api/tts/voices?provider=kokoro').then(voices => {
  const choices = asChoices(voices)
  if (choices.length) kokoroVoices.value = choices
}).catch(() => {})

function loadInworldVoices() {
  if (inworldVoicesLoaded.value) return
  inworldVoicesLoaded.value = true
  api.get('/api/tts/voices?provider=inworld').then(voices => {
    const choices = asChoices(voices)
    if (choices.length) inworldVoices.value = choices
  }).catch(() => {
    inworldVoicesLoaded.value = false
  })
}

// The selected TTS provider, from the catalog (step 12.4). This used to read the
// retired `app-config.json` key directly, so the pipeline and the provider modal
// could disagree about which engine a run would use. The per-provider voice
// routing below is 15.2's. Resolved on first use: this module is imported before
// Pinia is active.
let _ttsDomain = null
function ttsDomain() {
  if (!_ttsDomain) _ttsDomain = useDomainProvider('tts')
  return _ttsDomain
}

const ttsProvider = computed(() => ttsDomain().providerId.value)

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
