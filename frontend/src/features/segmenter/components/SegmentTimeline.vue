<script setup>
import { computed, ref } from 'vue'

defineOptions({ name: 'SegmentTimeline' })

const props = defineProps({
  segments: { type: Array, required: true },
  activeIndex: { type: Number, default: -1 },
  totalDuration: { type: Number, required: true },
  currentTime: { type: Number, default: 0 },
})

const emit = defineEmits(['play-segment', 'seek'])

const hoveredIdx = ref(-1)

const playheadLeft = computed(() => {
  if (!props.totalDuration) return '0%'
  const pct = (props.currentTime / props.totalDuration) * 100
  return `${Math.min(100, Math.max(0, pct))}%`
})

function segmentStyle(seg) {
  if (!props.totalDuration) return { flexBasis: '0%' }
  const pct = (seg.duration / props.totalDuration) * 100
  return { flexBasis: `${pct}%` }
}

function onSegmentClick(seg, idx) {
  emit('play-segment', { segment: seg, index: idx })
}

function onBarClick(event) {
  const bar = event.currentTarget
  const rect = bar.getBoundingClientRect()
  const pct = (event.clientX - rect.left) / rect.width
  const time = pct * props.totalDuration
  emit('seek', time)
}
</script>

<template>
  <div class="timeline-wrap" @click="onBarClick">
    <div class="timeline-bar">
      <div
        v-for="(seg, i) in segments"
        :key="i"
        class="timeline-segment"
        :class="{
          filler: seg.is_filler,
          active: i === activeIndex,
          hovered: i === hoveredIdx,
        }"
        :style="segmentStyle(seg)"
        @mouseenter="hoveredIdx = i"
        @mouseleave="hoveredIdx = -1"
        @click.stop="onSegmentClick(seg, i)"
      >
        <span v-if="seg.duration / totalDuration > 0.04" class="seg-label">
          {{ seg.index }}
        </span>
      </div>
    </div>
    <div class="playhead" :style="{ left: playheadLeft }" />
  </div>
</template>

<style scoped>
.timeline-wrap {
  position: relative;
  width: 100%;
  padding: 8px 0 16px;
  cursor: pointer;
}

.timeline-bar {
  display: flex;
  width: 100%;
  height: 32px;
  border-radius: 6px;
  overflow: hidden;
  gap: 2px;
}

.timeline-segment {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 4px;
  background: var(--accent);
  opacity: 0.7;
  transition: opacity 0.15s, filter 0.15s;
  cursor: pointer;
  border-radius: 3px;
}

.timeline-segment:first-child {
  border-radius: 6px 3px 3px 6px;
}

.timeline-segment:last-child {
  border-radius: 3px 6px 6px 3px;
}

.timeline-segment.filler {
  background: rgba(255, 255, 255, 0.06);
}

.timeline-segment.active {
  opacity: 1;
  filter: brightness(1.2);
}

.timeline-segment.hovered {
  opacity: 1;
}

.seg-label {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  color: rgba(0, 0, 0, 0.7);
  user-select: none;
}

.timeline-segment.filler .seg-label {
  color: var(--text-muted);
}

.playhead {
  position: absolute;
  top: 4px;
  width: 2px;
  height: 36px;
  background: #fff;
  border-radius: 1px;
  pointer-events: none;
  transition: left 0.05s linear;
  box-shadow: 0 0 4px rgba(0, 0, 0, 0.5);
}
</style>
