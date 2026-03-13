<script setup>
import { computed } from 'vue'

defineOptions({ name: 'GrabberControls' })

const props = defineProps({
  provider: { type: String, default: 'grok' },
  arguments: { type: String, default: '' },
  aspectRatio: { type: String, default: '16:9' },
  providerOptions: { type: Object, default: () => ({}) },
  grabberRunning: { type: Boolean, default: false },
  progress: { type: Object, default: () => ({ total: 0, ready: 0, error: 0, pending: 0, percent: 0 }) },
  selectedCount: { type: Number, default: 0 },
  sceneCount: { type: Number, default: 0 },
})

const emit = defineEmits([
  'update:provider',
  'update:arguments',
  'update:aspectRatio',
  'update:providerOption',
  'start',
  'stop',
  'select-all',
  'select-pending',
  'select-none',
  'resend-selected',
  'update:autoType',
])

const providers = [
  { value: 'grok', label: 'Grok' },
  { value: 'midjourney', label: 'Midjourney' },
  { value: 'meta-ai', label: 'Meta AI' },
  { value: 'kie-ai', label: 'Kie AI' },
]

const aspectRatios = ['16:9', '9:16', '1:1', '4:3', '3:4', '21:9']

const showMidjourneyArgs = computed(() => props.provider === 'midjourney')
const showGrokOptions = computed(() => props.provider === 'grok')
const showKieOptions = computed(() => props.provider === 'kie-ai')

const progressText = computed(() => {
  const p = props.progress
  if (!p.total) return ''
  const parts = [`${p.ready}/${p.total} ready`]
  if (p.error) parts.push(`${p.error} errors`)
  if (p.pending && props.grabberRunning) parts.push(`${p.pending} pending`)
  return parts.join(' \u00B7 ')
})

const progressPercent = computed(() => props.progress.percent)
</script>

<template>
  <section class="controls-card card">
    <h3 class="card-heading">Controls</h3>

    <div class="controls-grid">
      <!-- Provider -->
      <div class="control-group">
        <label class="control-label">Provider</label>
        <select
          class="control-select"
          :value="provider"
          @change="emit('update:provider', $event.target.value)"
        >
          <option v-for="p in providers" :key="p.value" :value="p.value">
            {{ p.label }}
          </option>
        </select>
      </div>

      <!-- Aspect Ratio -->
      <div class="control-group">
        <label class="control-label">Aspect Ratio</label>
        <div class="ratio-buttons">
          <button
            v-for="ar in aspectRatios"
            :key="ar"
            class="ratio-btn"
            :class="{ active: aspectRatio === ar }"
            @click="emit('update:aspectRatio', ar)"
          >
            {{ ar }}
          </button>
        </div>
      </div>

      <!-- Midjourney arguments -->
      <div v-if="showMidjourneyArgs" class="control-group full-width">
        <label class="control-label">Arguments</label>
        <input
          type="text"
          class="control-input"
          placeholder="--ar 16:9 --style raw --v 6"
          :value="arguments"
          @input="emit('update:arguments', $event.target.value)"
        />
      </div>

      <!-- Grok options -->
      <template v-if="showGrokOptions">
        <div class="control-group">
          <label class="control-label">Mode</label>
          <select
            class="control-select"
            :value="providerOptions.grok_mode || 'default'"
            @change="emit('update:providerOption', 'grok_mode', $event.target.value)"
          >
            <option value="default">Default</option>
            <option value="fast">Fast</option>
            <option value="quality">Quality</option>
          </select>
        </div>
        <div class="control-group">
          <label class="control-label">Quality</label>
          <select
            class="control-select"
            :value="providerOptions.grok_quality || 'standard'"
            @change="emit('update:providerOption', 'grok_quality', $event.target.value)"
          >
            <option value="standard">Standard</option>
            <option value="high">High</option>
          </select>
        </div>
        <div class="control-group">
          <label class="control-label">Duration</label>
          <select
            class="control-select"
            :value="providerOptions.grok_duration || '5'"
            @change="emit('update:providerOption', 'grok_duration', $event.target.value)"
          >
            <option value="5">5s</option>
            <option value="10">10s</option>
            <option value="15">15s</option>
          </select>
        </div>
      </template>

      <!-- Kie AI options -->
      <template v-if="showKieOptions">
        <div class="control-group">
          <label class="control-label">Model</label>
          <select
            class="control-select"
            :value="providerOptions.model || 'default'"
            @change="emit('update:providerOption', 'model', $event.target.value)"
          >
            <option value="default">Default</option>
            <option value="flux">Flux</option>
            <option value="sdxl">SDXL</option>
          </select>
        </div>
        <div class="control-group">
          <label class="control-label">Resolution</label>
          <select
            class="control-select"
            :value="providerOptions.resolution || '1024x1024'"
            @change="emit('update:providerOption', 'resolution', $event.target.value)"
          >
            <option value="512x512">512x512</option>
            <option value="768x768">768x768</option>
            <option value="1024x1024">1024x1024</option>
            <option value="1280x720">1280x720</option>
            <option value="1920x1080">1920x1080</option>
          </select>
        </div>
        <div class="control-group">
          <label class="control-label">Output Format</label>
          <select
            class="control-select"
            :value="providerOptions.output_format || 'png'"
            @change="emit('update:providerOption', 'output_format', $event.target.value)"
          >
            <option value="png">PNG</option>
            <option value="jpg">JPG</option>
            <option value="webp">WebP</option>
          </select>
        </div>
      </template>
    </div>

    <!-- Auto-type -->
    <label class="auto-type-toggle">
      <input
        type="checkbox"
        :checked="providerOptions.auto_type"
        @change="emit('update:autoType', $event.target.checked)"
      />
      <span>Auto-type prompts into provider</span>
    </label>

    <!-- Start / Stop -->
    <div class="action-row">
      <button
        v-if="!grabberRunning"
        class="btn-start"
        :disabled="!sceneCount"
        @click="emit('start')"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polygon points="5,3 19,12 5,21" />
        </svg>
        Start Grabber
      </button>
      <button
        v-else
        class="btn-stop"
        @click="emit('stop')"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="6" y="6" width="12" height="12" rx="1" />
        </svg>
        Stop Grabber
      </button>
    </div>

    <!-- Progress display -->
    <div v-if="progress.total" class="progress-section">
      <div class="progress-text">{{ progressText }}</div>
      <div class="progress-bar-track">
        <div
          class="progress-bar-fill"
          :style="{ width: progressPercent + '%' }"
        />
      </div>
    </div>

    <!-- Selection bar -->
    <div v-if="sceneCount" class="selection-bar">
      <span class="selection-count">{{ selectedCount }} selected</span>
      <div class="selection-actions">
        <button class="btn-sel" @click="emit('select-all')">Select All</button>
        <button class="btn-sel" @click="emit('select-pending')">Select Pending</button>
        <button
          v-if="selectedCount"
          class="btn-sel btn-sel-accent"
          @click="emit('resend-selected')"
        >
          Resend Selected
        </button>
        <button
          v-if="selectedCount"
          class="btn-sel"
          @click="emit('select-none')"
        >
          Clear
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.controls-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}

