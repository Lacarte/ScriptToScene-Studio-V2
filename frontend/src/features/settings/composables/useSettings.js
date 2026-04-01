import { ref, readonly } from 'vue'
import { api } from '@/shared/api/client.js'

const DEFAULTS = {
  'sts-normalize': true,
  'sts-clean': true,
  'sts-editor-storage': true,
  'sts-editor-session-storage': true,
  'sts-sound-enabled': true,
  'sts-caption-default-preset': 'bold_popup',
  'sts-default-style': 'cinematic',
  'sts-tts-provider': 'kokoro',
  'sts-storyboard-provider': 'gemini',
  'sts-asset-provider': 'grok',
  'sts-sync-folder': 'D:/@Sync/PHONE-S24-PC',
  'sts-auto-sync': true,
}

const settings = ref({ ...DEFAULTS })
const loading = ref(false)
const health = ref(null)
const healthLoading = ref(false)

let loaded = false

export function useSettings() {
  async function load() {
    loading.value = true
    try {
      const data = await api.get('/api/settings')
      settings.value = { ...DEFAULTS, ...data }
      loaded = true
    } catch (e) {
      console.warn('[Settings] Failed to load settings:', e.message)
      settings.value = { ...DEFAULTS }
    } finally {
      loading.value = false
    }
  }

  async function update(key, value) {
    settings.value[key] = value
    try {
      await api.patch('/api/settings', { body: { [key]: value } })
    } catch (err) {
      // revert on failure
      await load()
      throw err
    }
  }

  async function resetAll() {
    loading.value = true
    try {
      await api.delete('/api/settings')
      settings.value = { ...DEFAULTS }
    } finally {
      loading.value = false
    }
  }

  async function fetchHealth() {
    healthLoading.value = true
    try {
      health.value = await api.get('/api/health')
    } catch (e) {
      console.warn('[Settings] Health check failed:', e.message)
      health.value = null
    } finally {
      healthLoading.value = false
    }
  }

  async function fetchClearPreview() {
    return api.get('/api/settings/clear-all-projects/preview')
  }

  async function executeClearAll() {
    return api.delete('/api/settings/clear-all-projects')
  }

  // Auto-load on first use
  if (!loaded) {
    load()
  }

  return {
    settings: readonly(settings),
    loading: readonly(loading),
    health: readonly(health),
    healthLoading: readonly(healthLoading),
    load,
    update,
    resetAll,
    fetchHealth,
    fetchClearPreview,
    executeClearAll,
  }
}
