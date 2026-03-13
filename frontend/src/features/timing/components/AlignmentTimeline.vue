<script setup>
import { computed } from 'vue'

const props = defineProps({
  currentTime: { type: Number, default: 0 },
  duration: { type: Number, default: 0 },
  isPlaying: { type: Boolean, default: false },
})

const emit = defineEmits(['toggle-play', 'seek'])

const progress = computed(() => {
  if (!props.duration) return 0
  return (props.currentTime / props.duration) * 100
})

function formatTime(seconds) {
  if (!seconds || !isFinite(seconds)) return '0:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function onBarClick(e) {
  const rect = e.currentTarget.getBoundingClientRect()
  const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
  emit('seek', ratio * props.duration)
}
</script>

<template>
  <div class="timeline">
    <button class="play-btn" @click="emit('toggle-play')" :title="isPlaying ? 'Pause' : 'Play'">
      <svg v-if="!isPlaying" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
        <polygon points="6,4 20,12 6,20" />
      </svg>
      <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
        <rect x="5" y="4" width="4" height="16" rx="1" />
        <rect x="15" y="4" width="4" height="16" rx="1" />
      </svg>
    </button>

    <div class="bar-wrapper" @click="onBarClick">
      <div class="bar-bg">
        <div class="bar-fill" :style="{ width: progress + '%' }" />
      </div>
    </div>

    <span class="time-display">
      {{ formatTime(currentTime) }} / {{ formatTime(duration) }}
    </span>
  </div>
</template>

<style scoped>
.timeline {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
}

.play-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
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

.bar-wrapper {
  flex: 1;
  cursor: pointer;
  padding: 4px 0;
}

.bar-bg {
  height: 6px;
  border-radius: 3px;
  background: var(--border);
  overflow: hidden;
  position: relative;
}

.bar-fill {
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, var(--accent), #2FB8AE);
  transition: width 0.05s linear;
}

.time-display {
  flex-shrink: 0;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-secondary);
  min-width: 90px;
  text-align: right;
}
</style>
