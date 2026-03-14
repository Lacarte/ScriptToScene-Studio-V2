<script setup>
defineOptions({ name: 'SegmentCard' })

const props = defineProps({
  segment: { type: Object, required: true },
  index: { type: Number, required: true },
  displayIndex: { type: Number, default: 0 },
  isActive: { type: Boolean, default: false },
})

const emit = defineEmits(['play'])

function fmt(val) {
  return val != null ? val.toFixed(2) + 's' : '--'
}

const BREAK_COLORS = {
  strong_break: '#4ECDC4',
  natural_break: '#A78BFA',
  hard_max: '#ef4444',
  end_of_text: 'var(--text-muted)',
  silence: 'var(--text-muted)',
}

function breakColor(reason) {
  return BREAK_COLORS[reason] || 'var(--text-muted)'
}
</script>

<template>
  <!-- Filler / silence segments -->
  <div
    v-if="segment.is_filler"
    class="filler-card"
    :class="{ active: isActive }"
    @click="emit('play', segment)"
  >
    <span class="filler-label">silence</span>
    <div class="filler-line"></div>
    <span class="filler-duration">{{ fmt(segment.duration) }}</span>
  </div>

  <!-- Speech segments -->
  <div
    v-else
    class="segment-card"
    :class="{ active: isActive }"
    :style="{ borderLeftColor: breakColor(segment.break_reason) }"
    @click="emit('play', segment)"
  >
    <div class="seg-header">
      <span class="seg-title" :style="{ color: breakColor(segment.break_reason) }">
        Segment {{ displayIndex }} &middot; {{ fmt(segment.start) }} - {{ fmt(segment.end) }}
      </span>
      <div class="seg-badges">
        <span class="seg-duration">{{ fmt(segment.duration) }}</span>
        <span v-if="segment.break_reason" class="seg-break">{{ segment.break_reason }}</span>
      </div>
    </div>
    <p class="seg-text">{{ segment.words }}</p>
    <p v-if="segment.word_count != null" class="seg-words">{{ segment.word_count }} words</p>
  </div>
</template>

<style scoped>
/* ---- Speech Card ---- */
.segment-card {
  padding: 12px 14px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  border-left: 3px solid var(--accent);
  cursor: pointer;
  transition: all 0.2s;
}

.segment-card:hover {
  background: rgba(255, 255, 255, 0.02);
}

.segment-card.active {
  border-color: var(--accent);
  box-shadow: 0 0 12px rgba(78, 205, 196, 0.3);
}

.seg-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 6px;
}

.seg-title {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
}

.seg-badges {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.seg-duration {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--accent);
  background: rgba(78, 205, 196, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
}

.seg-break {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-muted);
  background: var(--bg-darkest);
  padding: 2px 6px;
  border-radius: 4px;
}

.seg-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text);
  margin: 0;
  word-break: break-word;
}

.seg-words {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  margin: 4px 0 0;
}

/* ---- Filler / Silence Card ---- */
.filler-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 8px;
  background: var(--bg-darkest);
  border: 1px dashed var(--border);
  opacity: 0.6;
  cursor: pointer;
  transition: all 0.15s;
}

.filler-card:hover {
  opacity: 0.8;
}

.filler-card.active {
  opacity: 1;
}

.filler-label {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  min-width: 40px;
}

.filler-line {
  flex: 1;
  height: 2px;
  background: var(--border);
  border-radius: 1px;
}

.filler-duration {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  flex-shrink: 0;
}
</style>
