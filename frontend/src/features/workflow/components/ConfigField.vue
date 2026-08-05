<script setup>
import { computed, ref, watch } from 'vue'
import { useOptionSource } from '../composables/useOptionSources.js'
import MediaAssetField from './MediaAssetField.vue'
import { isExpressionValue } from '../expressions.js'

/**
 * One schema field → one widget (n8n ParameterInput pattern).
 * Widget chosen by `field.type`: string, textarea, number, boolean,
 * options (static or allowlisted async source), json, media_asset.
 * Emits `update` with the new value.
 */
const props = defineProps({
  field: { type: Object, required: true },
  value: { required: false, default: undefined },
  expressionOptions: { type: Array, default: () => [] },
})
const emit = defineEmits(['update'])

// Async sources resolve through the backend allowlist; the composable
// caches one fetch per source for the whole session.
const asyncOptions = props.field.type === 'options' && props.field.options_source
  ? useOptionSource(props.field.options_source)
  : null

const jsonText = ref('')
const jsonError = ref('')

watch(
  () => props.value,
  (value) => {
    if (props.field.type === 'json') {
      jsonText.value = JSON.stringify(value ?? {}, null, 2)
      jsonError.value = ''
    }
  },
  { immediate: true },
)

function onJsonBlur() {
  try {
    const parsed = JSON.parse(jsonText.value || 'null')
    jsonError.value = ''
    emit('update', parsed ?? {})
  } catch {
    jsonError.value = 'Invalid JSON — fix it before it can be saved'
  }
}

function onNumberInput(event) {
  const raw = event.target.value
  if (raw === '') return
  const num = Number(raw)
  if (!Number.isFinite(num)) return
  const min = props.field.min
  const max = props.field.max
  let clamped = num
  if (min !== undefined && clamped < min) clamped = min
  if (max !== undefined && clamped > max) clamped = max
  emit('update', clamped)
}

const selectOptions = computed(() => {
  const listed = asyncOptions
    ? asyncOptions.value.options
    : (props.field.options || []).map((opt) => ({ value: opt, label: opt === '' ? '—' : String(opt) }))
  const current = props.value ?? props.field.default ?? ''
  // Keep a stored value visible even when it isn't offered any more
  // (older document, renamed provider) instead of silently showing option 0.
  if (current !== '' && !listed.some((opt) => opt.value === current)) {
    return [{ value: current, label: `${current} (unavailable)` }, ...listed]
  }
  return listed
})

const optionsLoading = computed(() => Boolean(asyncOptions?.value.loading))
const optionsError = computed(() => asyncOptions?.value.error || '')
const expressionActive = computed(() => isExpressionValue(props.value))

function restoreLiteral() {
  emit('update', props.field.default ?? (props.field.type === 'json' ? {} : ''))
}
</script>

