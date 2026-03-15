<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ratioLabel } from '../composables/useExportLibrary.js'
import { formatBytes, timeAgo, fmtDuration } from '@/shared/utils/format.js'

defineOptions({ name: 'ExportCard' })

const props = defineProps({
  item: { type: Object, required: true },
})

const emit = defineEmits(['download-video', 'download-zip', 'play'])

const videoEl = ref(null)
const loaded = ref(false)
const downloading = ref({ video: false, zip: false })

function stopPlayback() {
  if (videoEl.value && !videoEl.value.paused) {
    videoEl.value.pause()
    videoEl.value.currentTime = 0
  }
}

function onPlay() {
  emit('play', videoEl.value)
}

async function handleDownloadVideo() {
  downloading.value.video = true
  try {
    await emit('download-video', props.item)
  } finally {
    downloading.value.video = false
  }
}

async function handleDownloadZip() {
  downloading.value.zip = true
  try {
    await emit('download-zip', props.item)
  } finally {
    downloading.value.zip = false
  }
}

onBeforeUnmount(() => stopPlayback())

defineExpose({ stopPlayback, videoEl })

// --- Helpers ---

function styleLabel(id) {
  if (!id) return ''
  return id.replace(/[_-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function styleColor(id) {
  if (!id) return 'var(--text-muted)'
  // Common style colors
  const map = {
    cinematic_realistic: '#4ECDC4',
    anime_manga: '#FF6B6B',
    watercolor_dreamy: '#A78BFA',
    pop_art_bold: '#FFB347',
    minimalist_clean: '#56CCF2',
  }
  return map[id] || 'var(--text-muted)'
}

// Lazy load via IntersectionObserver
const cardEl = ref(null)
onMounted(() => {
  if (!cardEl.value) return
  const observer = new IntersectionObserver((entries, obs) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        loaded.value = true
        obs.unobserve(entry.target)
      }
    }
  }, { rootMargin: '200px' })
  observer.observe(cardEl.value)
})
</script>

<template>
  <article class="card">
    <div ref="cardEl" class="card-video-wrap">
      <video
        v-if="loaded"
        ref="videoEl"
        :src="item.preview_url"
        controls
        preload="metadata"
        playsinline
        class="card-video"
        @play="onPlay"
      />
    </div>
    <div class="card-body">
      <p class="card-title">{{ item.project_id || item.video_name }}</p>
      <p class="card-filename" :title="item.video_name || ''">{{ item.video_name || '' }}</p>
      <div class="card-meta">
        <template v-if="item.scene_count">
          <span class="meta-scenes">{{ item.scene_count }} scene{{ item.scene_count !== 1 ? 's' : '' }}</span>
          <span class="meta-sep">/</span>
        </template>
        <template v-if="fmtDuration(item.duration)">
          <span class="meta-duration">{{ fmtDuration(item.duration) }}</span>
          <span class="meta-sep">/</span>
        </template>
        <span class="meta-size">{{ formatBytes(item.size_bytes) }}</span>
        <span class="meta-sep">/</span>
        <span>{{ timeAgo(item.modified_at) }}</span>
        <template v-if="item.video_ratio">
          <span class="meta-sep">/</span>
          <span class="meta-ratio">{{ item.video_ratio.replace(':', 'x') }}</span>
        </template>
        <template v-if="ratioLabel(item.ratio)">
          <span class="meta-sep">/</span>
          <span class="meta-ratio">{{ ratioLabel(item.ratio) }}</span>
        </template>
        <template v-if="styleLabel(item.style)">
          <span class="meta-sep">/</span>
          <span class="meta-style">
            <span class="meta-style-dot" :style="{ background: styleColor(item.style) }"></span>
            <span :style="{ color: styleColor(item.style), fontWeight: 600 }">{{ styleLabel(item.style) }}</span>
          </span>
        </template>
      </div>

      <div class="card-actions">
        <button
          class="action-btn hover-accent"
          @click="emit('download-video', item)"
        >Download Video</button>
        <button
          v-if="item.zip_download_url"
          class="action-btn hover-accent accent"
          @click="emit('download-zip', item)"
        >Download Project ZIP</button>
        <span v-else class="action-btn disabled">ZIP Not Available</span>
      </div>
    </div>
  </article>
</template>

<style scoped>
.card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.card:hover {
  border-color: var(--border-hover);
}

.card-video-wrap {
  background: var(--bg-darkest);
  border-bottom: 1px solid var(--border);
}

.card-video {
  max-height: 360px;
  background: black;
}

.card-body {
  padding: 12px 12px 10px;
}

.card-title {
  font-size: 13px;
  color: var(--text);
  font-weight: 600;
  margin: 0 0 4px;
  word-break: break-word;
}

.card-filename {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  margin: 0 0 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-meta {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  margin: 4px 0 10px;
  display: flex;
  align-items: center;
  gap: 0;
  flex-wrap: wrap;
  line-height: 1.8;
}

.meta-scenes { color: #4ECDC4; }
.meta-duration { color: #FFB347; }
.meta-size { color: var(--text-secondary); }
.meta-ratio { color: #A78BFA; }

.meta-sep {
  opacity: 0.3;
  margin: 0 3px;
}

.meta-style {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.meta-style-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}

.card-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.action-btn {
  padding: 7px 10px;
  font-size: 11px;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s;
  display: inline-flex;
  align-items: center;
}

.action-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.action-btn.accent {
  border-color: var(--accent);
  color: var(--accent);
}

.action-btn.disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
