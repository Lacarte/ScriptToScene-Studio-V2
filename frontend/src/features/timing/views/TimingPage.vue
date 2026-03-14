<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useTiming } from '../composables/useTiming.js'
import { useToast } from '@/shared/composables/useToast.js'
import AlignmentTimeline from '../components/AlignmentTimeline.vue'
import WordChips from '../components/WordChips.vue'
import KaraokeOverlay from '../components/KaraokeOverlay.vue'

defineOptions({ name: 'TimingPage' })

const timing = useTiming()
const toast = useToast()

/* ── Local state ── */
const audioFile = ref(null)
const textInput = ref('')
const audioEl = ref(null)
const audioLoaded = ref(false)
const dragging = ref(false)
const showKaraoke = ref(false)
const showTtsPicker = ref(false)
const fileInputRef = ref(null)

let rafId = null

/* ── Computed ── */
const inputWordCount = computed(() => {
  const t = textInput.value.trim()
  return t ? t.split(/\s+/).length : 0
})

const canRun = computed(() => {
  return audioFile.value && textInput.value.trim() && !timing.isAligning.value
})

const hasResults = computed(() => {
  return timing.alignment.value && timing.alignment.value.length > 0
})

const alignmentDuration = computed(() => {
  if (timing.duration.value && isFinite(timing.duration.value)) return timing.duration.value
  const words = timing.alignment.value || []
  return words.length ? words[words.length - 1].end || 0 : 0
})

const resultsStats = computed(() => {
  const parts = []
  if (timing.projectId.value) parts.push(timing.projectId.value)
  if (timing.wordCount.value) parts.push(`${timing.wordCount.value} words`)
  if (alignmentDuration.value) parts.push(`${alignmentDuration.value.toFixed(1)}s duration`)
  if (timing.inferenceTime.value !== null && isFinite(timing.inferenceTime.value)) {
    parts.push(`${timing.inferenceTime.value.toFixed(2)}s processing`)
  }
  return parts.join(' · ')
})

const historyCountLabel = computed(() => {
  const count = timing.history.value.length
  return `${count} file${count === 1 ? '' : 's'}`
})

/* ── File handling ── */
const ACCEPTED = ['.wav', '.mp3', '.flac', '.ogg']
const ACCEPT_STR = ACCEPTED.join(',')

function onFileSelect(e) {
  const file = e.target.files?.[0]
  if (file) setFile(file)
}

function setFile(file) {
  const ext = '.' + file.name.split('.').pop().toLowerCase()
  if (!ACCEPTED.includes(ext)) {
    toast.error(`Unsupported format. Use WAV, MP3, FLAC, or OGG.`)
    return
  }
  audioFile.value = file
  // Load audio preview
  if (timing.audioUrl.value) {
    URL.revokeObjectURL(timing.audioUrl.value)
  }
  timing.audioUrl.value = URL.createObjectURL(file)
}

function onDrop(e) {
  e.preventDefault()
  dragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) setFile(file)
}

function onDragOver(e) {
  e.preventDefault()
  dragging.value = true
}

function onDragLeave() {
  dragging.value = false
}

function openFilePicker() {
  fileInputRef.value?.click()
}

/* ── TTS source ── */
async function useTtsResult() {
  // Load TTS history and use the latest result
  await timing.loadTtsHistory()
  if (timing.ttsHistory.value.length > 0) {
    const latest = timing.ttsHistory.value[0]
    await loadTtsGeneration(latest)
    toast.success('Loaded latest TTS result')
  } else {
    toast.warning('No TTS generations found')
  }
}

async function openTtsPicker() {
  await timing.loadTtsHistory()
  showTtsPicker.value = true
}

