import { ref, readonly } from 'vue'
import { api } from '@/shared/api/client.js'

// ── Singleton state ──
const webhookUrl = ref('')
const defaultWebhookUrl = ref('')
const categories = ref([])
const isGenerating = ref(false)
const result = ref(null)
const history = ref([])
const error = ref('')

// Form state
const storyCategory = ref('motivation')
const storyDuration = ref(45)
const storyLanguage = ref('english')
const storyStyle = ref('cinematic')

let initialized = false

const LANGUAGES = [
  { id: 'english', label: 'English' },
  { id: 'french', label: 'French' },
  { id: 'spanish', label: 'Spanish' },
]

// ── Actions ──

async function initStory() {
  if (initialized) return
  initialized = true

  try {
    const data = await api.get('/api/story/webhook-url')
    defaultWebhookUrl.value = data.url || ''
  } catch (e) {
    console.warn('[Story] Failed to load webhook URL:', e.message)
    defaultWebhookUrl.value = ''
  }

  const saved = localStorage.getItem('sts-story-webhook-url')
  webhookUrl.value = saved !== null ? saved : defaultWebhookUrl.value

  try {
    categories.value = await api.get('/api/story/categories')
  } catch (e) {
    console.warn('[Story] Failed to load categories:', e.message)
    categories.value = ['motivation', 'horror', 'mystery', 'science', 'survival', 'psychology', 'history']
  }

  // Restore saved form values
  const savedCat = localStorage.getItem('sts-story-category')
  if (savedCat && categories.value.includes(savedCat)) {
    storyCategory.value = savedCat
  } else if (savedCat) {
    localStorage.removeItem('sts-story-category')
  }

  const savedLang = localStorage.getItem('sts-story-language')
  if (savedLang) storyLanguage.value = savedLang

  const savedDur = localStorage.getItem('sts-story-duration')
  if (savedDur) {
    const parsedDuration = parseInt(savedDur, 10)
    storyDuration.value = Number.isFinite(parsedDuration) ? Math.min(180, Math.max(15, parsedDuration)) : 45
  }

  await loadHistory()
}

function saveWebhookUrl(url) {
  webhookUrl.value = url
  localStorage.setItem('sts-story-webhook-url', url)
}

function resetWebhookUrl() {
  webhookUrl.value = defaultWebhookUrl.value
  localStorage.removeItem('sts-story-webhook-url')
}

async function generateStory(styleOverride, { storyTone, idea } = {}) {
  const url = webhookUrl.value?.trim()
  if (!url) throw new Error('No story webhook URL configured')

  isGenerating.value = true
  error.value = ''
  result.value = null

  // Persist form selections
  localStorage.setItem('sts-story-category', storyCategory.value)
  localStorage.setItem('sts-story-language', storyLanguage.value)
  localStorage.setItem('sts-story-duration', String(storyDuration.value))

  try {
    const payload = {
      preset_style: styleOverride || storyStyle.value,
      story_category: storyCategory.value,
      duration: storyDuration.value,
      language: storyLanguage.value,
      webhook_url: url,
      ...(storyTone ? { story_tone: storyTone } : {}),
      ...(idea ? { idea } : {}),
    }

    const data = await api.post('/api/story/generate', {
      body: payload,
      timeout: 300000, // 5 min
    })

    result.value = data
    await loadHistory()
    return data
  } catch (e) {
    error.value = e.message || 'Story generation failed'
    throw e
  } finally {
    isGenerating.value = false
  }
}

async function loadHistory() {
  try {
    history.value = await api.get('/api/story/history')
  } catch (e) {
    console.warn('[Story] Failed to load history:', e.message)
    history.value = []
  }
}

async function loadStory(projectId) {
  const data = await api.get(`/api/story/${projectId}`)
  result.value = {
    success: true,
    project_id: data.project_id,
    story_text: data.story_text,
    sections: data.sections,
    ...(data.metadata || {}),
  }
  return result.value
}

function clearResult() {
  result.value = null
  error.value = ''
}

// ── Composable ──

export function useStory() {
  initStory()

  return {
    // Constants
    LANGUAGES,

    // State
    webhookUrl: readonly(webhookUrl),
    defaultWebhookUrl: readonly(defaultWebhookUrl),
    categories: readonly(categories),
    isGenerating: readonly(isGenerating),
    result: readonly(result),
    history: readonly(history),
    error: readonly(error),

    // Form
    storyCategory,
    storyDuration,
    storyLanguage,
    storyStyle,

    // Actions
    generateStory,
    loadHistory,
    loadStory,
    clearResult,
    saveWebhookUrl,
    resetWebhookUrl,
  }
}
