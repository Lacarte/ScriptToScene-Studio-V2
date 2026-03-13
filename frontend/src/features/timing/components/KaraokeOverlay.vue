<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  words: { type: Array, default: () => [] },
  audioSrc: { type: String, default: '' },
})

const emit = defineEmits(['close'])

const audioEl = ref(null)
const currentTime = ref(0)
const duration = ref(0)
const isPlaying = ref(false)
let rafId = null

const activeIndex = computed(() => {
  const t = currentTime.value
  for (let i = 0; i < props.words.length; i++) {
    if (t >= props.words[i].begin && t <= props.words[i].end) return i
  }
  return -1
})

const progress = computed(() => {
  if (!duration.value) return 0
  return (currentTime.value / duration.value) * 100
})

function wordClass(i) {
  const idx = activeIndex.value
  if (idx === -1) return ''
  if (i < idx) return 'spoken'
  if (i === idx) return 'active'
  return ''
}

function tick() {
  if (audioEl.value) {
    currentTime.value = audioEl.value.currentTime
  }
  rafId = requestAnimationFrame(tick)
}

function togglePlay() {
  if (!audioEl.value) return
  if (audioEl.value.paused) {
    audioEl.value.play()
    isPlaying.value = true
  } else {
    audioEl.value.pause()
    isPlaying.value = false
  }
}

function onLoaded() {
  if (audioEl.value) {
    duration.value = audioEl.value.duration
  }
}

function onEnded() {
  isPlaying.value = false
}

function seekBar(e) {
  if (!audioEl.value || !duration.value) return
  const rect = e.currentTarget.getBoundingClientRect()
  const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
  audioEl.value.currentTime = ratio * duration.value
}

function seekWord(index) {
  if (!audioEl.value) return
  audioEl.value.currentTime = props.words[index].begin
  if (!isPlaying.value) {
    audioEl.value.play()
    isPlaying.value = true
  }
}

function onKeydown(e) {
  if (e.key === 'Escape') {
    emit('close')
  } else if (e.key === ' ') {
    e.preventDefault()
    togglePlay()
  }
}

onMounted(() => {
  rafId = requestAnimationFrame(tick)
  document.addEventListener('keydown', onKeydown)
  // Auto-play
  if (audioEl.value) {
    audioEl.value.play().then(() => {
      isPlaying.value = true
    }).catch(() => {})
  }
})

onBeforeUnmount(() => {
  if (rafId) cancelAnimationFrame(rafId)
  document.removeEventListener('keydown', onKeydown)
  if (audioEl.value) {
    audioEl.value.pause()
  }
})
</script>

<template>
  <div class="karaoke-overlay" @click.self="emit('close')">
    <button class="close-btn" @click="emit('close')" title="Close (Esc)">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
        <path d="M18.3 5.7a1 1 0 0 0-1.4 0L12 10.6 7.1 5.7a1 1 0 0 0-1.4 1.4L10.6 12l-4.9 4.9a1 1 0 1 0 1.4 1.4L12 13.4l4.9 4.9a1 1 0 0 0 1.4-1.4L13.4 12l4.9-4.9a1 1 0 0 0 0-1.4z"/>
      </svg>
    </button>

    <audio
      ref="audioEl"
      :src="audioSrc"
      preload="auto"
      @loadedmetadata="onLoaded"
      @ended="onEnded"
    />

    <div class="karaoke-content">
      <div class="words-display">
        <span
          v-for="(w, i) in words"
          :key="i"
          class="karaoke-word"
          :class="wordClass(i)"
          @click="seekWord(i)"
        >{{ w.word }}</span>
      </div>
    </div>

    <div class="karaoke-controls">
      <button class="play-btn" @click="togglePlay">
        <svg v-if="!isPlaying" width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <polygon points="6,4 20,12 6,20" />
        </svg>
        <svg v-else width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
          <rect x="5" y="4" width="4" height="16" rx="1" />
          <rect x="15" y="4" width="4" height="16" rx="1" />
        </svg>
      </button>
      <div class="seek-bar" @click="seekBar">
        <div class="seek-bg">
          <div class="seek-fill" :style="{ width: progress + '%' }" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.karaoke-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.95);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.close-btn {
  position: absolute;
  top: 20px;
  right: 20px;
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 8px;
  border-radius: 8px;
  transition: color 0.15s, background 0.15s;
}

.close-btn:hover {
  color: var(--text);
  background: rgba(255, 255, 255, 0.08);
}

.karaoke-content {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 60px 40px;
  max-width: 900px;
  width: 100%;
}

.words-display {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px 12px;
  line-height: 1.8;
}

.karaoke-word {
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: color 0.15s, transform 0.15s;
  padding: 2px 4px;
  border-radius: 4px;
}

.karaoke-word.spoken {
  color: var(--text-muted);
  opacity: 0.4;
}

.karaoke-word.active {
  color: var(--accent);
  font-weight: 700;
  transform: scale(1.08);
}

.karaoke-word:hover {
  color: var(--text);
}

.karaoke-controls {
  width: 100%;
  max-width: 700px;
  padding: 20px 40px 40px;
  display: flex;
  align-items: center;
  gap: 16px;
}

.play-btn {
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: none;
  background: var(--accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: opacity 0.15s;
}

.play-btn:hover {
  opacity: 0.85;
}

.seek-bar {
  flex: 1;
  cursor: pointer;
  padding: 8px 0;
}

.seek-bg {
  height: 6px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.12);
  overflow: hidden;
}

.seek-fill {
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, var(--accent), #2FB8AE);
  transition: width 0.05s linear;
}
</style>
