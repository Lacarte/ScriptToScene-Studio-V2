import { ref, readonly, onScopeDispose } from 'vue'

const registry = {}
const playingSource = ref(null)

function syncIndicator() {
  let found = null
  for (const [label, el] of Object.entries(registry)) {
    if (el && !el.paused) { found = label; break }
  }
  playingSource.value = found
}

function register(label, audioEl) {
  if (!audioEl) return
  // Clean up previous element for this label
  if (registry[label] && registry[label] !== audioEl) {
    delete registry[label]
  }
  registry[label] = audioEl
  if (!audioEl.__stsExclusiveBound) {
    audioEl.__stsExclusiveBound = true
    audioEl.addEventListener('play', () => {
      for (const [, otherEl] of Object.entries(registry)) {
        if (!otherEl || otherEl === audioEl) continue
        if (!otherEl.paused) {
          otherEl.pause()
          otherEl.currentTime = 0
        }
      }
      syncIndicator()
    })
    audioEl.addEventListener('pause', syncIndicator)
    audioEl.addEventListener('ended', syncIndicator)
    audioEl.addEventListener('error', syncIndicator)
  }
  syncIndicator()

  // Auto-unregister when the calling component's scope is disposed
  try {
    onScopeDispose(() => {
      if (registry[label] === audioEl) {
        delete registry[label]
        syncIndicator()
      }
    })
  } catch {
    // Called outside a setup scope — manual unregister required
  }
}

function unregister(label) {
  delete registry[label]
  syncIndicator()
}

function stopAll() {
  const stopped = []
  for (const [label, el] of Object.entries(registry)) {
    if (el && !el.paused) {
      el.pause()
      el.currentTime = 0
      stopped.push(label)
    }
  }
  syncIndicator()
  return stopped
}

export function useAudioRegistry() {
  return {
    playingSource: readonly(playingSource),
    register,
    unregister,
    stopAll,
  }
}
