import { ref, readonly } from 'vue'
import { api } from '@/shared/api/client.js'
import { useProviderCatalogStore } from '@/features/providers/stores/providerCatalog.js'
import { ALL_STEPS } from '../constants/steps.js'

const pendingProviderUrl = ref(null)

/**
 * Activate the browser tab for an extension provider.
 *
 * `target` is a canonical provider id (or an accepted input alias). No provider
 * id is hard-coded here — the catalog decides which providers are extensions
 * (step 16.1 / P41).
 */
async function _activateProviderTab(target) {
  if (!target) return
  try {
    await api.post('/api/chromium/activate-tab', { body: { target } })
    pendingProviderUrl.value = null
  } catch (e) {
    const msg = e.message || ''
    if (msg.includes('404')) {
      pendingProviderUrl.value = `No ${target} tab found in Chromium \u2014 open it manually`
    } else {
      pendingProviderUrl.value = 'Chromium not running \u2014 launch it via start-dev'
    }
    console.warn('[STS] Tab activate failed:', msg)
  }
}

/**
 * Map an open URL onto the extension provider that declared it.
 *
 * Providers declare `open_url` on their manifest; matching the hostname is how
 * an SSE `open_url` event finds the right tab without naming a provider.
 */
function _providerForOpenUrl(url) {
  if (!url) return null
  const catalog = useProviderCatalogStore()
  for (const domain of ['storyboard', 'animator']) {
    for (const provider of catalog.providersFor(domain)) {
      if (provider.kind !== 'extension') continue
      const declared = provider.open_url
      if (!declared) continue
      try {
        const host = new URL(declared).hostname
        if (host && url.includes(host)) return provider
      } catch {
        if (url.includes(declared)) return provider
      }
    }
  }
  return null
}

function _openInProviderTab(url) {
  const provider = _providerForOpenUrl(url)
  if (provider) _activateProviderTab(provider.id)
}

function openPendingProvider() {
  pendingProviderUrl.value = null
}

function maybeOpenProviderLoadingTab({ stopValue, resumeStep = null }) {
  const stepIds = ALL_STEPS.map(step => step.id)
  const stopIdx = stopValue ? stepIds.indexOf(stopValue) : -1
  const resumeIdx = resumeStep ? stepIds.indexOf(resumeStep) : -1

  function _reaches(stepName) {
    const idx = stepIds.indexOf(stepName)
    const reaches = !stopValue || stopIdx >= idx
    const startsBefore = resumeStep == null || resumeIdx <= idx
    return reaches && startsBefore
  }

  const catalog = useProviderCatalogStore()
  catalog.loadCatalog()

  const storyboard = catalog.selectedProvider('storyboard')
  const animator = catalog.selectedProvider('animator')

  if (storyboard?.kind === 'extension' && _reaches('storyboard')) {
    _activateProviderTab(storyboard.id)
  }
  if (animator?.kind === 'extension' && _reaches('assets')) {
    _activateProviderTab(animator.id)
  }
}

export function useProviderTabs() {
  return {
    pendingProviderUrl: readonly(pendingProviderUrl),
    openPendingProvider,
    maybeOpenProviderLoadingTab,
    _activateProviderTab,
    _openInProviderTab,
  }
}
