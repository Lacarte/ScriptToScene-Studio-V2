import { describe, it, expect, beforeEach, vi } from 'vitest'

// Step 11.5 — selecting a provider is one targeted write to
// PUT /api/providers/<domain>/selection, not a read-modify-write of the whole
// settings document (contracts.md §24.2).

const get = vi.fn()
const put = vi.fn()
const post = vi.fn()

vi.mock('@/shared/api/client.js', () => ({
  api: {
    get: (...args) => get(...args),
    put: (...args) => put(...args),
    post: (...args) => post(...args),
  },
}))

const CATALOG = {
  catalog_version: 'abc123',
  domains: {
    tts: {
      domain: 'tts',
      selected: 'kokoro',
      count: 2,
      excluded: [],
      providers: [
        { id: 'kokoro', label: 'Kokoro', availability: 'available' },
        { id: 'inworld', label: 'Inworld', availability: 'needs_configuration' },
      ],
    },
  },
}

async function freshComposable() {
  // The composable holds module-level state and auto-loads on first use; reset
  // the registry and await the load so each test starts from the same catalog.
  vi.resetModules()
  const module = await import('../composables/useProviders.js')
  const composable = module.useProviders()
  await composable.loadProviders()
  return composable
}

describe('useProviders.selectProvider', () => {
  beforeEach(() => {
    get.mockReset()
    put.mockReset()
    post.mockReset()
    // A fresh copy per call: the composable assigns `data.domains` straight into
    // its state, so a shared object would carry one test's mutation to the next.
    get.mockImplementation(async () => structuredClone(CATALOG))
  })

  it('writes the selection through the targeted endpoint', async () => {
    put.mockResolvedValue({
      domain: 'tts',
      selected: 'inworld',
      availability: 'available',
      issues: [],
    })
    const { selectProvider, providers } = await freshComposable()

    const result = await selectProvider('tts', 'inworld')

    expect(put).toHaveBeenCalledTimes(1)
    expect(put).toHaveBeenCalledWith('/api/providers/tts/selection', {
      body: { provider_id: 'inworld' },
    })
    expect(result).toMatchObject({ switched: true, needsConfiguration: false })
    expect(providers.value.tts.selected).toBe('inworld')
  })

  it('never reads or rewrites the whole settings document', async () => {
    put.mockResolvedValue({ selected: 'inworld', availability: 'available', issues: [] })
    const { selectProvider } = await freshComposable()

    await selectProvider('tts', 'inworld')

    expect(get.mock.calls.map(([path]) => path)).not.toContain('/api/settings/v2')
    expect(put.mock.calls.map(([path]) => path)).not.toContain('/api/settings/v2')
    // The separate validate round trip is gone: availability answers it (§21.5).
    expect(post).not.toHaveBeenCalled()
  })

  it('reports an unconfigured provider from availability, and still switches', async () => {
    put.mockResolvedValue({
      selected: 'inworld',
      availability: 'needs_configuration',
      issues: [{ field: 'api_key', severity: 'error', message: 'Required' }],
    })
    const { selectProvider, providers } = await freshComposable()

    const result = await selectProvider('tts', 'inworld')

    expect(result.needsConfiguration).toBe(true)
    expect(result.availability).toBe('needs_configuration')
    expect(result.issues).toHaveLength(1)
    // Selection is non-blocking — the store reflects the server's answer.
    expect(providers.value.tts.selected).toBe('inworld')
  })

  it('stores the canonical id the server resolved, not the alias sent', async () => {
    put.mockResolvedValue({ selected: 'inworld', availability: 'available', issues: [] })
    const { selectProvider, providers } = await freshComposable()

    await selectProvider('tts', 'inworld-legacy')

    expect(providers.value.tts.selected).toBe('inworld')
  })

  it('does not write when the provider is already selected', async () => {
    const { selectProvider } = await freshComposable()

    const result = await selectProvider('tts', 'kokoro')

    expect(result).toEqual({ switched: false })
    expect(put).not.toHaveBeenCalled()
  })

  it('propagates a failed selection instead of faking a switch', async () => {
    const failure = Object.assign(new Error('Provider not found'), {
      status: 404,
      code: 'PROVIDER_NOT_FOUND',
    })
    put.mockRejectedValue(failure)
    const { selectProvider, providers } = await freshComposable()

    await expect(selectProvider('tts', 'ghost')).rejects.toThrow('Provider not found')
    expect(providers.value.tts.selected).toBe('kokoro')
  })
})
