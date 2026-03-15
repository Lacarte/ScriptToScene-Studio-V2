import { ref, readonly, computed } from 'vue'
import { api } from '@/shared/api/client.js'

/* ── Singleton state ── */
const alignment = ref([])
const transcript = ref('')
const sourceFile = ref('')
const sourceFolder = ref('')
const projectId = ref('')
const isAligning = ref(false)
const results = ref(null)
const history = ref([])

/* Audio playback */
const audioUrl = ref('')
const isPlaying = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const activeWordIdx = ref(-1)

/* TTS picker */
const ttsHistory = ref([])

export function useTiming() {
  /* ── Alignment ── */

  async function runAlignment(audioFile, text) {
    isAligning.value = true
    try {
      const form = new FormData()
      form.append('audio', audioFile)
      form.append('text', text)

      const res = await fetch('/api/timing/align', {
        method: 'POST',
        body: form,
      })

      if (!res.ok) {
        const errText = await res.text().catch(() => res.statusText)
        throw new Error(`POST /api/timing/align → ${res.status}: ${errText}`)
      }

      const data = await res.json()
      results.value = data
      alignment.value = data.alignment || []
      transcript.value = data.transcript || text
      sourceFile.value = data.source_file || audioFile.name
      sourceFolder.value = data.folder || ''
      projectId.value = data.project_id || ''

      // Build audio URL from the returned folder
      if (data.folder && data.source_file) {
        audioUrl.value = `/output/alignments/${data.folder}/${data.source_file}`
      }

      return data
    } finally {
      isAligning.value = false
    }
  }

  /* ── History ── */

  async function loadHistory() {
    try {
      const data = await api.get('/api/timing/history')
      history.value = Array.isArray(data) ? data : []
    } catch (e) {
      console.warn('[Timing] Failed to load history:', e.message)
      history.value = []
    }
  }

  async function loadResult(folder) {
    try {
      const items = history.value
      const item = items.find(h => h.folder === folder)
      if (item) {
        results.value = item
        alignment.value = item.alignment || []
        transcript.value = item.transcript || ''
        sourceFile.value = item.source_file || ''
        sourceFolder.value = item.folder || ''
        projectId.value = item.project_id || ''
        if (item.folder && item.source_file) {
          audioUrl.value = `/output/alignments/${item.folder}/${item.source_file}`
        }
      }
    } catch (e) {
      console.warn('[Timing] Failed to load result:', e.message)
    }
  }

  async function deleteResult(folder) {
    await api.delete(`/api/timing/${folder}`)
    history.value = history.value.filter(h => h.folder !== folder)

    // Clear active if deleted
    if (sourceFolder.value === folder) {
      results.value = null
      alignment.value = []
      transcript.value = ''
      sourceFile.value = ''
      sourceFolder.value = ''
      projectId.value = ''
      audioUrl.value = ''
      activeWordIdx.value = -1
    }
  }

  /* ── TTS picker ── */

  async function loadTtsHistory() {
    try {
      const data = await api.get('/api/tts/generation')
      ttsHistory.value = Array.isArray(data) ? data : []
    } catch (e) {
      console.warn('[Timing] Failed to load TTS history:', e.message)
      ttsHistory.value = []
    }
  }

  /* ── Audio helpers ── */

  function updateActiveWord(time) {
    currentTime.value = time
    const words = alignment.value
    let idx = -1
    for (let i = 0; i < words.length; i++) {
      if (time >= words[i].begin && time <= words[i].end) {
        idx = i
        break
      }
    }
    activeWordIdx.value = idx
  }

  function setPlaying(val) {
    isPlaying.value = val
  }

  function setDuration(val) {
    duration.value = val
  }

  /* ── Computed ── */

  const wordCount = computed(() => alignment.value.length)
  const inferenceTime = computed(() => results.value?.inference_time ?? null)

  return {
    // State
    alignment: readonly(alignment),
    transcript,
    sourceFile: readonly(sourceFile),
    sourceFolder: readonly(sourceFolder),
    projectId: readonly(projectId),
    isAligning: readonly(isAligning),
    results: readonly(results),
    history: readonly(history),

    // Audio
    audioUrl,
    isPlaying: readonly(isPlaying),
    currentTime: readonly(currentTime),
    duration: readonly(duration),
    activeWordIdx: readonly(activeWordIdx),

    // TTS
    ttsHistory: readonly(ttsHistory),

    // Computed
    wordCount,
    inferenceTime,

    // Actions
    runAlignment,
    loadHistory,
    loadResult,
    deleteResult,
    loadTtsHistory,
    updateActiveWord,
    setPlaying,
    setDuration,
  }
}
