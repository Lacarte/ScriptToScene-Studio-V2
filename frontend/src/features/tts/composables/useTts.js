import { ref, readonly, computed } from 'vue'
import { api } from '@/shared/api/client.js'
import { useToast } from '@/shared/composables/useToast.js'

// ── Constants ──

export const LANG_NAMES = {
  'en-us': 'American English', 'en-gb': 'British English', 'ja': 'Japanese',
  'zh': 'Chinese', 'es': 'Spanish', 'fr': 'French', 'hi': 'Hindi',
  'it': 'Italian', 'pt-br': 'Portuguese',
}

export const LANG_SHORT = {
  'en-us': 'English US', 'en-gb': 'English UK', 'ja': 'Japanese',
  'zh': 'Chinese', 'es': 'Spanish', 'fr': 'French', 'hi': 'Hindi',
  'it': 'Italian', 'pt-br': 'Portuguese',
}

export const LANG_SHORT_COMPACT = {
  'en-us': 'US', 'en-gb': 'UK', 'ja': 'JA', 'zh': 'ZH', 'es': 'ES',
  'fr': 'FR', 'hi': 'HI', 'it': 'IT', 'pt-br': 'PT',
}

export const LANG_ORDER = ['en-us', 'en-gb', 'ja', 'zh', 'es', 'fr', 'hi', 'it', 'pt-br']

