<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAssets } from '../composables/useAssets.js'
import { useToast } from '@/shared/composables/useToast.js'
import AssetCard from '../components/AssetCard.vue'
import AssetLightbox from '../components/AssetLightbox.vue'
import GrabberControls from '../components/GrabberControls.vue'

defineOptions({ name: 'AssetsPage' })

const toast = useToast()
const {
  scenes,
  provider,
  arguments: args,
  aspectRatio,
  providerOptions,
  grabberRunning,
  sceneStatuses,
  selectedScenes,
  history,
  analysisData,
  audioUrl,
  isPlaying,
  currentTime,
  lightboxOpen,
  lightboxScene,
  lightboxFile,
  sceneCount,
  selectedCount,
  progress,
  TYPE_COLORS,
  loadScenes,
  setProvider,
  setArguments,
  setAspectRatio,
  setProviderOption,
  startGrabber,
  stopGrabber,
  redownload,
  loadHistory,
  loadFromHistory,
  reconcile,
  editPrompt,
  savePrompt,
  copyPrompt,
  openFolder,
  downloadScene,
  downloadAll,
  toggleSelect,
  selectAll,
  selectNone,
  selectPending,
  resendSelected,
  openLightbox,
  closeLightbox,
  loadSceneHistory,
} = useAssets()

const projectId = ref(null)
const analysisOpen = ref(false)
const historyVisible = ref(false)
const scenePickerOpen = ref(false)
const scenePickerData = ref([])
const audioRef = ref(null)

// Audio
function toggleAudio() {
  if (!audioRef.value) return
  if (isPlaying.value) {
    audioRef.value.pause()
    isPlaying.value = false
  } else {
    audioRef.value.play()
    isPlaying.value = true
  }
}

function onAudioTimeUpdate() {
  if (audioRef.value) currentTime.value = audioRef.value.currentTime
}

function onAudioEnded() {
  isPlaying.value = false
  currentTime.value = 0
}

function seekAudio(e) {
  if (!audioRef.value) return
  const rect = e.currentTarget.getBoundingClientRect()
  const pct = (e.clientX - rect.left) / rect.width
  audioRef.value.currentTime = pct * audioRef.value.duration
}

const audioDuration = computed(() => audioRef.value?.duration || 0)
const audioProgress = computed(() => {
  if (!audioDuration.value) return 0
  return (currentTime.value / audioDuration.value) * 100
})

