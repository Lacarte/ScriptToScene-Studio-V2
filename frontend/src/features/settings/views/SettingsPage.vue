<script setup>
import { ref, onMounted } from 'vue'
import { useSettings } from '../composables/useSettings.js'
import { useScenes } from '@/features/scenes/composables/useScenes.js'
import { useToast } from '@/shared/composables/useToast.js'
import { useWelcomeOverlay } from '@/shared/composables/useWelcomeOverlay.js'
import { api } from '@/shared/api/client.js'
import SettingsToggle from '../components/SettingsToggle.vue'
import ClearProjectsDialog from '../components/ClearProjectsDialog.vue'

defineOptions({ name: 'SettingsPage' })

const { settings, loading, health, healthLoading, update, fetchHealth } = useSettings()
const { templates: styleTemplates } = useScenes()
const toast = useToast()
const welcome = useWelcomeOverlay()
const showClearDialog = ref(false)
const restarting = ref(false)
const browsing = ref(false)

async function browseSyncFolder() {
  browsing.value = true
  try {
    const current = settings.value['sts-sync-folder'] || ''
    const result = await api.post('/api/settings/browse-folder', { body: { initial: current } })
    if (result.path) {
      await update('sts-sync-folder', result.path)
      toast.success('Sync folder updated')
    }
  } catch (e) {
    toast.error('Failed to open folder picker')
  } finally {
    browsing.value = false
  }
}
const captionPresets = ref([
  { id: 'bold_popup', name: 'Bold Pop-up' },
  { id: 'subtitle_bar', name: 'Subtitle Bar' },
  { id: 'karaoke', name: 'Karaoke Highlight' },
  { id: 'minimal', name: 'Minimal' },
  { id: 'single_line', name: 'Single Line' },
])

async function restartServer() {
  restarting.value = true
  toast.info('Restarting server...')
  try {
    await api.post('/api/restart')
  } catch {
    // Expected — server shuts down before responding
  }
  // Wait for old server to die
  await new Promise(r => setTimeout(r, 2000))
  // Poll until new server is healthy
  for (let i = 0; i < 20; i++) {
    try {
      await api.get('/api/health')
      toast.success('Server restarted — refreshing...')
      await new Promise(r => setTimeout(r, 500))
      window.location.reload()
      return
    } catch {
      await new Promise(r => setTimeout(r, 1000))
    }
  }
  restarting.value = false
  toast.error('Server did not come back. Check the terminal.')
}

function refreshFrontend() {
  window.location.reload()
}

async function loadCaptionPresets() {
  try {
    const presets = await api.get('/api/captions/presets')
    if (Array.isArray(presets) && presets.length) {
      captionPresets.value = presets
    }
  } catch (e) {
    console.warn('[Settings] Failed to load caption presets:', e.message)
  }
}

