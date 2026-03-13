<script setup>
defineOptions({ name: 'SettingsToggle' })

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  label: { type: String, required: true },
  description: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

function toggle() {
  if (!props.disabled) {
    emit('update:modelValue', !props.modelValue)
  }
}
</script>

<template>
  <div class="toggle-row" :class="{ disabled }" @click="toggle">
    <div class="toggle-info">
      <span class="toggle-label">{{ label }}</span>
      <span v-if="description" class="toggle-desc">{{ description }}</span>
    </div>
    <button
      type="button"
      role="switch"
      :aria-checked="modelValue"
      :aria-label="label"
      class="toggle-switch"
      :class="{ active: modelValue }"
      :disabled="disabled"
      @click.stop="toggle"
    >
      <span class="toggle-slider" />
    </button>
  </div>
</template>

<style scoped>
.toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 0;
  cursor: pointer;
  user-select: none;
}

.toggle-row:not(:last-child) {
  border-bottom: 1px solid var(--border);
}

.toggle-row.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.toggle-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.toggle-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
}

.toggle-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.toggle-switch {
  position: relative;
  flex-shrink: 0;
  width: 38px;
  height: 20px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s;
  padding: 0;
}

.toggle-switch:hover {
  border-color: var(--border-hover);
}

.toggle-switch.active {
  background: var(--accent);
  border-color: var(--accent);
}

.toggle-slider {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 14px;
  height: 14px;
  background: var(--text-secondary);
  border-radius: 50%;
  transition: transform 0.2s, background 0.2s;
}

.toggle-switch.active .toggle-slider {
  transform: translateX(18px);
  background: #fff;
}

.toggle-switch:disabled {
  cursor: not-allowed;
}
</style>