function formatTime(secs) {
  if (!secs || isNaN(secs)) return '0:00'
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

// Scene loading
async function loadCurrentScenes() {
  try {
    const data = await loadSceneHistory()
    if (data && data.length) {
      scenePickerData.value = data
      scenePickerOpen.value = true
    } else {
      toast.warning('No scene history found.')
    }
  } catch {
    toast.error('Failed to load scene history.')
  }
}

function pickScene(entry) {
  loadScenes(entry)
  projectId.value = entry.project_id || `project_${Date.now()}`
  scenePickerOpen.value = false
  toast.success(`Loaded ${entry.scenes?.length || 0} scenes.`)
}

async function loadFromHistoryProject(pid) {
  try {
    await loadFromHistory(pid)
    projectId.value = pid
    historyVisible.value = false
    toast.success('Project loaded.')
  } catch {
    toast.error('Failed to load project.')
  }
}

async function showHistory() {
  await loadHistory()
  historyVisible.value = true
}

// Grabber actions
async function onStart() {
  if (!projectId.value) projectId.value = `project_${Date.now()}`
  try {
    await startGrabber(projectId.value)
    toast.success('Grabber started.')
  } catch {
    toast.error('Failed to start grabber.')
  }
}

async function onStop() {
  stopGrabber()
  toast.info('Grabber stopped.')
}

async function onResendSelected() {
  if (!projectId.value) projectId.value = `project_${Date.now()}`
  try {
    await resendSelected(projectId.value)
    toast.success('Resending selected scenes.')
  } catch {
    toast.error('Failed to resend.')
  }
}

// Card actions
function onSavePrompt(idx, text) {
  savePrompt(idx, text)
  toast.success('Prompt updated.')
}

function onCopyPrompt(idx) {
  copyPrompt(idx)
  toast.success('Prompt copied.')
}

async function onOpenFolder(idx) {
  if (!projectId.value) return
  try {
    await openFolder(idx, projectId.value)
  } catch {
    toast.error('Failed to open folder.')
  }
}

function onDownloadScene(idx) {
  downloadScene(idx, projectId.value)
}

function onOpenLightbox(scene, file) {
  const status = sceneStatuses.value[scene.index]
  const files = status?.local_files || status?.urls || []
  if (!files.length) return
  const fileIdx = file ? files.indexOf(file) : 0
  openLightbox(scene, file)
}

// Analysis chips
const analysisChips = computed(() => {
  if (!analysisData.value) return []
  const data = analysisData.value
  const chips = []
  if (data.mood) chips.push({ label: 'Mood', value: data.mood, color: '#A78BFA' })
  if (data.environment) chips.push({ label: 'Environment', value: data.environment, color: '#4ECDC4' })
  if (data.style) chips.push({ label: 'Style', value: data.style, color: '#FFB347' })
  if (data.time_of_day) chips.push({ label: 'Time', value: data.time_of_day, color: '#F472B6' })
  if (data.color_palette) chips.push({ label: 'Palette', value: data.color_palette, color: '#60A5FA' })
  if (data.genre) chips.push({ label: 'Genre', value: data.genre, color: '#34D399' })
  if (data.theme) chips.push({ label: 'Theme', value: data.theme, color: '#FBBF24' })
  return chips
})

// Lightbox file list
const lightboxFiles = computed(() => {
  if (!lightboxScene.value) return []
  const status = sceneStatuses.value[lightboxScene.value.index]
  return status?.local_files || status?.urls || []
})

const lightboxInitialIndex = computed(() => {
  if (!lightboxFile.value || !lightboxFiles.value.length) return 0
  const idx = lightboxFiles.value.indexOf(lightboxFile.value)
  return idx >= 0 ? idx : 0
})

// History counts
function historyStatusCounts(project) {
  const counts = { ready: 0, error: 0, pending: 0 }
  if (project.scene_statuses) {
    for (const st of Object.values(project.scene_statuses)) {
      if (st.status === 'ready') counts.ready++
      else if (st.status === 'error') counts.error++
      else counts.pending++
    }
  }
  return counts
}

onMounted(() => {
  loadHistory()
})
</script>

<template>
  <div class="assets-page">
    <!-- Header -->
    <div class="page-header">
      <h2 class="page-title">Asset Manager</h2>
      <span v-if="projectId" class="project-badge">{{ projectId }}</span>
    </div>
    <p class="page-subtitle">Generate, download, and manage visual assets for your scenes.</p>

    <!-- AI Analysis Bar -->
    <section
      v-if="analysisChips.length"
      class="card analysis-card"
    >
      <button class="analysis-toggle" @click="analysisOpen = !analysisOpen">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4M12 8h.01" />
        </svg>
        <span>AI Analysis</span>
        <svg
          class="chevron"
          :class="{ open: analysisOpen }"
          width="14" height="14" viewBox="0 0 24 24"
          fill="none" stroke="currentColor" stroke-width="2"
        >
          <polyline points="6,9 12,15 18,9" />
        </svg>
      </button>
      <div v-if="analysisOpen" class="analysis-chips">
        <span
          v-for="chip in analysisChips"
          :key="chip.label"
          class="analysis-chip"
          :style="{ background: chip.color + '15', color: chip.color }"
        >
          <strong>{{ chip.label }}:</strong> {{ chip.value }}
        </span>
      </div>
    </section>

    <!-- Source Info -->
    <section class="card">
      <h3 class="card-heading">Source</h3>
      <div class="source-row">
        <div class="source-actions">
          <button class="btn-primary" @click="loadCurrentScenes">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14,2 14,8 20,8" />
            </svg>
            Load Current Scenes
          </button>
          <button class="btn-secondary" @click="showHistory">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12,6 12,12 16,14" />
            </svg>
            Pick from History
          </button>
        </div>
        <span v-if="sceneCount" class="scene-count-badge">
          {{ sceneCount }} scene{{ sceneCount !== 1 ? 's' : '' }}
        </span>
      </div>
    </section>

    <!-- Scene Picker Modal -->
    <div v-if="scenePickerOpen" class="modal-backdrop" @click.self="scenePickerOpen = false">
      <div class="modal-panel">
        <div class="modal-header">
          <h3>Pick Scenes</h3>
          <button class="modal-close" @click="scenePickerOpen = false">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <div
            v-for="(entry, i) in scenePickerData"
            :key="i"
            class="picker-row"
            @click="pickScene(entry)"
          >
            <span class="picker-label">{{ entry.project_id || entry.title || `Set ${i + 1}` }}</span>
            <span class="picker-count">{{ entry.scenes?.length || 0 }} scenes</span>
          </div>
          <div v-if="!scenePickerData.length" class="picker-empty">No scene sets found.</div>
        </div>
      </div>
    </div>

    <!-- Audio Player -->
    <section v-if="audioUrl" class="card audio-card">
      <audio
        ref="audioRef"
        :src="audioUrl"
        preload="metadata"
        @timeupdate="onAudioTimeUpdate"
        @ended="onAudioEnded"
      />
      <div class="audio-player">
        <button class="audio-play-btn" @click="toggleAudio">
          <svg v-if="!isPlaying" width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M8 5v14l11-7z" />
          </svg>
          <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" />
          </svg>
        </button>
        <div class="audio-progress" @click="seekAudio">
          <div class="audio-track">
            <div class="audio-fill" :style="{ width: audioProgress + '%' }" />
            <!-- Scene markers -->
            <template v-if="audioDuration">
              <span
                v-for="scene in scenes"
                :key="'marker-' + scene.index"
                class="scene-marker"
                :style="{ left: ((scene.start_time || 0) / audioDuration * 100) + '%' }"
                :title="'Scene ' + (scene.index + 1)"
              />
            </template>
          </div>
        </div>
        <span class="audio-time">
          {{ formatTime(currentTime) }} / {{ formatTime(audioDuration) }}
        </span>
      </div>
    </section>

    <!-- Controls -->
    <GrabberControls
      :provider="provider"
      :arguments="args"
      :aspect-ratio="aspectRatio"
      :provider-options="providerOptions"
      :grabber-running="grabberRunning"
      :progress="progress"
      :selected-count="selectedCount"
      :scene-count="sceneCount"
      @update:provider="setProvider"
      @update:arguments="setArguments"
      @update:aspect-ratio="setAspectRatio"
      @update:provider-option="(k, v) => setProviderOption(k, v)"
      @update:auto-type="(v) => setProviderOption('auto_type', v)"
      @start="onStart"
      @stop="onStop"
      @select-all="selectAll"
      @select-pending="selectPending"
      @select-none="selectNone"
      @resend-selected="onResendSelected"
    />

    <!-- Asset Grid -->
    <section v-if="sceneCount" class="asset-grid">
      <AssetCard
        v-for="scene in scenes"
        :key="scene.index"
        :scene="scene"
        :scene-index="scene.index"
        :status="sceneStatuses[scene.index] || {}"
        :selected="selectedScenes.has(scene.index)"
        :provider="provider"
        @toggle-select="toggleSelect"
        @edit-prompt="editPrompt"
        @save-prompt="onSavePrompt"
        @copy-prompt="onCopyPrompt"
        @download="onDownloadScene"
        @open-folder="onOpenFolder"
        @open-lightbox="onOpenLightbox"
      />
    </section>

    <!-- Empty State -->
    <section v-else class="card empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" class="empty-icon">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <circle cx="8.5" cy="8.5" r="1.5" />
        <path d="m21 15-5-5L5 21" />
      </svg>
      <p class="empty-title">No scenes loaded</p>
      <p class="empty-desc">Load scenes from the scene generator or pick from history to get started.</p>
    </section>

    <!-- History -->
    <section v-if="historyVisible" class="card">
      <h3 class="card-heading">Project History</h3>
      <div v-if="history.length" class="history-list">
        <div
          v-for="project in history"
          :key="project.project_id"
          class="history-item"
        >
          <div class="history-thumb">
            <img
              v-if="project.thumbnail"
              :src="'/output/assets/' + project.thumbnail"
              alt=""
            />
            <div v-else class="history-thumb-placeholder">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="3" y="3" width="18" height="18" rx="2" />
              </svg>
            </div>
          </div>
          <div class="history-info">
            <span class="history-name">{{ project.project_id }}</span>
            <div class="history-counts">
              <span v-if="historyStatusCounts(project).ready" class="count-ready">
                {{ historyStatusCounts(project).ready }} ready
              </span>
              <span v-if="historyStatusCounts(project).error" class="count-error">
                {{ historyStatusCounts(project).error }} error
              </span>
              <span v-if="historyStatusCounts(project).pending" class="count-pending">
                {{ historyStatusCounts(project).pending }} pending
              </span>
            </div>
          </div>
          <button class="btn-secondary btn-sm" @click="loadFromHistoryProject(project.project_id)">
            Load
          </button>
        </div>
      </div>
      <div v-else class="history-empty">
        No project history found.
      </div>
    </section>

    <!-- Lightbox -->
    <AssetLightbox
      v-if="lightboxOpen && lightboxScene"
      :scene="lightboxScene"
      :files="lightboxFiles"
      :initial-index="lightboxInitialIndex"
      @close="closeLightbox"
    />
  </div>
</template>

<style scoped>
.assets-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 0 20px 40px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ---- Header ---- */
.page-header {
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
  color: var(--accent);
  background: rgba(78, 205, 196, 0.1);
  padding: 3px 10px;
  border-radius: 8px;
}

.page-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
  margin-top: -12px;
}

