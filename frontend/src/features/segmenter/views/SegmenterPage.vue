<script setup>
import { ref, onMounted } from 'vue'
import { useSegmenter } from '../composables/useSegmenter.js'
import { useTiming } from '@/features/timing/composables/useTiming.js'
import { useToast } from '@/shared/composables/useToast.js'
import SegmentTimeline from '../components/SegmentTimeline.vue'
import SegmentCard from '../components/SegmentCard.vue'
import AlignmentPicker from '../components/AlignmentPicker.vue'

defineOptions({ name: 'SegmenterPage' })

const {
  alignment, alignmentSource, projectId, config, isRunning,
  hasAlignment, hasResult, segments, stats, totalDuration,
  audioUrl, isPlaying, currentTime, activeSegmentIdx,
  history, timingHistory,
  setAlignment, updateConfig, runSegmenter,
  loadHistory, loadResult, loadTimingHistory,
  updateActiveSegment, setPlaying, setDuration,
  copyJSON, downloadJSON,
} = useSegmenter()

const timing = useTiming()
const toast = useToast()

const showPicker = ref(false)
const audioRef = ref(null)

onMounted(() => {
  loadHistory()
  loadTimingHistory()
})

/* ── Alignment source ── */

function useCurrentResult() {
  if (!timing.alignment.value.length) {
    toast.error('No alignment result available. Run timing first.')
    return
  }
  setAlignment({
    alignment: timing.alignment.value,
    transcript: timing.transcript.value,
    folder: timing.sourceFolder.value,
    project_id: timing.projectId.value,
    source_file: timing.sourceFile.value,
  })
  toast.success('Alignment loaded from current result.')
}

async function openPicker() {
  await loadTimingHistory()
  showPicker.value = true
}

function onPickAlignment(item) {
  setAlignment({
    alignment: item.alignment || [],
    transcript: item.transcript || '',
    folder: item.folder || '',
    project_id: item.project_id || '',
    source_file: item.source_file || '',
  })
  showPicker.value = false
  toast.success('Alignment loaded from history.')
}

/* ── Run ── */

async function onRun() {
  try {
    await runSegmenter()
    await loadHistory()
    toast.success('Segmentation complete.')
  } catch (err) {
    toast.error(err.message || 'Segmenter failed.')
  }
}

/* ── Audio playback ── */

function playFromSegment({ segment }) {
  const audio = audioRef.value
  if (!audio || !audioUrl.value) return
  audio.currentTime = segment.start
  audio.play()
}

function seekTo(time) {
  const audio = audioRef.value
  if (!audio || !audioUrl.value) return
  audio.currentTime = time
}

function onTimeUpdate() {
  const audio = audioRef.value
  if (!audio) return
  updateActiveSegment(audio.currentTime)
}

function onPlay() { setPlaying(true) }
function onPause() { setPlaying(false) }
function onLoadedMetadata() {
  const audio = audioRef.value
  if (audio) setDuration(audio.duration)
}

/* ── History ── */

async function onHistoryClick(item) {
  try {
    await loadResult(item.folder || item.source_folder)
    toast.success('Loaded saved result.')
  } catch {
    toast.error('Failed to load result.')
  }
}

/* ── Export ── */

function onCopy() {
  copyJSON()
  toast.success('JSON copied to clipboard.')
}

/* ── Helpers ── */

function formatDuration(val) {
  if (val == null) return '--'
  return val.toFixed(2) + 's'
}

