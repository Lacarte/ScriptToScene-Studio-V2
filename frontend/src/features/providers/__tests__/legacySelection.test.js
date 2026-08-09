import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useProviderCatalogStore } from '../stores/providerCatalog.js'
import { useSettings } from '@/features/settings/composables/useSettings.js'
import { api } from '@/shared/api/client.js'

// Step 12.4 — the retired `app-config.json` selection keys (contracts.md §24.3).
// Rule 3 gives the legacy pages one release of read-through, and the mirror keeps
// the readers this step does not touch — the pipeline run payload, the preflight,
// the provider tab opener — agreeing with the catalog. 16.1 deletes both.
//
// No shipped provider id appears here: the domain, the ids, and the legacy key
// are all fixtures, which is the whole claim being tested.

const CATALOG_URL = '/api/providers'
const LEGACY_KEY = 'sts-demo-provider'

function catalog({ selected = null, legacyKey = LEGACY_KEY } = {}) {
  return {
    catalog_version: 'v1',
    dev_reload_enabled: false,
    domains: {
      demo: {
        domain: 'demo',
        label: 'Demo',
        default_provider: 'alpha',
        selected,
        legacy_selection_key: legacyKey,
        count: 2,
        excluded: [],
        providers: [
          { id: 'alpha', label: 'Alpha', aliases: [], availability: 'available' },
          { id: 'beta', label: 'Beta', aliases: ['beta-legacy'], availability: 'available' },
        ],
      },
    },
  }
}

async function loadedStore(options) {
  api.get.mockImplementation(async (url) =>
    url === '/api/settings'
      ? { [LEGACY_KEY]: 'beta-legacy' }
      : structuredClone(catalog(options)),
  )
  await useSettings().load()
  const store = useProviderCatalogStore()
  await store.loadCatalog()
  return store
}

describe('legacy selection interop', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.spyOn(api, 'get')
    vi.spyOn(api, 'put').mockResolvedValue({})
    vi.spyOn(api, 'patch').mockResolvedValue({})
  })

  afterEach(() => vi.restoreAllMocks())

  it('reads through to the legacy key when the catalog has no selection', async () => {
    const store = await loadedStore({ selected: null })

    // Stored as an alias, resolved to the canonical id — a browser that loads
    // before the backend migration must not silently fall to the domain default.
    expect(store.selectedProvider('demo').id).toBe('beta')
  })

  it('prefers an explicit selection over the legacy key', async () => {
    const store = await loadedStore({ selected: 'alpha' })

    expect(store.selectedProvider('demo').id).toBe('alpha')
  })

  it('falls back to the domain default when neither store answers', async () => {
    api.get.mockImplementation(async (url) =>
      url === '/api/settings' ? {} : structuredClone(catalog({ selected: null })),
    )
    await useSettings().load()
    const store = useProviderCatalogStore()
    await store.loadCatalog()

    expect(store.selectedProvider('demo').id).toBe('alpha')
  })

  it('spells a provider on the legacy wire as its first alias', async () => {
    const store = await loadedStore({ selected: 'alpha' })

    // §40.3's output column: the string the un-migrated routes compare against.
    expect(store.legacyIdFor('demo', 'beta')).toBe('beta-legacy')
    // A provider that never had another name is already canonical there.
    expect(store.legacyIdFor('demo', 'alpha')).toBe('alpha')
  })

  it('mirrors a selection into the legacy key so the two stores cannot diverge', async () => {
    api.put.mockResolvedValue({ selected: 'beta', availability: 'available', issues: [] })
    const store = await loadedStore({ selected: 'alpha' })

    await store.selectProvider('demo', 'beta')

    expect(api.patch).toHaveBeenCalledWith('/api/settings', {
      body: { [LEGACY_KEY]: 'beta-legacy' },
    })
  })

  it('leaves the legacy store alone for a domain that never had one', async () => {
    api.put.mockResolvedValue({ selected: 'beta', availability: 'available', issues: [] })
    const store = await loadedStore({ selected: 'alpha', legacyKey: null })

    await store.selectProvider('demo', 'beta')

    expect(api.patch).not.toHaveBeenCalled()
    expect(store.selectedId('demo')).toBe('beta')
  })

  it('keeps the selection when the mirror write fails', async () => {
    api.put.mockResolvedValue({ selected: 'beta', availability: 'available', issues: [] })
    api.patch.mockRejectedValue(new Error('offline'))
    const store = await loadedStore({ selected: 'alpha' })

    await expect(store.selectProvider('demo', 'beta')).resolves.toMatchObject({ switched: true })
    expect(store.selectedId('demo')).toBe('beta')
  })

  it('never asks the settings endpoint for a catalog that ships no legacy key', async () => {
    await loadedStore({ selected: 'alpha', legacyKey: null })
    api.get.mockClear()
    const store = useProviderCatalogStore()

    store.selectedProvider('demo')

    expect(api.get.mock.calls.map(([url]) => url)).not.toContain('/api/settings')
    expect(api.get.mock.calls.map(([url]) => url)).not.toContain(CATALOG_URL)
  })
})
