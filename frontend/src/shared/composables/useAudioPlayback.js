/**
 * Shared audio playback composable — used by scenes, segmenter, and timing.
 *
 * Provides: audioUrl, isPlaying, currentTime, activeIdx,
 *           loadAudio, togglePlay, seekTo, playFrom, stopAudio
 *
 * @param {Object} options
 * @param {string} options.label - Registry label (e.g. 'Scenes', 'Segmenter')
 * @param {Function} options.getAudioEndpoint - returns the API url for loading audio
 * @param {Function} options.findActiveIdx - (time) => index of active segment/scene
 * @param {Function} [options.onRegister] - called with Audio element after creation
 */

import { ref } from 'vue'
import { api } from '@/shared/api/client.js'

export function useAudioPlayback({ label, getAudioEndpoint, findActiveIdx, onRegister }) {
  const audioUrl = ref(null)
  const isPlaying = ref(false)
  const currentTime = ref(0)
  const duration = ref(0)
  const activeIdx = ref(-1)

  let audioEl = null
  let rafId = null

  function _startRaf() {
    _stopRaf()
    const tick = () => {
      if (audioEl) {
        currentTime.value = audioEl.currentTime
        activeIdx.value = findActiveIdx ? findActiveIdx(audioEl.currentTime) : -1
      }
      rafId = requestAnimationFrame(tick)
    }
    rafId = requestAnimationFrame(tick)
  }

  function _stopRaf() {
    if (rafId) { cancelAnimationFrame(rafId); rafId = null }
  }

  async function loadAudio() {
    stopAudio()
    const endpoint = getAudioEndpoint()
    if (!endpoint) { audioUrl.value = null; return }
    try {
      const res = await api.get(endpoint)
      if (res?.url) {
        audioUrl.value = res.url
        audioEl = new Audio(res.url)
        audioEl.onended = () => _reset()
        audioEl.onerror = () => { audioUrl.value = null }
        audioEl.onloadedmetadata = () => { duration.value = audioEl.duration }
        if (onRegister) onRegister(audioEl)
      }
    } catch (e) {
      console.warn(`[${label}] Failed to load audio:`, e.message)
      audioUrl.value = null
    }
  }

  function togglePlay() {
    if (!audioEl) return
    if (audioEl.paused) {
      if (audioEl.duration && audioEl.currentTime >= audioEl.duration - 0.05) {
        audioEl.currentTime = 0
      }
      audioEl.play().then(() => {
        isPlaying.value = true
        _startRaf()
      }).catch(() => {})
    } else {
      audioEl.pause()
      isPlaying.value = false
      _stopRaf()
    }
  }

  function seekTo(time) {
    if (!audioEl) return
    audioEl.currentTime = time
    currentTime.value = time
    activeIdx.value = findActiveIdx ? findActiveIdx(time) : -1
  }

  function playFrom(time) {
    if (!audioEl) return
    audioEl.currentTime = time
    currentTime.value = time
    activeIdx.value = findActiveIdx ? findActiveIdx(time) : -1
    audioEl.play().then(() => {
      isPlaying.value = true
      _startRaf()
    }).catch(() => {})
  }

  function stopAudio() {
    if (audioEl) {
      audioEl.pause()
      audioEl.onended = null
      audioEl.onerror = null
      audioEl.onloadedmetadata = null
      audioEl.src = ''
      audioEl = null
    }
    _stopRaf()
    audioUrl.value = null
    isPlaying.value = false
    currentTime.value = 0
    duration.value = 0
    activeIdx.value = -1
  }

  function _reset() {
    if (audioEl) {
      audioEl.pause()
      audioEl.currentTime = 0
    }
    isPlaying.value = false
    currentTime.value = 0
    activeIdx.value = -1
    _stopRaf()
  }

  function getAudioEl() { return audioEl }

  return {
    audioUrl, isPlaying, currentTime, duration, activeIdx,
    loadAudio, togglePlay, seekTo, playFrom, stopAudio,
    getAudioEl,
  }
}
