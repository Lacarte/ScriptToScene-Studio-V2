<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useScenes } from '../composables/useScenes.js'
import { useToast } from '@/shared/composables/useToast.js'
import { useStagingStore } from '@/shared/stores/stagingStore.js'
import { timeAgo } from '@/shared/utils/format.js'
import { useProjectSync } from '@/shared/composables/useProjectSync.js'
import StylePicker from '../components/StylePicker.vue'
import SceneCard from '../components/SceneCard.vue'
import SceneTimeline from '../components/SceneTimeline.vue'

defineOptions({ name: 'ScenesPage' })

const route = useRoute()
const router = useRouter()
const scenes = useScenes()
const toast = useToast()
const staging = useStagingStore()

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
useProjectSync(projectBadge)

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
  await scenes.loadHistory()
  const projectParam = route.query.project
  if (projectParam) {
    try {
      await scenes.loadProject(projectParam)
      toast.success(`Loaded project ${projectParam}`)
    } catch {
      toast.error(`Failed to load project ${projectParam}`)
    }
  }
})

onUnmounted(() => {
  scenes.stopAudio()
})

// ---- Source selection ----
async function useCurrent() {
  // If segData already loaded, use it
  if (scenes.segData.value?.segments) {
    toast.success('Segmentation loaded')
    return
  }
  // Otherwise load the latest from segmenter history
  try {
    await scenes.loadSegHistory()
    const history = scenes.segHistory.value
    if (history.length) {
      await scenes.loadSegProject(history[0].folder)
      toast.success(`Loaded latest segmentation: ${history[0].project_id || history[0].folder}`)
    } else {
      toast.error('No segmenter results. Run the segmenter first.')
    }
  } catch {
    toast.error('Failed to load segmenter result.')
  }
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

function openInAssets(projectId) {
  router.push({ path: '/assets', query: { project: projectId } })
}

function sendToAssets() {
  const r = scenes.result.value
  if (!r?.scenes) { toast.error('No scenes to send'); return }
  staging.stage(r)
  router.push({ path: '/assets', query: { project: r.project_id } })
}

function sendToEditor() {
  const r = scenes.result.value
  if (!r) { toast.error('No scenes to send'); return }
  staging.stage(r)
  router.push({ path: '/editor', query: { project: r.project_id } })
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
        Transform word-level timestamps into AI-powered visual scene scripts
      </p>
    </div>

    <!-- Segmentation Source -->
    <section class="card">
      <label class="section-label">Segmentation Source</label>

      <div class="source-buttons">
        <button class="action-btn action-btn-lg" @click="useCurrent">Use Current Result</button>
        <button class="action-btn action-btn-lg" @click="openSegPicker">Pick from History</button>
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
      <label class="section-label">Generation Settings</label>

      <StylePicker
        :templates="scenes.templates.value"
        :selected="scenes.selectedStyle.value"
        @select="scenes.selectStyle"
      />

      <!-- Webhook -->
      <div class="webhook-section">
        <div class="webhook-header">
          <span class="webhook-label">Send to Webhook</span>
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
            placeholder="Webhook URL..."
            @input="scenes.saveWebhookUrl($event.target.value)"
          />
          <button class="action-btn" style="padding:6px 10px;font-size:10px;white-space:nowrap" @click="scenes.resetWebhookUrl()">Reset</button>
        </div>
        <p v-else class="setting-hint" style="font-style:italic">Webhook disabled — will only preview the payload without sending</p>
      </div>
    </section>

    <!-- Generate Button -->
    <div class="generate-row">
      <button
        class="gen-btn generate-btn"
        :class="{ 'gen-btn--disabled': !scenes.segData.value?.segments }"
        :disabled="scenes.isGenerating.value || !scenes.segData.value?.segments"
        @click="handleGenerate"
      >
        <svg v-if="!scenes.isGenerating.value" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
        <span v-else class="spinner"></span>
        {{ btnLabel }}
      </button>
      <label class="fork-toggle" for="scenes-fork-style">
        <input id="scenes-fork-style" v-model="scenes.forkPerStyle.value" type="checkbox" class="fork-check">
        <span class="fork-text">New project per style</span>
      </label>
      <span v-if="!scenes.segData.value?.segments && !scenes.isGenerating.value" class="gen-hint">Load a segmentation source first</span>
    </div>

    <!-- Payload Preview Panel -->
    <div v-if="payloadPreviewOpen" class="payload-panel">
      <div class="payload-panel-inner">
        <!-- Header -->
        <div class="payload-panel-header">
          <span class="payload-panel-title">Webhook Payload Preview</span>
          <div class="payload-panel-actions">
            <button class="action-btn" @click="copyPayload">Copy</button>
            <button class="payload-panel-close" @click="payloadPreviewOpen = false">&times;</button>
          </div>
        </div>
        <!-- JSON Content -->
        <pre class="payload-panel-content">{{ payloadJson }}</pre>
        <!-- Webhook URL + Send -->
        <div class="payload-panel-send">
          <input
            type="text"
            class="webhook-url-input"
            v-model="previewWebhookUrl"
            placeholder="Webhook URL..."
          />
          <button
            class="payload-send-btn"
            :disabled="scenes.isGenerating.value"
            @click="sendFromPreview"
          >
            <span v-if="scenes.isGenerating.value" class="spinner"></span>
            <template v-else>
              <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="vertical-align:-2px;margin-right:4px"><path d="M22 2L11 13" /><path d="M22 2l-7 20-4-9-9-4 20-7z" /></svg>
              Send
            </template>
          </button>
        </div>
      </div>
    </div>

    <!-- Results -->
    <div v-if="scenes.result.value" class="results-section">
      <div class="results-header">
        <label class="section-label" style="margin-bottom:0">Generated Scenes</label>
        <div class="results-actions">
          <button class="action-btn preview-btn" @click="scriptPreviewOpen = !scriptPreviewOpen">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-2px;margin-right:2px"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            Preview Script
          </button>
          <button class="action-btn accent" @click="sendToAssets">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-1px"><path d="M5 12h14"/><path d="M12 5l7 7-7 7"/></svg>
            Send to Assets
          </button>
        </div>
      </div>

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
      <div class="timeline-wrap">
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
      </div>

      <!-- Script Preview Panel -->
      <div v-if="scriptPreviewOpen" class="script-preview-panel">
        <div class="script-preview-header">
          <span class="script-preview-title">Generated Scene Script</span>
          <button class="script-preview-close" @click="scriptPreviewOpen = false">&times;</button>
        </div>
        <pre class="script-preview-content">{{ scriptPreviewText }}</pre>
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
    </div>

    <!-- History -->
    <div class="history-section">
      <div class="history-header">
        <h3 class="history-title">History</h3>
        <span class="history-count">{{ scenes.history.value.length }} project{{ scenes.history.value.length !== 1 ? 's' : '' }}</span>
      </div>

      <p v-if="!scenes.history.value.length" class="history-empty">
        No scene projects yet
      </p>

      <div v-else class="history-list">
        <button
          v-for="item in scenes.history.value"
          :key="item.project_id"
          class="history-item"
          :class="{ active: item.project_id === scenes.result.value?.project_id }"
          @click="loadFromHistory(item.project_id)"
        >
          <div class="history-item-body">
            <div class="history-item-title-row">
              <span class="history-item-title">{{ item.project_id }}</span>
              <span
                v-if="item.project_id === scenes.result.value?.project_id"
                class="history-active-badge font-mono"
              >ACTIVE</span>
              <span v-if="item.parent_id" class="history-item-parent">from {{ item.parent_id }}</span>
            </div>

            <div class="history-item-meta font-mono">
              <span style="color: var(--accent)">{{ item.scene_count }} scenes</span>
              <span class="history-divider">/</span>
              <span style="color: var(--text-secondary)">{{ timeAgo(item.timestamp) }}</span>
              <template v-if="scenes.styleLabel(item.style)">
                <span class="history-divider">/</span>
                <span class="history-style-badge">
                  <span class="style-dot-sm" :style="{ background: scenes.styleColor(item.style) }"></span>
                  <span :style="{ color: scenes.styleColor(item.style), fontWeight: 600 }">{{ scenes.styleLabel(item.style) }}</span>
                </span>
              </template>
            </div>
          </div>

          <span class="history-next-btn" @click.stop="openInAssets(item.project_id)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
              <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" />
              <rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" />
            </svg>
            Assets
          </span>
        </button>
      </div>
    </div>

    <!-- Segmenter Picker Modal -->
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
  margin-bottom: 16px;
}

.page-header-row {
  display: flex;
  align-items: center;
  gap: 10px;
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

/* ---- Card ---- */
.card {
  padding: 24px;
}

.card-heading {
  display: block;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--text-muted);
  margin: 0 0 12px;
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
.generate-row {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.generate-btn {
  padding: 0 28px;
  height: 44px;
  font-size: 13px;
  font-weight: 700;
  font-family: var(--font-mono);
  letter-spacing: 0.02em;
  color: #1f1307;
  background:
    radial-gradient(circle at top left, rgba(255, 226, 150, 0.22), transparent 42%),
    linear-gradient(135deg, #ff7a18 0%, var(--accent-active) 52%, #ffd166 100%);
  border: 1px solid rgba(255, 163, 77, 0.45);
  box-shadow:
    0 10px 26px rgba(255, 122, 24, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.28);
  border-radius: 10px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  transition: transform 0.15s, box-shadow 0.15s;
}

.generate-btn:hover:not(:disabled):not(.gen-btn--disabled) {
  transform: translateY(-1px);
  box-shadow:
    0 14px 34px rgba(255, 138, 61, 0.38),
    inset 0 1px 0 rgba(255, 255, 255, 0.34);
}

.generate-btn:active:not(:disabled):not(.gen-btn--disabled) {
  transform: translateY(0);
}

.gen-btn--disabled {
  background: var(--bg-darkest) !important;
  border-color: var(--border) !important;
  color: var(--text-muted) !important;
  box-shadow: none !important;
  cursor: not-allowed;
  opacity: 0.5;
}

.gen-hint {
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  opacity: 0.7;
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

/* ---- Payload Preview (source section) ---- */
.payload-pre {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-secondary);
  white-space: pre-wrap;
  max-height: 250px;
  overflow-y: auto;
  padding: 12px;
  margin-top: 0;
}

/* ---- Payload Panel (webhook preview) ---- */
.payload-panel {
  margin-top: 16px;
}

.payload-panel-inner {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-darkest);
  overflow: hidden;
}

.payload-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
}

.payload-panel-title {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--accent);
}

.payload-panel-actions {
  display: flex;
  gap: 6px;
}

.payload-panel-close {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 14px;
  padding: 0 4px;
}

.payload-panel-close:hover {
  color: var(--text);
}

.payload-panel-content {
  padding: 14px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0;
  max-height: 400px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.payload-panel-send {
  padding: 12px 14px;
  border-top: 1px solid var(--border);
  display: flex;
  gap: 8px;
  align-items: center;
}

.payload-send-btn {
  padding: 8px 20px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  border: none;
  cursor: pointer;
  color: white;
  background: linear-gradient(135deg, var(--accent), #3BA89F);
  box-shadow: 0 2px 12px rgba(78, 205, 196, 0.25);
  transition: all 0.2s;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
}

.payload-send-btn:hover {
  box-shadow: 0 4px 16px rgba(78, 205, 196, 0.35);
}

.payload-send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ---- Settings ---- */
.section-label {
  display: block;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--text-muted);
  margin-bottom: 10px;
}

.setting-hint {
  font-size: 11px;
  color: var(--text-muted);
}

/* ---- Fork per style ---- */
.fork-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg-surface);
  transition: border-color 0.15s;
  flex-shrink: 0;
}