<template>
  <label class="cfg-field">
    <span class="cfg-label">
      {{ field.label || field.name }}
      <span v-if="field.required" class="cfg-required" title="Required">*</span>
    </span>

    <span v-if="expressionOptions.length" class="cfg-expression-picker">
      <select aria-label="Insert expression" @change="$event.target.value && emit('update', $event.target.value); $event.target.value = ''">
        <option value="">Map from upstream output…</option>
        <option v-for="option in expressionOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
      </select>
      <button v-if="expressionActive" type="button" @click="restoreLiteral">Use literal</button>
    </span>

    <input
      v-if="expressionActive"
      class="cfg-input cfg-expression"
      type="text"
      :value="value"
      spellcheck="false"
      @input="emit('update', $event.target.value)"
    />

    <!-- string -->
    <input
      v-else-if="field.type === 'string'"
      class="cfg-input"
      type="text"
      :value="value ?? ''"
      :maxlength="field.max_length"
      :placeholder="field.placeholder || ''"
      @input="emit('update', $event.target.value)"
    />

    <!-- textarea -->
    <textarea
      v-else-if="field.type === 'textarea'"
      class="cfg-input cfg-textarea"
      :value="value ?? ''"
      :maxlength="field.max_length"
      rows="4"
      @input="emit('update', $event.target.value)"
    />

    <!-- number -->
    <span v-else-if="field.type === 'number'" class="cfg-number-row">
      <input
        class="cfg-input cfg-number"
        type="number"
        :value="value ?? field.default ?? 0"
        :min="field.min"
        :max="field.max"
        :step="field.step"
        @change="onNumberInput"
      />
      <input
        v-if="field.min !== undefined && field.max !== undefined"
        class="cfg-slider"
        type="range"
        :value="value ?? field.default ?? 0"
        :min="field.min"
        :max="field.max"
        :step="field.step"
        @input="onNumberInput"
      />
    </span>

    <!-- boolean -->
    <span v-else-if="field.type === 'boolean'" class="cfg-toggle-row">
      <input
        class="cfg-checkbox"
        type="checkbox"
        :checked="Boolean(value)"
        @change="emit('update', $event.target.checked)"
      />
      <span class="cfg-toggle-hint">{{ value ? 'On' : 'Off' }}</span>
    </span>

    <!-- options (static, or resolved through the backend allowlist) -->
    <span v-else-if="field.type === 'options'" class="cfg-json">
      <select
        class="cfg-input cfg-select"
        :value="value ?? field.default ?? ''"
        :disabled="optionsLoading"
        :title="optionsLoading ? 'Loading options…' : ''"
        @change="emit('update', $event.target.value)"
      >
        <option v-if="optionsLoading" :value="value ?? field.default ?? ''">Loading…</option>
        <option v-for="opt in selectOptions" :key="String(opt.value)" :value="opt.value">
          {{ opt.label }}
        </option>
      </select>
      <span v-if="optionsError" class="cfg-error">{{ optionsError }}</span>
    </span>

    <!-- json -->
    <span v-else-if="field.type === 'json'" class="cfg-json">
      <textarea
        v-model="jsonText"
        class="cfg-input cfg-textarea cfg-mono"
        rows="5"
        spellcheck="false"
        @blur="onJsonBlur"
      />
      <span v-if="jsonError" class="cfg-error">{{ jsonError }}</span>
    </span>

    <!-- media_asset: managed reference into output/branding/ -->
    <MediaAssetField
      v-else-if="field.type === 'media_asset'"
      :field="field"
      :value="value"
      @update="(asset) => emit('update', asset)"
    />

    <span v-else class="cfg-note">Unsupported field type: {{ field.type }}</span>

    <span v-if="field.description" class="cfg-desc">{{ field.description }}</span>
  </label>
</template>

<style scoped>
.cfg-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 8px 14px;
}

.cfg-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
}

.cfg-required {
  color: var(--accent-warning, #ffb347);
}

.cfg-input {
  width: 100%;
  background: var(--bg-dark);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  font-size: 12px;
  padding: 7px 10px;
  outline: none;
  font-family: inherit;
}

.cfg-input:focus {
  border-color: var(--accent);
}

.cfg-textarea {
  resize: vertical;
  min-height: 60px;
}

.cfg-mono {
  font-family: ui-monospace, 'Cascadia Mono', Consolas, monospace;
  font-size: 11.5px;
}

.cfg-number-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.cfg-number {
  width: 84px;
}

.cfg-slider {
  flex: 1;
  accent-color: var(--accent);
}

.cfg-toggle-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.cfg-checkbox {
  width: 16px;
  height: 16px;
  accent-color: var(--accent);
}

.cfg-toggle-hint {
  font-size: 11px;
  color: var(--text-muted);
}

.cfg-select {
  cursor: pointer;
}

.cfg-json {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.cfg-error {
  font-size: 11px;
  color: #f87171;
}

.cfg-note {
  font-size: 11px;
  color: var(--text-muted);
  font-style: italic;
}

.cfg-desc {
  font-size: 10.5px;
  color: var(--text-muted);
  line-height: 1.4;
}

.cfg-expression-picker { display: flex; gap: 5px; }
.cfg-expression-picker select { min-width: 0; flex: 1; }
.cfg-expression-picker select,
.cfg-expression-picker button { background: var(--bg-dark); border: 1px solid var(--border); border-radius: 6px; color: var(--text-secondary); font-size: 10.5px; padding: 4px 6px; }
.cfg-expression { font-family: ui-monospace, 'Cascadia Mono', Consolas, monospace; color: var(--accent); }
</style>
