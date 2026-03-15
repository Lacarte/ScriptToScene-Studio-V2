<script setup>
import { computed, onMounted, ref } from 'vue'
import { useSegmenter } from '../composables/useSegmenter.js'
import { useTiming } from '@/features/timing/composables/useTiming.js'
import { useToast } from '@/shared/composables/useToast.js'
import { timeAgo } from '@/shared/utils/format.js'
import { useProjectSync } from '@/shared/composables/useProjectSync.js'
import SegmentTimeline from '../components/SegmentTimeline.vue'
import SegmentCard from '../components/SegmentCard.vue'
import AlignmentPicker from '../components/AlignmentPicker.vue'

defineOptions({ name: 'SegmenterPage' })

const {
  alignment,
  alignmentSource,
  sourceFolder,
  projectId,
  config,
  result,
  isRunning,
  hasAlignment,
  hasResult,
  segments,
  stats,
  totalDuration,
  audioUrl,
  isPlaying,
  currentTime,
  activeSegmentIdx,
  history,
  timingHistory,
  setAlignment,
  updateConfig,
  runSegmenter,
  loadHistory,
  loadResult,
  loadTimingHistory,
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
} = useSegmenter()

const timing = useTiming()
const toast = useToast()

const showPicker = ref(false)
useProjectSync(projectId)

const sourceInfoText = computed(() => {
  if (!hasAlignment.value) return 'No alignment selected'
  const wordCount = alignment.value.length
  const duration = wordCount ? alignment.value[wordCount - 1].end || 0 : 0
  const label = sourceFolder.value || 'uploaded'
  const pid = projectId.value ? `${projectId.value} · ` : ''
  return `${pid}${wordCount} words · ${duration.toFixed(1)}s from ${label}`
})

const resultsSummary = computed(() => {
  if (!stats.value) return ''
  const parts = []
  if (projectId.value) parts.push(projectId.value)
  parts.push(`${stats.value.segment_count ?? segments.value.length} segments`)
  parts.push(`${stats.value.filler_count ?? 0} fillers`)
  parts.push(`avg ${formatDuration(stats.value.avg_duration)}`)
  parts.push(`range ${formatDuration(stats.value.min_duration)} - ${formatDuration(stats.value.max_duration)}`)
  return parts.join(' · ')
})

const historyCountLabel = computed(() => {
  const count = history.value.length
  return `${count} result${count === 1 ? '' : 's'}`
})

const activeHistoryFolder = computed(() => result.value?.output_folder || '')

const displaySegments = computed(() => {
  let speechIndex = 0
  return segments.value.map((segment, arrayIndex) => {
    const item = {
      key: `${segment.index ?? arrayIndex}-${segment.start ?? 0}`,
      segment,
      arrayIndex,
      displayIndex: speechIndex,
    }
    if (!segment.is_filler) {
      speechIndex += 1
    }
    return item
  })
})

onMounted(async () => {
  await Promise.allSettled([loadHistory(), loadTimingHistory()])
  // Load audio if we already have alignment data
  if (sourceFolder.value) {
    await loadAudio()
  }
})

async function useCurrentResult() {
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
  await loadAudio()
  toast.success('Alignment loaded from current result.')
}

async function openPicker() {
  await loadTimingHistory()
  showPicker.value = true
}

async function onPickAlignment(item) {
  setAlignment({
    alignment: item.alignment || item.word_alignment || [],
    transcript: item.transcript || '',
    folder: item.folder || '',
    project_id: item.project_id || '',
    source_file: item.source_file || '',
  })
  showPicker.value = false
  await loadAudio()
  toast.success('Alignment loaded from history.')
}

async function onRun() {
  try {
    await runSegmenter()
    await loadHistory()
    await loadAudio()
    toast.success('Segmentation complete.')
  } catch (err) {
    toast.error(err.message || 'Segmenter failed.')
  }
}

function togglePlayback() {
  togglePlay()
}

function playFromSegment({ segment }) {
  playSegment(segment)
}

function handleSeek(time) {
  seekTo(time)
}

async function onHistoryClick(item) {
  const folder = item.folder || item.source_folder
  if (!folder) return

  try {
    await loadResult(folder)
    await loadAudio()
    toast.success('Loaded saved result.')
  } catch {
    toast.error('Failed to load result.')
  }
}

function onCopy() {
  copyJSON()
  toast.success('JSON copied to clipboard.')
}

function formatDuration(value) {
  if (!Number.isFinite(value)) return '--'
  return `${value.toFixed(2)}s`
}

function formatTotal(value) {
  if (!Number.isFinite(value)) return '--'
  return `${value.toFixed(1)}s total`
}

const relativeTime = timeAgo
</script>

