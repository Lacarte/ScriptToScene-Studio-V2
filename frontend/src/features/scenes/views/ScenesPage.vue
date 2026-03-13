<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useScenes } from '../composables/useScenes.js'
import { useToast } from '@/shared/composables/useToast.js'
import StylePicker from '../components/StylePicker.vue'
import SceneCard from '../components/SceneCard.vue'
import SceneTimeline from '../components/SceneTimeline.vue'

defineOptions({ name: 'ScenesPage' })

const scenes = useScenes()
const toast = useToast()

// UI state
const sourceExpanded = ref(false)
const payloadPreviewOpen = ref(false)
const scriptPreviewOpen = ref(false)
const showSegPicker = ref(false)
const previewWebhookUrl = ref('')
const historyExpanded = ref(true)

// ---- Computed ----
const projectBadge = computed(() => {
  return scenes.result.value?.project_id || scenes.segData.value?.metadata?.project_id || ''
})

const sourceInfo = computed(() => {
  const d = scenes.segData.value
  if (!d?.segments) return null
  const stats = d.stats || {}
  const meta = d.metadata || {}
  const segCount = stats.segment_count || d.segments.filter(s => !s.is_filler).length
  const dur = meta.total_duration || 0
  const src = meta.source_folder || d.output_folder || 'uploaded'
  const pid = meta.project_id ? `${meta.project_id} \u00b7 ` : ''
  return `${pid}${segCount} segments \u00b7 ${dur.toFixed(1)}s from ${src}`
})

const payloadJson = computed(() => {
  if (!scenes.payload.value) return ''
  return JSON.stringify(scenes.payload.value, null, 2)
})

const resultScenes = computed(() => scenes.result.value?.scenes || [])

const resultStats = computed(() => {
  const r = scenes.result.value
  if (!r) return null
  const sc = r.scenes || []
  const totalDur = sc.reduce((sum, s) => sum + (s.duration || 0), 0)
  return {
    projectId: r.project_id || '',
    sceneCount: sc.length,
    totalDuration: totalDur,
    style: r.style || '',
    timestamp: r.timestamp || '',
  }
})

const segWordsByIndex = computed(() => {
  const map = {}
  const segs = scenes.segData.value?.segments
  if (!segs) return map
  for (const seg of segs) {
    if (!seg.is_filler) map[seg.index] = seg.words || ''
  }
  return map
})

const btnLabel = computed(() => {
  if (scenes.isGenerating.value) return 'Generating...'
  return 'Generate Scene Script'
})

// ---- Lifecycle ----
onMounted(async () => {
  scenes.loadHistory()
})

onUnmounted(() => {
  scenes.stopAudio()
})

// ---- Source selection ----
function useCurrent() {
  // For cross-feature integration, we'd read from a shared store.
  // For now, rely on segData already being set externally or via history.
  if (!scenes.segData.value?.segments) {
    toast.error('No segmenter result available. Run the segmenter first.')
    return
  }
  toast.success('Segmentation loaded')
}

async function openSegPicker() {
  await scenes.loadSegHistory()
  if (!scenes.segHistory.value.length) {
    toast.error('No segmenter history. Run the segmenter first.')
    return
  }
  showSegPicker.value = true
}

async function pickSegItem(folder) {
  showSegPicker.value = false
  try {
    await scenes.loadSegProject(folder)
    toast.success('Segmentation loaded from history')
  } catch (e) {
    toast.error(e.message || 'Failed to load segmentation')
  }
}

function handleFileUpload(e) {
  const file = e.target?.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (ev) => {
    try {
      const data = JSON.parse(ev.target.result)
      if (!data.segments?.length) throw new Error('No segments array found')
      scenes.setSegData(data)
      toast.success('Segmentation loaded from file')
    } catch (err) {
      toast.error('Invalid segmentation JSON: ' + err.message)
    }
  }
  reader.readAsText(file)
  e.target.value = ''
}

// ---- Generation ----
async function handleGenerate() {
  if (!scenes.segData.value?.segments) {
    toast.error('Select a segmentation source first')
    return
  }

  // Build payload for preview
  scenes.buildPayload()

  // Always show preview first
  const meta = scenes.segData.value.metadata || {}
  const fullPayload = {
    ...scenes.payload.value,
    source_folder: meta.source_folder || '',
    aspect_ratio: '9:16',
  }
  previewWebhookUrl.value = scenes.webhookUrl.value || ''
  payloadPreviewOpen.value = true
}

