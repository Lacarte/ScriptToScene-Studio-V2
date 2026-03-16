/**
 * Play a completion sound when pipeline, export, or asset download finishes.
 * Respects the 'sts-sound-enabled' setting.
 */

let audioEl = null

export function useDoneSound() {
  function play() {
    // Check setting — default to enabled
    const enabled = localStorage.getItem('sts-sound-enabled')
    if (enabled === 'false') return

    try {
      if (!audioEl) {
        audioEl = new Audio(`${import.meta.env.BASE_URL}sounds/done.mp3`)
        audioEl.volume = 0.5
      }
      audioEl.currentTime = 0
      audioEl.play().catch(() => {})
    } catch {
      // Audio not available
    }
  }

  return { play }
}
