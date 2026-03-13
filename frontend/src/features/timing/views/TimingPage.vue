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
    return new Date(ts).toLocaleString()
  } catch {
    return ts
  }
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
    <!-- Header -->
    <div class="page-header">
      <div class="title-row">
        <h2 class="page-title">Force Alignment</h2>
        <span v-if="timing.projectId.value" class="project-badge">{{ timing.projectId.value }}</span>
      </div>
      <p class="page-subtitle">Align transcript to audio with word-level timestamps</p>
    </div>

    <!-- TTS Source -->
    <section class="card">
      <label class="section-label">TTS Source</label>
      <div class="tts-source-row">
        <button class="action-btn action-btn-lg" @click="useTtsResult">Use Current Result</button>
        <button class="action-btn action-btn-lg" @click="openTtsPicker">Pick from History</button>
      </div>
      <div v-if="timing.sourceFile.value" class="source-info">
        <span class="source-tag">Source</span>
        <span class="source-name">{{ timing.sourceFile.value }}</span>
      </div>
    </section>

    <!-- TTS Picker Modal -->
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

    <!-- Audio File -->
    <section class="card">
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
          <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor" class="drop-icon">
            <path d="M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z"/>
          </svg>
          <span>Drop audio file here or click to browse</span>
          <span class="drop-hint">WAV, MP3, FLAC, OGG</span>
        </div>
      </div>
    </section>

    <!-- Transcript -->
    <section class="card">
      <div class="label-row">
        <label class="section-label">Transcript</label>
        <span class="word-count">{{ inputWordCount }} words</span>
      </div>
      <textarea
        v-model="textInput"
        class="transcript-input"
        placeholder="Enter the transcript text to align..."
        rows="5"
      />
    </section>

    <!-- Run Button -->
    <button
      class="gen-btn"
      :disabled="!canRun"
      @click="runAlignment"
    >
      <svg v-if="timing.isAligning.value" class="spinner" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <circle cx="12" cy="12" r="10" stroke-opacity="0.25" />
        <path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round" />
      </svg>
      <span>{{ timing.isAligning.value ? 'Aligning...' : 'Run Alignment' }}</span>
    </button>

    <!-- Hidden audio element -->
    <audio
      ref="audioEl"
      :src="timing.audioUrl.value"
      preload="auto"
      @loadedmetadata="onAudioLoaded"
      @ended="onAudioEnded"
    />

    <!-- Results -->
    <template v-if="hasResults">
      <section class="card">
        <label class="section-label">Results</label>

        <!-- Stats -->
        <div class="stats-row">
          <div class="stat">
            <span class="stat-value">{{ timing.wordCount.value }}</span>
            <span class="stat-label">Words</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ formatDuration(timing.duration.value) }}</span>
            <span class="stat-label">Duration</span>
          </div>
          <div class="stat" v-if="timing.inferenceTime.value !== null">
            <span class="stat-value">{{ timing.inferenceTime.value.toFixed(2) }}s</span>
            <span class="stat-label">Inference</span>
          </div>
        </div>

        <!-- Timeline -->
        <AlignmentTimeline
          :current-time="timing.currentTime.value"
          :duration="timing.duration.value"
          :is-playing="timing.isPlaying.value"
          @toggle-play="togglePlay"
          @seek="seekTo"
        />

        <!-- Word Chips -->
        <WordChips
          :words="timing.alignment.value"
          :active-index="timing.activeWordIdx.value"
          :audio-loaded="audioLoaded"
          @seek-word="seekWord"
        />

        <!-- Action Buttons -->
        <div class="actions-row">
          <button class="action-btn" @click="showKaraoke = true" title="Fullscreen Karaoke">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/>
            </svg>
            Karaoke
          </button>
          <button class="action-btn" @click="copyJson" title="Copy JSON">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/>
            </svg>
            Copy JSON
          </button>
          <button class="action-btn" @click="downloadJson" title="Download JSON">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
            </svg>
            Download
          </button>
          <button class="action-btn danger" @click="deleteCurrentResult" title="Delete Result">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>
            </svg>
            Delete
          </button>
        </div>
      </section>
    </template>

    <!-- History -->
    <section class="card" v-if="timing.history.value.length">
      <label class="section-label">History</label>
      <div class="history-list">
        <div
          v-for="item in timing.history.value"
          :key="item.folder"
          class="history-item"
          :class="{ 'history-item--active': item.folder === timing.sourceFolder.value }"
        >
          <div class="history-info" @click="loadHistoryItem(item)">
            <span class="history-name">{{ item.source_file || item.folder }}</span>
            <span class="history-meta">
              {{ item.word_count || '?' }} words
              <template v-if="item.timestamp"> &middot; {{ formatDate(item.timestamp) }}</template>
            </span>
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

    <!-- Karaoke Overlay -->
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
  padding: 0 20px 40px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ---- Header ---- */
