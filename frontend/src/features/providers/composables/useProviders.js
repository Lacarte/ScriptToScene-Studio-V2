import { ref, readonly } from 'vue'
import { api } from '@/shared/api/client.js'

const providers = ref({
  tts: { providers: [], selected: null },
  storyboard: { providers: [], selected: null },
  animator: { providers: [], selected: null },
})
const loading = ref(false)
const error = ref(null)

let loaded = false

export function useProviders() {
  async function loadProviders() {
    loading.value = true
    error.value = null
    try {
      const data = await api.get('/api/providers')
      providers.value = data.domains || {}
      loaded = true
    } catch (e) {
      error.value = e.message
      console.error('[Providers] Failed to load providers:', e)
    } finally {
      loading.value = false
    }
  }

  async function getProviderSettings(domain, providerId) {
    try {
      return await api.get(`/api/providers/${domain}/${providerId}/settings`)
    } catch (e) {
      console.error('[Providers] Failed to get settings:', e)
      throw e
    }
  }

  async function saveProviderSettings(domain, providerId, settings) {
    try {
      return await api.put(`/api/providers/${domain}/${providerId}/settings`, { body: settings })
    } catch (e) {
      console.error('[Providers] Failed to save settings:', e)
      throw e
    }
  }

  async function validateProviderSettings(domain, providerId, settings = {}) {
    try {
      return await api.post(`/api/providers/${domain}/${providerId}/validate`, { body: settings })
    } catch (e) {
      console.error('[Providers] Failed to validate settings:', e)
      throw e
    }
  }

  async function testProvider(domain, providerId, settings = {}) {
    try {
      return await api.post(`/api/providers/${domain}/${providerId}/test`, { body: settings })
    } catch (e) {
      console.error('[Providers] Failed to test provider:', e)
      throw e
    }
  }

  // One targeted write, not a read-modify-write of the whole settings document
  // (contracts.md §24.2). The old GET+spread+PUT of /api/settings/v2 had a real
  // lost-update window and needed a second round trip just to learn whether the
  // provider was configured; the endpoint answers both in one call.
  async function selectProvider(domain, providerId) {
    try {
      const current = providers.value[domain]?.selected
      if (current === providerId) return { switched: false }

      const result = await api.put(`/api/providers/${domain}/selection`, {
        body: { provider_id: providerId },
      })

      providers.value[domain] = {
        ...providers.value[domain],
        selected: result.selected,
      }

      return {
        switched: true,
        needsConfiguration: result.availability !== 'available',
        availability: result.availability,
        issues: result.issues || [],
      }
    } catch (e) {
      console.error('[Providers] Failed to select provider:', e)
      throw e
    }
  }

  function getSelectedProvider(domain) {
    const selected = providers.value[domain]?.selected
    if (!selected) return null
    const list = providers.value[domain]?.providers || []
    return list.find(p => p.id === selected) || null
  }

  function getProvidersByDomain(domain) {
    return providers.value[domain]?.providers || []
  }

  if (!loaded) {
    loadProviders()
  }

  return {
    providers: readonly(providers),
    loading: readonly(loading),
    error: readonly(error),
    loadProviders,
    getProviderSettings,
    saveProviderSettings,
    validateProviderSettings,
    testProvider,
    selectProvider,
    getSelectedProvider,
    getProvidersByDomain,
  }
}