function formatDate(ts) {
  if (!ts) return '--'
  const d = new Date(ts)
  return d.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <div class="segmenter-page">
    <!-- Hidden audio element -->
    <audio
      v-if="audioUrl"
      ref="audioRef"
      :src="audioUrl"
      @timeupdate="onTimeUpdate"
      @play="onPlay"
      @pause="onPause"
      @loadedmetadata="onLoadedMetadata"
    />

    <!-- Header -->
    <div class="page-header">
      <div class="title-row">
        <h2 class="page-title">Segmenter</h2>
        <span v-if="projectId" class="project-badge">{{ projectId }}</span>
      </div>
      <p class="page-subtitle">Split alignment into timed segments for scene generation</p>
    </div>

    <!-- Alignment Source -->
    <section class="card">
      <h3 class="card-heading">Alignment Source</h3>
      <div class="source-actions">
        <button class="btn-secondary" @click="useCurrentResult">Use Current Result</button>
        <button class="btn-secondary" @click="openPicker">Pick from History</button>
      </div>
      <p v-if="hasAlignment" class="source-info">
        <span class="source-label">Loaded:</span>
        <span class="source-value">{{ alignmentSource }}</span>
        <span class="source-detail">&middot; {{ alignment.length }} words</span>
      </p>
      <p v-else class="source-empty">No alignment loaded</p>
    </section>

    <!-- Segment Config -->
    <section class="card">
      <h3 class="card-heading">Segment Config</h3>
      <div class="config-grid">
        <div class="config-item">
          <div class="config-label-row">
            <span class="config-label">Target Min</span>
            <span class="config-value">{{ config.target_min.toFixed(1) }}s</span>
          </div>
          <input
            type="range"
            :value="config.target_min"
            min="0.5"
            max="3.0"
            step="0.1"
            @input="updateConfig('target_min', parseFloat($event.target.value))"
          />
        </div>
        <div class="config-item">
          <div class="config-label-row">
            <span class="config-label">Target Max</span>
            <span class="config-value">{{ config.target_max.toFixed(1) }}s</span>
          </div>
          <input
            type="range"
            :value="config.target_max"
            min="2.0"
            max="6.0"
            step="0.1"
            @input="updateConfig('target_max', parseFloat($event.target.value))"
          />
        </div>
        <div class="config-item">
          <div class="config-label-row">
            <span class="config-label">Hard Max</span>
            <span class="config-value">{{ config.hard_max.toFixed(1) }}s</span>
          </div>
          <input
            type="range"
            :value="config.hard_max"
            min="3.0"
            max="8.0"
            step="0.1"
            @input="updateConfig('hard_max', parseFloat($event.target.value))"
          />
        </div>
        <div class="config-item">
          <div class="config-label-row">
            <span class="config-label">Gap Filler</span>
            <span class="config-value">{{ config.gap_filler.toFixed(2) }}s</span>
          </div>
          <input
            type="range"
            :value="config.gap_filler"
            min="0.1"
            max="1.0"
            step="0.05"
            @input="updateConfig('gap_filler', parseFloat($event.target.value))"
          />
        </div>
      </div>
    </section>

    <!-- Run Button -->
    <button
      class="gen-btn"
      :disabled="!hasAlignment || isRunning"
      @click="onRun"
    >
      <span v-if="isRunning" class="spinner" />
      <span>{{ isRunning ? 'Running...' : 'Run Segmenter' }}</span>
    </button>

    <!-- Results -->
    <template v-if="hasResult">
      <!-- Stats Bar -->
      <section class="card stats-card">
        <h3 class="card-heading">Results</h3>
        <div class="stats-bar" v-if="stats">
          <div class="stat">
            <span class="stat-value">{{ stats.segment_count ?? segments.length }}</span>
            <span class="stat-label">Segments</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ stats.filler_count ?? 0 }}</span>
            <span class="stat-label">Fillers</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ formatDuration(stats.avg_duration) }}</span>
            <span class="stat-label">Avg</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ formatDuration(stats.min_duration) }}</span>
            <span class="stat-label">Min</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ formatDuration(stats.max_duration) }}</span>
            <span class="stat-label">Max</span>
          </div>
        </div>
      </section>

      <!-- Timeline -->
      <section class="card">
        <h3 class="card-heading">Timeline</h3>
        <SegmentTimeline
          :segments="segments"
          :active-index="activeSegmentIdx"
          :total-duration="totalDuration"
          :current-time="currentTime"
          @play-segment="playFromSegment"
          @seek="seekTo"
        />
      </section>

      <!-- Segment List -->
      <section class="segment-list">
        <SegmentCard
          v-for="(seg, i) in segments"
          :key="i"
          :segment="seg"
          :index="i"
          :is-active="i === activeSegmentIdx"
          @play="playFromSegment({ segment: seg, index: i })"
        />
      </section>

      <!-- Action Buttons -->
      <div class="action-row">
        <button class="btn-secondary" @click="onCopy">Copy JSON</button>
        <button class="btn-secondary" @click="downloadJSON">Download</button>
      </div>
    </template>

    <!-- History -->
    <section class="card" v-if="history.length">
      <h3 class="card-heading">History <span class="history-count">{{ history.length }}</span></h3>
      <div class="history-list">
        <button
          v-for="item in history"
          :key="item.folder || item.source_folder"
          class="history-item"
          @click="onHistoryClick(item)"
        >
          <span class="history-project">{{ item.project_id || item.folder || item.source_folder }}</span>
          <span class="history-meta">
            <span v-if="item.segment_count != null">{{ item.segment_count }} segs</span>
            <span v-if="item.timestamp || item.created_at">{{ formatDate(item.timestamp || item.created_at) }}</span>
          </span>
        </button>
      </div>
    </section>

    <!-- Alignment Picker Modal -->
    <AlignmentPicker
      :show="showPicker"
      :items="timingHistory"
      @select="onPickAlignment"
      @close="showPicker = false"
    />
  </div>
