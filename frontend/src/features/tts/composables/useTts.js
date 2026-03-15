import { ref, readonly, computed } from 'vue'
import { api } from '@/shared/api/client.js'
import { useToast } from '@/shared/composables/useToast.js'
import { timeAgo, fmtTime } from '@/shared/utils/format.js'

// ── Constants (extracted to tts/data/voiceData.js) ──
export {
  LANG_NAMES, LANG_SHORT, LANG_SHORT_COMPACT, LANG_ORDER,
  VOICE_META, TOP_PICKS, BLEND_PRESETS,
} from '../data/voiceData.js'
import { VOICE_META, LANG_ORDER, BLEND_PRESETS } from '../data/voiceData.js'
import { RANDOM_STORIES } from '@/shared/data/stories.js'

// ── Singleton state ──

const modelReady = ref(false)
const voices = ref([])
const selectedVoice = ref(localStorage.getItem('sts-tts-voice') || 'af_heart')
const selectedLang = ref(localStorage.getItem('sts-tts-lang') || 'top-picks')
const blendMode = ref(localStorage.getItem('sts-tts-blend') === 'true')
const blendVoiceA = ref(localStorage.getItem('sts-tts-blendA') || 'af_heart')
const blendVoiceB = ref(localStorage.getItem('sts-tts-blendB') || 'am_adam')
const blendRatio = ref(parseInt(localStorage.getItem('sts-tts-blendRatio') || '50'))
const blendMethod = ref(localStorage.getItem('sts-tts-blendMethod') || 'slerp')
const genMode = ref(localStorage.getItem('sts-tts-genMode') || 'generate')
const speed = ref(parseFloat(localStorage.getItem('sts-tts-speed') || '1.0'))
const prompt = ref(localStorage.getItem('sts-tts-prompt') || '')

const initializing = ref(false)
const isGenerating = ref(false)
const currentJobId = ref(null)
const progressText = ref('')

const nowPlaying = ref(null)
const audioSrc = ref('')

const history = ref([])

const multiVoiceMode = ref(false)
const mvSegments = ref([])

// Internal handles (not exposed as readonly)
let chunkEventSource = null
let downloadEventSource = null
let streamAbortController = null
let streamAudioCtx = null
let lastStoryIdx = -1

// ── Computed ──

const voiceSummary = computed(() => {
  if (blendMode.value) {
    const mA = VOICE_META[blendVoiceA.value] || {}
    const mB = VOICE_META[blendVoiceB.value] || {}
    return `${mA.name || blendVoiceA.value} + ${mB.name || blendVoiceB.value} (${blendRatio.value}%)`
  }
  const m = VOICE_META[selectedVoice.value] || {}
  return m.name || selectedVoice.value
})

const voiceSummaryLabel = computed(() => blendMode.value ? 'Voice Blend' : 'Voice')

const wordCount = computed(() => {
  const text = prompt.value.trim()
  return text ? text.split(/\s+/).length : 0
})

const tokenCount = computed(() => Math.round(wordCount.value * 1.3))

// ── Helpers ──

function buildVoiceGroups() {
  const groups = {}
  const voiceList = voices.value.length ? voices.value : Object.keys(VOICE_META)
  voiceList.forEach(v => {
    const meta = VOICE_META[v] || { g: 'm', hue: '#AAB8CC', lang: 'en-us' }
    const lang = meta.lang || 'en-us'
    if (!groups[lang]) groups[lang] = []
    groups[lang].push(v)
  })
  return groups
}

function sortedLangs(groups) {
  return Object.keys(groups).sort((a, b) => {
    const ia = LANG_ORDER.indexOf(a)
    const ib = LANG_ORDER.indexOf(b)
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
  })
}

function persist(key, value) {
  localStorage.setItem(key, String(value))
}

// ── Actions ──

async function checkModel() {
  try {
    const d = await api.get('/api/tts/model-status/kokoro')
    modelReady.value = d.cached
  } catch (e) {
    console.warn('[TTS] Model status check failed:', e.message)
    // server not ready
  }
}