/* ---- Card base ---- */
.card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}

.card-heading {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 12px;
}

/* ---- Analysis ---- */
.analysis-card {
  padding: 14px 20px;
}

.analysis-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  background: none;
  border: none;
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  width: 100%;
}

.chevron {
  margin-left: auto;
  transition: transform 0.2s;
}

.chevron.open {
  transform: rotate(180deg);
}

.analysis-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.analysis-chip {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 20px;
  white-space: nowrap;
}

.analysis-chip strong {
  font-weight: 600;
}

/* ---- Source ---- */
.source-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.source-actions {
  display: flex;
  gap: 8px;
}

.btn-primary,
.btn-secondary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: opacity 0.15s;
}

.btn-primary {
  background: var(--accent);
  color: #0d1117;
}

.btn-secondary {
  background: var(--bg-deeper, #0a0a0a);
  color: var(--text-secondary);
  border: 1px solid var(--border);
}

.btn-primary:hover,
.btn-secondary:hover {
  opacity: 0.9;
}

.btn-sm {
  font-size: 12px;
  padding: 5px 12px;
}

.scene-count-badge {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--accent);
  background: rgba(78, 205, 196, 0.1);
  padding: 4px 12px;
  border-radius: 8px;
  font-weight: 600;
}

/* ---- Audio Player ---- */
.audio-card {
  padding: 14px 20px;
}