async function loadTtsGeneration(gen) {
  // Set audio from TTS generation
  if (gen.audio_url || gen.file_path) {
    const url = gen.audio_url || gen.file_path
    try {
      const res = await fetch(url)
      const blob = await res.blob()
      const filename = gen.filename || url.split('/').pop()
      const file = new File([blob], filename, { type: blob.type })
      setFile(file)
    } catch {
      toast.error('Failed to load TTS audio file')
      return
    }
  }
  // Set transcript from TTS text
  if (gen.text) {
    textInput.value = gen.text
  }
  showTtsPicker.value = false
}

/* ── Alignment ── */
async function runAlignment() {
  if (!canRun.value) return
  try {
    await timing.runAlignment(audioFile.value, textInput.value.trim())
    toast.success('Alignment complete')
    await timing.loadHistory()
    // Audio URL is now set from the response, reload audio element
    audioLoaded.value = false
  } catch (err) {
    toast.error(err.message || 'Alignment failed')
  }
}

/* ── Audio playback ── */
function onAudioLoaded() {
  if (audioEl.value) {
    timing.setDuration(audioEl.value.duration)
    audioLoaded.value = true
  }
}

function onAudioEnded() {
  timing.setPlaying(false)
}

function togglePlay() {
  if (!audioEl.value || !audioLoaded.value) return
  if (audioEl.value.paused) {
    audioEl.value.play()
    timing.setPlaying(true)
  } else {
    audioEl.value.pause()
    timing.setPlaying(false)
  }
}

function seekTo(time) {
  if (!audioEl.value) return
  audioEl.value.currentTime = time
  timing.updateActiveWord(time)
}

function seekWord(begin) {
  seekTo(begin)
  if (audioEl.value && audioEl.value.paused) {
    audioEl.value.play()
    timing.setPlaying(true)
  }
}

function tick() {
  if (audioEl.value && !audioEl.value.paused) {
    timing.updateActiveWord(audioEl.value.currentTime)
  }
  rafId = requestAnimationFrame(tick)
}

/* ── Results actions ── */
function copyJson() {
  if (!timing.results.value) return
  navigator.clipboard.writeText(JSON.stringify(timing.alignment.value, null, 2))
  toast.success('JSON copied to clipboard')
}

