<script setup>
import { ref, onMounted } from 'vue'
import { useSettings } from '../composables/useSettings.js'
import { useToast } from '@/shared/composables/useToast.js'
import { useWelcomeOverlay } from '@/shared/composables/useWelcomeOverlay.js'
import SettingsToggle from '../components/SettingsToggle.vue'
import ClearProjectsDialog from '../components/ClearProjectsDialog.vue'

defineOptions({ name: 'SettingsPage' })

const { settings, loading, health, healthLoading, update, fetchHealth } = useSettings()
const toast = useToast()
const welcome = useWelcomeOverlay()
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

function replayWelcome() {
  welcome.replayWelcome()
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
    <div style="margin-bottom:32px">
      <h2 class="page-title">Settings</h2>
      <p class="page-subtitle">Configure generation parameters</p>
    </div>

    <!-- Text Processing -->
    <section class="card p-5 mb-4">
      <label class="section-label">Text Processing</label>
      <SettingsToggle
        :model-value="settings['sts-normalize'] ?? true"
        label="Text Normalization"
        description="Convert numbers, symbols, abbreviations to spoken words before TTS"
        @update:model-value="onToggle('sts-normalize', $event)"
      />
      <SettingsToggle
        :model-value="settings['sts-clean'] ?? true"
        label="Markdown Cleanup"
        description="Strip markdown formatting, URLs, and brackets before generation"
        @update:model-value="onToggle('sts-clean', $event)"
      />
    </section>

    <!-- Storage -->
    <section class="card p-5 mb-4">
      <label class="section-label">Storage</label>
      <SettingsToggle
        :model-value="settings['sts-editor-storage'] ?? true"
        label="Local Storage"
        description="Save edits, history, zoom, and preferences across sessions"
        @update:model-value="onToggle('sts-editor-storage', $event)"
      />
      <SettingsToggle
        :model-value="settings['sts-editor-session-storage'] ?? true"
        label="Session Storage"
        description="Keep staged timeline data when navigating between pages"
        @update:model-value="onToggle('sts-editor-session-storage', $event)"
      />
    </section>

    <!-- Notifications -->
    <section class="card p-5 mb-4">
      <label class="section-label">Notifications</label>
      <SettingsToggle
        :model-value="settings['sts-sound-enabled'] ?? true"
        label="Sound Notifications"
        description="Play a sound when pipeline, export, or asset download completes"
        @update:model-value="onToggle('sts-sound-enabled', $event)"
      />
    </section>

    <!-- Features -->
    <section class="card p-5 mb-4">
      <label class="section-label">Features</label>
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
    <section class="card p-5 mb-4 danger-card">
      <label class="danger-zone-label">Danger Zone</label>
      <div class="danger-row">
        <div class="danger-info">
          <span class="danger-label">Clear All Projects</span>
          <span class="danger-desc">Move all project data (TTS, alignments, scenes, assets, captions, music) to trash folders. This cannot be easily undone.</span>
        </div>
        <button class="btn-danger" @click="showClearDialog = true">Clear All</button>
      </div>
    </section>

    <!-- About -->
    <section class="card p-5 mb-4 about-card">
      <label class="about-heading">About</label>
      <div class="about-grid">
        <div class="about-row">
          <span class="about-label">Application</span>
          <span class="about-value mono">ScriptToScene Studio</span>
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
          <span class="about-value accent">Mr. Lacarte</span>
        </div>
      </div>
      <button class="action-btn replay-btn" @click="replayWelcome">Replay Welcome</button>
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
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text);
  margin: 0;
}

.page-subtitle {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
}

.p-5 { padding: 20px; }
.mb-4 { margin-bottom: 16px; }

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

.danger-zone-label {
  display: block;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: #ef4444;
  margin-bottom: 12px;
}

.danger-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(239, 68, 68, 0.06);
}

.danger-info {
  flex: 1;
  min-width: 0;
}

.danger-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
}

.danger-desc {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
  line-height: 1.4;
}

.btn-danger {
  flex-shrink: 0;
  margin-left: 12px;
  padding: 7px 16px;
  font-size: 12px;
  font-weight: 600;
  color: #ef4444;
  background: transparent;
  border: 1px solid rgba(239, 68, 68, 0.4);
  border-radius: 8px;
  cursor: pointer;
  transition: opacity 0.15s;
}

.btn-danger:hover {
  background: #ef4444;
  color: #fff;
}

/* ---- About ---- */
.about-heading {
  display: block;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--text-muted);
  margin-bottom: 12px;
}

.about-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.about-row {
  display: flex;
  justify-content: space-between;
}

.about-label {
  font-size: 13px;
  color: var(--text-muted);
}

.about-value {
  font-size: 13px;
  color: var(--text);
}

.about-value.mono {
  font-family: var(--font-mono);
}

.about-value.accent {
  font-weight: 500;
  color: var(--accent);
}

.replay-btn {
  margin-top: 14px;
  padding: 5px 12px;
  font-size: 10px;
  width: 100%;
}
</style>
