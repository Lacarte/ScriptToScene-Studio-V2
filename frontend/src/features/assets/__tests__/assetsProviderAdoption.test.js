import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import GrabberControls from '../components/GrabberControls.vue'
import { useAssets } from '../composables/useAssets.js'
import { api } from '@/shared/api/client.js'

// Step 12.4 — the Assets page is the surface that carried the most provider
// knowledge: a four-entry dropdown (two of whose entries were not providers),
// three `v-if` blocks keyed on provider ids, and a URL table. Every fixture here
// is invented, which is the point: the page renders a provider it has never
// heard of, from the catalog alone.

const FIXTURE_ID = 'fixture_animator'

const CATALOG = {
  catalog_version: 'v1',
  dev_reload_enabled: false,
  domains: {
    animator: {
      domain: 'animator',
      label: 'Animator',
      default_provider: FIXTURE_ID,
      selected: FIXTURE_ID,
      count: 1,
      excluded: [],
      providers: [
        {
          id: FIXTURE_ID,
          label: 'Fixture Animator',
          aliases: ['fixture-legacy'],
          availability: 'available',
          open_url: 'https://fixture.test/imagine',
          capabilities: { batch: true, image_to_video: true },
          has_settings: true,
        },
      ],
    },
  },
}

const SCHEMA = {
  type: 'object',
  properties: {
    api_key: { type: 'string', label: 'API key', default: '', ui: { type: 'password' } },
    mode: {
      type: 'string',
      label: 'Mode',
      default: 'video',
      ui: { type: 'dropdown', options: ['video', 'image'] },
    },
    duration: { type: 'string', label: 'Duration', default: '6s', ui: { type: 'dropdown', options: ['6s'] } },
  },
  required: ['api_key'],
}

function mockApi() {
  vi.spyOn(api, 'get').mockImplementation(async (url) => {
    if (url.endsWith('/settings')) {
      return { schema: SCHEMA, settings: { api_key: '***', mode: 'image' } }
    }
    if (url === '/api/settings') return {}
    return structuredClone(CATALOG)
  })
  vi.spyOn(api, 'post').mockResolvedValue({ grabber_id: 'g1' })
  vi.spyOn(api, 'put').mockResolvedValue({})
  vi.spyOn(api, 'patch').mockResolvedValue({})
}

describe('Assets grabber controls', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockApi()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('offers a provider it has never heard of, from the catalog', async () => {
    const wrapper = mount(GrabberControls, { props: { providerId: FIXTURE_ID } })
    await flushPromises()

    const labels = wrapper.findAll('.selector-select option').map((el) => el.text())
    expect(labels).toEqual(['Fixture Animator'])
  })

  it('names the selected provider on the start button', async () => {
    const wrapper = mount(GrabberControls, {
      props: { providerId: FIXTURE_ID, providerLabel: 'Fixture Animator', sceneCount: 2 },
    })
    await flushPromises()

    expect(wrapper.find('.btn-grabber').text()).toContain('Send to Fixture Animator')
  })

  it('renders per-run options from the provider schema, without its secret', async () => {
    const wrapper = mount(GrabberControls, {
      props: {
        providerId: FIXTURE_ID,
        providerSchema: SCHEMA,
        providerOptions: { mode: 'image', duration: '6s' },
      },
    })
    await flushPromises()

    const labels = wrapper.findAll('.per-run-options .field-label').map((el) => el.text())
    expect(labels).toEqual(['Mode', 'Duration'])
    // These values are persisted with the job and pushed to an extension.
    expect(wrapper.find('.per-run-options').html()).not.toContain('password')
  })

  it('draws no per-run form for a provider that declares no settings', async () => {
    const wrapper = mount(GrabberControls, { props: { providerId: FIXTURE_ID } })
    await flushPromises()

    expect(wrapper.find('.per-run-options').exists()).toBe(false)
  })
})

describe('Assets grabber request', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockApi()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('sends the canonical id on both provider fields and generic options', async () => {
    vi.useFakeTimers()
    const assets = useAssets()
    vi.useRealTimers()
    await vi.waitUntil(() => assets.providerId.value === FIXTURE_ID)
    await vi.waitUntil(() => Object.keys(assets.providerOptions.value).length > 0)

    assets.loadScenes({ scenes: [{ index: 0, image_prompt: 'a cat' }] })
    await assets.startGrabber('proj_1')
    assets.stopGrabber()

    const [url, { body }] = api.post.mock.calls.at(-1)
    expect(url).toBe('/api/animator/grabber/start')
    // Step 16.1: canonical ids on the wire; aliases remain accepted as input only.
    expect(body.provider_override).toBe(FIXTURE_ID)
    expect(body.provider).toBe(FIXTURE_ID)
    // Per-run options are seeded from the provider's configured values, and the
    // credential is not one of them.
    expect(body.provider_options).toEqual({ mode: 'image', duration: '6s' })
    expect(body.aspect_ratio).toBe('9:16')
    expect(body.arguments).toBe('')
  })
})

describe('no provider id on the adopted legacy surfaces', () => {
  // The 12.2 guard, extended to the pages that adopted the shared UI in 12.4.
  const src = resolve(process.cwd(), 'src')
  const SHIPPED_PROVIDER_IDS = [
    'kokoro', 'inworld', 'gemini_ws', 'wavespeed_webhook', 'wavespeed_direct',
    'grok_automa', 'kie_ai',
    // The legacy wire spellings are just as much a hardcoded identity.
    'midjourney', 'meta-ai', 'kie-ai',
  ]
  const FILES = [
    join(src, 'features', 'assets', 'components', 'GrabberControls.vue'),
    join(src, 'features', 'assets', 'components', 'AssetCard.vue'),
    join(src, 'features', 'assets', 'composables', 'useAssets.js'),
    join(src, 'features', 'assets', 'views', 'AssetsPage.vue'),
    join(src, 'features', 'storyboard', 'views', 'StoryboardPage.vue'),
    join(src, 'features', 'tts', 'views', 'TtsPage.vue'),
    join(src, 'features', 'providers', 'composables', 'useDomainProvider.js'),
    join(src, 'features', 'providers', 'components', 'ProviderConfigurator.vue'),
  ]
  // `useTts.js` and `usePipelineForm.js` are deliberately absent. Their
  // *selection* reads were converted here; their per-engine generation and
  // voice-routing branches (P36, P37) belong to 15.2 and still name engines.

  it.each(FILES)('%s names no provider', (path) => {
    const source = readFileSync(path, 'utf8').toLowerCase()
    for (const id of SHIPPED_PROVIDER_IDS) {
      expect(source, `${path} mentions ${id}`).not.toContain(id)
    }
  })
})
