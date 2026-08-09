<script setup>
import { computed } from 'vue'
import ProviderConfigurator from '@/features/providers/components/ProviderConfigurator.vue'
import ProviderSettingsForm from '@/features/providers/components/ProviderSettingsForm.vue'
import { isSecretField } from '@/shared/schema/providerSettings.js'

defineOptions({ name: 'GrabberControls' })

const props = defineProps({
  providerId: { type: String, default: '' },
  providerLabel: { type: String, default: '' },
  providerSchema: { type: Object, default: () => ({}) },
  aspectRatio: { type: String, default: '9:16' },
  providerOptions: { type: Object, default: () => ({}) },
  grabberRunning: { type: Boolean, default: false },
  progress: { type: Object, default: () => ({ total: 0, ready: 0, error: 0, pending: 0, percent: 0 }) },
  selectedCount: { type: Number, default: 0 },
  sceneCount: { type: Number, default: 0 },
})

const emit = defineEmits([
  'update:aspectRatio',
  'update:providerOptions',
  'start',
  'stop',
  'select-all',
  'select-pending',
  'select-none',
  'resend-selected',
  'validate-and-build',
])

/**
 * The per-run form is the selected provider's own settings schema minus its
 * secrets (step 12.4). It replaces three hand-written blocks, each gated on a
 * literal provider id — one of which named an alias rather than a provider
 * (contracts.md §40.3 rule 2) and so could never render at all.
 *
 * Secrets are dropped rather than masked: these values travel in the grabber
 * request and are persisted with the job, so a credential belongs behind the
 * gear, in the settings modal, and nowhere on this page (§22.6). Nothing is
 * required here either — a per-run override may always be left alone.
 */
const perRunSchema = computed(() => {
  const properties = props.providerSchema?.properties || {}
  const visible = Object.fromEntries(
    Object.entries(properties).filter(([key, prop]) => !isSecretField(key, prop)),
  )
  return { ...props.providerSchema, properties: visible, required: [] }
})

const hasPerRunOptions = computed(() => Object.keys(perRunSchema.value.properties).length > 0)

const startLabel = computed(() =>
  props.providerLabel ? `Send to ${props.providerLabel}` : 'Start Grabber',
)

const progressText = computed(() => {
  const p = props.progress
  if (!p.total) return '0 / 0 complete'
  return `${p.ready} / ${p.total} complete`
})

const progressPercent = computed(() => props.progress.percent)
</script>

<template>
  <section class="controls-card card">
    <!-- Controls row -->
    <div class="controls-row">
      <div class="control-group">
        <ProviderConfigurator domain="animator" label="Provider" variant="inline" />
      </div>

      <div class="control-group">
        <label class="control-label">Aspect Ratio</label>
        <select
          class="control-select"
          :value="aspectRatio"
          @change="emit('update:aspectRatio', $event.target.value)"
        >
          <option value="9:16">9:16 (Vertical)</option>
          <option value="16:9">16:9 (Landscape)</option>
          <option value="1:1">1:1 (Square)</option>
        </select>
      </div>
    </div>

    <!-- Per-run provider options, rendered from the provider's own schema -->
    <div v-if="hasPerRunOptions" class="per-run-options">
      <ProviderSettingsForm
        :model-value="providerOptions"
        :schema="perRunSchema"
        domain="animator"
        :provider-id="providerId"
        @update:model-value="(val) => emit('update:providerOptions', val)"
      />
    </div>

    <!-- Grabber + Progress row -->
    <div class="grabber-row">
      <button
        v-if="!grabberRunning"
        class="gen-btn btn-grabber"
        :disabled="!sceneCount"
        @click="emit('start')"
      >
        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="vertical-align:-2px;margin-right:6px">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
        {{ startLabel }}
      </button>
      <button
        v-else
        class="btn-stop"
        @click="emit('stop')"
      >
        <svg width="14" height="14" fill="currentColor" viewBox="0 0 24 24" style="vertical-align:-2px;margin-right:6px">
          <rect x="5" y="5" width="14" height="14" rx="2" />
        </svg>
        Stop Grabber
      </button>

      <span class="progress-text">{{ progressText }}</span>

      <button
        class="action-btn"
        style="padding:6px 14px;font-size:11px;margin-left:auto"
        title="Retry failed/pending downloads"
        @click="emit('resend-selected')"
      >Retry Downloads</button>
      <button
        class="action-btn"
        style="padding:6px 14px;font-size:11px"
        @click="emit('select-all')"
      >Download All</button>
      <button
        class="action-btn validate-build-btn"
        title="Validate assets, generate thumbnails, assemble & edit"
        @click="emit('validate-and-build')"
      >
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
        Validate &amp; Build
      </button>
    </div>

    <!-- Progress bar -->
    <div v-if="progress.total && grabberRunning" class="progress-bar-wrap">
      <div class="progress-bar-track">
        <div class="progress-bar-fill" :style="{ width: progressPercent + '%' }" />
      </div>
    </div>

    <!-- Selection bar -->
    <div v-if="selectedCount > 0" class="selection-bar">
      <span class="selection-count">{{ selectedCount }} selected</span>
      <button class="action-btn" style="padding:5px 12px;font-size:10px;font-weight:600;background:rgba(78,205,196,0.12);color:var(--accent);border:1px solid rgba(78,205,196,0.25);border-radius:6px" @click="emit('resend-selected')">Resend Selected</button>
      <button class="action-btn" style="padding:5px 12px;font-size:10px" @click="emit('select-pending')">Select Pending</button>
      <button class="action-btn" style="padding:5px 12px;font-size:10px" @click="emit('select-all')">Toggle All</button>
    </div>
  </section>