.page-header {
  margin-bottom: 4px;
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
}

.project-badge {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 10px;
  background: rgba(78, 205, 196, 0.12);
  color: var(--accent);
}

.page-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin-top: 4px;
}

/* ---- Card ---- */
.card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}

/* ---- Labels ---- */
.section-label {
  display: block;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--text-muted);
  margin-bottom: 12px;
}

.label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.word-count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-secondary);
}

/* ---- TTS Source ---- */
.tts-source-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.action-btn {
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s;
}
.action-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.action-btn-lg {
  padding: 6px 14px;
  font-size: 11px;
}

.source-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 4px;
}

.source-tag {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--accent);
  background: rgba(78, 205, 196, 0.1);
  padding: 2px 8px;
  border-radius: 4px;
}

.source-name {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-secondary);
}

/* ---- Drop Zone ---- */
.drop-zone {
  border: 2px dashed var(--border);
  border-radius: 12px;
  padding: 28px 20px;
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
  color: var(--text-muted);
}

.drop-hint {
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--font-mono);
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

/* ---- Transcript ---- */
.transcript-input {
  width: 100%;
  min-height: 100px;
  padding: 12px;
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text);
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 8px;
  resize: vertical;
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
}

.transcript-input::placeholder {
  color: var(--text-muted);
}

.transcript-input:focus {
  border-color: var(--accent);
}

/* ---- Gen Button ---- */
.gen-btn {
  width: 100%;
  padding: 14px 24px;
  font-family: 'JetBrains Mono', var(--font-mono);
  font-size: 14px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, #4ECDC4, #2FB8AE);
  border: none;
  border-radius: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: opacity 0.15s, transform 0.1s;
}

.gen-btn:hover:not(:disabled) {
  opacity: 0.92;
  transform: translateY(-1px);
}

.gen-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.spinner {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ---- Stats ---- */
.stats-row {
  display: flex;
  gap: 24px;
  margin-bottom: 8px;
}

.stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.stat-value {
  font-family: var(--font-mono);
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
}

.stat-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--text-muted);
}

/* ---- Actions ---- */
.actions-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.action-btn.danger {
  border-color: rgba(239, 68, 68, 0.3);
  color: var(--coral, #ef4444);
}
.action-btn.danger:hover {
  border-color: var(--coral, #ef4444);
}

/* ---- History ---- */
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
  border-radius: 8px;
  transition: background 0.15s;
}

.history-item:hover {
  background: rgba(255, 255, 255, 0.03);
}

.history-item--active {
  background: rgba(78, 205, 196, 0.06);
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
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-meta {
  font-size: 11px;
  color: var(--text-muted);
}

.history-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.btn-icon {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: 1px solid transparent;
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}

.btn-icon:hover {
  color: var(--accent);
  border-color: var(--border);
  background: var(--bg-input);
}

.btn-icon--danger:hover {
  color: var(--coral);
}

/* ---- Modal ---- */
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
</style>
