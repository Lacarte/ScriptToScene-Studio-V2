<script setup>
import { ref, onBeforeUnmount } from 'vue'
import { formatBytes, formatDuration, timeAgo, ratioLabel } from '../composables/useExportLibrary.js'

defineOptions({ name: 'ExportCard' })

const props = defineProps({
  item: { type: Object, required: true },
})

const emit = defineEmits(['download-video', 'download-zip', 'play'])

const videoEl = ref(null)
const playing = ref(false)
const hovered = ref(false)

function handleMouseEnter() {
  hovered.value = true
  play()
}

function handleMouseLeave() {
  hovered.value = false
  pause()
}

function play() {
  if (!videoEl.value) return
  emit('play', videoEl.value)
  videoEl.value.play().catch(() => {})
  playing.value = true
}

function pause() {
  if (!videoEl.value) return
  videoEl.value.pause()
  playing.value = false
}

/** Called from parent to stop playback when another card starts */
function stopPlayback() {
  pause()
}

onBeforeUnmount(() => {
  pause()
})

defineExpose({ stopPlayback, videoEl })
</script>

<template>
  <div
    class="export-card"
    @mouseenter="handleMouseEnter"
    @mouseleave="handleMouseLeave"
  >
    <!-- Video preview -->
    <div class="card-preview">
      <video
        ref="videoEl"
        :src="item.preview_url"
        :poster="item.preview_url"
        class="card-video"
        preload="metadata"
        muted
        loop
        playsinline
        @click="playing ? pause() : play()"
      />
      <div v-if="!playing" class="play-overlay">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="currentColor">
          <path d="M8 5v14l11-7z" />
        </svg>
      </div>
      <span v-if="item.duration" class="duration-badge">
        {{ formatDuration(item.duration) }}
      </span>
    </div>

    <!-- Card body -->
    <div class="card-body">
      <div class="card-title-row">
        <span class="card-title" :title="item.video_name">
          {{ item.video_name || 'Untitled' }}
        </span>
        <span class="card-time">{{ timeAgo(item.modified_at) }}</span>
      </div>

      <div class="card-project-id" :title="item.project_id">
        {{ item.project_id }}
      </div>

      <div class="card-meta">
        <span class="meta-item" v-if="item.size_bytes">
          {{ formatBytes(item.size_bytes) }}
        </span>
        <span class="meta-item" v-if="item.video_ratio || item.ratio">
          {{ ratioLabel(item.video_ratio || item.ratio) }}
        </span>
        <span class="meta-item" v-if="item.scene_count">
          {{ item.scene_count }} scenes
        </span>
        <span class="style-badge" v-if="item.style">
          {{ item.style }}
        </span>
      </div>

      <div class="card-actions">
        <button class="btn-download btn-video" @click="emit('download-video', item)">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          Video
        </button>
        <button
          class="btn-download btn-zip"
          :disabled="!item.zip_download_url"
          @click="emit('download-zip', item)"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          ZIP
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.export-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
  display: flex;
  flex-direction: column;
}

.export-card:hover {
  border-color: var(--border-hover);
  box-shadow: var(--shadow-sm);
}

/* ── Preview ─────────────────────────── */

.card-preview {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: var(--bg-dark);
  cursor: pointer;
  overflow: hidden;
}

.card-video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.play-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.35);
  color: rgba(255, 255, 255, 0.85);
  pointer-events: none;
  transition: opacity 0.2s;
}

.export-card:hover .play-overlay {
  opacity: 0;
}

.duration-badge {
  position: absolute;
  bottom: 8px;
  right: 8px;
  background: rgba(0, 0, 0, 0.75);
  color: #fff;
  font-family: var(--font-mono);
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 4px;
  pointer-events: none;
}

/* ── Body ────────────────────────────── */

.card-body {
  padding: 14px 16px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
}

.card-title-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.card-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.card-time {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.card-project-id {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ── Meta ────────────────────────────── */

.card-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
}

.meta-item {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--bg-dark);
  padding: 2px 8px;
  border-radius: 4px;
}

.style-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  background: var(--accent-dim);
  padding: 2px 8px;
  border-radius: 10px;
  white-space: nowrap;
}

/* ── Actions ─────────────────────────── */

.card-actions {
  display: flex;
  gap: 8px;
  margin-top: auto;
  padding-top: 4px;
}

.btn-download {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 7px 0;
  font-size: 12px;
  font-weight: 600;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
  border: none;
}

.btn-video {
  background: var(--accent);
  color: var(--bg-darkest);
}

.btn-video:hover {
  background: var(--accent-hover);
}

.btn-zip {
  background: var(--bg-elevated);
  color: var(--text);
  border: 1px solid var(--border);
}

.btn-zip:hover:not(:disabled) {
  border-color: var(--border-hover);
  background: var(--bg-surface-hover);
}

.btn-download:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
</style>