async function downloadModel() {
  return new Promise((resolve, reject) => {
    const es = new EventSource('/api/tts/download-model/kokoro')
    downloadEventSource = es

    es.onmessage = (e) => {
      const d = JSON.parse(e.data)
      if (d.phase === 'downloading') {
        progressText.value = `Downloading ${d.file} ${d.progress}% ${d.speed}`
      } else if (d.phase === 'loading') {
        progressText.value = 'Loading model into memory...'
      } else if (d.phase === 'ready') {
        es.close()
        modelReady.value = true
        downloadEventSource = null
        progressText.value = ''
        loadVoices()
        resolve()
      } else if (d.phase === 'error') {
        es.close()
        downloadEventSource = null
        reject(new Error(d.message))
      }
    }
    es.onerror = () => {
      es.close()
      downloadEventSource = null
      reject(new Error('Connection lost'))
    }
  })
}

async function loadVoices() {
  try {
    const data = await api.get('/api/tts/voices')
    voices.value = data
  } catch (e) {
    console.warn('[TTS] Failed to load voices:', e.message)
    // use defaults from VOICE_META
  }
}

function selectVoice(v) {
  selectedVoice.value = v
  persist('sts-tts-voice', v)
}

function selectLang(lang) {
  selectedLang.value = lang
  persist('sts-tts-lang', lang)
}

function setBlendMode(on) {
  blendMode.value = on
  persist('sts-tts-blend', on)
}

function setBlendVoiceA(v) {
  blendVoiceA.value = v
  persist('sts-tts-blendA', v)
}

function setBlendVoiceB(v) {
  blendVoiceB.value = v
  persist('sts-tts-blendB', v)
}

function setBlendRatio(val) {
  blendRatio.value = parseInt(val)
  persist('sts-tts-blendRatio', val)
}

function setBlendMethod(m) {
  blendMethod.value = m
  persist('sts-tts-blendMethod', m)
}

function applyBlendPreset(idx) {
  const p = BLEND_PRESETS[idx]
  if (!p) return
  blendVoiceA.value = p.a
  blendVoiceB.value = p.b
  blendRatio.value = p.ratio
  persist('sts-tts-blendA', p.a)
  persist('sts-tts-blendB', p.b)
  persist('sts-tts-blendRatio', p.ratio)
  return `${VOICE_META[p.a]?.name || p.a} + ${VOICE_META[p.b]?.name || p.b}`
}

function randomBlend() {
  const keys = Object.keys(VOICE_META)
  const females = keys.filter(k => VOICE_META[k].g === 'f')
  const males = keys.filter(k => VOICE_META[k].g === 'm')
  const pick = arr => arr[Math.floor(Math.random() * arr.length)]
  const a = pick(females)
  let b = pick(males)
  while (b === a) b = pick(males)
  const ratio = Math.floor(Math.random() * 81) + 10
  blendVoiceA.value = a
  blendVoiceB.value = b
  blendRatio.value = ratio
  blendMethod.value = 'slerp'
  persist('sts-tts-blendA', a)
  persist('sts-tts-blendB', b)
  persist('sts-tts-blendRatio', ratio)
  persist('sts-tts-blendMethod', 'slerp')
  return `${VOICE_META[a].name} + ${VOICE_META[b].name} @ ${ratio}%`
}

function setGenMode(mode) {
  genMode.value = mode
  persist('sts-tts-genMode', mode)
}

function setSpeed(val) {
  speed.value = parseFloat(val)
  persist('sts-tts-speed', val)
}

function setPrompt(text) {
  prompt.value = text
  persist('sts-tts-prompt', text)
}

async function normalize() {
  const text = prompt.value.trim()
  if (!text) return null
  try {
    const d = await api.post('/api/tts/normalize', { body: { text } })
    if (d.normalized) {
      prompt.value = d.normalized
      persist('sts-tts-prompt', d.normalized)
      return d.normalized
    }
  } catch {
    throw new Error('Normalization failed')
  }
  return null
}

function copyPromptPlain() {
  const text = prompt.value.trim()
  if (!text) return Promise.reject(new Error('Nothing to copy'))
  const plain = text.replace(/[\[\]]/g, '').replace(/\n{2,}/g, ' ').replace(/\s+/g, ' ').trim()
  return navigator.clipboard.writeText(plain)
}