</template>

<style scoped>
.segmenter-page {
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
  letter-spacing: 0.02em;
}

.page-subtitle {
  font-size: 13px;
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

.card-heading {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 12px;
}

/* ---- Alignment Source ---- */
.source-actions {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}

.source-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.source-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--text-muted);
}

.source-value {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--accent);
}

.source-detail {
  font-size: 12px;
  color: var(--text-secondary);
}

.source-empty {
  font-size: 13px;
  color: var(--text-muted);
}

/* ---- Config Grid ---- */
.config-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px 24px;
}

.config-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.config-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.config-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--text-muted);
}

.config-value {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
}

.config-item input[type="range"] {
  width: 100%;
  height: 6px;
  -webkit-appearance: none;
  appearance: none;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 3px;
  outline: none;
  accent-color: var(--accent);
}

.config-item input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
  border: 2px solid var(--bg-surface);
}

/* ---- Run Button ---- */
.gen-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
  padding: 14px;
  font-size: 15px;
  font-weight: 600;
  font-family: var(--font-display);
  color: #000;
  background: var(--accent);
  border: none;
  border-radius: 12px;
  cursor: pointer;
  transition: opacity 0.15s, filter 0.15s;
}

.gen-btn:hover:not(:disabled) {
  filter: brightness(1.1);
}

.gen-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(0, 0, 0, 0.2);
  border-top-color: #000;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ---- Stats ---- */
.stats-card .card-heading {
  margin-bottom: 16px;
}

.stats-bar {
  display: flex;
  gap: 4px;
}

.stat {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 10px 8px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
}

.stat-value {
  font-family: var(--font-mono);
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
}

.stat-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--text-muted);
}

/* ---- Segment List ---- */
.segment-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ---- Action Row ---- */
.action-row {
  display: flex;
  gap: 10px;
}

/* ---- Buttons ---- */
.btn-secondary {
  padding: 9px 18px;
  font-size: 13px;
  font-weight: 600;
  font-family: var(--font-display);
  color: var(--text);
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm, 8px);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.btn-secondary:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.15);
}

/* ---- History ---- */
.history-count {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  margin-left: 6px;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 260px;
  overflow-y: auto;
}

.history-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  text-align: left;
  padding: 10px 14px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  color: var(--text);
  font-family: inherit;
  font-size: inherit;
}

.history-item:hover {
  background: rgba(255, 255, 255, 0.03);
  border-color: var(--border);
}

.history-project {
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}
</style>
