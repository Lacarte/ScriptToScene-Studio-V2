import { ref, readonly } from 'vue'
import { api } from '@/shared/api/client.js'
import { ALL_STEPS } from '../constants/steps.js'

const pendingProviderUrl = ref(null)

async function _activateProviderTab(target) {
  try {
    await api.post('/api/chromium/activate-tab', { body: { target } })
    pendingProviderUrl.value = null
  } catch (e) {
    const msg = e.message || ''
    // Gemini is always open — the STS Gemini extension handles the connection
    if (target === 'gemini') {
      pendingProviderUrl.value = null
      return
    }
    if (msg.includes('404')) {
      pendingProviderUrl.value = `No ${target} tab found in Chromium \u2014 open it manually`
    } else {
      pendingProviderUrl.value = 'Chromium not running \u2014 launch it via start-dev'
    }
    console.warn('[STS] Tab activate failed:', msg)
  }
}

function _openInProviderTab(url) {
  const target = url.includes('gemini.google.com') ? 'gemini' : 'grok'
  _activateProviderTab(target)
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

  const storyboardProvider = localStorage.getItem('sts-storyboard-provider') || 'gemini'
  if (storyboardProvider === 'gemini' && _reaches('storyboard')) {
    _activateProviderTab('gemini')
  } else if (_reaches('assets')) {
    _activateProviderTab('grok')
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
