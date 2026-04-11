import { ref } from 'vue'
import { api } from '@/shared/api/client.js'
import { useActivityFeed } from '@/shared/composables/useActivityFeed.js'

const booted = ref(false)
const booting = ref(false)

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function fetchHealth() {
  try {
    return await api.get('/api/chromium/health')
  } catch {
    return { gemini: { connected: false }, grok: { connected: false } }
  }
}

async function activateTab(target) {
  try {
    await api.post('/api/chromium/activate-tab', { body: { target } })
    return true
  } catch {
    return false
  }
}

async function focusStudio() {
  try {
    return await api.post('/api/chromium/focus-studio', { body: {} })
  } catch {
    return null
  }
}

/**
 * Startup boot sequence:
 *   1. Check Chromium extension health (Gemini + Grok)
 *   2. For each disconnected extension, activate its tab to wake it
 *   3. Re-check after a short grace window
 *   4. Ask the extensions to refocus the ScriptToScene Studio tab
 */
async function runBoot() {
  if (booted.value || booting.value) return
  booting.value = true
  const activity = useActivityFeed()

  try {
    let health = await fetchHealth()
    const targets = []
    if (!health.gemini?.connected) targets.push('gemini')
    if (!health.grok?.connected) targets.push('grok')

    if (targets.length === 0) {
      activity.push('Extensions ready (Gemini + Grok)', 'success', { source: 'boot' })
    } else {
      activity.push(`Waking ${targets.join(' + ')} tab(s)...`, 'info', { source: 'boot' })
      for (const target of targets) {
        await activateTab(target)
      }
      await sleep(1500)
      health = await fetchHealth()

      const stillDown = []
      if (!health.gemini?.connected) stillDown.push('gemini')
      if (!health.grok?.connected) stillDown.push('grok')

      if (stillDown.length === 0) {
        activity.push('Extensions ready (Gemini + Grok)', 'success', { source: 'boot' })
      } else {
        activity.push(
          `Extensions offline: ${stillDown.join(', ')}`,
          'warning',
          { source: 'boot' },
        )
      }
    }

    // Bring the Studio tab back into focus regardless of health outcome
    await focusStudio()
  } finally {
    booting.value = false
    booted.value = true
  }
}

export function useStartupBoot() {
  return {
    booted,
    booting,
    runBoot,
  }
}
