<script setup>
import { ref, watch, onBeforeUnmount } from 'vue'
import { useAudioRegistry } from '@/shared/composables/useAudioRegistry.js'
import { fmtTime } from '@/shared/utils/format.js'

const props = defineProps({
  metadata: { type: Object, default: null },
  audioSrc: { type: String, default: '' },
})

const emit = defineEmits(['ended'])

const { register: audioRegister } = useAudioRegistry()

const audioEl = ref(null)
const isPlaying = ref(false)

watch(audioEl, (el) => { if (el) audioRegister('TTS', el) })
const currentTime = ref(0)
const duration = ref(0)

function togglePlayback() {
  const el = audioEl.value
  if (!el || !el.src) return
  if (el.paused) {
    el.play().catch(() => {})
  } else {
    el.pause()
  }
}

function onPlay() {
  isPlaying.value = true
}

function onPause() {
  isPlaying.value = false
}

function onEnded() {
  isPlaying.value = false
  emit('ended')
}

function onTimeUpdate() {
  const el = audioEl.value
  if (!el) return
  currentTime.value = el.currentTime
  duration.value = el.duration || 0
}

function onLoadedMetadata() {
  const el = audioEl.value
  if (!el) return
  duration.value = el.duration || 0
}

function seekAudio(e) {
  const el = audioEl.value
  if (!el || !el.duration) return
  const bar = e.currentTarget
  const rect = bar.getBoundingClientRect()
  const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
  el.currentTime = pct * el.duration
}

const seekPercent = ref(0)
watch(currentTime, () => {
  seekPercent.value = duration.value ? (currentTime.value / duration.value * 100) : 0
})

watch(() => props.audioSrc, (src) => {
  const el = audioEl.value
  if (!el) return
  if (src) {
    el.src = src
    el.load()
    el.oncanplay = () => {
      el.oncanplay = null
      el.play().catch(() => {})
    }
  } else {
    el.pause()
    el.src = ''
    isPlaying.value = false
    currentTime.value = 0
    duration.value = 0
  }
}, { immediate: true, flush: 'post' })

onBeforeUnmount(() => {
  const el = audioEl.value
  if (el) {
    el.pause()
    el.src = ''
  }
})
</script>

<template>
  <div v-if="metadata" class="now-playing card">
    <audio
      ref="audioEl"
      @play="onPlay"
      @pause="onPause"
      @ended="onEnded"
      @timeupdate="onTimeUpdate"
      @loadedmetadata="onLoadedMetadata"
    />

    <div class="np-header">
      <button class="play-btn" @click="togglePlayback" title="Play/Pause">
        <svg v-if="!isPlaying" width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
          <path d="M8 5v14l11-7z" />
        </svg>
        <svg v-else width="16" height="16" fill="currentColor" viewBox="0 0 24 24">
          <path d="M6 4h4v16H6zM14 4h4v16h-4z" />
        </svg>
      </button>

      <div class="np-info">
        <p class="np-text">{{ (metadata.prompt || '').slice(0, 80) }}{{ (metadata.prompt || '').length > 80 ? '...' : '' }}</p>
        <div class="np-meta">
          <span class="np-voice">{{ metadata.voiceName || metadata.voice }}</span>
          <span class="np-sep">/</span>
          <span class="np-duration">{{ metadata.duration_seconds ? metadata.duration_seconds.toFixed(1) + 's' : fmtTime(duration) }}</span>
          <span class="np-current">{{ fmtTime(currentTime) }}</span>
        </div>
      </div>
    </div>

    <div class="seek-bar" @click="seekAudio">
      <div class="seek-fill" :style="{ width: seekPercent + '%' }"></div>
    </div>
  </div>
</template>

<style scoped>
.now-playing {
  margin-top: 16px;
  padding: 16px;
}

.np-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.play-btn {
  width: 36px;
  height: 36px;
  min-width: 36px;
  border-radius: 10px;
  background: rgba(78, 205, 196, 0.12);
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent);
  transition: background 0.15s;
}

.play-btn:hover {
  background: rgba(78, 205, 196, 0.2);
}

.np-info {
  flex: 1;
  min-width: 0;
}

.np-text {
  margin: 0;
  font-size: 12px;
  color: var(--text);
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.np-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
  font-size: 10px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.np-sep {
  opacity: 0.3;
}

.np-current {
  margin-left: auto;
}

.seek-bar {
  height: 6px;
  background: var(--bg-darkest);
  border-radius: 3px;
  cursor: pointer;
  overflow: hidden;
}

.seek-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 3px;
  transition: width 0.1s linear;
}
</style>