.card-heading {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 16px;
}

/* ---- Controls grid ---- */
.controls-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-bottom: 14px;
}

.control-group.full-width {
  grid-column: 1 / -1;
}

.control-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}

.control-select,
.control-input {
  width: 100%;
  font-size: 13px;
  font-family: var(--font-mono);
  color: var(--text);
  background: var(--bg-deeper, #0a0a0a);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 7px 10px;
  transition: border-color 0.15s;
}

.control-select:focus,
.control-input:focus {
  outline: none;
  border-color: var(--accent);
}

.control-select option {
  background: var(--bg-surface);
  color: var(--text);
}

/* ---- Ratio buttons ---- */
.ratio-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.ratio-btn {
  font-size: 11px;
  font-family: var(--font-mono);
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--bg-deeper, #0a0a0a);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 3px 8px;
  cursor: pointer;
  transition: all 0.15s;
}

.ratio-btn.active {
  color: var(--accent);
  border-color: var(--accent);
  background: rgba(78, 205, 196, 0.08);
}

.ratio-btn:hover:not(.active) {
  border-color: var(--text-secondary);
}

/* ---- Auto-type ---- */
.auto-type-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 14px;
  cursor: pointer;
}

.auto-type-toggle input {
  accent-color: var(--accent);
  width: 15px;
  height: 15px;
}

/* ---- Start / Stop ---- */
.action-row {
  margin-bottom: 14px;
}

.btn-start,
.btn-stop {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  padding: 10px 24px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: opacity 0.15s;
}

.btn-start {
  background: var(--accent);
  color: #0d1117;
}

.btn-stop {
  background: var(--coral);
  color: #fff;
}

.btn-start:hover,
.btn-stop:hover {
  opacity: 0.9;
}

.btn-start:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ---- Progress ---- */
.progress-section {
  margin-bottom: 14px;
}

.progress-text {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.progress-bar-track {
  width: 100%;
  height: 6px;
  background: var(--bg-deeper, #0a0a0a);
  border-radius: 3px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 3px;
  transition: width 0.4s ease;
}

/* ---- Selection ---- */
.selection-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.selection-count {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.selection-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.btn-sel {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--bg-deeper, #0a0a0a);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-sel:hover {
  color: var(--text);
  border-color: var(--text-secondary);
}

.btn-sel-accent {
  color: var(--accent);
  border-color: var(--accent);
  background: rgba(78, 205, 196, 0.06);
}

.btn-sel-accent:hover {
  color: var(--accent);
  background: rgba(78, 205, 196, 0.12);
}

@media (max-width: 600px) {
  .controls-grid {
    grid-template-columns: 1fr;
  }

  .selection-bar {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