.fork-toggle:hover {
  border-color: var(--accent);
}

.fork-check {
  accent-color: var(--accent);
  cursor: pointer;
  width: 14px;
  height: 14px;
}

.fork-text {
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
}

/* ---- Webhook ---- */
.webhook-section {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}

.webhook-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.webhook-label {
  font-size: 12px;
  color: var(--text-secondary);
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
  gap: 8px;
  align-items: center;
}

.webhook-url-input {
  flex: 1;
  padding: 8px 12px;
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text);
  background: var(--bg-darkest);
  border: 1.5px solid var(--border);
  border-radius: 8px;
  outline: none;
  transition: border-color 0.15s;
}

.webhook-url-input:focus {
  border-color: var(--accent);
}

/* ---- Results ---- */
.results-section {
  margin-top: 8px;
}

.results-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}

.results-actions {
  display: flex;
  gap: 6px;
}

.preview-btn {
  border-color: #A78BFA;
  color: #A78BFA;
}

.preview-btn:hover {
  border-color: #c4b5fd;
  color: #c4b5fd;
}

.result-stats {
  font-size: 11px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-family: var(--font-mono);
  margin-bottom: 10px;
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
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}

.timeline-wrap {
  margin-bottom: 16px;
}

/* ---- Script Preview Panel ---- */
.script-preview-panel {
  margin-bottom: 16px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-darkest);
  overflow: hidden;
}

