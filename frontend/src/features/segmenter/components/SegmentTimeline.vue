<script setup>
import { computed, ref } from 'vue'

defineOptions({ name: 'SegmentTimeline' })

const props = defineProps({
  segments: { type: Array, required: true },
  activeIndex: { type: Number, default: -1 },
  totalDuration: { type: Number, required: true },
  currentTime: { type: Number, default: 0 },
  isPlaying: { type: Boolean, default: false },
  hasAudio: { type: Boolean, default: false },
})

const emit = defineEmits(['play-segment', 'seek', 'toggle-play'])

const hoveredIdx = ref(-1)

const playheadLeft = computed(() => {
  if (!props.totalDuration) return '0%'
  const pct = (props.currentTime / props.totalDuration) * 100
  return `${Math.min(100, Math.max(0, pct))}%`
})

const playheadOpacity = computed(() => (
  props.currentTime > 0 || props.isPlaying ? 1 : 0
))

const bottomOffsetStyle = computed(() => ({
  marginLeft: props.hasAudio ? '38px' : '0',
}))

function formatTime(value) {
  return Number.isFinite(value) ? `${value.toFixed(2)}s` : '0.00s'
}

function blockStyle(seg) {
  if (!props.totalDuration) {
    return {
      left: '0%',
      width: '0%',
    }
  }

  const left = (seg.start / props.totalDuration) * 100
  const width = Math.max((seg.duration / props.totalDuration) * 100, 0.3)
  let background = 'hsla(210,20%,45%,0.7)'

  if (seg.is_filler) {
    background = 'rgba(255,255,255,0.04)'
  } else if (seg.break_reason === 'hard_max') {
    background = 'hsla(0,70%,60%,0.7)'
  } else if (seg.break_reason === 'strong_break') {
    background = 'hsla(174,58%,55%,0.7)'
  } else if (seg.break_reason === 'natural_break') {
    background = 'hsla(263,68%,65%,0.7)'
  }

  return {
    left: `${left.toFixed(2)}%`,
    width: `${width.toFixed(2)}%`,
    background,
  }
}

function blockLabel(seg) {
  if (seg.is_filler || !seg.words) return ''
  return seg.words.split(/\s+/).slice(0, 3).join(' ')
}

function blockTitle(seg) {
  if (!seg.words) return formatTime(seg.duration)
  return `${seg.words} (${formatTime(seg.duration)})`
}

function onSegmentClick(seg, idx) {
  emit('play-segment', { segment: seg, index: idx })
}

function onBarClick(event) {
  if (!props.totalDuration) return
  const bar = event.currentTarget
  const rect = bar.getBoundingClientRect()
  const pct = (event.clientX - rect.left) / rect.width
  emit('seek', Math.max(0, Math.min(1, pct)) * props.totalDuration)
}
</script>

<template>
  <div>
    <div class="timeline-row">
      <button
        type="button"
        class="timeline-play-btn"
        @click="emit('toggle-play')"
      >
        <svg v-if="!isPlaying" width="12" height="12" viewBox="0 0 24 24" fill="white" aria-hidden="true">
          <polygon points="5,3 19,12 5,21" />
        </svg>
        <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="white" aria-hidden="true">
          <rect x="5" y="4" width="4" height="16" />
          <rect x="15" y="4" width="4" height="16" />
        </svg>
      </button>

      <div class="timeline-bar" @click="onBarClick">
        <div
          v-for="(seg, idx) in segments"
          :key="`${seg.index ?? idx}-${seg.start ?? 0}`"
          class="timeline-block"
          :class="{
            filler: seg.is_filler,
            active: idx === activeIndex,
            hovered: idx === hoveredIdx,
          }"
          :style="blockStyle(seg)"
          :title="blockTitle(seg)"
          @mouseenter="hoveredIdx = idx"
          @mouseleave="hoveredIdx = -1"
          @click.stop="onSegmentClick(seg, idx)"
        >
          <span v-if="blockLabel(seg)" class="timeline-label">{{ blockLabel(seg) }}</span>
        </div>

        <div class="playhead" :style="{ left: playheadLeft, opacity: playheadOpacity }" />
      </div>

      <span class="time-display">{{ formatTime(currentTime) }}</span>
    </div>

    <div class="timeline-scale" :style="bottomOffsetStyle">
      <span>0.00s</span>
      <span>{{ formatTime(totalDuration) }}</span>
    </div>
  </div>
</template>

<style scoped>
.timeline-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}

.timeline-play-btn {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: none;
  background: var(--accent);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  cursor: pointer;
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
  border: 1px solid var(--border);
  border-radius: 0;
  overflow: hidden;
  cursor: pointer;
}

.timeline-block {
  position: absolute;
  top: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-right: 1px solid var(--bg-darkest);
  cursor: pointer;
  transition: opacity 0.15s;
}

.timeline-block.active,
.timeline-block.hovered {
  box-shadow: inset 2px 0 0 rgba(255, 255, 255, 0.92), inset -2px 0 0 rgba(255, 255, 255, 0.92);
}

.timeline-label {
  padding: 0 4px;
  font-size: 8px;
  color: rgba(255, 255, 255, 0.8);
  font-family: var(--font-mono);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.playhead {
  position: absolute;
  top: 0;
  width: 2px;
  height: 100%;
  background: white;
  z-index: 10;
  pointer-events: none;
  transition: left 0.15s linear, opacity 0.15s;
  will-change: left;
}

.time-display,
.timeline-scale {
  font-family: var(--font-mono);
}

.time-display {
  min-width: 48px;
  text-align: right;
  flex-shrink: 0;
  font-size: 10px;
  color: var(--text-muted);
}

.timeline-scale {
  display: flex;
  justify-content: space-between;
  font-size: 9px;
  color: var(--text-muted);
}
</style>
