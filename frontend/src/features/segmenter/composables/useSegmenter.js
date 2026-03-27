import { ref, readonly, computed } from 'vue'
import { api } from '@/shared/api/client.js'
import { useAudioPlayback } from '@/shared/composables/useAudioPlayback.js'

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

/* Alignment history (for alignment picker) */
const alignmentHistory = ref([])

let historyLoaded = false

export function useSegmenter() {
  /* ── Audio (shared composable) ── */
  const audio = useAudioPlayback({
    label: 'Segmenter',
    getAudioEndpoint: () => {
      const sf = sourceFolder.value || result.value?.metadata?.source_folder
      return sf ? `/api/scenes/audio/${encodeURIComponent(sf)}` : null
    },
    findActiveIdx: (t) => {
      const segs = result.value?.segments
      if (!segs) return -1
      for (let i = 0; i < segs.length; i++) {
        if (t >= segs[i].start && t < segs[i].end) return i
      }
      return -1
    },
  })

  /* ── Alignment source ── */

  function setAlignment(data) {
    alignment.value = data.alignment || []
    transcript.value = data.transcript || ''
    sourceFolder.value = data.folder || ''
    projectId.value = data.project_id || ''
    style.value = data.style || ''
    aspectRatio.value = data.aspect_ratio || ''
    alignmentSource.value = data.source_file || data.folder || 'Current result'
    audio.stopAudio()
    audio.audioUrl.value = data.folder && data.source_file
      ? `/output/alignments/${data.folder}/${data.source_file}`
      : null
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

  function playSegment(seg) {
    audio.playFrom(seg.start)
  }

  function updateActiveSegment(time) {
    audio.seekTo(time)
  }

  function setPlaying(val) {
    audio.isPlaying.value = val
  }

  function setDuration(val) {
    audio.duration.value = val
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

    // Audio (shared composable)
    audioUrl: audio.audioUrl,
    isPlaying: audio.isPlaying,
    currentTime: audio.currentTime,
    duration: audio.duration,
    activeSegmentIdx: audio.activeIdx,

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
    loadAudio: audio.loadAudio,
    togglePlay: audio.togglePlay,
    playSegment,
    seekTo: audio.seekTo,
    stopAudio: audio.stopAudio,
    updateActiveSegment,
    setPlaying,
    setDuration,
    copyJSON,
    downloadJSON,
  }
}
