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
    return { extensions: {} }
  }
}

function extensionEntries(health) {
  // Step 16.1: keys are canonical provider ids under `extensions`.
  const map = health?.extensions || {}
  return Object.entries(map).map(([id, info]) => ({
    id,
    connected: Boolean(info?.connected),
    label: info?.label || id,
  }))
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
 *   1. Check Chromium extension health for every registered extension provider
 *   2. For each disconnected extension, activate its tab to wake it
 *   3. Re-check after a short grace window
 *   4. Ask the extensions to refocus the ScriptToScene Studio tab
 *
 * No provider id is hard-coded (step 16.1).
 */
async function runBoot() {
  if (booted.value || booting.value) return
  booting.value = true
  const activity = useActivityFeed()

  try {
    let health = await fetchHealth()
    let entries = extensionEntries(health)
    const targets = entries.filter(e => !e.connected).map(e => e.id)

    if (targets.length === 0) {
      const labels = entries.map(e => e.label).join(' + ') || 'none'
      activity.push(
        entries.length ? `Extensions ready (${labels})` : 'No browser extensions registered',
        entries.length ? 'success' : 'info',
        { source: 'boot' },
      )
    } else {
      activity.push(`Waking ${targets.join(' + ')} tab(s)...`, 'info', { source: 'boot' })
      for (const target of targets) {
        await activateTab(target)
      }
      await sleep(1500)
      health = await fetchHealth()
      entries = extensionEntries(health)

      const stillDown = entries.filter(e => !e.connected)
      if (stillDown.length === 0) {
        const labels = entries.map(e => e.label).join(' + ')
        activity.push(`Extensions ready (${labels})`, 'success', { source: 'boot' })
      } else {
        activity.push(
          `Extensions offline: ${stillDown.map(e => e.label).join(', ')}`,
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