export const VOICE_META = {
  // American Female — coral/pink
  af_alloy:   { g: 'f', hue: '#FF9B9B', lang: 'en-us', name: 'Alloy',   desc: 'Neutral, versatile' },
  af_aoede:   { g: 'f', hue: '#FFB5B5', lang: 'en-us', name: 'Aoede',   desc: 'Soft, melodic' },
  af_bella:   { g: 'f', hue: '#FF8A8A', lang: 'en-us', name: 'Bella',   desc: 'Energetic, engaging' },
  af_heart:   { g: 'f', hue: '#FF7070', lang: 'en-us', name: 'Heart',   desc: 'Warm, friendly, natural' },
  af_jessica: { g: 'f', hue: '#FFA5A5', lang: 'en-us', name: 'Jessica', desc: 'Bright, conversational' },
  af_kore:    { g: 'f', hue: '#FFCECE', lang: 'en-us', name: 'Kore',    desc: 'Gentle, soothing' },
  af_nicole:  { g: 'f', hue: '#FF8080', lang: 'en-us', name: 'Nicole',  desc: 'Clear, professional' },
  af_nova:    { g: 'f', hue: '#FFD0D0', lang: 'en-us', name: 'Nova',    desc: 'Bright, modern' },
  af_river:   { g: 'f', hue: '#FFB0B0', lang: 'en-us', name: 'River',   desc: 'Calm, flowing' },
  af_sarah:   { g: 'f', hue: '#FF9595', lang: 'en-us', name: 'Sarah',   desc: 'Smooth, balanced' },
  af_sky:     { g: 'f', hue: '#FFBABA', lang: 'en-us', name: 'Sky',     desc: 'Light, airy' },
  // American Male — teal
  am_adam:    { g: 'm', hue: '#6FE3DA', lang: 'en-us', name: 'Adam',    desc: 'Warm, approachable' },
  am_echo:    { g: 'm', hue: '#5ED5CC', lang: 'en-us', name: 'Echo',    desc: 'Resonant, clear' },
  am_eric:    { g: 'm', hue: '#7EEFEA', lang: 'en-us', name: 'Eric',    desc: 'Confident, steady' },
  am_fenrir:  { g: 'm', hue: '#4ECDC4', lang: 'en-us', name: 'Fenrir',  desc: 'Bold, dynamic' },
  am_liam:    { g: 'm', hue: '#6DE0D8', lang: 'en-us', name: 'Liam',    desc: 'Friendly, casual' },
  am_michael: { g: 'm', hue: '#8AF0E8', lang: 'en-us', name: 'Michael', desc: 'Deep, authoritative' },
  am_onyx:    { g: 'm', hue: '#5CD8D0', lang: 'en-us', name: 'Onyx',    desc: 'Rich, powerful' },
  am_puck:    { g: 'm', hue: '#7AE8E0', lang: 'en-us', name: 'Puck',    desc: 'Playful, expressive' },
  // British Female — purple/lavender
  bf_alice:    { g: 'f', hue: '#C4B5FD', lang: 'en-gb', name: 'Alice',    desc: 'Refined, poised' },
  bf_emma:     { g: 'f', hue: '#D4C5FF', lang: 'en-gb', name: 'Emma',     desc: 'Elegant, articulate' },
  bf_isabella: { g: 'f', hue: '#B4A5ED', lang: 'en-gb', name: 'Isabella', desc: 'Graceful, warm' },
  bf_lily:     { g: 'f', hue: '#E4D5FF', lang: 'en-gb', name: 'Lily',     desc: 'Soft, gentle' },
  // British Male — steel blue
  bm_daniel: { g: 'm', hue: '#7B90A9', lang: 'en-gb', name: 'Daniel', desc: 'Composed, clear' },
  bm_fable:  { g: 'm', hue: '#8BA0B9', lang: 'en-gb', name: 'Fable',  desc: 'Storytelling, warm' },
  bm_george: { g: 'm', hue: '#6B80A0', lang: 'en-gb', name: 'George', desc: 'Classic narrator' },
  bm_lewis:  { g: 'm', hue: '#9BB0C9', lang: 'en-gb', name: 'Lewis',  desc: 'Thoughtful, measured' },
  // Japanese — sakura pink / muted blue
  jf_alpha:      { g: 'f', hue: '#FFB7C5', lang: 'ja', name: 'Alpha',      desc: 'Clear, natural' },
  jf_gongitsune: { g: 'f', hue: '#FFC7D5', lang: 'ja', name: 'Gongitsune', desc: 'Gentle, expressive' },
  jf_nezumi:     { g: 'f', hue: '#FFD7E5', lang: 'ja', name: 'Nezumi',     desc: 'Soft, delicate' },
  jf_tebukuro:   { g: 'f', hue: '#FFA7B5', lang: 'ja', name: 'Tebukuro',   desc: 'Warm, friendly' },
  jm_kumo:       { g: 'm', hue: '#A0B4C8', lang: 'ja', name: 'Kumo',       desc: 'Calm, steady' },
  // Chinese — gold
  zf_xiaobei:  { g: 'f', hue: '#FFD700', lang: 'zh', name: 'Xiaobei',  desc: 'Bright, cheerful' },
  zf_xiaoni:   { g: 'f', hue: '#FFE740', lang: 'zh', name: 'Xiaoni',   desc: 'Warm, gentle' },
  zf_xiaoxuan: { g: 'f', hue: '#FFC800', lang: 'zh', name: 'Xiaoxuan', desc: 'Clear, professional' },
  zf_xiaoyi:   { g: 'f', hue: '#FFF060', lang: 'zh', name: 'Xiaoyi',   desc: 'Soft, soothing' },
  zm_yunjian:  { g: 'm', hue: '#E8B800', lang: 'zh', name: 'Yunjian',  desc: 'Strong, commanding' },
  zm_yunxi:    { g: 'm', hue: '#D8A800', lang: 'zh', name: 'Yunxi',    desc: 'Warm, rich' },
  zm_yunxia:   { g: 'm', hue: '#C89800', lang: 'zh', name: 'Yunxia',   desc: 'Smooth, mellow' },
  zm_yunyang:  { g: 'm', hue: '#F0C000', lang: 'zh', name: 'Yunyang',  desc: 'Energetic, bright' },
  // Spanish — warm orange
  ef_dora:  { g: 'f', hue: '#FFB074', lang: 'es', name: 'Dora',  desc: 'Warm, expressive' },
  em_alex:  { g: 'm', hue: '#FFA060', lang: 'es', name: 'Alex',  desc: 'Clear, confident' },
  em_santa: { g: 'm', hue: '#FF9050', lang: 'es', name: 'Santa', desc: 'Rich, resonant' },
  // French — soft mauve
  ff_siwis: { g: 'f', hue: '#D4A0D0', lang: 'fr', name: 'Siwis', desc: 'Elegant, smooth' },
  // Hindi — saffron
  hf_alpha: { g: 'f', hue: '#FFB347', lang: 'hi', name: 'Alpha', desc: 'Clear, natural' },
  hf_beta:  { g: 'f', hue: '#FFC370', lang: 'hi', name: 'Beta',  desc: 'Warm, gentle' },
  hm_omega: { g: 'm', hue: '#E0A030', lang: 'hi', name: 'Omega', desc: 'Deep, steady' },
  hm_psi:   { g: 'm', hue: '#D09020', lang: 'hi', name: 'Psi',   desc: 'Rich, expressive' },
  // Italian — warm green
  if_sara:   { g: 'f', hue: '#90D890', lang: 'it', name: 'Sara',   desc: 'Warm, melodic' },
  im_nicola: { g: 'm', hue: '#70C870', lang: 'it', name: 'Nicola', desc: 'Clear, engaging' },
  // Portuguese — ocean blue
  pf_dora:  { g: 'f', hue: '#70B0E0', lang: 'pt-br', name: 'Dora',  desc: 'Bright, friendly' },
  pm_alex:  { g: 'm', hue: '#60A0D0', lang: 'pt-br', name: 'Alex',  desc: 'Warm, clear' },
  pm_santa: { g: 'm', hue: '#5090C0', lang: 'pt-br', name: 'Santa', desc: 'Deep, resonant' },
}