</template>

<style scoped>
.controls-card {
  padding: 20px;
  margin-bottom: 16px;
  transition: border-color 0.2s;
}

.controls-card:hover {
  border-color: var(--border-hover);
}

/* ---- Controls row (inline flex like original) ---- */
.controls-row {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.control-label {
  display: block;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.control-select {
  padding: 8px 12px;
  font-size: 12px;
  font-family: inherit;
  color: var(--text);
  background: var(--bg-darkest);
  border: 1.5px solid var(--border);
  border-radius: 8px;
  outline: none;
  transition: border-color 0.2s;
}

.control-select:focus {
  border-color: var(--accent);
}

.control-select option {
  background: var(--bg-surface);
  color: var(--text);
}

/* ---- Grabber row (inline flex like original) ---- */
.grabber-row {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}

.gen-btn.btn-grabber {
  padding: 10px 20px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  color: white;
  background: linear-gradient(135deg, var(--accent), #3BA89F);
  box-shadow: 0 4px 16px rgba(78, 205, 196, 0.25);
  border: none;
  cursor: pointer;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.gen-btn.btn-grabber:hover:not(:disabled) {
  box-shadow: 0 6px 24px rgba(78, 205, 196, 0.35);
  transform: translateY(-1px);
}

.gen-btn.btn-grabber:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-stop {
  display: inline-flex;
  align-items: center;
  padding: 10px 20px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  color: white;
  background: var(--coral);
  border: none;
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 0.15s;
}

.btn-stop:hover {
  opacity: 0.9;
}

.per-run-options {
  margin-bottom: 14px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-darkest);
}

.progress-text {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}

.action-btn {
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s;
}

.action-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.validate-build-btn {
  padding: 6px 14px !important;
  font-size: 11px !important;
  background: rgba(78, 205, 196, 0.08);
  border-color: rgba(78, 205, 196, 0.3);
  color: #4ECDC4;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.validate-build-btn:hover {
  background: rgba(78, 205, 196, 0.15);
  border-color: #4ECDC4;
  color: #4ECDC4;
}

/* ---- Progress bar ---- */
.progress-bar-wrap {
  margin-top: 10px;
}

.progress-bar-track {
  height: 3px;
  background: var(--bg-darkest);
  border-radius: 2px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--accent), #3BA89F);
  border-radius: 2px;
  transition: width 0.4s ease;
}

/* ---- Selection bar ---- */
.selection-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 10px;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(78, 205, 196, 0.06);
  border: 1px solid rgba(78, 205, 196, 0.2);
}

.selection-count {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
}
</style>