function randomStory() {
  let idx
  do {
    idx = Math.floor(Math.random() * RANDOM_STORIES.length)
  } while (idx === lastStoryIdx && RANDOM_STORIES.length > 1)
  lastStoryIdx = idx
  prompt.value = RANDOM_STORIES[idx]
  persist('sts-tts-prompt', prompt.value)
  return prompt.value
}

// ── Generate ──

function buildPayload() {
  const payload = {
    model: 'kokoro',
    voice: selectedVoice.value,
    prompt: prompt.value.trim(),
    speed: speed.value,
    max_silence_ms: 500,
    skip_clean: false,
  }
  if (blendMode.value) {
    payload.blend = {
      voice_a: blendVoiceA.value,
      voice_b: blendVoiceB.value,
      ratio: (100 - blendRatio.value) / 100,
      method: blendMethod.value,
    }
  }
  return payload
}

async function generate() {
  const text = prompt.value.trim()
  if (!text) throw new Error('Enter some text first')
  if (text.length > 50000) throw new Error('Text is too long (max 50,000 characters)')
  if (speed.value < 0.5 || speed.value > 2.0) throw new Error('Speed must be between 0.5 and 2.0')
  if (isGenerating.value) return

  isGenerating.value = true
  progressText.value = ''

  try {
    if (!modelReady.value) {
      progressText.value = 'Downloading model...'
      await downloadModel()
    }

    // Normalize
    let genPrompt = text
    try {
      progressText.value = 'Normalizing text...'
      const nd = await api.post('/api/tts/normalize', { body: { text } })
      if (nd.normalized) genPrompt = nd.normalized
    } catch (e) {
      console.warn('[TTS] Normalization failed, using original:', e.message)
      // use original
    }

    const payload = buildPayload()
    payload.prompt = genPrompt

    progressText.value = 'Generating audio...'
    const d = await api.post('/api/tts/generate', { body: payload })

    if (d.job_id) {
      currentJobId.value = d.job_id
      await streamChunkedProgress(d.job_id)
    } else if (d.error) {
      throw new Error(d.error)
    } else {
      progressText.value = 'Done!'
      playAudio(d)
      await loadHistory()
    }
  } finally {
    isGenerating.value = false
    currentJobId.value = null
    progressText.value = ''
  }
}

async function streamChunkedProgress(jobId) {
  return new Promise((resolve, reject) => {
    const es = new EventSource(`/api/tts/generate-progress/${jobId}`)
    chunkEventSource = es

    es.onmessage = (e) => {
      const d = JSON.parse(e.data)
      if (d.phase === 'generating') {
        progressText.value = `Generating chunk ${d.chunk}/${d.total}...`
      } else if (d.phase === 'concatenating') {
        progressText.value = 'Concatenating audio...'
      } else if (d.phase === 'normalizing') {
        progressText.value = 'Normalizing volume...'
      } else if (d.phase === 'done') {
        es.close()
        chunkEventSource = null
        progressText.value = 'Done!'
        if (d.metadata) playAudio(d.metadata)
        loadHistory()
        resolve()
      } else if (d.phase === 'error') {
        es.close()
        chunkEventSource = null
        reject(new Error(d.message || 'Generation failed'))
      } else if (d.phase === 'aborted') {
        es.close()
        chunkEventSource = null
        resolve()
      }
    }
    es.onerror = () => {
      es.close()
      chunkEventSource = null
      reject(new Error('Connection lost'))
    }
  })
}