onMounted(() => {
  fetchHealth()
  loadCaptionPresets()
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

    <!-- Pipeline Defaults -->
    <section class="card p-5 mb-4">
      <label class="section-label">Pipeline Defaults</label>
      <div class="export-defaults">
        <div class="export-default-row">
          <div class="export-copy">
            <label class="export-label">Default Style</label>
            <p class="export-help">Visual style applied to new pipelines and story generation</p>
          </div>
          <select
            class="input-field export-select"
            :value="settings['sts-default-style'] ?? 'cinematic'"
            @change="onToggle('sts-default-style', $event.target.value)"
          >
            <option v-for="t in styleTemplates" :key="t.id" :value="t.id">{{ t.name }}</option>
          </select>
        </div>
      </div>
    </section>

    <!-- Export Defaults -->
    <section class="card p-5 mb-4">
      <label class="section-label">Export Defaults</label>
      <div class="export-defaults">
        <div class="export-default-row">
          <label class="export-label">Profile</label>
          <select
            class="input-field export-select"
            :value="settings['sts-export-profile'] ?? 'yt_shorts'"
            @change="onToggle('sts-export-profile', $event.target.value)"
          >
            <option value="yt_shorts">YouTube Shorts (9:16)</option>
            <option value="tiktok">TikTok (9:16)</option>
            <option value="reels">Reels (9:16)</option>
            <option value="yt_landscape">YouTube (16:9)</option>
            <option value="square">Square (1:1)</option>
          </select>
        </div>
        <SettingsToggle
          :model-value="settings['sts-export-captions'] ?? true"
          label="Captions"
          description="Include captions in exported videos by default"
          @update:model-value="onToggle('sts-export-captions', $event)"
        />
        <div class="export-default-row">
          <div class="export-copy">
            <label class="export-label">Caption Preset</label>
            <p class="export-help">Applied when captions are auto-generated for new projects</p>
          </div>
          <select
            class="input-field export-select"
            :value="settings['sts-caption-default-preset'] ?? 'bold_popup'"
            @change="onToggle('sts-caption-default-preset', $event.target.value)"
          >
            <option
              v-for="preset in captionPresets"
              :key="preset.id"
              :value="preset.id"
            >
              {{ preset.name || preset.id }}
            </option>
          </select>
        </div>
        <SettingsToggle
          :model-value="settings['sts-export-grain'] ?? false"
          label="Film Grain"
          description="Apply grain overlay texture to exports"
          @update:model-value="onToggle('sts-export-grain', $event)"
        />
      </div>
    </section>

    <!-- Sync -->
    <section class="card p-5 mb-4">
      <label class="section-label">Phone Sync</label>
      <div class="export-defaults">
        <div class="export-default-row" style="flex-direction: column; align-items: stretch; gap: 8px;">
          <div class="export-copy">
            <label class="export-label">Sync Folder</label>
            <p class="export-help">Exported videos will be copied to this folder when you press "Sync to Folder" in the Export Library. Duplicates with the same filename and size are skipped automatically.</p>
          </div>
          <div class="sync-row">
            <input
              type="text"
              class="input-field sync-input"
              :value="settings['sts-sync-folder'] ?? ''"
              placeholder="D:/@Sync/PHONE-S24-PC"
              @change="onToggle('sts-sync-folder', $event.target.value.trim())"
            />
            <button class="browse-btn" :disabled="browsing" @click="browseSyncFolder">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-1px">
                <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
              </svg>
              {{ browsing ? '...' : 'Browse' }}
            </button>
          </div>
        </div>
        <SettingsToggle
          :model-value="settings['sts-auto-sync'] ?? true"
          label="Auto-sync after export"
          description="Automatically copy the video to the sync folder when a pipeline export finishes"
          @update:model-value="onToggle('sts-auto-sync', $event)"
        />
      </div>
    </section>

    <!-- Server -->
    <section class="card p-5 mb-4">
      <label class="section-label">Server</label>
      <div class="server-actions">
        <button class="action-btn server-btn" :disabled="restarting" @click="restartServer">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-2px">
            <path d="M23 4v6h-6"/><path d="M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </svg>
          {{ restarting ? 'Restarting...' : 'Restart Server' }}
        </button>
        <button class="action-btn server-btn" @click="refreshFrontend">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-2px">
            <path d="M1 4v6h6"/><path d="M23 20v-6h-6"/><path d="M20.49 9A9 9 0 005.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 013.51 15"/>
          </svg>
          Refresh Frontend
        </button>
      </div>
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

/* ---- Export Defaults ---- */
.export-defaults {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.export-default-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 14px;
  background: var(--bg-darkest);
  border: 1px solid var(--border);
  border-radius: 10px;
}

.export-copy {
  min-width: 0;
}

.export-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
}

.export-help {
  margin: 2px 0 0;
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.35;
}

.export-select {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 6px 10px;
  font-size: 12px;
  cursor: pointer;
  outline: none;
}

.export-select:focus {
  border-color: var(--accent);
}

.sync-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.sync-input {
  flex: 1;
  min-width: 0;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 8px 10px;
  font-size: 12px;
  font-family: var(--font-mono);
  outline: none;
  width: 100%;
  box-sizing: border-box;
}

.sync-input:focus {
  border-color: var(--accent);
}

.browse-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  font-size: 12px;
  font-weight: 600;
  font-family: var(--font-mono);
  white-space: nowrap;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-surface);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
}

.browse-btn:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}

.browse-btn:disabled {
  opacity: 0.5;
  cursor: wait;
}

/* ---- Server ---- */
.server-actions {
  display: flex;
  gap: 10px;
}

.server-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px !important;
  font-size: 12px !important;
}

.server-btn:disabled {
  opacity: 0.5;
  cursor: wait;
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
