/**
 * Play a completion sound when pipeline, export, or asset download finishes.
 * Respects the 'sts-sound-enabled' setting.
 */

let audioEl = null
let tickEl = null

export function useDoneSound() {
  function _isEnabled() {
    return localStorage.getItem('sts-sound-enabled') !== 'false'
  }

  /** Full pipeline completion sound (louder). */
  function play() {
    if (!_isEnabled()) return
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

  /** Per-scene completion tick (softer, non-blocking). */
  function playTick() {
    if (!_isEnabled()) return
    try {
      if (!tickEl) {
        tickEl = new Audio(`${import.meta.env.BASE_URL}sounds/done.mp3`)
        tickEl.volume = 0.15
      }
      tickEl.currentTime = 0
      tickEl.play().catch(() => {})
    } catch {
      // Audio not available
    }
  }

  return { play, playTick }
}