async function stream() {
  const text = prompt.value.trim()
  if (!text) throw new Error('Enter some text first')
  if (isGenerating.value) return

  isGenerating.value = true
  progressText.value = ''

  try {
    if (!modelReady.value) {
      progressText.value = 'Downloading model...'
      await downloadModel()
    }

    const payload = buildPayload()
    progressText.value = 'Streaming...'
    const ctrl = new AbortController()
    streamAbortController = ctrl

    const resp = await fetch('/api/tts/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: ctrl.signal,
    })

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 })
    streamAudioCtx = audioCtx
    let nextPlayTime = audioCtx.currentTime
    let buffer = ''
    let chunks = 0

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const d = JSON.parse(line.slice(6))

        if (d.phase === 'audio') {
          chunks++
          const pcm = Uint8Array.from(atob(d.samples), c => c.charCodeAt(0))
          const float32 = new Float32Array(pcm.buffer)
          const audioBuf = audioCtx.createBuffer(1, float32.length, d.sample_rate)
          audioBuf.getChannelData(0).set(float32)
          const source = audioCtx.createBufferSource()
          source.buffer = audioBuf
          source.connect(audioCtx.destination)
          if (nextPlayTime < audioCtx.currentTime) nextPlayTime = audioCtx.currentTime
          source.start(nextPlayTime)
          nextPlayTime += audioBuf.duration
          progressText.value = `Streaming chunk ${chunks}...`
        } else if (d.phase === 'done') {
          progressText.value = 'Stream complete'
        } else if (d.phase === 'error') {
          throw new Error(d.message)
        }
      }
    }

    const remaining = nextPlayTime - audioCtx.currentTime
    if (remaining > 0) {
      await new Promise(r => setTimeout(r, remaining * 1000 + 200))
    }
    audioCtx.close()
    streamAudioCtx = null
  } catch (e) {
    if (e.name !== 'AbortError') throw e
  } finally {
    isGenerating.value = false
    streamAbortController = null
    progressText.value = ''
  }
}

async function abort() {
  if (currentJobId.value) {
    try {
      await fetch(`/api/tts/generate-abort/${currentJobId.value}`, { method: 'POST' })
    } catch (e) {
      console.warn('[TTS] Abort request failed:', e.message)
      // best effort
    }
  }
  if (chunkEventSource) {
    chunkEventSource.close()
    chunkEventSource = null
  }
  if (downloadEventSource) {
    downloadEventSource.close()
    downloadEventSource = null
  }
  if (streamAbortController) {
    streamAbortController.abort()
    streamAbortController = null
  }
  if (streamAudioCtx) {
    try { streamAudioCtx.close() } catch {}
    streamAudioCtx = null
  }
  isGenerating.value = false
  currentJobId.value = null
  progressText.value = ''
}

async function handleAction() {
  if (isGenerating.value) return
  if (multiVoiceMode.value && genMode.value === 'generate') {
    return multiVoiceGenerate()
  } else if (genMode.value === 'listen') {
    return stream()
  } else {
    return generate()
  }
}

// ── Audio Playback ──

function playAudio(meta) {
  if (!meta || !meta.filename) return
  nowPlaying.value = meta
  audioSrc.value = `/output/tts/${meta.folder}/${meta.filename}`
}

// ── History ──

async function loadHistory() {
  try {
    const data = await api.get('/api/tts/generation')
    history.value = data
  } catch (e) {
    console.warn('[TTS] Failed to load history:', e.message)
    // no-op
  }
}

async function deleteItem(filename) {
  await api.delete(`/api/tts/generation/${filename}`)
  if (nowPlaying.value?.filename === filename) {
    nowPlaying.value = null
    audioSrc.value = ''
  }
  await loadHistory()
}

async function deleteAll() {
  if (isGenerating.value) throw new Error('Wait for generation to finish')
  const d = await api.delete('/api/tts/generation')
  nowPlaying.value = null
  audioSrc.value = ''
  await loadHistory()
  return d.count
}

// ── Multi-Voice ──

function setVoiceMode(mode) {
  multiVoiceMode.value = mode === 'multi'
}

function addMvSegment(text = '', voice = 'af_heart', role = 'narrator') {
  mvSegments.value.push({ text, voice, role })
}

function removeMvSegment(idx) {
  mvSegments.value.splice(idx, 1)
}

function updateMvSegment(idx, field, value) {
  if (mvSegments.value[idx]) {
    mvSegments.value[idx][field] = value
  }
}

