import { ref, watch } from 'vue'
import { api } from '@/shared/api/client.js'
import { useSettings } from '@/features/settings/composables/useSettings.js'

// ── Singleton state ──

const text = ref('')
const voice = ref('af_heart')
const speed = ref(1.0)
const style = ref('cinematic')
const autoScenes = ref(true)   // always enabled (UI toggle removed)
const autoStoryboard = ref(true) // always enabled (UI toggle removed)
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

const VOICES = ref([
  { id: 'af_heart', label: 'af_heart' },
  { id: 'af_bella', label: 'af_bella' },
  { id: 'am_adam', label: 'am_adam' },
  { id: 'am_michael', label: 'am_michael' },
  { id: 'bf_emma', label: 'bf_emma' },
])

// Load full voice list from TTS API
api.get('/api/tts/voices').then(voices => {
  if (Array.isArray(voices) && voices.length) {
    VOICES.value = voices.map(v => ({ id: v, label: v }))
  }
}).catch(() => {})

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
    text,
    voice,
    speed,
    style,
    autoScenes,
    autoStoryboard,
    stopAfter,
    imageModel,
    imageModelsConfig,
    templates,
  }
}
