<script setup>
import { ref } from 'vue'

defineOptions({ name: 'StylePicker' })

const props = defineProps({
  templates: { type: Array, default: () => [] },
  selected: { type: String, default: '' },
})

const emit = defineEmits(['select'])

const open = ref(true)

function toggle() {
  open.value = !open.value
}
</script>

<template>
  <div class="style-picker">
    <button class="style-picker-header" @click="toggle">
      <span class="style-picker-left">
        <span class="style-picker-title">Style Template</span>
        <span v-if="selected" class="style-picker-badge">
          <span
            class="style-dot"
            :style="{ background: templates.find(t => t.id === selected)?.color || 'var(--text-muted)' }"
          ></span>
          {{ templates.find(t => t.id === selected)?.name || selected }}
        </span>
      </span>
      <svg
        class="style-picker-chevron"
        :class="{ open }"
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </button>

    <div v-show="open" class="style-grid">
      <div
        v-for="tmpl in templates"
        :key="tmpl.id"
        class="style-card"
        :class="{ selected: tmpl.id === selected }"
        :style="{
          borderLeftColor: tmpl.color,
          borderColor: tmpl.id === selected ? tmpl.color : undefined,
          background: tmpl.id === selected ? tmpl.color + '12' : undefined,
          boxShadow: tmpl.id === selected ? '0 0 12px ' + tmpl.color + '25' : undefined,
        }"
        @click="emit('select', tmpl.id)"
      >
        <div class="style-card-header">
          <span class="style-dot" :style="{ background: tmpl.color }"></span>
          <span class="style-card-name">{{ tmpl.name }}</span>
        </div>
        <p class="style-card-desc">{{ tmpl.description }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.style-picker {
  display: flex;
  flex-direction: column;
  margin-bottom: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.style-picker-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 8px;
  background: var(--bg-darkest);
  border: none;
  cursor: pointer;
  padding: 10px 14px;
  color: var(--text);
}

.style-picker-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.style-picker-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.style-picker-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
}

.style-picker-chevron {
  color: var(--text-muted);
  transition: transform 0.2s;
  flex-shrink: 0;
}

.style-picker-chevron.open {
  transform: rotate(180deg);
}

.style-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 8px;
  padding: 10px 14px 14px;
}

.style-card {
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1.5px solid var(--border);
  border-left-width: 4px;
  background: var(--bg-card, var(--bg-surface));
}

.style-card:hover {
  border-color: var(--text-muted);
}

.style-card.selected {
  /* border-color and background set via inline style for dynamic color */
}

.style-card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.style-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.style-card-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}

.style-card-desc {
  font-size: 10px;
  color: var(--text-muted);
  margin: 0;
  line-height: 1.4;
}
</style>
