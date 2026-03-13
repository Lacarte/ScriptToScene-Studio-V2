<script setup>
import { ref, onMounted } from 'vue'
import { useSettings } from '../composables/useSettings.js'
import { useToast } from '@/shared/composables/useToast.js'
import SettingsToggle from '../components/SettingsToggle.vue'
import ClearProjectsDialog from '../components/ClearProjectsDialog.vue'

defineOptions({ name: 'SettingsPage' })

const { settings, loading, health, healthLoading, update, fetchHealth } = useSettings()
const toast = useToast()
const showClearDialog = ref(false)

onMounted(() => {
  fetchHealth()
})

async function onToggle(key, value) {
  try {
    await update(key, value)
  } catch {
    toast.error(`Failed to update setting.`)
  }
}

function featureStatus(val) {
  if (val === true || val === 'ok' || val === 'available') return 'available'
  if (val && typeof val === 'string' && val !== 'unavailable' && val !== 'missing') return 'available'
  return 'unavailable'
}

function featureLabel(val) {
  if (val === true) return 'Available'
  if (val === false || val === null || val === undefined) return 'Unavailable'
  return String(val)
}
</script>

<template>
  <div class="settings-page">
    <h2 class="page-title">Settings</h2>

    <!-- Text Processing -->
    <section class="card">
      <h3 class="card-heading">Text Processing</h3>
      <SettingsToggle
        :model-value="settings['sts-normalize'] ?? true"
        label="Normalize"
        description="Convert numbers, symbols, abbreviations to spoken words"
        @update:model-value="onToggle('sts-normalize', $event)"
      />
      <SettingsToggle
        :model-value="settings['sts-clean'] ?? true"
        label="Markdown cleanup"
        description="Strip markdown, URLs, brackets before generation"
        @update:model-value="onToggle('sts-clean', $event)"
      />
    </section>

    <!-- Storage -->
    <section class="card">
      <h3 class="card-heading">Storage</h3>
      <SettingsToggle
        :model-value="settings['sts-editor-storage'] ?? true"
        label="Local Storage"
        description="Save edits, history, zoom, preferences"
        @update:model-value="onToggle('sts-editor-storage', $event)"
      />
      <SettingsToggle
        :model-value="settings['sts-editor-session-storage'] ?? true"
        label="Session Storage"
        description="Keep staged timeline data between pages"
        @update:model-value="onToggle('sts-editor-session-storage', $event)"
      />
    </section>

    <!-- Notifications -->
    <section class="card">
      <h3 class="card-heading">Notifications</h3>
      <SettingsToggle
        :model-value="settings['sts-sound-enabled'] ?? true"
        label="Sound Notifications"
        description="Play sound on pipeline/export/asset completion"
        @update:model-value="onToggle('sts-sound-enabled', $event)"
      />
    </section>

    <!-- Feature Status -->
    <section class="card">
      <h3 class="card-heading">Feature Status</h3>
      <div v-if="healthLoading" class="status-loading">Checking features...</div>
      <div v-else-if="!health" class="status-loading">Unable to reach server.</div>
      <div v-else class="status-grid">
        <div class="status-row">
          <span class="status-label">Alignment</span>
          <span class="status-badge" :class="featureStatus(health.alignment)">
            {{ featureLabel(health.alignment) }}
          </span>
        </div>
        <div class="status-row">
          <span class="status-label">FFmpeg</span>
          <span class="status-badge" :class="featureStatus(health.ffmpeg)">
            {{ featureLabel(health.ffmpeg) }}
          </span>
        </div>
        <div class="status-row">
          <span class="status-label">TTS Model</span>
          <span class="status-badge" :class="featureStatus(health.tts_model)">
            {{ featureLabel(health.tts_model) }}
          </span>
        </div>
      </div>
    </section>

    <!-- Danger Zone -->
    <section class="card danger-card">
      <h3 class="card-heading danger-heading">Danger Zone</h3>
      <div class="danger-row">
        <div class="danger-info">
          <span class="danger-label">Clear All Projects</span>
          <span class="danger-desc">Permanently delete all generated project data, audio, and exports.</span>
        </div>
        <button class="btn-danger" @click="showClearDialog = true">Clear All</button>
      </div>
    </section>

    <!-- About -->
    <section class="card">
      <h3 class="card-heading">About</h3>
      <div class="about-grid">
        <div class="about-row">
          <span class="about-label">App</span>
          <span class="about-value">ScriptToScene Studio</span>
        </div>
        <div class="about-row">
          <span class="about-label">TTS Engine</span>
          <span class="about-value mono">kokoro-onnx</span>
        </div>
        <div class="about-row">
          <span class="about-label">Sample Rate</span>
          <span class="about-value mono">24,000 Hz</span>
        </div>
        <div class="about-row">
          <span class="about-label">Built by</span>
          <span class="about-value">Mr. Lacarte</span>
        </div>
      </div>
    </section>

    <ClearProjectsDialog v-if="showClearDialog" @close="showClearDialog = false" />
  </div>
</template>

<style scoped>
.settings-page {
  max-width: 640px;
  margin: 0 auto;
  padding: 32px 24px;
}

.page-title {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 700;
  margin: 0 0 4px;
}

/* ---- Card ---- */
.card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 16px;
}

.card-heading {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 8px;
}

/* ---- Feature Status ---- */
.status-loading {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 8px 0;
}

.status-grid {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
}

.status-row:not(:last-child) {
  border-bottom: 1px solid var(--border);
}

.status-label {
  font-size: 14px;
  color: var(--text);
}

.status-badge {
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 10px;
}

.status-badge.available {
  background: rgba(78, 205, 196, 0.12);
  color: var(--accent);
}

.status-badge.unavailable {
  background: rgba(239, 68, 68, 0.12);
  color: var(--coral);
}

/* ---- Danger Zone ---- */
.danger-card {
  border-color: rgba(239, 68, 68, 0.25);
}

.danger-heading {
  color: var(--coral);
}

.danger-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.danger-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.danger-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
}

.danger-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.btn-danger {
  flex-shrink: 0;
  padding: 8px 18px;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  background: var(--coral);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: opacity 0.15s;
}

.btn-danger:hover {
  opacity: 0.9;
}

/* ---- About ---- */
.about-grid {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.about-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
}

.about-row:not(:last-child) {
  border-bottom: 1px solid var(--border);
}

.about-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.about-value {
  font-size: 13px;
  color: var(--text);
  font-weight: 500;
}

.about-value.mono {
  font-family: var(--font-mono);
  font-size: 12px;
}
</style>
