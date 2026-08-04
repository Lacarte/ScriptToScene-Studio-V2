import { ref } from 'vue'
import { api } from '@/shared/api/client.js'

// One fetch per source per session; every field instance shares the result.
const cache = new Map()

export function useOptionSource(source) {
  if (!cache.has(source)) {
    const state = ref({ loading: true, options: [], error: '' })
    cache.set(source, state)
    api
      .get(`/api/workflow/options/${encodeURIComponent(source)}`)
      .then((data) => {
        state.value = { loading: false, options: data.options || [], error: '' }
      })
      .catch((err) => {
        state.value = { loading: false, options: [], error: err?.message || 'Failed to load options' }
      })
  }
  return cache.get(source)
}

// Test hook: drop cached results so mocks take effect per test.
export function clearOptionSourceCache() {
  cache.clear()
}