function downloadJson() {
  if (!timing.alignment.value.length) return
  const blob = new Blob([JSON.stringify(timing.alignment.value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `alignment-${timing.sourceFolder.value || 'result'}.json`
  a.click()
  URL.revokeObjectURL(url)
}

async function deleteCurrentResult() {
  if (!timing.sourceFolder.value) return
  try {
    await timing.deleteResult(timing.sourceFolder.value)
    toast.success('Result deleted')
    audioLoaded.value = false
  } catch {
    toast.error('Failed to delete result')
  }
}

/* ── History ── */
function loadHistoryItem(item) {
  timing.loadResult(item.folder)
  textInput.value = item.transcript || ''
  audioLoaded.value = false
  toast.info('Loaded alignment result')
}

async function deleteHistoryItem(folder) {
  try {
    await timing.deleteResult(folder)
    toast.success('Deleted')
  } catch {
    toast.error('Failed to delete')
  }
}

function formatDuration(secs) {
  if (!secs || !isFinite(secs)) return '--'
  return secs.toFixed(1) + 's'
}

function formatDate(ts) {
  if (!ts) return ''
  try {
    const diff = (Date.now() - new Date(ts).getTime()) / 1000
    if (diff < 60) return 'just now'
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
    return `${Math.floor(diff / 86400)}d ago`
  } catch {
    return ts
  }
}

function truncateText(text, max = 60) {
  if (!text) return ''
  return text.length > max ? text.slice(0, max) + '...' : text
}

/* ── Lifecycle ── */
onMounted(() => {
  timing.loadHistory()
  rafId = requestAnimationFrame(tick)
})

onBeforeUnmount(() => {
  if (rafId) cancelAnimationFrame(rafId)
})
</script>

<template>
  <div class="timing-page">
    <div class="page-header">
      <div class="title-row">
        <h2 class="page-title">Force Alignment</h2>
        <span v-if="timing.projectId.value" class="module-project-badge visible">{{ timing.projectId.value }}</span>
      </div>
      <p class="page-subtitle">Align audio to text with word-level timestamps</p>
    </div>

    <section class="card legacy-card">
      <label class="section-label">From TTS</label>
      <div class="tts-source-row">
        <button class="action-btn action-btn-lg hover-accent" @click="useTtsResult">Use Current Result</button>
        <button class="action-btn action-btn-lg hover-accent" @click="openTtsPicker">Pick from History</button>
      </div>
      <p v-if="timing.sourceFile.value" class="source-info">{{ timing.sourceFile.value }}</p>
    </section>

    <div v-if="showTtsPicker" class="modal-backdrop" @click.self="showTtsPicker = false">
      <div class="modal-card">
        <div class="modal-header">
          <h3>Pick TTS Generation</h3>
          <button class="close-btn" @click="showTtsPicker = false">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
              <path d="M18.3 5.7a1 1 0 0 0-1.4 0L12 10.6 7.1 5.7a1 1 0 0 0-1.4 1.4L10.6 12l-4.9 4.9a1 1 0 1 0 1.4 1.4L12 13.4l4.9 4.9a1 1 0 0 0 1.4-1.4L13.4 12l4.9-4.9a1 1 0 0 0 0-1.4z"/>
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <div v-if="!timing.ttsHistory.value.length" class="empty-state">No TTS generations found.</div>
          <div
            v-for="gen in timing.ttsHistory.value"
            :key="gen.id || gen.filename"
            class="tts-item"
            @click="loadTtsGeneration(gen)"
          >
            <span class="tts-item-name">{{ gen.filename || gen.text?.slice(0, 50) || 'Untitled' }}</span>
            <span class="tts-item-meta">{{ formatDate(gen.timestamp) }}</span>
          </div>
        </div>
      </div>
    </div>

    <section class="card legacy-card">
      <label class="section-label">Audio File</label>
      <div
        class="drop-zone"
        :class="{ 'drop-zone--active': dragging, 'drop-zone--has-file': audioFile }"
        @drop="onDrop"
        @dragover="onDragOver"
        @dragleave="onDragLeave"
        @click="openFilePicker"
      >
        <input
          ref="fileInputRef"
          type="file"
          :accept="ACCEPT_STR"
          class="file-input-hidden"
          @change="onFileSelect"
        />
        <div v-if="audioFile" class="file-info">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" class="file-icon">
            <path d="M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z"/>
          </svg>
          <span class="file-name">{{ audioFile.name }}</span>
          <span class="file-size">{{ (audioFile.size / 1024).toFixed(0) }} KB</span>
        </div>
        <div v-else class="drop-prompt">
          <svg width="28" height="28" fill="none" stroke="var(--text-muted)" stroke-width="1.5" viewBox="0 0 24 24" class="drop-icon">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          <span>Drop a WAV/MP3 file here or click to browse</span>
          <span class="drop-subtext">WAV, MP3, FLAC, OGG</span>
        </div>
      </div>
    </section>

    <section class="card legacy-card">
      <label class="section-label">Transcript</label>
      <textarea
        v-model="textInput"
        class="input-field transcript-input"
        placeholder="Paste the transcript text that matches the audio..."
        rows="5"
      />
      <div class="transcript-meta">
        <span>{{ inputWordCount }} words</span>
        <span>English only</span>
      </div>
    </section>

    <button
      class="gen-btn run-btn"
      :disabled="!canRun"
      @click="runAlignment"
    >
      <svg v-if="timing.isAligning.value" class="spinner" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <circle cx="12" cy="12" r="10" stroke-opacity="0.25" />
        <path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round" />
      </svg>
      <span>{{ timing.isAligning.value ? 'Aligning...' : 'Run Alignment' }}</span>
    </button>

    <audio
      ref="audioEl"
      :src="timing.audioUrl.value"
      preload="auto"
      @loadedmetadata="onAudioLoaded"
      @ended="onAudioEnded"
    />

    <template v-if="hasResults">
      <section class="card legacy-card results-card">
        <div class="results-header">
          <label class="section-label section-label--inline">Results</label>
          <div class="results-actions">
            <button class="action-btn hover-accent" @click="showKaraoke = true" title="Fullscreen Karaoke">
              <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" viewBox="0 0 24 24">
                <path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3" />
              </svg>
              Karaoke
            </button>
            <button class="action-btn hover-accent" @click="copyJson" title="Copy JSON">Copy JSON</button>
            <button class="action-btn hover-accent" @click="downloadJson" title="Download JSON">Download</button>
            <button class="action-btn hover-coral-border" @click="deleteCurrentResult" title="Delete Result">Delete</button>
          </div>
        </div>
        <div class="results-stats">{{ resultsStats }}</div>
        <AlignmentTimeline
          :current-time="timing.currentTime.value"
          :duration="alignmentDuration"
          :is-playing="timing.isPlaying.value"
          @toggle-play="togglePlay"
          @seek="seekTo"
        />
        <WordChips
          :words="timing.alignment.value"
          :active-index="timing.activeWordIdx.value"
          :audio-loaded="audioLoaded"
          @seek-word="seekWord"
        />
      </section>
    </template>

    <section class="history-section">
      <div class="history-header">
        <h3 class="history-title">History</h3>
        <span class="history-count">{{ historyCountLabel }}</span>
      </div>
      <div class="history-list">
        <p v-if="!timing.history.value.length" class="empty-history">No alignments yet</p>
        <div
          v-for="item in timing.history.value"
          :key="item.folder"
          class="history-item hist-item"
          :class="{ 'history-item--active': item.folder === timing.sourceFolder.value }"
        >
          <div class="history-row" @click="loadHistoryItem(item)">
            <div class="history-info">
              <p class="history-name">{{ truncateText(item.transcript || item.source_file || item.folder) }}</p>
              <div class="history-meta">
                <span v-if="item.project_id">{{ item.project_id }}</span>
                <span v-if="item.project_id" class="meta-sep">/</span>
                <span class="meta-words">{{ item.word_count || '?' }} words</span>
                <span class="meta-sep">/</span>
                <span>{{ formatDuration(item.duration_seconds) }}</span>
                <span v-if="item.timestamp" class="meta-sep">/</span>
                <span v-if="item.timestamp">{{ formatDate(item.timestamp) }}</span>
              </div>
            </div>
            <span class="history-source">{{ item.source_file || '' }}</span>
          </div>
          <div class="history-actions">
            <button class="btn-icon" @click="loadHistoryItem(item)" title="Load">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="6,4 20,12 6,20" />
              </svg>
            </button>
            <button class="btn-icon btn-icon--danger" @click="deleteHistoryItem(item.folder)" title="Delete">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </section>

    <KaraokeOverlay
      v-if="showKaraoke"
      :words="timing.alignment.value"
      :audio-src="timing.audioUrl.value"
      @close="showKaraoke = false"
    />
  </div>
</template>

<style scoped>
.timing-page {
  max-width: 780px;
  margin: 0 auto;
  padding: 32px 24px 40px;
}

.page-header {
  margin-bottom: 16px;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 700;
  margin: 0;
}

.page-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.legacy-card {
  padding: 20px;
  margin-bottom: 16px;
}

.section-label {
  display: block;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--text-muted);
  margin-bottom: 12px;
}

.section-label--inline {
  margin-bottom: 0;
}

.tts-source-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.action-btn-lg {
  padding: 6px 14px;
  font-size: 11px;
}

.source-info {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--accent);
  font-family: "JetBrains Mono", monospace;
}

.drop-zone {
  border: 2px dashed var(--border);
  border-radius: 10px;
  padding: 18px 16px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}

.drop-zone:hover {
  border-color: var(--text-secondary);
}

.drop-zone--active {
  border-color: var(--accent);
  background: rgba(78, 205, 196, 0.05);
}

.drop-zone--has-file {
  border-style: solid;
  border-color: var(--border);
  padding: 16px 20px;
}

.file-input-hidden {
  display: none;
}

.drop-prompt {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 13px;
}

.drop-icon {
  margin: 0 auto 8px;
}

.drop-subtext {
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-secondary);
  font-family: "JetBrains Mono", monospace;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.file-icon {
  color: var(--accent);
  flex-shrink: 0;
}

.file-name {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text);
  font-weight: 500;
}