.audio-player {
  display: flex;
  align-items: center;
  gap: 12px;
}

.audio-play-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent);
  color: #0d1117;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  transition: opacity 0.15s;
}

.audio-play-btn:hover {
  opacity: 0.85;
}

.audio-progress {
  flex: 1;
  cursor: pointer;
  padding: 8px 0;
}

.audio-track {
  position: relative;
  width: 100%;
  height: 4px;
  background: var(--bg-deeper, #0a0a0a);
  border-radius: 2px;
}

.audio-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
  transition: width 0.1s linear;
}

.scene-marker {
  position: absolute;
  top: -3px;
  width: 2px;
  height: 10px;
  background: rgba(255, 255, 255, 0.3);
  border-radius: 1px;
  pointer-events: none;
}

.audio-time {
  flex-shrink: 0;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-secondary);
  min-width: 80px;
  text-align: right;
}

/* ---- Asset Grid ---- */
.asset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

/* ---- Empty State ---- */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 20px;
  text-align: center;
}

.empty-icon {
  color: var(--text-secondary);
  opacity: 0.4;
  margin-bottom: 16px;
}

.empty-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 6px;
}

.empty-desc {
  font-size: 13px;
  color: var(--text-secondary);
  max-width: 360px;
}

/* ---- History ---- */
.history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--bg-deeper, #0a0a0a);
  border: 1px solid var(--border);
  border-radius: 8px;
  transition: border-color 0.15s;
}

.history-item:hover {
  border-color: var(--text-secondary);
}

.history-thumb {
  width: 48px;
  height: 36px;
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
  background: var(--bg-surface);
}

.history-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.history-thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  opacity: 0.4;
}

.history-info {
  flex: 1;
  min-width: 0;
}

.history-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-counts {
  display: flex;
  gap: 8px;
  margin-top: 2px;
}

.count-ready {
  font-size: 11px;
  color: #22C55E;
}

.count-error {
  font-size: 11px;
  color: #EF4444;
}

.count-pending {
  font-size: 11px;
  color: #9CA3AF;
}

.history-empty {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 12px 0;
}

/* ---- Scene Picker Modal ---- */
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-panel {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  width: 480px;
  max-width: 90vw;
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
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.modal-close {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
}

.modal-close:hover {
  color: var(--text);
}

.modal-body {
  padding: 12px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.picker-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}

.picker-row:hover {
  background: rgba(78, 205, 196, 0.06);
}

.picker-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
}

.picker-count {
  font-size: 12px;
  color: var(--text-secondary);
  font-family: var(--font-mono);
}

.picker-empty {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 20px;
  text-align: center;
}
</style>
