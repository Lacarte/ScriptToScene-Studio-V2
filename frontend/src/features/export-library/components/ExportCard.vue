<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ratioLabel, aspectRatioFromDimensions } from '../composables/useExportLibrary.js'
import { formatBytes, timeAgo, fmtDuration } from '@/shared/utils/format.js'

defineOptions({ name: 'ExportCard' })

const props = defineProps({
  item: { type: Object, required: true },
  highlighted: { type: Boolean, default: false },
})

const emit = defineEmits(['download-video', 'download-zip', 'play', 'trash'])

const rootEl = ref(null)
const videoEl = ref(null)
const loaded = ref(false)

function stopPlayback() {
  if (videoEl.value && !videoEl.value.paused) {
    videoEl.value.pause()
    videoEl.value.currentTime = 0
  }
}

function onPlay() {
  emit('play', videoEl.value)
}

onBeforeUnmount(() => stopPlayback())

defineExpose({ stopPlayback, videoEl, cardRootEl: rootEl })

// --- Helpers ---
function styleLabel(id) {
  if (!id) return ''
  return id.replace(/[_-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function styleColor(id) {
  if (!id) return 'var(--text-muted)'
  const map = {
    cinematic_realistic: '#4ECDC4',
    anime_manga: '#FF6B6B',
    watercolor_dreamy: '#A78BFA',
    pop_art_bold: '#FFB347',
    minimalist_clean: '#56CCF2',
    dark_horror: '#FF4757',
    nature_documentary: '#26DE81',
    noir_mystery: '#A0A0B0',
    surreal_dreamlike: '#C084FC',
    cyberpunk_neon: '#00D2FF',
    stickman_animation: '#FFD93D',
  }
  return map[id] || '#8B8B8B'
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
  <article
    ref="rootEl"
    class="export-card"
    :class="{ highlighted: props.highlighted }"
    tabindex="-1"
  >
    <!-- Video -->
    <div ref="cardEl" class="video-wrap">
      <!-- Blurred background fill -->
      <video
        v-if="loaded"
        :src="item.preview_url"
        muted
        preload="metadata"
        playsinline
        class="video-bg"
        aria-hidden="true"
      />
      <!-- Main video -->
      <video
        v-if="loaded"
        ref="videoEl"
        :src="item.preview_url"
        controls
        preload="metadata"
        playsinline
        class="video-player"
        @play="onPlay"
      />
      <div v-if="!loaded" class="video-placeholder">
        <svg width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" opacity="0.3">
          <polygon points="5,3 19,12 5,21" />
        </svg>
      </div>
    </div>

    <!-- Content -->
    <div class="card-content">
      <!-- Header row: project + style badge -->
      <div class="card-header">
        <h3 class="project-name">{{ item.project_id || item.video_name }}</h3>
        <span
          v-if="item.style"
          class="style-badge"
          :style="{ '--badge-color': styleColor(item.style) }"
        >
          <span class="style-dot"></span>
          {{ styleLabel(item.style) }}
        </span>
      </div>

      <!-- Filename -->
      <p class="filename" :title="item.video_name || ''">{{ item.video_name || '' }}</p>

      <!-- Metadata chips -->
      <div class="meta-row">
        <span v-if="item.scene_count" class="chip chip--teal">{{ item.scene_count }} scenes</span>
        <span v-if="fmtDuration(item.duration)" class="chip chip--amber">{{ fmtDuration(item.duration) }}</span>
        <span class="chip">{{ formatBytes(item.size_bytes) }}</span>
        <span class="chip">{{ timeAgo(item.modified_at) }}</span>
        <span v-if="item.video_ratio" class="chip chip--purple">{{ item.video_ratio.replace(':', 'x') }}</span>
        <span v-if="aspectRatioFromDimensions(item.video_ratio)" class="chip chip--purple-bold">{{ aspectRatioFromDimensions(item.video_ratio) }}</span>
        <span v-else-if="ratioLabel(item.ratio)" class="chip chip--purple-bold">{{ ratioLabel(item.ratio) }}</span>
      </div>

      <!-- Actions -->
      <div class="actions">
        <button class="dl-btn" @click="emit('download-video', item)">
          <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
          Video
        </button>
        <button
          v-if="item.zip_download_url"
          class="dl-btn dl-btn--accent"
          @click="emit('download-zip', item)"
        >
          <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
          Project ZIP
        </button>
        <button
          class="dl-btn dl-btn--trash"
          title="Move to trash"
          @click="emit('trash', item)"
        >
          <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
          </svg>
        </button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.export-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.25s, transform 0.2s;
  outline: none;
  display: flex;
  flex-direction: column;
}

.export-card:hover {
  border-color: var(--border-hover);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
  transform: translateY(-1px);
}

.export-card.highlighted {
  border-color: #4ECDC4;
  box-shadow:
    0 0 0 1px rgba(78, 205, 196, 0.85),
    0 0 0 10px rgba(78, 205, 196, 0.10),
    0 18px 40px rgba(78, 205, 196, 0.18);
  animation: highlight-pulse 1.6s ease-in-out 3;
}

@keyframes highlight-pulse {
  0%, 100% { transform: translateY(0); box-shadow: 0 0 0 1px rgba(78,205,196,0.85), 0 0 0 10px rgba(78,205,196,0.1), 0 18px 40px rgba(78,205,196,0.18); }
  50% { transform: translateY(-2px); box-shadow: 0 0 0 1px rgba(78,205,196,1), 0 0 0 14px rgba(78,205,196,0.14), 0 22px 44px rgba(78,205,196,0.24); }
}

/* ---- Video ---- */
.video-wrap {
  position: relative;
  background: #000;
  aspect-ratio: 9 / 16;
  max-height: 380px;
  overflow: hidden;
}

.video-bg {
  position: absolute;
  inset: -20px;
  width: calc(100% + 40px);
  height: calc(100% + 40px);
  object-fit: cover;
  filter: blur(20px) brightness(0.5);
  pointer-events: none;
  z-index: 0;
}

.video-player {
  position: relative;
  width: 100%;
  height: 100%;
  display: block;
  object-fit: contain;
  z-index: 1;
}

.video-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
}

/* ---- Content ---- */
.card-content {
  padding: 12px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.project-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.style-badge {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 9px;
  font-weight: 600;
  font-family: var(--font-mono);
  padding: 2px 8px;
  border-radius: 4px;
  color: var(--badge-color);
  background: color-mix(in srgb, var(--badge-color) 12%, transparent);
  letter-spacing: 0.02em;
}

.style-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--badge-color);
}

.filename {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0.7;
}

/* ---- Metadata chips ---- */
.meta-row {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  margin: 2px 0 4px;
}

.chip {
  font-family: var(--font-mono);
  font-size: 9px;
  padding: 2px 6px;
  border-radius: 3px;
  background: var(--bg-darkest);
  color: var(--text-muted);
  white-space: nowrap;
}

.chip--teal { color: #4ECDC4; background: rgba(78, 205, 196, 0.1); }
.chip--amber { color: #FFB347; background: rgba(255, 179, 71, 0.1); }
.chip--purple { color: #A78BFA; background: rgba(167, 139, 250, 0.1); }
.chip--purple-bold { color: #C084FC; background: rgba(192, 132, 252, 0.12); font-weight: 600; }

/* ---- Actions ---- */
.actions {
  display: flex;
  gap: 6px;
  margin-top: auto;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.dl-btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 7px 8px;
  font-size: 10px;
  font-weight: 600;
  font-family: var(--font-mono);
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
}

.dl-btn:hover {
  border-color: var(--border-hover);
  color: var(--text);
  background: var(--bg-darkest);
}

.dl-btn--accent {
  border-color: rgba(78, 205, 196, 0.3);
  color: var(--accent);
}

.dl-btn--accent:hover {
  border-color: var(--accent);
  background: rgba(78, 205, 196, 0.08);
  color: var(--accent);
}

.dl-btn--trash {
  flex: 0 0 auto;
  padding: 7px 8px;
  color: var(--text-muted);
  border-color: var(--border);
  opacity: 0.7;
  transition: all 0.15s;
  margin-left: auto;
}

.dl-btn--trash:hover {
  opacity: 1;
  color: #FF6B6B;
  border-color: rgba(255, 107, 107, 0.5);
  background: rgba(255, 107, 107, 0.1);
}
</style>