export const TOP_PICKS = [
  { voice: 'af_heart',   badge: '#1 Narration',  bestFor: 'Audiobooks, narration, general purpose' },
  { voice: 'af_bella',   badge: 'Dynamic',       bestFor: 'Dynamic narration, marketing' },
  { voice: 'af_nicole',  badge: 'Professional',  bestFor: 'Non-fiction, tutorials, professional' },
  { voice: 'af_sarah',   badge: 'Versatile',     bestFor: 'General audiobooks, balanced delivery' },
  { voice: 'am_adam',    badge: 'Male Lead',     bestFor: 'Male narration, approachable tone' },
  { voice: 'am_michael', badge: 'Authoritative', bestFor: 'Deep narration, documentary' },
  { voice: 'bf_emma',    badge: 'British',       bestFor: 'British female, elegant narration' },
  { voice: 'bm_george',  badge: 'Classic',       bestFor: 'British male, classic narrator' },
]

export const BLEND_PRESETS = [
  { name: 'Narrator',    a: 'af_heart',  b: 'am_michael', ratio: 35, desc: 'Warm + authoritative' },
  { name: 'Podcast',     a: 'af_bella',  b: 'am_adam',    ratio: 50, desc: 'Energetic duo' },
  { name: 'Storyteller', a: 'bf_emma',   b: 'bm_fable',   ratio: 40, desc: 'British elegance' },
  { name: 'Newscast',    a: 'af_nicole', b: 'am_eric',    ratio: 30, desc: 'Clear + confident' },
  { name: 'Gentle',      a: 'af_kore',   b: 'af_river',   ratio: 50, desc: 'Soothing blend' },
  { name: 'Bold',        a: 'am_fenrir', b: 'am_onyx',    ratio: 50, desc: 'Dynamic power' },
  { name: 'Velvet',      a: 'af_bella',  b: 'am_adam',    ratio: 80, desc: 'Bella-forward warmth' },
]