.script-preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
}

.script-preview-title {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}

.script-preview-close {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 14px;
  padding: 0 4px;
}

.script-preview-close:hover {
  color: var(--text);
}

.script-preview-content {
  padding: 14px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.7;
  margin: 0;
  max-height: 500px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.scene-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ---- History ---- */
.history-section {
  margin-top: 16px;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.history-title {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
}

.history-count {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}

.history-empty {
  text-align: center;
  padding: 32px 0;
  font-size: 13px;
  color: var(--text-muted);
}

.history-list {
  max-height: 400px;
  overflow-y: auto;
}

.history-item {
  width: 100%;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 6px;
  color: var(--text);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.2s, box-shadow 0.2s;
  display: flex;
  align-items: center;
}

.history-item:hover {
  border-color: var(--border-hover);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
}

.history-item.active {
  border-color: var(--accent-active);
  box-shadow: inset 3px 0 0 var(--accent-active), 0 0 12px rgba(255, 159, 67, 0.15);
}

.history-item-body {
  flex: 1;
  min-width: 0;
  padding: 4px 12px 4px 14px;
}

.history-item-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 3px;
}

.history-item-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--text);
}

.history-item.active .history-item-title {
  color: var(--text);
  font-weight: 600;
}

.history-active-badge {
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(78, 205, 196, 0.15);
  color: var(--accent);
  font-size: 8px;
  letter-spacing: 0.05em;
}

.history-item-parent {
  color: var(--text-muted);
  font-size: 10px;
}

.history-item-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin: 0;
  font-size: 10px;
  color: var(--text-muted);
}

.history-divider {
  opacity: 0.3;
}

.history-style-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.history-next-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-left: auto;
  margin-right: 12px;
  flex-shrink: 0;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  opacity: 0.5;
  transition: opacity 0.15s, color 0.15s;
}

.history-next-btn:hover {
  opacity: 1;
  color: var(--accent);
}

.history-item.active .history-next-btn {
  color: var(--accent);
  opacity: 0.8;
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
  padding: 4px 12px 4px 14px;
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