async function sendFromPreview() {
  if (!previewWebhookUrl.value.trim()) {
    toast.error('Enter a webhook URL before sending')
    return
  }
  scenes.saveWebhookUrl(previewWebhookUrl.value.trim())

  try {
    const data = await scenes.sendToWebhook('9:16')
    toast.success('Scenes generated successfully')
    payloadPreviewOpen.value = false
  } catch (e) {
    toast.error(e.message || 'Failed to generate scenes')
  }
}

function copyPayload() {
  const text = payloadJson.value
  navigator.clipboard.writeText(text)
    .then(() => toast.success('Payload copied'))
    .catch(() => toast.error('Copy failed'))
}

// ---- Results actions ----
function copyScenes() {
  const json = JSON.stringify(resultScenes.value, null, 2)
  navigator.clipboard.writeText(json)
    .then(() => toast.success('Scenes JSON copied'))
    .catch(() => toast.error('Copy failed'))
}

function downloadScenes() {
  const r = scenes.result.value
  if (!r) return
  const json = JSON.stringify(r, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = (r.project_id || 'scenes') + '.json'
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function sendToAssets() {
  const r = scenes.result.value
  if (!r?.scenes) { toast.error('No scenes to send'); return }
  // Store for cross-feature navigation
  try { sessionStorage.setItem('sts-staged-timeline', JSON.stringify(r)) } catch {}
  localStorage.setItem('sts-editor-boot-project', JSON.stringify(r))
  localStorage.setItem('sts-editor-scenes', JSON.stringify(r))
  toast.info('Scenes staged for Assets')
}

function sendToEditor() {
  const r = scenes.result.value
  if (!r) { toast.error('No scenes to send'); return }
  try { sessionStorage.setItem('sts-staged-timeline', JSON.stringify(r)) } catch {}
  localStorage.setItem('sts-editor-boot-project', JSON.stringify(r))
  localStorage.setItem('sts-editor-scenes', JSON.stringify(r))
  if (r.source_folder) {
    localStorage.setItem('sts-editor-source-folder', r.source_folder)
  } else {
    localStorage.removeItem('sts-editor-source-folder')
  }
  localStorage.removeItem('sts-editor-captions')
  toast.info('Scenes sent to editor')
}

// ---- History ----
async function loadFromHistory(projectId) {
  try {
    await scenes.loadProject(projectId)
    toast.success('Scenes loaded')
  } catch (e) {
    toast.error(e.message || 'Failed to load project')
  }
}

// ---- Script preview ----
const scriptPreviewText = computed(() => {
  const sc = resultScenes.value
  if (!sc.length) return ''
  return sc.map((s, i) => {
    let header = `[#${i + 1}] ${s.title || ''}  |  ${s.type_of_scene || 'video'}  |  ${(s.duration || 0).toFixed(1)}s`
    if (s.narrative_role) header += `  |  ${s.narrative_role}`
    let body = ''
    if (s.text_content) body += `  Text: "${s.text_content}"\n`
    if (s.image_prompt) body += `  Visual: ${s.image_prompt}\n`
    return header + '\n' + body
  }).join('\n')
})

function timeAgo(ts) {
  if (!ts) return ''
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

function truncate(str, len = 45) {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '...' : str
}
</script>

<template>
  <div class="scenes-page">
    <!-- Header -->
    <div class="page-header">
      <div class="page-header-row">
        <h2 class="page-title">Scene Generator</h2>
        <span v-if="projectBadge" class="project-badge">{{ projectBadge }}</span>
      </div>
      <p class="page-subtitle">
        Build AI scene scripts from segmented audio. Select a source, pick a style, and generate.
      </p>
    </div>

    <!-- Segmentation Source -->
    <section class="card">
      <h3 class="card-heading">Segmentation Source</h3>

      <div class="source-buttons">
        <button class="action-btn action-btn-lg" @click="useCurrent">Use Current Result</button>
        <button class="action-btn action-btn-lg" @click="openSegPicker">Pick from History</button>
        <label class="action-btn action-btn-lg upload-label">
          Upload JSON
          <input type="file" accept=".json" hidden @change="handleFileUpload" />
        </label>
      </div>

      <p v-if="sourceInfo" class="source-info accent">{{ sourceInfo }}</p>
      <p v-else class="source-info muted">No segmentation selected</p>

      <!-- Payload preview collapse -->
      <div v-if="scenes.payload.value" class="collapse-section">
        <button class="collapse-toggle" @click="sourceExpanded = !sourceExpanded">
          <span>Payload Preview</span>
          <svg
            class="collapse-chevron"
            :class="{ open: sourceExpanded }"
            width="12" height="12" viewBox="0 0 24 24"
            fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>
        <pre v-show="sourceExpanded" class="payload-pre">{{ payloadJson }}</pre>
      </div>
    </section>

    <!-- Generation Settings -->
    <section class="card">
      <h3 class="card-heading">Generation Settings</h3>

      <StylePicker
        :templates="scenes.templates.value"
        :selected="scenes.selectedStyle.value"
        @select="scenes.selectStyle"
      />

      <div class="setting-row">
        <label class="checkbox-label">
          <input type="checkbox" v-model="scenes.forkPerStyle.value" />
          <span>Fork per style</span>
        </label>
        <span class="setting-hint">Create a new project ID instead of reusing the source</span>
      </div>

      <div class="setting-row">
        <div class="webhook-toggle-row">
          <span class="setting-label">Webhook</span>
          <button
            class="toggle-track"
            :class="{ on: scenes.webhookEnabled.value }"
            @click="scenes.toggleWebhook()"
          >
            <span class="toggle-dot"></span>
          </button>
        </div>

        <div v-if="scenes.webhookEnabled.value" class="webhook-url-row">
          <input
            type="text"
            class="webhook-url-input"
            :value="scenes.webhookUrl.value"
            placeholder="n8n webhook URL"
            @input="scenes.saveWebhookUrl($event.target.value)"
          />
          <button class="btn-ghost-sm" @click="scenes.resetWebhookUrl()" title="Reset to default">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="1 4 1 10 7 10" />
              <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
            </svg>
          </button>
        </div>
        <p v-else class="setting-hint">Webhook disabled - will preview payload only</p>
      </div>
    </section>

    <!-- Generate Button -->
    <button
      class="gen-btn"
      :disabled="scenes.isGenerating.value || !scenes.segData.value?.segments"
      @click="handleGenerate"
    >
      <span v-if="scenes.isGenerating.value" class="spinner"></span>
      {{ btnLabel }}
    </button>

    <!-- Payload Preview Panel -->
    <section v-if="payloadPreviewOpen" class="card payload-card">
      <div class="payload-header">
        <h3 class="card-heading">Payload Preview</h3>
        <div class="payload-actions">
          <button class="btn-ghost-sm" @click="copyPayload">Copy</button>
          <button class="btn-ghost-sm" @click="payloadPreviewOpen = false">Close</button>
        </div>
      </div>
      <pre class="payload-pre">{{ payloadJson }}</pre>

      <div class="payload-send-row">
        <input
          type="text"
          class="webhook-url-input"
          v-model="previewWebhookUrl"
          placeholder="Webhook URL"
        />
        <button
          class="btn-accent"
          :disabled="scenes.isGenerating.value"
          @click="sendFromPreview"
        >
          <span v-if="scenes.isGenerating.value" class="spinner"></span>
          {{ scenes.isGenerating.value ? 'Sending...' : 'Send to Webhook' }}
        </button>
      </div>
    </section>

    <!-- Results -->
    <section v-if="scenes.result.value" class="card results-card">
      <h3 class="card-heading">Results</h3>

      <!-- Stats -->
      <div v-if="resultStats" class="result-stats">
        <span class="stat-project">{{ resultStats.projectId }}</span>
        <span class="stat-sep">&middot;</span>
        <span>{{ resultStats.sceneCount }} scenes</span>
        <span class="stat-sep">&middot;</span>
        <span>{{ resultStats.totalDuration.toFixed(1) }}s total</span>
        <template v-if="resultStats.timestamp">
          <span class="stat-sep">&middot;</span>
          <span class="stat-muted">{{ timeAgo(resultStats.timestamp) }}</span>
        </template>
        <template v-if="resultStats.style">
          <span class="stat-sep">&middot;</span>
          <span class="stat-style">
            <span
              class="style-dot-sm"
              :style="{ background: scenes.styleColor(resultStats.style) }"
            ></span>
            <span :style="{ color: scenes.styleColor(resultStats.style), fontWeight: 600 }">
              {{ scenes.styleLabel(resultStats.style) }}
            </span>
          </span>
        </template>
      </div>

      <!-- Timeline -->
      <SceneTimeline
        v-if="resultScenes.length"
        :scenes="resultScenes"
        :timings="scenes.segTimings.value"
        :active-index="scenes.activeSceneIdx.value"
        :total-duration="scenes.totalDuration.value"
        :current-time="scenes.currentTime.value"
        :is-playing="scenes.isPlaying.value"
        :audio-loaded="!!scenes.audioUrl.value"
        @play="scenes.playBlock"
        @seek="scenes.seekTo"
        @toggle-play="scenes.togglePlay"
      />

      <!-- Script Preview -->
      <div class="collapse-section">
        <button class="collapse-toggle" @click="scriptPreviewOpen = !scriptPreviewOpen">
          <span>{{ scriptPreviewOpen ? 'Hide Script' : 'Preview Script' }}</span>
          <svg
            class="collapse-chevron"
            :class="{ open: scriptPreviewOpen }"
            width="12" height="12" viewBox="0 0 24 24"
            fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>
        <pre v-show="scriptPreviewOpen" class="payload-pre script-pre">{{ scriptPreviewText }}</pre>
      </div>

      <!-- Scene Cards -->
      <div class="scene-list">
        <SceneCard
          v-for="(scene, idx) in resultScenes"
          :key="idx"
          :scene="scene"
          :index="idx"
          :is-active="scenes.activeSceneIdx.value === idx"
          :segment-words="segWordsByIndex[scene.index] || ''"
          @play="scenes.playBlock"
        />
      </div>

      <!-- Action Buttons -->
      <div class="result-actions">
        <button class="action-btn" @click="copyScenes">Copy JSON</button>
        <button class="action-btn" @click="downloadScenes">Download</button>
        <button class="action-btn accent" @click="sendToAssets">Send to Assets</button>
        <button class="action-btn accent" @click="sendToEditor">Send to Editor</button>
      </div>
    </section>

    <!-- History -->
    <section class="card">
      <div class="history-header">
        <h3 class="card-heading">History</h3>
        <span class="history-count">{{ scenes.history.value.length }} project{{ scenes.history.value.length !== 1 ? 's' : '' }}</span>
      </div>

      <div v-if="!scenes.history.value.length" class="history-empty">
        No scene projects yet
      </div>

      <div v-else class="history-list">
        <div
          v-for="item in scenes.history.value"
          :key="item.project_id"
          class="history-item"
          :class="{ active: item.project_id === scenes.result.value?.project_id }"
          @click="loadFromHistory(item.project_id)"
        >
          <div class="history-item-inner">
            <div class="history-item-info">
              <div class="history-item-title-row">
                <span class="history-item-id">{{ item.project_id }}</span>
                <span v-if="item.parent_id" class="history-item-parent">from {{ item.parent_id }}</span>
              </div>
              <div class="history-item-meta">
                <span class="history-scene-count">{{ item.scene_count }} scenes</span>
                <span class="history-sep">/</span>
                <span>{{ timeAgo(item.timestamp) }}</span>
                <template v-if="scenes.styleLabel(item.style)">
                  <span class="history-sep">/</span>
                  <span class="history-style-badge">
                    <span class="style-dot-sm" :style="{ background: scenes.styleColor(item.style) }"></span>
                    <span :style="{ color: scenes.styleColor(item.style), fontWeight: 600 }">{{ scenes.styleLabel(item.style) }}</span>
                  </span>
                </template>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Segmenter Picker Modal -->
    <Teleport to="body">
      <div v-if="showSegPicker" class="modal-overlay" @click.self="showSegPicker = false">
        <div class="modal-panel">
          <div class="modal-header">
            <h3 class="modal-title">Pick Segmentation</h3>
            <button class="btn-ghost-sm" @click="showSegPicker = false">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
          <div class="modal-body">
            <div
              v-for="item in scenes.segHistory.value"
              :key="item.folder"
              class="picker-item"
              @click="pickSegItem(item.folder)"
            >
              <div class="picker-item-info">
                <p class="picker-item-source">{{ truncate(item.source_folder || '') }}</p>
                <p class="picker-item-meta">
                  {{ item.project_id ? item.project_id + ' \u00b7 ' : '' }}{{ item.segment_count }} segments &middot;
                  {{ item.total_duration.toFixed(1) }}s &middot; avg {{ item.avg_duration.toFixed(2) }}s
                </p>
              </div>
              <span class="picker-item-time">{{ timeAgo(item.segmented_at) }}</span>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.scenes-page {
  max-width: 780px;
  margin: 0 auto;
  padding: 32px 24px;
}

/* ---- Header ---- */
.page-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 24px;
}

.page-header-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.page-title {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 700;
  margin: 0;
}

.project-badge {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  background: rgba(78, 205, 196, 0.1);
  padding: 3px 10px;
  border-radius: 10px;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
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
  margin-bottom: 12px;
}

/* ---- Source ---- */
.source-buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.source-info {
  font-size: 13px;
  margin: 0 0 8px;
  font-family: var(--font-mono);
}

.source-info.accent {
  color: var(--accent);
}

.source-info.muted {
  color: var(--text-muted);
}

.upload-label {
  cursor: pointer;
}

/* ---- Buttons ---- */
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
.action-btn-lg {
  padding: 6px 14px;
  font-size: 11px;
}
.action-btn.accent {
  border-color: var(--accent);
  color: var(--accent);
}

.btn-ghost-sm {
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.15s;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.btn-ghost-sm:hover {
  border-color: var(--text-muted);
}

/* ---- Generate Button ---- */
.gen-btn {
  width: 100%;
  padding: 14px;
  font-size: 15px;
  font-weight: 700;
  color: #fff;
  background: var(--accent);
  border: none;
  border-radius: 12px;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.1s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.gen-btn:hover:not(:disabled) {
  opacity: 0.9;
  transform: translateY(-1px);
}

.gen-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ---- Collapse ---- */
.collapse-section {
  margin-top: 12px;
}

.collapse-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.collapse-toggle:hover {
  color: var(--text);
}

.collapse-chevron {
  transition: transform 0.2s;
  color: var(--text-muted);
}

.collapse-chevron.open {
  transform: rotate(180deg);
}

/* ---- Payload ---- */
.payload-pre {
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-secondary);
  background: var(--bg-darkest);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
  margin-top: 8px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
}

.payload-card {
  border-color: var(--accent);
}

.payload-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.payload-actions {
  display: flex;
  gap: 6px;
}

.payload-send-row {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  align-items: center;
}

/* ---- Settings ---- */
.setting-row {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.setting-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.setting-hint {
  font-size: 11px;
  color: var(--text-muted);
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
}

.checkbox-label input[type="checkbox"] {
  accent-color: var(--accent);
  width: 16px;
  height: 16px;
}

/* ---- Webhook Toggle ---- */
.webhook-toggle-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.toggle-track {
  width: 36px;
  height: 20px;
  border-radius: 10px;
  background: var(--border);
  border: none;
  cursor: pointer;
  position: relative;
  transition: background 0.2s;
  padding: 0;
}

.toggle-track.on {
  background: rgba(78, 205, 196, 0.3);
}

.toggle-dot {
  display: block;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--text-muted);
  position: absolute;
  top: 2px;
  left: 2px;
  transition: transform 0.2s, background 0.2s;
}

.toggle-track.on .toggle-dot {
  transform: translateX(16px);
  background: var(--accent);
}

.webhook-url-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.webhook-url-input {
  flex: 1;
  padding: 8px 12px;
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--text);
  background: var(--bg-darkest);
  border: 1px solid var(--border);
  border-radius: 8px;
  outline: none;
  transition: border-color 0.15s;
}

.webhook-url-input:focus {
  border-color: var(--accent);
}

/* ---- Results ---- */
.results-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.result-stats {
  font-size: 13px;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-family: var(--font-mono);
}

.stat-project {
  color: var(--accent);
  font-weight: 600;
}

.stat-sep {
  color: var(--text-muted);
  opacity: 0.5;
}

.stat-muted {
  color: var(--text-muted);
}

.stat-style {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.style-dot-sm {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  display: inline-block;
}

.script-pre {
  font-size: 12px;
}

.scene-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

/* ---- History ---- */
.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.history-count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
}

.history-empty {
  text-align: center;
  padding: 32px 0;
  font-size: 13px;
  color: var(--text-muted);
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.history-item {
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s;
  background: transparent;
  border: 1px solid transparent;
}

.history-item:hover {
  background: rgba(255, 255, 255, 0.02);
  border-color: var(--border);
}

.history-item.active {
  border-color: var(--accent);
  background: rgba(78, 205, 196, 0.05);
}

.history-item-inner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px 10px 14px;
}

.history-item-info {
  flex: 1;
  min-width: 0;
}

.history-item-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.history-item-id {
  font-size: 13px;
  color: var(--text);
}

.history-item-parent {
  color: var(--text-muted);
  font-size: 10px;
}

.history-item-meta {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  margin-top: 2px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.history-scene-count {
  color: var(--accent);
}

.history-sep {
  opacity: 0.3;
}

.history-style-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

/* ---- Modal ---- */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-panel {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  width: 520px;
  max-width: 90vw;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.modal-title {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  margin: 0;
}

.modal-body {
  overflow-y: auto;
  padding: 8px;
}

.picker-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px 10px 14px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}

.picker-item:hover {
  background: rgba(255, 255, 255, 0.03);
}

.picker-item-info {
  flex: 1;
  min-width: 0;
}

.picker-item-source {
  font-size: 13px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin: 0;
}

.picker-item-meta {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  margin: 2px 0 0;
}

.picker-item-time {
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--text-muted);
  flex-shrink: 0;
  background: var(--bg-darkest);
  padding: 2px 6px;
  border-radius: 4px;
}
</style>