export const RANDOM_STORIES = [
  `The old lighthouse keeper climbed the spiral staircase one final time. Seventy-three steps \u2014 he'd counted them every night for forty years. Tonight the light would go automatic, and the sea would lose its last human guardian. He pressed his palm against the cold glass and watched the beam sweep across black water. Somewhere out there, a fishing boat adjusted course. They'd never know it was his last turn of the lens.`,
  `She found the letter tucked inside a library book, dated nineteen fifty-two. "If you're reading this," it began, "then the maples outside must be enormous by now." She glanced out the window. The maples were enormous. She kept reading. "I buried something beneath the tallest one. Something that mattered to me once. I hope it matters to you too." She closed the book, grabbed her coat, and walked outside with a borrowed shovel.`,
  `The robot had been designed to sort mail, but somewhere between firmware update seven and firmware update eight, it developed a fondness for poetry. It would pause at each envelope, scanning the handwritten addresses with what its engineers could only describe as admiration. "Beautiful ligatures," it murmured one Tuesday, holding a birthday card up to the fluorescent light. The engineers exchanged nervous glances.`,
  `Rain hammered the tin roof of the roadside diner. A truck driver sat at the counter, stirring coffee he'd never drink. Across from him, a woman in a red coat studied a road atlas, tracing routes with her fingertip. Neither spoke. The waitress refilled his cup anyway. Outside, lightning split the sky and for one bright instant, every puddle in the parking lot turned to silver. The woman folded her map and smiled.`,
  `The astronaut floated by the observation window, watching Earth turn below. Continents drifted past like slow clouds. She pressed record on her personal log. "Day two hundred and fourteen. I can see a hurricane forming over the Atlantic. From up here it looks like a pinwheel. Beautiful and terrible. I think about my daughter learning to ride her bike in the backyard. I wonder if she looks up at the stars and knows which one is me."`,
  `The violin had been silent for twenty years, sealed in its velvet-lined case in the attic. When the old man's granddaughter found it, she lifted the bow and drew it across the strings. The sound was thin and ghostly at first, but the wood remembered. By the third note, the kitchen below fell quiet. By the seventh, her grandfather had risen from his chair, tears tracking down weathered cheeks. The violin remembered everything.`,
  `The detective stared at the chessboard. The suspect sat across from him, calm as still water. "You left one clue," the detective said, moving a pawn. "Just one. But it was enough." The suspect tilted his head. "Enlighten me." The detective placed a photograph on the table \u2014 a reflection in a window, barely visible, showing a figure in a doorway. "You forgot about the glass." The suspect's smile faded by exactly one degree.`,
  `The last bookshop on Elm Street had a cat named Tolstoy and a policy of lending books on the honor system. No cards, no due dates. Just a handwritten note on the door: "Take what you need. Return when you're ready." Most people returned their books. Some left new ones. By December, the shelves held twice as many titles as they had in spring. The owner didn't question it. She just made more tea and added another shelf.`,
  `The ship's captain spoke into the radio one final time. "This is the Aurora, signing off after thirty years of service. She's carried cargo to fourteen countries, weathered nine storms, and never once let her crew down." He paused, running his hand along the bridge console. "They'll scrap her hull and melt her steel. But steel doesn't forget the shape of a ship. Somewhere in a bridge or a building, she'll keep standing."`,
  `The garden had been abandoned for decades, but it refused to die. Roses climbed the iron gate, their thorns locking it shut. Ivy covered the stone walls like a second skin. And at the center, where a fountain had once stood, a single apple tree grew crooked and wild, its branches heavy with fruit that no one picked. Birds came and went. Seasons turned. The garden kept its own time, answering to no one.`,
  `The pianist's hands trembled above the keys. The concert hall held two thousand people, and every one of them was silent. She closed her eyes and thought of her teacher \u2014 a quiet woman who smelled of lavender and never raised her voice. "Don't play for them," the teacher had said. "Play for the version of yourself who needed music most." Her fingers found the first chord. The trembling stopped. The music began.`,
]

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

function timeAgo(ts) {
  if (!ts) return ''
  const diff = (Date.now() - new Date(ts).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

function fmtTime(s) {
  if (!s || isNaN(s)) return '0:00'
  return Math.floor(s / 60) + ':' + String(Math.floor(s % 60)).padStart(2, '0')
}

function persist(key, value) {
  localStorage.setItem(key, String(value))
}

// ── Actions ──

async function checkModel() {
  try {
    const d = await api.get('/api/tts/model-status/kokoro')
    modelReady.value = d.cached
  } catch {
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
  } catch {
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
    } catch {
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
    } catch {
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
  } catch {
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
    checkModel()
    loadVoices()
    loadHistory()
  }

  return {
    // State (readonly)
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
  }
}
