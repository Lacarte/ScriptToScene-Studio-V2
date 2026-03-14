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
  if (!seconds || !isFinite(seconds)) return '0.00s'
  return `${seconds.toFixed(2)}s`
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
      <svg v-if="!isPlaying" width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
        <polygon points="6,4 20,12 6,20" />
      </svg>
      <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
        <rect x="6" y="4" width="4" height="16" rx="1" />
        <rect x="14" y="4" width="4" height="16" rx="1" />
      </svg>
    </button>

    <div class="bar-wrapper" @click="onBarClick">
      <div class="bar-bg">
        <div class="bar-progress" :style="{ width: progress + '%' }" />
        <div v-if="duration" class="bar-playhead" :style="{ left: progress + '%' }"></div>
      </div>
    </div>

    <span class="time-display">{{ formatTime(currentTime) }}</span>
  </div>
</template>

<style scoped>
.timeline {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.play-btn {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
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
}

.bar-bg {
  position: relative;
  height: 28px;
  border-radius: 8px;
  background: var(--bg-darkest);
  border: 1px solid var(--border);
  overflow: hidden;
}

.bar-progress {
  position: absolute;
  inset: 0 auto 0 0;
  height: 100%;
  background: rgba(78, 205, 196, 0.15);
  transition: width 0.05s linear;
}

.bar-playhead {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: white;
  transform: translateX(-1px);
}

.time-display {
  flex-shrink: 0;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  min-width: 52px;
  text-align: right;
}
</style>