.file-size {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
}

.transcript-input {
  width: 100%;
  padding: 6px 14px;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text);
  background: var(--bg-darkest);
  border: 1.5px solid var(--border);
  border-radius: 8px;
  resize: vertical;
  outline: none;
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.transcript-input:focus {
  border-color: var(--accent);
}

.transcript-meta {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  font-size: 10px;
  color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace;
}

.run-btn {
  width: 100%;
  padding: 14px 24px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: white;
  background: linear-gradient(135deg, var(--accent), #3BA89F);
  box-shadow: 0 4px 16px rgba(78, 205, 196, 0.25);
  border: none;
  border-radius: 12px;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.gen-btn:hover:not(:disabled) {
  box-shadow: 0 6px 24px rgba(78, 205, 196, 0.35);
  transform: translateY(-1px);
}

.gen-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinner {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.results-card {
  margin-top: 20px;
}

.results-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.results-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.results-stats {
  margin-bottom: 10px;
  font-size: 11px;
  color: var(--text-secondary);
  font-family: "JetBrains Mono", monospace;
}

.history-section {
  margin-top: 16px;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.history-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
}

.history-count {
  font-size: 12px;
  color: var(--text-muted);
  font-family: "JetBrains Mono", monospace;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 6px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.history-item:hover {
  border-color: var(--border-hover);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
}

.history-item--active {
  border-color: #ff9f43;
  box-shadow: inset 3px 0 0 #ff9f43, 0 0 12px rgba(255, 159, 67, 0.15);
}

.history-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
  padding: 10px 0 10px 2px;
  cursor: pointer;
}

.history-info {
  flex: 1;
  min-width: 0;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.history-name {
  margin: 0;
  font-size: 13px;
  color: var(--text);
  line-height: 1.4;
}

.history-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 10px;
  color: var(--text-muted);
  font-family: "JetBrains Mono", monospace;
}

.meta-sep {
  opacity: 0.3;
}

.meta-words {
  color: var(--accent);
}

.history-source {
  flex-shrink: 0;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--bg-darkest);
  font-size: 9px;
  color: var(--text-muted);
  font-family: "JetBrains Mono", monospace;
}

.history-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.btn-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  opacity: 0.55;
  transition: all 0.2s;
}

.btn-icon:hover {
  color: var(--accent);
  background: rgba(78, 205, 196, 0.08);
  opacity: 1;
}

.btn-icon--danger:hover {
  color: var(--coral);
  background: rgba(255, 107, 107, 0.08);
}

.empty-history {
  margin: 0;
  padding: 32px 0;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.modal-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 16px;
  width: 100%;
  max-width: 480px;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.modal-header h3 {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 600;
}

.close-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  transition: color 0.15s;
}

.close-btn:hover {
  color: var(--text);
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 20px;
}

.tts-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 8px;
  cursor: pointer;
  border-radius: 8px;
  transition: background 0.15s;
}

.tts-item:hover {
  background: rgba(78, 205, 196, 0.06);
}

.tts-item-name {
  font-size: 13px;
  color: var(--text);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 280px;
}

.tts-item-meta {
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.empty-state {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  padding: 24px 0;
}

@media (max-width: 720px) {
  .timing-page {
    padding: 24px 16px 32px;
  }

  .results-header,
  .history-header,
  .history-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .history-actions,
  .results-actions {
    width: 100%;
  }
}
</style>
