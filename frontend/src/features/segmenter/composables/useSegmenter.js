import { ref, readonly, computed } from 'vue'
import { api } from '@/shared/api/client.js'

/* ── Singleton state ── */
const alignment = ref([])
const transcript = ref('')
const sourceFolder = ref('')
const projectId = ref('')
const style = ref('')
const aspectRatio = ref('')
const alignmentSource = ref('')   // label for UI

const config = ref({
  target_min: 1.5,
  target_max: 3.0,
  hard_max: 4.0,
  gap_filler: 0.3,
})

const result = ref(null)          // { metadata, config, segments, stats }
const isRunning = ref(false)
const history = ref([])

/* Audio playback */
const audioUrl = ref('')
const isPlaying = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const activeSegmentIdx = ref(-1)

/* Alignment history (for alignment picker) */
const alignmentHistory = ref([])

let historyLoaded = false

export function useSegmenter() {
  /* ── Alignment source ── */

  function setAlignment(data) {
    alignment.value = data.alignment || []
    transcript.value = data.transcript || ''
    sourceFolder.value = data.folder || ''
    projectId.value = data.project_id || ''
    style.value = data.style || ''
    aspectRatio.value = data.aspect_ratio || ''
    alignmentSource.value = data.source_file || data.folder || 'Current result'
    audioUrl.value = data.folder && data.source_file
      ? `/output/alignments/${data.folder}/${data.source_file}`
      : ''
    isPlaying.value = false
    currentTime.value = 0
    duration.value = 0
    activeSegmentIdx.value = -1
  }

  /* ── Config ── */

  function updateConfig(key, value) {
    config.value = { ...config.value, [key]: value }
  }

  function resetConfig() {
    config.value = {
      target_min: 1.5,
      target_max: 3.0,
      hard_max: 4.0,
      gap_filler: 0.3,
    }
  }

  /* ── Run ── */

  async function runSegmenter() {
    if (!alignment.value.length) {
      throw new Error('No alignment data loaded')
    }
    isRunning.value = true
    try {
      const payload = {
        alignment: alignment.value,
        transcript: transcript.value,
        source_folder: sourceFolder.value,
        project_id: projectId.value,
        style: style.value,
        aspect_ratio: aspectRatio.value,
        config: config.value,
        save: true,
      }
      const data = await api.post('/api/segmenter/run', { body: payload })
      result.value = data
      return data
    } finally {
      isRunning.value = false
    }
  }

  /* ── History ── */

  async function loadHistory() {
    try {
      const data = await api.get('/api/segmenter/history')
      history.value = Array.isArray(data) ? data : []
      historyLoaded = true
    } catch (e) {
      console.warn('[Segmenter] Failed to load history:', e.message)
      history.value = []
    }
  }

  async function loadResult(folder) {
    try {
      const data = await api.get(`/api/segmenter/${folder}`)
      result.value = data
      if (data.metadata) {
        sourceFolder.value = data.metadata.source_folder || folder
        projectId.value = data.metadata.project_id || ''
        alignmentSource.value = data.metadata.source_folder || folder
        if (data.metadata.source_folder && data.metadata.source_file) {
          audioUrl.value = `/output/alignments/${data.metadata.source_folder}/${data.metadata.source_file}`
        }
      }
      isPlaying.value = false
      currentTime.value = 0
      duration.value = 0
      activeSegmentIdx.value = -1
      return data
    } catch (err) {
      throw err
    }
  }

  /* ── Alignment history (for alignment picker) ── */

  async function loadAlignmentHistory() {
    try {
      const data = await api.get('/api/alignment/history')
      alignmentHistory.value = Array.isArray(data) ? data : []
    } catch (e) {
      console.warn('[Segmenter] Failed to load alignment history:', e.message)
      alignmentHistory.value = []
    }
  }

  /* ── Audio ── */

  let _audioEl = null
  let _rafId = null

  async function loadAudio() {
    stopAudio()
    const sf = sourceFolder.value || result.value?.metadata?.source_folder
    if (!sf) { audioUrl.value = ''; return }
    try {
      const res = await api.get(`/api/scenes/audio/${encodeURIComponent(sf)}`)
      if (res?.url) {
        audioUrl.value = res.url
        _audioEl = new Audio(res.url)
        _audioEl.onended = () => {
          isPlaying.value = false
          currentTime.value = 0
          activeSegmentIdx.value = -1
          _stopRaf()
        }
        _audioEl.onerror = () => { audioUrl.value = '' }
        _audioEl.onloadedmetadata = () => { duration.value = _audioEl.duration }
      }
    } catch {
      audioUrl.value = ''
    }
  }

  function _startRaf() {
    _stopRaf()
    const tick = () => {
      if (_audioEl) {
        currentTime.value = _audioEl.currentTime
        updateActiveSegment(_audioEl.currentTime)
      }
      _rafId = requestAnimationFrame(tick)
    }
    _rafId = requestAnimationFrame(tick)
  }

  function _stopRaf() {
    if (_rafId) { cancelAnimationFrame(_rafId); _rafId = null }
  }

  function togglePlay() {
    if (!_audioEl) return
    if (_audioEl.paused) {
      if (_audioEl.duration && _audioEl.currentTime >= _audioEl.duration - 0.05) {
        _audioEl.currentTime = 0
        updateActiveSegment(0)
      }
      _audioEl.play().catch(() => {})
      isPlaying.value = true
      _startRaf()
    } else {
      _audioEl.pause()
      isPlaying.value = false
      _stopRaf()
    }
  }

  function playSegment(seg) {
    if (!_audioEl) return
    _audioEl.currentTime = seg.start
    updateActiveSegment(seg.start)
    _audioEl.play().catch(() => {})
    isPlaying.value = true
    _startRaf()
  }

  function seekTo(time) {
    if (!_audioEl) return
    _audioEl.currentTime = time
    updateActiveSegment(time)
    if (_audioEl.paused) {
      _audioEl.play().catch(() => {})
      isPlaying.value = true
      _startRaf()
    }
  }

  function stopAudio() {
    if (_audioEl) {
      _audioEl.pause()
      _audioEl.src = ''
      _audioEl = null
    }
    _stopRaf()
    audioUrl.value = ''
    isPlaying.value = false
    currentTime.value = 0
    activeSegmentIdx.value = -1
  }

  function updateActiveSegment(time) {
    currentTime.value = time
    const segs = result.value?.segments
    if (!segs) {
      activeSegmentIdx.value = -1
      return
    }
    let idx = -1
    for (let i = 0; i < segs.length; i++) {
      if (time >= segs[i].start && time <= segs[i].end) {
        idx = i
        break
      }
    }
    activeSegmentIdx.value = idx
  }

  function setPlaying(val) {
    isPlaying.value = val
  }

  function setDuration(val) {
    duration.value = val
  }

  /* ── Export ── */

  function copyJSON() {
    if (!result.value) return
    const json = JSON.stringify(result.value, null, 2)
    navigator.clipboard.writeText(json)
  }

  function downloadJSON() {
    if (!result.value) return
    const json = JSON.stringify(result.value, null, 2)
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `segments-${projectId.value || 'export'}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  /* ── Computed ── */

  const segments = computed(() => result.value?.segments || [])
  const stats = computed(() => result.value?.stats || null)
  const totalDuration = computed(() => {
    const metadataDuration = result.value?.metadata?.total_duration
    if (metadataDuration && Number.isFinite(metadataDuration)) return metadataDuration
    const segs = segments.value
    if (!segs.length) return 0
    return segs[segs.length - 1].end
  })
  const hasAlignment = computed(() => alignment.value.length > 0)
  const hasResult = computed(() => result.value !== null)

  // Auto-load history on first use
  if (!historyLoaded) {
    loadHistory()
  }

  return {
    // State
    alignment: readonly(alignment),
    transcript: readonly(transcript),
    sourceFolder: readonly(sourceFolder),
    projectId: readonly(projectId),
    alignmentSource: readonly(alignmentSource),
    config: readonly(config),
    result: readonly(result),
    isRunning: readonly(isRunning),
    history: readonly(history),
    alignmentHistory: readonly(alignmentHistory),
    timingHistory: readonly(alignmentHistory),

    // Audio
    audioUrl: readonly(audioUrl),
    isPlaying: readonly(isPlaying),
    currentTime: readonly(currentTime),
    duration: readonly(duration),
    activeSegmentIdx: readonly(activeSegmentIdx),

    // Computed
    segments,
    stats,
    totalDuration,
    hasAlignment,
    hasResult,

    // Actions
    setAlignment,
    updateConfig,
    resetConfig,
    runSegmenter,
    loadHistory,
    loadResult,
    loadAlignmentHistory,
    loadTimingHistory: loadAlignmentHistory,
    loadAudio,
    togglePlay,
    playSegment,
    seekTo,
    stopAudio,
    updateActiveSegment,
    setPlaying,
    setDuration,
    copyJSON,
    downloadJSON,
  }
}