function autoDetectRoles() {
  const text = prompt.value.trim()
  if (!text) throw new Error('Enter text in the prompt first')

  mvSegments.value = []

  const bracketBlocks = text.match(/\[([^\[\]]+)\]/g)
  let blocks
  if (bracketBlocks && bracketBlocks.length >= 2) {
    blocks = bracketBlocks.map(b => b.replace(/^\[|\]$/g, '').trim()).filter(Boolean)
  } else {
    blocks = text.split(/(?<=[.!?])\s+/).filter(s => s.trim())
  }

  const narratorVoice = selectedVoice.value
  const dialogueVoice = narratorVoice.startsWith('af_') ? 'am_adam'
    : narratorVoice.startsWith('am_') ? 'af_heart'
    : narratorVoice.startsWith('bf_') ? 'bm_george'
    : narratorVoice.startsWith('bm_') ? 'bf_emma'
    : 'am_adam'

  for (const block of blocks) {
    const hasQuotes = /[""\u201C\u201D]/.test(block)
    mvSegments.value.push({
      text: block,
      voice: hasQuotes ? dialogueVoice : narratorVoice,
      role: hasQuotes ? 'dialogue' : 'narrator',
    })
  }

  return mvSegments.value.length
}

async function multiVoiceGenerate() {
  if (!mvSegments.value.length) throw new Error('Add segments first (use Auto-detect or + Add)')

  const validSegments = mvSegments.value.filter(s => s.text.trim())
  if (!validSegments.length) throw new Error('All segments are empty')

  isGenerating.value = true
  progressText.value = ''

  try {
    if (!modelReady.value) {
      progressText.value = 'Downloading model...'
      await downloadModel()
    }

    const promptText = prompt.value.trim() || validSegments.map(s => s.text).join(' ')

    progressText.value = 'Starting multi-voice generation...'
    const d = await api.post('/api/tts/generate-multivoice', {
      body: {
        segments: validSegments.map(s => ({ text: s.text, voice: s.voice, speed: speed.value })),
        gap_ms: 80,
        prompt: promptText,
        speed: speed.value,
      },
    })

    if (d.job_id) {
      currentJobId.value = d.job_id
      await streamChunkedProgress(d.job_id)
    } else if (d.error) {
      throw new Error(d.error)
    }
  } finally {
    isGenerating.value = false
    currentJobId.value = null
    progressText.value = ''
  }
}

// ── Singleton composable ──

let initialized = false

export function useTts() {
  if (!initialized) {
    initialized = true
    initializing.value = true
    Promise.all([checkModel(), loadVoices(), loadHistory()])
      .finally(() => { initializing.value = false })
  }

  return {
    // State (readonly)
    initializing: readonly(initializing),
    modelReady: readonly(modelReady),
    voices: readonly(voices),
    selectedVoice: readonly(selectedVoice),
    selectedLang: readonly(selectedLang),
    blendMode: readonly(blendMode),
    blendVoiceA: readonly(blendVoiceA),
    blendVoiceB: readonly(blendVoiceB),
    blendRatio: readonly(blendRatio),
    blendMethod: readonly(blendMethod),
    genMode: readonly(genMode),
    speed: readonly(speed),
    prompt: readonly(prompt),
    isGenerating: readonly(isGenerating),
    currentJobId: readonly(currentJobId),
    progressText: readonly(progressText),
    nowPlaying: readonly(nowPlaying),
    audioSrc: readonly(audioSrc),
    history: readonly(history),
    multiVoiceMode: readonly(multiVoiceMode),
    mvSegments: readonly(mvSegments),

    // Computed
    voiceSummary,
    voiceSummaryLabel,
    wordCount,
    tokenCount,

    // Actions
    checkModel,
    downloadModel,
    loadVoices,
    selectVoice,
    selectLang,
    setBlendMode,
    setBlendVoiceA,
    setBlendVoiceB,
    setBlendRatio,
    setBlendMethod,
    applyBlendPreset,
    randomBlend,
    setGenMode,
    setSpeed,
    setPrompt,
    normalize,
    copyPromptPlain,
    randomStory,
    generate,
    stream,
    abort,
    handleAction,
    playAudio,
    loadHistory,
    deleteItem,
    deleteAll,
    setVoiceMode,
    addMvSegment,
    removeMvSegment,
    updateMvSegment,
    autoDetectRoles,
    multiVoiceGenerate,

    // Helpers
    buildVoiceGroups,
    sortedLangs,
    timeAgo,
    fmtTime,

    // Cleanup
    dispose() { abort() },
  }
}