<template>
  <div class="segmenter-page mx-auto px-6 py-8" style="max-width: 780px">

    <div style="margin-bottom: 16px">
      <div style="display: flex; align-items: center; gap: 10px">
        <h2 class="font-display text-2xl font-bold tracking-tight" style="color: var(--text)">Segmenter</h2>
        <span v-if="projectId" class="module-project-badge visible">{{ projectId }}</span>
      </div>
      <p class="text-sm mt-1" style="color: var(--text-secondary)">
        Split alignment into timed segments for scene generation
      </p>
    </div>

    <section class="card p-5 mb-4">
      <label class="block text-[10px] font-bold uppercase tracking-[0.15em] mb-2.5" style="color: var(--text-muted)">
        Alignment Source
      </label>
      <div class="flex gap-3 mb-3 flex-wrap">
        <button class="action-btn hover-accent" style="padding: 6px 14px; font-size: 11px" @click="useCurrentResult">
          Use Current Result
        </button>
        <button class="action-btn hover-accent" style="padding: 6px 14px; font-size: 11px" @click="openPicker">
          Pick from History
        </button>
      </div>
      <div class="font-mono source-info" :class="{ empty: !hasAlignment }">{{ sourceInfoText }}</div>
    </section>

    <section class="card p-5 mb-4">
      <label class="block text-[10px] font-bold uppercase tracking-[0.15em] mb-3" style="color: var(--text-muted)">
        Segment Config
      </label>
      <div class="grid grid-cols-2 gap-x-6 gap-y-3" style="max-width: 500px">
        <div>
          <div class="config-row">
            <span>Target Min</span>
            <span class="font-mono config-value">{{ config.target_min.toFixed(1) }}s</span>
          </div>
          <input
            type="range"
            :value="config.target_min"
            min="0.5"
            max="3.0"
            step="0.1"
            class="config-range"
            @input="updateConfig('target_min', parseFloat($event.target.value))"
          />
        </div>
        <div>
          <div class="config-row">
            <span>Target Max</span>
            <span class="font-mono config-value">{{ config.target_max.toFixed(1) }}s</span>
          </div>
          <input
            type="range"
            :value="config.target_max"
            min="2.0"
            max="6.0"
            step="0.1"
            class="config-range"
            @input="updateConfig('target_max', parseFloat($event.target.value))"
          />
        </div>
        <div>
          <div class="config-row">
            <span>Hard Max</span>
            <span class="font-mono config-value">{{ config.hard_max.toFixed(1) }}s</span>
          </div>
          <input
            type="range"
            :value="config.hard_max"
            min="3.0"
            max="8.0"
            step="0.1"
            class="config-range"
            @input="updateConfig('hard_max', parseFloat($event.target.value))"
          />
        </div>
        <div>
          <div class="config-row">
            <span>Gap Filler</span>
            <span class="font-mono config-value">{{ config.gap_filler.toFixed(1) }}s</span>
          </div>
          <input
            type="range"
            :value="config.gap_filler"
            min="0.1"
            max="1.0"
            step="0.05"
            class="config-range"
            @input="updateConfig('gap_filler', parseFloat($event.target.value))"
          />
        </div>
      </div>
    </section>

    <button
      class="gen-btn w-full"
      style="padding: 14px 24px; border-radius: 12px; font-size: 14px; font-weight: 700; font-family: 'JetBrains Mono', 'Fira Code', monospace; letter-spacing: 0.02em; color: white; cursor: pointer; transition: all 0.3s cubic-bezier(0.16,1,0.3,1); border: none; position: relative; overflow: hidden"
      :disabled="!hasAlignment || isRunning"
      @click="onRun"
    >
      <span v-if="isRunning" class="button-spinner" />
      <span>{{ isRunning ? 'Segmenting...' : 'Run Segmenter' }}</span>
    </button>

    <div v-if="hasResult" style="margin-top: 20px">
      <section class="card p-5">
        <div class="flex items-center justify-between mb-3">
          <label class="block text-[10px] font-bold uppercase tracking-[0.15em]" style="color: var(--text-muted)">
            Results
          </label>
          <div style="display: flex; gap: 6px">
            <button class="action-btn hover-accent" @click="onCopy">Copy JSON</button>
            <button class="action-btn hover-accent" @click="downloadJSON">Download</button>
          </div>
        </div>

        <div v-if="hasResult && stats" class="font-mono results-summary">
          <span v-if="projectId" class="rs-project">{{ projectId }}</span>
          <span v-if="projectId" class="rs-dot"> · </span>
          <span class="rs-segments">{{ stats.segment_count ?? segments.length }} segments</span>
          <span class="rs-dot"> · </span>
          <span class="rs-fillers">{{ stats.filler_count ?? 0 }} fillers</span>
          <span class="rs-dot"> · </span>
          <span class="rs-avg">avg {{ formatDuration(stats.avg_duration) }}</span>
          <span class="rs-dot"> · </span>
          <span class="rs-range">range {{ formatDuration(stats.min_duration) }} – {{ formatDuration(stats.max_duration) }}</span>
        </div>

        <div style="margin-bottom: 16px">
          <SegmentTimeline
            :segments="segments"
            :active-index="activeSegmentIdx"
            :total-duration="totalDuration"
            :current-time="currentTime"
            :is-playing="isPlaying"
            :has-audio="Boolean(audioUrl)"
            @toggle-play="togglePlayback"
            @play-segment="playFromSegment"
            @seek="seekTo"
          />
        </div>

        <div style="display: flex; flex-direction: column; gap: 6px; max-height: 600px; overflow-y: auto; padding-right: 4px">
          <SegmentCard
            v-for="item in displaySegments"
            :key="item.key"
            :segment="item.segment"
            :index="item.arrayIndex"
            :display-index="item.displayIndex"
            :is-active="item.arrayIndex === activeSegmentIdx"
            @play="playFromSegment({ segment: item.segment })"
          />
        </div>
      </section>
    </div>

    <div style="margin-top: 16px">
      <div class="flex items-center justify-between mb-3">
        <h3 class="history-title">History</h3>
        <span class="font-mono text-xs" style="color: var(--text-muted)">{{ historyCountLabel }}</span>
      </div>

      <div v-if="history.length" class="history-list">
        <button
          v-for="item in history"
          :key="item.folder || item.source_folder"
          class="history-item"
          :class="{ active: activeHistoryFolder === (item.folder || item.source_folder) }"
          @click="onHistoryClick(item)"
        >
          <div class="history-item-body">
            <div class="history-item-title-row">
              <span class="history-item-title">{{ item.project_id || item.source_folder || item.folder }}</span>
              <span
                v-if="activeHistoryFolder === (item.folder || item.source_folder)"
                class="font-mono history-active-badge"
              >
                ACTIVE
              </span>
            </div>

            <div class="font-mono history-item-meta">
              <span style="color: var(--accent)">{{ item.segment_count }} segments</span>
              <span class="history-divider">/</span>
              <span style="color: var(--accent-warning)">{{ item.filler_count }} fillers</span>
              <span class="history-divider">/</span>
              <span style="color: var(--text-secondary)">avg {{ formatDuration(item.avg_duration) }}</span>
              <span class="history-divider">/</span>
              <span style="color: var(--text-secondary)">{{ formatTotal(item.total_duration) }}</span>
              <span class="history-divider">/</span>
              <span>{{ relativeTime(item.segmented_at || item.timestamp || item.created_at) }}</span>
            </div>
          </div>

          <svg
            class="history-chevron"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            aria-hidden="true"
          >
            <path d="M9 18l6-6-6-6" />
          </svg>
        </button>
      </div>

      <p v-else class="history-empty">No segmentations yet</p>
    </div>

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
  width: 100%;
}

