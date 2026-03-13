<script setup>
import { computed } from 'vue'

defineOptions({ name: 'SceneTimeline' })

const props = defineProps({
  scenes: { type: Array, default: () => [] },
  timings: { type: Array, default: () => [] },
  activeIndex: { type: Number, default: -1 },
  totalDuration: { type: Number, default: 0 },
  currentTime: { type: Number, default: 0 },
  isPlaying: { type: Boolean, default: false },
  audioLoaded: { type: Boolean, default: false },
})

const emit = defineEmits(['play', 'seek', 'toggle-play'])

const typeHsl = {
  video: '174, 58%, 55%',
  image: '263, 68%, 65%',
  text_overlay: '30, 100%, 64%',
  text: '30, 100%, 64%',
}

const playheadPct = computed(() => {
  if (!props.totalDuration) return '0%'
  return ((props.currentTime / props.totalDuration) * 100).toFixed(2) + '%'
})

function segmentStyle(scene, idx) {
  const timing = props.timings[idx]
  if (!timing || !props.totalDuration) return { display: 'none' }
  const left = ((timing.start / props.totalDuration) * 100).toFixed(2)
  const width = Math.max(((timing.end - timing.start) / props.totalDuration) * 100, 0.3).toFixed(2)
  const hue = typeHsl[scene.type_of_scene] || '210, 20%, 45%'
  return {
    position: 'absolute',
    left: left + '%',
    width: width + '%',
    height: '100%',
    background: `hsla(${hue}, 0.7)`,
    borderRight: '1px solid var(--bg-darkest)',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
    transition: 'opacity 0.15s',
    outline: idx === props.activeIndex ? '2px solid white' : 'none',
  }
}

function segmentLabel(scene) {
  return (scene.title || '').split(' ').slice(0, 3).join(' ')
}

function onBarClick(e) {
  const bar = e.currentTarget
  const rect = bar.getBoundingClientRect()
  const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
  const time = pct * props.totalDuration
  emit('seek', time)
}

function onBlockClick(idx, e) {
  e.stopPropagation()
  emit('play', idx)
}
</script>

<template>
  <div class="scene-timeline">
    <div class="timeline-controls">
      <button
        v-if="audioLoaded"
        class="timeline-play-btn"
        @click="emit('toggle-play')"
      >
        <svg v-if="!isPlaying" width="12" height="12" fill="white" viewBox="0 0 24 24">
          <polygon points="5,3 19,12 5,21" />
        </svg>
        <svg v-else width="12" height="12" fill="white" viewBox="0 0 24 24">
          <rect x="5" y="4" width="4" height="16" />
          <rect x="15" y="4" width="4" height="16" />
        </svg>
      </button>

      <div class="timeline-bar" @click="onBarClick">
        <div
          v-for="(scene, idx) in scenes"
          :key="idx"
          :style="segmentStyle(scene, idx)"
          :title="`${scene.title || ''} (${(scene.duration || 0).toFixed(1)}s)`"
          @click="onBlockClick(idx, $event)"
        >
          <span class="timeline-block-label">{{ segmentLabel(scene) }}</span>
        </div>

        <div
          class="timeline-playhead"
          :style="{ left: playheadPct, opacity: isPlaying || currentTime > 0 ? '1' : '0' }"
        ></div>
      </div>

      <span class="timeline-time">{{ currentTime.toFixed(2) }}s</span>
    </div>

    <div class="timeline-range">
      <span>0.00s</span>
      <span>{{ totalDuration.toFixed(2) }}s</span>
    </div>
  </div>
</template>

<style scoped>
.scene-timeline {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.timeline-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

.timeline-play-btn {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--accent);
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: transform 0.15s, background 0.15s;
}

.timeline-play-btn:hover {
  transform: scale(1.1);
}

.timeline-bar {
  position: relative;
  flex: 1;
  height: 32px;
  background: var(--bg-darkest);
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border);
  cursor: pointer;
}

.timeline-block-label {
  font-size: 8px;
  color: rgba(255, 255, 255, 0.8);
  font-family: var(--font-mono);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 0 4px;
}

.timeline-playhead {
  position: absolute;
  top: 0;
  width: 2px;
  height: 100%;
  background: white;
  z-index: 10;
  pointer-events: none;
  transition: opacity 0.15s;
}

.timeline-time {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  min-width: 48px;
  text-align: right;
  flex-shrink: 0;
}

.timeline-range {
  display: flex;
  justify-content: space-between;
  font-size: 9px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  margin-left: 38px;
}
</style>
