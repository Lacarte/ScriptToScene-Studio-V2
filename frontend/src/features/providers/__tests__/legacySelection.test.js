import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { useProviderCatalogStore } from '../stores/providerCatalog.js'
import { useSettings } from '@/features/settings/composables/useSettings.js'
import { api } from '@/shared/api/client.js'

// Step 16.1 — the retired app-config selection store is gone.
// settings.json via the catalog is the only selection authority. These tests
// prove the read-through, the mirror, and the three key names no longer exist
// in the frontend surfaces that used to own them.

const RETIRED_KEYS = [
  'sts-tts-provider',
  'sts-storyboard-provider',
  'sts-asset-provider',
]

function catalog({ selected = 'alpha' } = {}) {
  return {
    catalog_version: 'v1',
    dev_reload_enabled: false,
    domains: {
      demo: {
        domain: 'demo',
        label: 'Demo',
        default_provider: 'alpha',
        selected,
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

describe('legacy selection retirement (step 16.1)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.spyOn(api, 'get')
    vi.spyOn(api, 'put').mockResolvedValue({})
    vi.spyOn(api, 'patch').mockResolvedValue({})
  })

  afterEach(() => vi.restoreAllMocks())

  it('selects from the catalog alone when selected is set', async () => {
    api.get.mockImplementation(async (url) =>
      url === '/api/settings' ? {} : structuredClone(catalog({ selected: 'beta' })),
    )
    await useSettings().load()
    const store = useProviderCatalogStore()
    await store.loadCatalog()

    expect(store.selectedProvider('demo').id).toBe('beta')
  })

  it('falls back to the domain default when the catalog has no selection', async () => {
    api.get.mockImplementation(async (url) =>
      url === '/api/settings' ? {} : structuredClone(catalog({ selected: null })),
    )
    await useSettings().load()
    const store = useProviderCatalogStore()
    await store.loadCatalog()

    expect(store.selectedProvider('demo').id).toBe('alpha')
  })

  it('does not mirror a selection into app-config', async () => {
    api.get.mockResolvedValue(structuredClone(catalog({ selected: 'alpha' })))
    api.put.mockResolvedValue({ selected: 'beta', availability: 'available', issues: [] })
    const store = useProviderCatalogStore()
    await store.loadCatalog()

    await store.selectProvider('demo', 'beta')

    expect(api.patch).not.toHaveBeenCalled()
    expect(store.selectedId('demo')).toBe('beta')
  })

  it('no longer exposes legacySelectionKey or legacyIdFor', async () => {
    api.get.mockResolvedValue(structuredClone(catalog()))
    const store = useProviderCatalogStore()
    await store.loadCatalog()

    expect(store.legacySelectionKey).toBeUndefined()
    expect(store.legacyIdFor).toBeUndefined()
  })

  it('does not default the three retired keys in useSettings', () => {
    const source = readFileSync(
      resolve(process.cwd(), 'src/features/settings/composables/useSettings.js'),
      'utf8',
    )
    // Comments may name the keys; only a DEFAULTS entry is a regression.
    const defaultsBlock = source.match(/const DEFAULTS = \{[\s\S]*?\n\}/)?.[0] || ''
    for (const key of RETIRED_KEYS) {
      expect(defaultsBlock, `DEFAULTS still ships ${key}`).not.toContain(`'${key}'`)
    }
  })

  it('pipeline and provider-tab composables no longer name the retired keys', () => {
    const files = [
      'src/features/pipeline/composables/usePipeline.js',
      'src/features/pipeline/composables/useProviderTabs.js',
      'src/features/providers/stores/providerCatalog.js',
      'src/features/providers/composables/useDomainProvider.js',
    ]
    for (const relative of files) {
      const source = readFileSync(resolve(process.cwd(), relative), 'utf8')
      for (const key of RETIRED_KEYS) {
        // Allow the useSettings comment that documents the deletion.
        if (relative.includes('useSettings')) continue
        expect(source, `${relative} still names ${key}`).not.toContain(key)
      }
    }
  })
})