.source-info {
  font-size: 12px;
  color: var(--accent);
}

.source-info.empty {
  color: var(--text-muted);
}

.config-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
  font-size: 11px;
  color: var(--text-secondary);
}

.config-value {
  color: var(--accent);
}

.config-range {
  width: 100%;
  accent-color: var(--accent);
}

.button-spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  margin-right: 8px;
  vertical-align: middle;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

.results-summary {
  font-size: 11px;
  margin-bottom: 12px;
  color: var(--text-muted);
}

.rs-project {
  color: var(--accent);
}

.rs-segments {
  color: #4ECDC4;
}

.rs-fillers {
  color: #FFB347;
}

.rs-avg {
  color: #A78BFA;
}

.rs-range {
  color: #7DD3FC;
}

.rs-dot {
  opacity: 0.3;
}

.history-title {
  margin: 0;
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
}

.history-list {
  max-height: 400px;
  overflow-y: auto;
}

.history-item {
  width: 100%;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 6px;
  color: var(--text);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.history-item:hover {
  border-color: var(--border-hover);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
}

.history-item.active {
  border-color: var(--accent-active);
  box-shadow: inset 3px 0 0 var(--accent-active), 0 0 12px rgba(255, 159, 67, 0.15);
}

.history-item-body {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 12px 4px 14px;
}

.history-item-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 3px;
}

.history-item-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--text);
}

.history-item.active .history-item-title {
  color: var(--text);
  font-weight: 600;
}

.history-active-badge {
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(78, 205, 196, 0.15);
  color: var(--accent);
  font-size: 8px;
  letter-spacing: 0.05em;
}

.history-item-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin: 0;
  font-size: 10px;
  color: var(--text-muted);
}

.history-divider {
  opacity: 0.3;
}

.history-chevron {
  margin-left: auto;
  flex-shrink: 0;
  color: var(--text-muted);
  opacity: 0.4;
}

.history-item.active .history-chevron {
  color: var(--accent-active);
  opacity: 0.8;
}

.history-empty {
  padding: 32px 0;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
