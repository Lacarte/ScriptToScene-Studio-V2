<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Object, required: true },
  schema: { type: Object, required: true },
  errors: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue'])

const formData = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

function updateField(key, value) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}

function getFieldError(key) {
  return props.errors.find(e => e.field === key)
}

function getFieldIssues(key) {
  return props.errors.filter(e => e.field === key)
}

function isPassword(key) {
  return props.schema?.properties?.[key]?.ui?.type === 'password'
}

function isDropdown(key) {
  const uiType = props.schema?.properties?.[key]?.ui?.type
  return uiType === 'dropdown' || uiType === 'select'
}

function isSlider(key) {
  return props.schema?.properties?.[key]?.ui?.type === 'slider'
}

function isToggle(key) {
  return props.schema?.properties?.[key]?.ui?.type === 'toggle'
}

function getOptions(key) {
  const prop = props.schema?.properties?.[key]
  if (!prop?.ui?.options) return []
  return prop.ui.options.map(opt => {
    if (typeof opt === 'string') {
      return { value: opt, label: opt }
    }
    return opt
  })
}

function getMin(key) {
  return props.schema?.properties?.[key]?.minimum ?? 0
}

function getMax(key) {
  return props.schema?.properties?.[key]?.maximum ?? 100
}

function getStep(key) {
  return props.schema?.properties?.[key]?.multipleOf ?? 1
}

function getDefault(key) {
  return props.schema?.properties?.[key]?.default
}
</script>

<template>
  <div class="provider-settings-form">
    <div
      v-for="(prop, key) in schema?.properties || {}"
      :key="key"
      class="form-field"
      :class="{ 'has-error': getFieldError(key) }"
    >
      <label :for="`field-${key}`" class="field-label">
        {{ prop.label || key }}
        <span v-if="prop.ui?.type === 'password'" class="required-badge">*</span>
      </label>
      
      <p v-if="prop.description" class="field-description">
        {{ prop.description }}
      </p>
      
      <!-- Dropdown -->
      <select
        v-if="isDropdown(key)"
        :id="`field-${key}`"
        :value="formData[key] ?? getDefault(key)"
        class="field-input"
        @change="updateField(key, ($event.target).value)"
      >
        <option
          v-for="opt in getOptions(key)"
          :key="opt.value"
          :value="opt.value"
        >
          {{ opt.label || opt.value }}
        </option>
      </select>
      
      <!-- Slider -->
      <div v-else-if="isSlider(key)" class="slider-field">
        <input
          type="range"
          :id="`field-${key}`"
          :min="getMin(key)"
          :max="getMax(key)"
          :step="getStep(key)"
          :value="formData[key] ?? getDefault(key)"
          class="slider-input"
          @input="updateField(key, parseFloat(($event.target).value))"
        />
        <span class="slider-value">{{ formData[key] ?? getDefault(key) }}</span>
      </div>
      
      <!-- Toggle -->
      <label v-else-if="isToggle(key)" class="toggle-field">
        <input
          type="checkbox"
          :id="`field-${key}`"
          :checked="formData[key] ?? getDefault(key)"
          class="toggle-input"
          @change="updateField(key, ($event.target).checked)"
        />
        <span class="toggle-slider"></span>
      </label>
      
      <!-- Password -->
      <input
        v-else-if="isPassword(key)"
        type="password"
        :id="`field-${key}`"
        :value="formData[key] ?? ''"
        class="field-input"
        placeholder="Enter API key..."
        autocomplete="off"
        @input="updateField(key, ($event.target).value)"
      />
      
      <!-- Text -->
      <input
        v-else
        type="text"
        :id="`field-${key}`"
        :value="formData[key] ?? getDefault(key)"
        class="field-input"
        @input="updateField(key, ($event.target).value)"
      />
      
      <!-- Error/Warning display -->
      <div v-if="getFieldIssues(key).length" class="field-issues">
        <p
          v-for="(issue, idx) in getFieldIssues(key)"
          :key="idx"
          class="issue-message"
          :class="issue.severity"
        >
          {{ issue.message }}
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.provider-settings-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-field.has-error .field-input,
.form-field.has-error select {
  border-color: var(--accent-error, #ef4444);
}

.field-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text, #e5e5e5);
}

.required-badge {
  color: var(--accent-error, #ef4444);
  margin-left: 4px;
}

.field-description {
  font-size: 12px;
  color: var(--text-secondary, #9ca3af);
  margin: 0;
}

.field-input,
select {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border, #3f3f46);
  border-radius: 6px;
  background: var(--bg-surface, #1f1f23);
  color: var(--text, #e5e5e5);
  font-size: 14px;
  transition: border-color 0.15s;
}

.field-input:focus,
select:focus {
  outline: none;
  border-color: var(--accent, #4ECDC4);
}

select {
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%239ca3af' d='M6 8L2 4h8z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  padding-right: 32px;
}

.slider-field {
  display: flex;
  align-items: center;
  gap: 12px;
}

.slider-input {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: var(--border, #3f3f46);
  appearance: none;
  cursor: pointer;
}

.slider-input::-webkit-slider-thumb {
  appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--accent, #4ECDC4);
  cursor: pointer;
}

.slider-value {
  min-width: 48px;
  text-align: right;
  font-size: 14px;
  font-family: monospace;
  color: var(--text, #e5e5e5);
}

.toggle-field {
  position: relative;
  display: inline-block;
  width: 48px;
  height: 24px;
  cursor: pointer;
}

.toggle-input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  inset: 0;
  background: var(--border, #3f3f46);
  border-radius: 24px;
  transition: background 0.2s;
}

.toggle-slider::before {
  content: '';
  position: absolute;
  width: 18px;
  height: 18px;
  left: 3px;
  bottom: 3px;
  background: white;
  border-radius: 50%;
  transition: transform 0.2s;
}

.toggle-input:checked + .toggle-slider {
  background: var(--accent, #4ECDC4);
}

.toggle-input:checked + .toggle-slider::before {
  transform: translateX(24px);
}

.field-issues {
  margin-top: 4px;
}

.issue-message {
  font-size: 12px;
  margin: 2px 0;
}

.issue-message.error {
  color: var(--accent-error, #ef4444);
}

.issue-message.warning {
  color: var(--accent-warning, #f59e0b);
}
</style>
