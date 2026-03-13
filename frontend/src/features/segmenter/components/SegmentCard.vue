<script setup>
defineOptions({ name: 'SegmentCard' })

defineProps({
  segment: { type: Object, required: true },
  index: { type: Number, required: true },
  isActive: { type: Boolean, default: false },
})

const emit = defineEmits(['play'])

function formatDuration(val) {
  return val != null ? val.toFixed(2) + 's' : '--'
}
</script>

<template>
  <div
    class="segment-card"
    :class="{ active: isActive, filler: segment.is_filler }"
    @click="emit('play', segment)"
  >
    <div class="card-left">
      <span class="index-badge">{{ segment.index }}</span>
    </div>
    <div class="card-body">
      <p class="words-text" :class="{ 'filler-text': segment.is_filler }">
        {{ segment.words || '(silence)' }}
      </p>
      <div class="card-meta">
        <span class="meta-item duration">{{ formatDuration(segment.duration) }}</span>
        <span v-if="segment.word_count != null" class="meta-item">{{ segment.word_count }} words</span>
        <span class="type-badge" :class="segment.is_filler ? 'badge-filler' : 'badge-speech'">
          {{ segment.is_filler ? 'filler' : 'speech' }}
        </span>
        <span v-if="segment.break_reason" class="meta-item reason">{{ segment.break_reason }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.segment-card {
  display: flex;
  gap: 14px;
  padding: 14px 16px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  border-left: 3px solid transparent;
}

.segment-card:hover {
  border-color: var(--border-hover, rgba(255, 255, 255, 0.12));
  background: rgba(255, 255, 255, 0.02);
}

.segment-card.active {
  border-left-color: var(--accent);
  background: rgba(78, 205, 196, 0.04);
}

.segment-card.filler {
  opacity: 0.6;
}

.segment-card.filler:hover {
  opacity: 0.8;
}

.card-left {
  display: flex;
  align-items: flex-start;
  padding-top: 2px;
}

.index-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.card-body {
  flex: 1;
  min-width: 0;
}

.words-text {
  font-size: 14px;
  line-height: 1.5;
  color: var(--text);
  margin-bottom: 8px;
  word-break: break-word;
}

.words-text.filler-text {
  font-style: italic;
  color: var(--text-muted);
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.meta-item {
  font-size: 12px;
  color: var(--text-secondary);
}

.meta-item.duration {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--accent);
}

.meta-item.reason {
  font-style: italic;
  color: var(--text-muted);
}

.type-badge {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 2px 8px;
  border-radius: 6px;
}

.badge-speech {
  background: rgba(78, 205, 196, 0.12);
  color: var(--accent);
}

.badge-filler {
  background: rgba(255, 255, 255, 0.04);
  color: var(--text-muted);
}
</style>
