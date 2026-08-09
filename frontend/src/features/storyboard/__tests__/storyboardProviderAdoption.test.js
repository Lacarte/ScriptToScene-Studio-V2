import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { api } from '@/shared/api/client.js'

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

import StoryboardPage from '../views/StoryboardPage.vue'

// Step 12.4 — the Storyboard page had a two-option dropdown over a three-provider
// domain, and kept the webhook URL, image model, and prompt prefix in
// `localStorage` behind blocks gated on provider ids. All of it now comes from
// the catalog and the selected provider's settings, and the request shape the
// routes still compare against is unchanged (contracts.md §40.3).

const FIXTURE_ID = 'fixture_storyboard'

const CATALOG = {
  catalog_version: 'v1',
  dev_reload_enabled: false,
  domains: {
    storyboard: {
      domain: 'storyboard',
      label: 'Storyboard',
      default_provider: FIXTURE_ID,
      selected: FIXTURE_ID,
      count: 1,
      excluded: [],
      providers: [
        {
          id: FIXTURE_ID,
          label: 'Fixture Storyboard',
          aliases: ['fixture-legacy'],
          availability: 'available',
          description: 'A storyboard provider this page has never heard of.',
          capabilities: {},
          has_settings: true,
        },
      ],
    },
  },
}

const SCHEMA = {
  type: 'object',
  properties: {
    webhook_url: { type: 'string', label: 'Webhook URL', default: '' },
    image_model: { type: 'string', label: 'Image Model', default: '' },
    prompt_prefix: { type: 'string', label: 'Prompt prefix', default: '' },
  },
  required: [],
}

let stored

function mockApi() {
  vi.spyOn(api, 'get').mockImplementation(async (url) => {
    if (url.endsWith('/settings')) return { schema: SCHEMA, settings: { ...stored } }
    if (url === '/api/settings') return {}
    if (url.startsWith('/api/providers')) return structuredClone(CATALOG)
    if (url.startsWith('/api/storyboard/history')) return []
    return {}
  })
  vi.spyOn(api, 'post').mockResolvedValue({ status: 'running' })
  vi.spyOn(api, 'put').mockResolvedValue({ ok: true })
  vi.spyOn(api, 'patch').mockResolvedValue({})
}

async function page() {
  const wrapper = mount(StoryboardPage)
  await flushPromises()
  await flushPromises()
  return wrapper
}

describe('Storyboard provider adoption', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    stored = {
      webhook_url: 'https://fixture.test/hook',
      image_model: 'model-a',
      prompt_prefix: 'draw ',
    }
    mockApi()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('lists a provider it has never heard of, with the catalog label', async () => {
    const wrapper = await page()

    const options = wrapper.findAll('.selector-select option').map((el) => el.text())
    expect(options).toEqual(['Fixture Storyboard'])
    expect(wrapper.text()).toContain('A storyboard provider this page has never heard of.')
  })

  it('sends the legacy provider spelling and the configured fields', async () => {
    const wrapper = await page()
    wrapper.vm.scenes = [{ index: 0, prompt: 'a castle' }]
    await wrapper.vm.grabAll()

    const [url, { body }] = api.post.mock.calls.at(-1)
    expect(url).toBe('/api/storyboard/generate')
    // §40.3's output column: what `POST /api/storyboard/grab` still compares.
    expect(body.provider).toBe('fixture-legacy')
    expect(body.webhook_url).toBe('https://fixture.test/hook')
    expect(body.image_model).toBe('model-a')
    // The prefix is still applied client-side; it just no longer lives in
    // `localStorage` behind a provider-id check.
    expect(body.scenes).toEqual([{ scene: 0, prompt: 'draw a castle' }])
  })

  it('omits the optional fields a provider does not have configured', async () => {
    stored = {}
    const wrapper = await page()
    wrapper.vm.scenes = [{ index: 0, prompt: 'a castle' }]
    await wrapper.vm.grabAll()

    const [, { body }] = api.post.mock.calls.at(-1)
    expect(body).not.toHaveProperty('webhook_url')
    expect(body).not.toHaveProperty('image_model')
    expect(body.scenes).toEqual([{ scene: 0, prompt: 'a castle' }])
  })

  it('refuses to run an unconfigured provider, whichever one it is', async () => {
    const unconfigured = structuredClone(CATALOG)
    unconfigured.domains.storyboard.providers[0].availability = 'needs_configuration'
    api.get.mockImplementation(async (url) => {
      if (url.endsWith('/settings')) return { schema: SCHEMA, settings: {} }
      if (url === '/api/settings') return {}
      if (url.startsWith('/api/providers')) return unconfigured
      return url.startsWith('/api/storyboard/history') ? [] : {}
    })
    const wrapper = await page()
    wrapper.vm.scenes = [{ index: 0, prompt: 'a castle' }]

    await wrapper.vm.grabAll()

    // `needs_configuration` *is* "a required setting is empty" (§21.5) — one
    // check replaces the webhook-enabled-and-has-a-URL guard.
    expect(api.post).not.toHaveBeenCalled()
  })

  it('adopts a value left in the retired localStorage key exactly once', async () => {
    stored = {}
    localStorage.setItem('sts-storyboard-webhook-url', 'https://old.test/hook')
    await page()
    await flushPromises()

    expect(api.put).toHaveBeenCalledWith(
      `/api/providers/storyboard/${FIXTURE_ID}/settings`,
      { body: { webhook_url: 'https://old.test/hook' } },
    )
  })

  it('leaves a configured provider alone rather than reviving an old value', async () => {
    localStorage.setItem('sts-storyboard-webhook-url', 'https://old.test/hook')
    await page()
    await flushPromises()

    expect(api.put).not.toHaveBeenCalled()
  })
})
