<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  words: { type: Array, default: () => [] },
  activeIndex: { type: Number, default: -1 },
  audioLoaded: { type: Boolean, default: false },
})

const emit = defineEmits(['seek-word'])

const container = ref(null)

/* Auto-scroll active word into view */
watch(() => props.activeIndex, async (idx) => {
  if (idx < 0 || !container.value) return
  await nextTick()
  const chip = container.value.children[idx]
  if (chip) {
    chip.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
  }
})

function onChipClick(word, index) {
  if (!props.audioLoaded) return
  emit('seek-word', word.begin, index)
}
</script>

<template>
  <div ref="container" class="word-chips">
    <span
      v-for="(w, i) in words"
      :key="i"
      class="chip"
      :class="{
        active: i === activeIndex,
        clickable: audioLoaded,
      }"
      @click="onChipClick(w, i)"
    >
      {{ w.word }}
    </span>
    <span v-if="!words.length" class="empty">No alignment data</span>
  </div>
</template>

<style scoped>
.word-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  max-height: 200px;
  overflow-y: auto;
  padding: 8px 0;
}

.chip {
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--text-secondary);
  background: transparent;
  transition: all 0.15s;
  user-select: none;
}

.chip.clickable {
  cursor: pointer;
}

.chip.clickable:hover {
  background: rgba(78, 205, 196, 0.08);
  color: var(--text);
}

.chip.active {
  background: rgba(78, 205, 196, 0.15);
  color: var(--accent);
  font-weight: 600;
}

.empty {
  font-size: 13px;
  color: var(--text-muted);
  padding: 8px 0;
}
</style>
