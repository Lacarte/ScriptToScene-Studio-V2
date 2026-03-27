<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/shared/api/client.js'
import { useToast } from '@/shared/composables/useToast.js'
import { useProjectSync } from '@/shared/composables/useProjectSync.js'
import { timeAgo } from '@/shared/utils/format.js'

defineOptions({ name: 'StoryboardPage' })

const route = useRoute()
const toast = useToast()

const projectId = ref(null)
useProjectSync(projectId)

const images = ref([])
const status = ref(null)
const loading = ref(false)
const historyVisible = ref(true)
const history = ref([])
const scenePickerOpen = ref(false)
const scenePickerData = ref([])

// Provider state
const storyboardProvider = ref(localStorage.getItem('sts-storyboard-provider') || 'gemini')
function setProvider(val) {
  storyboardProvider.value = val
  localStorage.setItem('sts-storyboard-provider', val)
}

// Prompt prefix (prepended to each prompt when using Gemini)
const promptPrefix = ref(localStorage.getItem('sts-prompt-prefix') ?? 'generate an image ')
function setPromptPrefix(val) {
  promptPrefix.value = val
  localStorage.setItem('sts-prompt-prefix', val)
}

// Webhook state
const webhookEnabled = ref(true)
const webhookUrl = ref('')
const defaultWebhookUrl = ref('')
let webhookLoaded = false

// Image model (for webhook provider)
const imageModel = ref(localStorage.getItem('sts-image-model') || '')
const imageModelsConfig = ref({})
const availableImageModels = computed(() => {
  const cfg = imageModelsConfig.value || {}
  const models = cfg['default']?.models || []
  return models
})
function setImageModel(val) {
  imageModel.value = val
  if (val) localStorage.setItem('sts-image-model', val)
  else localStorage.removeItem('sts-image-model')
}
async function loadImageModels() {
  try {
    imageModelsConfig.value = await api.get('/api/storyboard/image-models')
  } catch (e) { /* ignore */ }
}

// Image settings
const aspectRatio = ref(localStorage.getItem('sts-storyboard-aspect-ratio') || '9:16')
const aspectRatioOptions = [
  { value: '9:16', label: '9:16 (Vertical)',   size: '576×1024' },
  { value: '16:9', label: '16:9 (Landscape)',   size: '1024×576' },
  { value: '1:1',  label: '1:1 (Square)',       size: '1024×1024' },
  { value: '4:3',  label: '4:3 (Standard)',     size: '1024×768' },
  { value: '3:4',  label: '3:4 (Portrait)',     size: '768×1024' },
  { value: '3:2',  label: '3:2 (Landscape)',    size: '1024×683' },
  { value: '2:3',  label: '2:3 (Portrait)',     size: '683×1024' },
]

function setAspectRatio(val) {
  aspectRatio.value = val
  localStorage.setItem('sts-storyboard-aspect-ratio', val)
}

// Scene data for grabber
const scenes = ref([])
const sceneStatuses = ref({})
const grabbing = ref(false)
let pollTimer = null

// Lightbox with arrow navigation
const lightboxSrc = ref(null)
const lightboxIndex = ref(-1)

const lightboxScenes = computed(() =>
  scenes.value
    .map(s => ({ index: s.index, src: sceneImage(s.index) }))
    .filter(s => s.src)
)

function openLightbox(sceneIndex) {
  const src = sceneImage(sceneIndex)
  if (!src) return
  lightboxSrc.value = src
  lightboxIndex.value = sceneIndex
}

function closeLightbox() {
  lightboxSrc.value = null
  lightboxIndex.value = -1
}

function lightboxNav(dir) {
  const list = lightboxScenes.value
  if (list.length === 0) return
  const curPos = list.findIndex(s => s.index === lightboxIndex.value)
  const next = curPos + dir
  if (next < 0 || next >= list.length) return
  lightboxIndex.value = list[next].index
  lightboxSrc.value = list[next].src
}

function onLightboxKey(e) {
  if (!lightboxSrc.value) return
  if (e.key === 'ArrowLeft') lightboxNav(-1)
  else if (e.key === 'ArrowRight') lightboxNav(1)
  else if (e.key === 'Escape') closeLightbox()
}

onMounted(() => window.addEventListener('keydown', onLightboxKey))
onUnmounted(() => window.removeEventListener('keydown', onLightboxKey))

// ── Webhook ──

async function initWebhook() {
  if (webhookLoaded) return
  try {
    const data = await api.get('/api/storyboard/webhook-url')
    defaultWebhookUrl.value = data.url || ''
  } catch (e) {
    console.warn('[Storyboard] Failed to load webhook URL:', e.message)
    defaultWebhookUrl.value = ''
  }
  const saved = localStorage.getItem('sts-storyboard-webhook-url')
  webhookUrl.value = saved !== null ? saved : defaultWebhookUrl.value
  const savedToggle = localStorage.getItem('sts-storyboard-webhook-enabled')
  if (savedToggle === 'false') webhookEnabled.value = false
  webhookLoaded = true
}

function toggleWebhook() {
  webhookEnabled.value = !webhookEnabled.value
  localStorage.setItem('sts-storyboard-webhook-enabled', webhookEnabled.value)
}

function saveWebhookUrl(url) {
  webhookUrl.value = url
  localStorage.setItem('sts-storyboard-webhook-url', url)
}

function resetWebhookUrl() {
  webhookUrl.value = defaultWebhookUrl.value
  localStorage.removeItem('sts-storyboard-webhook-url')
}

// ── Data loading ──

async function loadImages() {
  if (!projectId.value) return
  loading.value = true
  try {
    const res = await api.get(`/api/storyboard/images/${projectId.value}`)
    images.value = res.images || []
  } catch {
    images.value = []
  }
  loading.value = false
}

async function loadStatus() {
  if (!projectId.value) return
  try {
    const res = await api.get(`/api/storyboard/status/${projectId.value}`)
    status.value = res
    sceneStatuses.value = res.scene_statuses || {}
  } catch {
    status.value = null
  }
}

async function loadScenes() {
  if (!projectId.value) return
  try {
    const data = await api.get(`/api/scenes/${projectId.value}`)
    const raw = data.scenes || []
    scenes.value = raw.map((s, i) => ({
      index: s.index ?? i,
      prompt: s.image_prompt || s.prompt || '',
      description: s.description || '',
    })).filter(s => s.prompt)
  } catch {
    scenes.value = []
  }

  // Fallback: if no scene data but we have storyboard images or status, build from those
  if (!scenes.value.length) {
    const fallbackScenes = []
    // From storyboard status (scene keys)
    if (status.value?.scene_statuses) {
      for (const key of Object.keys(status.value.scene_statuses).sort((a, b) => Number(a) - Number(b))) {
        fallbackScenes.push({ index: Number(key), prompt: '', description: '' })
      }
    }
    // From downloaded images
    if (!fallbackScenes.length && images.value.length) {
      for (const img of images.value) {
        const idx = parseInt(img.filename.replace(/\.\w+$/, ''), 10)
        if (!isNaN(idx)) fallbackScenes.push({ index: idx, prompt: '', description: '' })
      }
    }
    scenes.value = fallbackScenes
  }
}

async function loadProject() {
  await Promise.all([loadImages(), loadStatus()])
  await loadScenes()
}

async function loadHistory() {
  try {
    const jobs = await api.get('/api/pipeline/jobs')
    history.value = (jobs || [])
      .filter(j => j.project_id && j.scene_count > 0)
      .sort((a, b) => (b.created || 0) - (a.created || 0))
  } catch {}
}

async function loadCurrentResult() {
  try {
    const jobs = await api.get('/api/pipeline/jobs')
    const sorted = (jobs || [])
      .filter(j => j.project_id && j.status === 'done')
      .sort((a, b) => (b.created || 0) - (a.created || 0))
    if (sorted.length) {
      projectId.value = sorted[0].project_id
      await loadProject()
      toast.success(`Loaded storyboard for ${sorted[0].project_id}`)
    } else {
      toast.warning('No completed projects found.')
    }
  } catch {
    toast.error('Failed to load current result.')
  }
}

async function pickFromHistory() {
  try {
    const jobs = await api.get('/api/pipeline/jobs')
    scenePickerData.value = (jobs || [])
      .filter(j => j.project_id && j.scene_count > 0)
      .sort((a, b) => (b.created || 0) - (a.created || 0))
    scenePickerOpen.value = true
  } catch {
    toast.error('Failed to load project list.')
  }
}

async function pickProject(entry) {
  scenePickerOpen.value = false
  projectId.value = entry.project_id
  await loadProject()
  toast.success(`Loaded ${entry.project_id}`)
}

async function loadFromHistory(pid) {
  projectId.value = pid
  await loadProject()
}

function statusColor(s) {
  if (s === 'done') return '#4ecdc4'
  if (s === 'running') return '#f0c674'
  if (s === 'error') return '#ff6b6b'
  return '#64748b'
}

async function copyPrompt(text) {
  try {
    await navigator.clipboard.writeText(text)
    toast.success('Prompt copied')
  } catch {
    toast.error('Failed to copy')
  }
}

function downloadImage(scene) {
  const src = sceneImage(scene.index)
  if (!src) return
  const a = document.createElement('a')
  a.href = src
  a.download = `${projectId.value || 'storyboard'}_scene_${scene.index}.jpg`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

// ── Grabber ──

function sceneStatus(idx) {
  return sceneStatuses.value[String(idx)]?.status || 'pending'
}

function sceneImage(idx) {
  const st = sceneStatuses.value[String(idx)]
  if (st?.local_path) return st.local_path
  const img = images.value.find(i => i.scene === idx)
  return img?.path || null
}

function sceneVersions(idx) {
  const img = images.value.find(i => i.scene === idx)
  return img?.versions || []
}

function sceneVersionCount(idx) {
  const img = images.value.find(i => i.scene === idx)
  return img?.version_count || 0
}

// Prompt editing
const editingIndex = ref(null)
const editingPrompt = ref('')

function startEdit(scene) {
  editingIndex.value = scene.index
  editingPrompt.value = scene.prompt || ''
}

function cancelEdit() {
  editingIndex.value = null
  editingPrompt.value = ''
}

function saveEdit(scene) {
  scene.prompt = editingPrompt.value.trim()
  editingIndex.value = null
  editingPrompt.value = ''
  toast.success(`Scene ${scene.index} prompt updated`)
}

async function grabScene(scene) {
  const provider = storyboardProvider.value

  if (provider === 'webhook') {
    if (!webhookEnabled.value) { toast.warning('Enable the webhook first'); return }
    const url = webhookUrl.value?.trim()
    if (!url) { toast.warning('Enter a webhook URL'); return }
  }

  sceneStatuses.value[String(scene.index)] = { status: 'generating' }
  grabbing.value = true

  try {
    const body = {
      project_id: projectId.value,
      scene: scene.index,
      prompt: (provider === 'gemini' && promptPrefix.value ? promptPrefix.value : '') + scene.prompt,
      aspect_ratio: aspectRatio.value,
      provider,
    }
    if (provider === 'webhook') {
      body.webhook_url = webhookUrl.value?.trim()
      if (imageModel.value) body.image_model = imageModel.value
    }

    const res = await api.post('/api/storyboard/grab', { body })
    if (res?.error) {
      toast.error(res.error)
      sceneStatuses.value[String(scene.index)] = { status: 'error' }
      return
    }
    toast.success(`Scene ${scene.index} — generating via ${provider}...`)
    startPolling()
  } catch (e) {
    toast.error(`Scene ${scene.index} failed: ${e.message}`)
    sceneStatuses.value[String(scene.index)] = { status: 'error' }
  }
}

async function grabAll() {
  const provider = storyboardProvider.value

  if (provider === 'webhook') {
    if (!webhookEnabled.value) { toast.warning('Enable the webhook first'); return }
    const url = webhookUrl.value?.trim()
    if (!url) { toast.warning('Enter a webhook URL'); return }
  }
  if (!scenes.value.length) {
    toast.warning('No scenes loaded')
    return
  }

  const pfx = provider === 'gemini' && promptPrefix.value ? promptPrefix.value : ''
  const scenesPayload = scenes.value.map(s => ({ scene: s.index, prompt: pfx + s.prompt }))

  try {
    const body = {
      project_id: projectId.value,
      scenes: scenesPayload,
      aspect_ratio: aspectRatio.value,
      provider,
    }
    if (provider === 'webhook') {
      body.webhook_url = webhookUrl.value?.trim()
      if (imageModel.value) body.image_model = imageModel.value
    }

    const res = await api.post('/api/storyboard/generate', { body })
    if (res?.error) {
      toast.error(res.error)
      return
    }
    toast.success(`Generating ${scenesPayload.length} images via ${provider}...`)
    grabbing.value = true
    startPolling()
  } catch (e) {
    toast.error(`Generation failed: ${e.message}`)
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    await loadStatus()
    await loadImages()
    const st = status.value
    if (st && (st.status === 'done' || st.status === 'error')) {
      grabbing.value = false
      // Check if any scene is still generating
      const anyGenerating = Object.values(sceneStatuses.value).some(
        s => s.status === 'generating' || s.status === 'downloading'
      )
      if (!anyGenerating) stopPolling()
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

// ── Computed ──

const imageCount = computed(() => images.value.length)
const readyCount = computed(() => status.value?.ready || 0)
const totalCount = computed(() => status.value?.total || 0)

const statusLabel = computed(() => {
  if (!status.value) return ''
  const s = status.value
  if (s.status === 'done') return `${s.ready}/${s.total} images`
  if (s.status === 'running') return `Generating... ${s.ready}/${s.total}`
  return s.status
})

const progressPercent = computed(() => {
  if (!totalCount.value) return 0
  return Math.round((readyCount.value / totalCount.value) * 100)
})

// ── Lifecycle ──

watch(() => route.query.project, (pid) => {
  if (pid) {
    projectId.value = pid
    loadProject()
  }
})

onMounted(async () => {
  await initWebhook()
  await loadHistory()
  await loadImageModels()
  if (projectId.value) loadProject()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <div class="storyboard-page">
    <!-- Header -->
    <div class="page-header">
      <h2 class="page-title">Storyboard</h2>
      <span v-if="projectId" class="project-badge">{{ projectId }}</span>
    </div>
    <p class="page-subtitle">Reference images generated per scene for visual consistency</p>

    <!-- Source Info -->
    <section class="card source-card">
      <div class="source-row">
        <div class="source-info-left">
          <span class="source-label">
            <template v-if="imageCount && projectId">
              {{ projectId }} &middot; {{ imageCount }} images
              <template v-if="statusLabel">
                &middot; <span class="source-style">{{ statusLabel }}</span>
              </template>
            </template>
            <template v-else>No storyboard loaded</template>
          </span>
        </div>
        <div class="source-actions">
          <button class="action-btn" style="padding:6px 14px;font-size:11px" @click="pickFromHistory">
            Pick from History
          </button>
        </div>
      </div>

      <!-- Provider Selector -->
      <div class="webhook-section">
        <div class="webhook-header">
          <span class="webhook-label">Image Provider</span>
        </div>
        <select class="aspect-select" style="margin-top:6px;" :value="storyboardProvider" @change="setProvider($event.target.value)">
          <option value="gemini">Gemini Grabber</option>
          <option value="webhook">Webhook (n8n)</option>
        </select>
      </div>

      <!-- Webhook Config (only when webhook provider selected) -->
      <div v-if="storyboardProvider === 'webhook'" class="webhook-section">
        <div class="webhook-header">
          <span class="webhook-label">Send to Webhook</span>
          <button
            class="toggle-track"
            :class="{ on: webhookEnabled }"
            @click="toggleWebhook()"
          >
            <span class="toggle-dot"></span>
          </button>
        </div>

        <div v-if="webhookEnabled" class="webhook-url-row">
          <input
            type="text"
            class="webhook-url-input"
            :value="webhookUrl"
            placeholder="Webhook URL..."
            @input="saveWebhookUrl($event.target.value)"
          />
          <button class="action-btn" style="padding:6px 10px;font-size:10px;white-space:nowrap" @click="resetWebhookUrl()">Reset</button>
        </div>
        <p v-else class="setting-hint" style="font-style:italic">Webhook disabled — grabber won't send to n8n</p>

        <!-- Image Model (webhook only) -->
        <div v-if="availableImageModels.length > 1" style="margin-top:8px;">
          <span class="webhook-label" style="font-size:10px;">Image Model</span>
          <select class="aspect-select" style="margin-top:4px;" :value="imageModel" @change="setImageModel($event.target.value)">
            <option value="">Auto ({{ availableImageModels[0]?.name || 'default' }})</option>
            <option v-for="m in availableImageModels" :key="m.id" :value="m.id">
              {{ m.name }}{{ m.price ? ` ($${m.price})` : '' }}
            </option>
          </select>
        </div>
      </div>

      <!-- Gemini Info (only when gemini provider selected) -->
      <div v-if="storyboardProvider === 'gemini'" class="webhook-section">
        <p class="setting-hint" style="color:var(--text-secondary);font-size:11px;line-height:1.5">
          Prompts are sent via WebSocket to the <b style="color:var(--accent)">STS Gemini</b> Chrome extension.
          Make sure <b>gemini.google.com</b> is open and the extension panel shows <b style="color:#34d399">Connected</b>.
        </p>
        <div style="margin-top:8px;">
          <span class="webhook-label" style="font-size:10px;">Prompt Prefix</span>
          <input
            type="text"
            class="webhook-url-input"
            :value="promptPrefix"
            placeholder="Prefix prepended to each prompt..."
            @input="setPromptPrefix($event.target.value)"
            style="margin-top:4px;"
          />
        </div>
      </div>

      <!-- Aspect Ratio -->
      <div class="aspect-ratio-section">
        <span class="webhook-label">Aspect Ratio</span>
        <select class="aspect-select" :value="aspectRatio" @change="setAspectRatio($event.target.value)">
          <option v-for="opt in aspectRatioOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }} — {{ opt.size }}
          </option>
        </select>
      </div>
    </section>

    <!-- Scene Picker Modal -->
    <div v-if="scenePickerOpen" class="modal-backdrop" @click.self="scenePickerOpen = false">
      <div class="modal-panel">
        <div class="modal-header">
          <h3>Pick Scenes</h3>
          <button class="modal-close" @click="scenePickerOpen = false">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <div
            v-for="(entry, i) in scenePickerData"
            :key="i"
            class="picker-row"
            @click="pickProject(entry)"
          >
            <svg class="picker-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><path d="M4 11V7a2 2 0 012-2h12a2 2 0 012 2v4"/><path d="M4 11h16"/></svg>
            <div class="picker-info">
              <span class="picker-label">{{ entry.project_id }}</span>
              <div class="picker-meta font-mono">
                <span style="color: var(--accent)">{{ entry.scene_count || 0 }} scenes</span>
                <template v-if="entry.style">
                  <span class="picker-sep">/</span>
                  <span class="picker-style">{{ entry.style.replace(/_/g, ' ') }}</span>
                </template>
                <template v-if="entry.timestamp">
                  <span class="picker-sep">/</span>
                  <span>{{ timeAgo(entry.timestamp) }}</span>
                </template>
              </div>
            </div>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" stroke-width="1.5" style="flex-shrink:0;opacity:0.4"><path d="M9 18l6-6-6-6"/></svg>
          </div>
          <div v-if="!scenePickerData.length" class="picker-empty">No projects found.</div>
        </div>
      </div>
    </div>

    <!-- Storyboard Gallery + Grabber -->
    <section v-if="scenes.length && projectId" class="gallery-section">
      <div class="gallery-header">
        <div class="gallery-header-left">
          <svg width="16" height="16" fill="none" stroke="var(--accent)" stroke-width="1.5" viewBox="0 0 24 24">
            <rect x="3" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" />
            <rect x="14" y="14" width="7" height="7" rx="1" />
          </svg>
          <span class="gallery-title">Storyboard</span>
          <span class="gallery-count font-mono">{{ imageCount }}/{{ scenes.length }} images</span>
        </div>
        <button
          class="gen-btn btn-grab-all"
          :disabled="grabbing || !webhookEnabled"
          @click="grabAll"
        >
          <template v-if="grabbing">
            <span class="spinner-sm" style="margin-right:4px"></span>
            Generating...
          </template>
          <template v-else>
            <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="vertical-align:-1px;margin-right:4px">
              <rect x="3" y="3" width="18" height="18" rx="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <path d="M21 15l-5-5L5 21" />
            </svg>
            Generate All
          </template>
        </button>
      </div>

      <!-- Progress bar -->
      <div v-if="grabbing && totalCount" class="progress-bar-wrap">
        <div class="progress-bar-track">
          <div class="progress-bar-fill" :style="{ width: progressPercent + '%' }" />
        </div>
        <span class="progress-text font-mono">{{ readyCount }}/{{ totalCount }} ready</span>
      </div>

      <!-- Image cards with prompts -->
      <div class="image-grid">
        <div v-for="scene in scenes" :key="scene.index" class="image-card" :class="{ 'image-card--empty': !sceneImage(scene.index) }">
          <div class="image-preview" :class="{ clickable: !!sceneImage(scene.index) }" @click="openLightbox(scene.index)">
            <img v-if="sceneImage(scene.index)" :src="sceneImage(scene.index)" :alt="`Scene ${scene.index}`" loading="lazy" />
            <div v-else class="image-placeholder" :class="{ 'is-loading': sceneStatus(scene.index) === 'generating' || sceneStatus(scene.index) === 'downloading' }">
              <template v-if="sceneStatus(scene.index) === 'generating' || sceneStatus(scene.index) === 'downloading'">
                <div class="loading-visual">
                  <div class="pulse-ring"></div>
                  <div class="pulse-ring delay-1"></div>
                  <div class="pulse-ring delay-2"></div>
                  <svg class="loading-icon" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z" />
                    <path d="M5 18l1 2.5L8.5 22l-2.5 0L5 18z" opacity="0.6" />
                    <path d="M19 16l.5 1.5L21 18l-1.5.5L19 20l-.5-1.5L17 18l1.5-.5L19 16z" opacity="0.6" />
                  </svg>
                </div>
                <span class="loading-label">{{ sceneStatus(scene.index) === 'downloading' ? 'Downloading...' : 'Generating...' }}</span>
              </template>
              <svg v-else width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" style="opacity:0.2">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <path d="M21 15l-5-5L5 21" />
              </svg>
            </div>
            <!-- Version count badge -->
            <span v-if="sceneVersionCount(scene.index) > 1" class="version-badge">
              {{ sceneVersionCount(scene.index) }}
            </span>
          </div>

          <!-- Version strip (previous versions) -->
          <div v-if="sceneVersions(scene.index).length > 1" class="version-strip">
            <div
              v-for="(ver, vi) in sceneVersions(scene.index)"
              :key="vi"
              class="version-thumb"
              :class="{ 'version-thumb--current': ver.is_current }"
              @click="lightboxSrc = ver.path"
            >
              <img :src="ver.path" loading="lazy" :alt="ver.is_current ? 'Current' : `v${ver.version}`" />
              <span class="version-label">{{ ver.is_current ? 'Current' : `v${ver.version}` }}</span>
            </div>
          </div>
          <div class="image-body">
            <div class="image-footer">
              <span class="image-scene">Scene {{ scene.index }}</span>
              <span class="image-status font-mono" :class="`status--${sceneStatus(scene.index)}`">{{ sceneStatus(scene.index) }}</span>
            </div>

            <!-- Editing mode -->
            <template v-if="editingIndex === scene.index">
              <textarea
                class="prompt-edit-area"
                v-model="editingPrompt"
                rows="4"
                @keydown.escape="cancelEdit"
              ></textarea>
              <div class="edit-actions">
                <button class="btn-edit-save" @click="saveEdit(scene)">Save</button>
                <button class="btn-edit-cancel" @click="cancelEdit">Cancel</button>
              </div>
            </template>

            <!-- Display mode -->
            <template v-else>
              <p v-if="scene.prompt" class="image-prompt">{{ scene.prompt }}</p>
              <div class="image-actions">
                <button v-if="scene.prompt" class="btn-copy" title="Copy prompt" @click="copyPrompt(scene.prompt)">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
                  <span>Copy</span>
                </button>
                <button class="btn-copy" title="Edit prompt" @click="startEdit(scene)">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                  <span>Edit</span>
                </button>
                <button v-if="sceneImage(scene.index)" class="btn-copy btn-download" title="Download image" @click="downloadImage(scene)">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                </button>
                <button
                  class="btn-grab-one"
                  :disabled="!scene.prompt || sceneStatus(scene.index) === 'generating' || sceneStatus(scene.index) === 'downloading'"
                  @click="grabScene(scene)"
                >
                  <template v-if="sceneStatus(scene.index) === 'generating' || sceneStatus(scene.index) === 'downloading'">
                    <span class="spinner-sm"></span>
                  </template>
                  <template v-else-if="sceneStatus(scene.index) === 'ready'">Regrab</template>
                  <template v-else>Grab</template>
                </button>
              </div>
            </template>
          </div>
        </div>
      </div>
    </section>

    <!-- Empty State -->
    <section v-else class="empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" class="empty-icon">
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </svg>
      <p class="empty-title">No storyboard loaded</p>
      <p class="empty-desc">Run the pipeline with the Storyboard step enabled, or pick a project from history below.</p>
    </section>

    <!-- History -->
    <section class="card history-card">
      <div class="history-header">
        <div class="history-header-left">
          <svg width="16" height="16" fill="none" stroke="var(--text-muted)" stroke-width="1.5" viewBox="0 0 24 24">
            <path d="M12 8v4l3 3" />
            <circle cx="12" cy="12" r="10" />
          </svg>
          <span class="history-title">History</span>
        </div>
        <button class="action-btn history-refresh-btn" title="Refresh" @click="loadHistory">
          <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="vertical-align:-1px">
            <path d="M23 4v6h-6" />
            <path d="M1 20v-6h6" />
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
          </svg>
        </button>
      </div>

      <p v-if="!history.length" class="history-empty">No project history found.</p>

      <div v-else class="history-list">
        <div
          v-for="project in history"
          :key="project.project_id"
          class="hist-item"
          :class="{ active: project.project_id === projectId }"
          @click="loadFromHistory(project.project_id)"
        >
          <div class="hist-inner">
            <div class="hist-thumb" :class="{ 'hist-thumb--active': project.project_id === projectId }">
              <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
                <rect x="3" y="3" width="7" height="7" rx="1" />
                <rect x="14" y="3" width="7" height="7" rx="1" />
                <rect x="3" y="14" width="7" height="7" rx="1" />
                <rect x="14" y="14" width="7" height="7" rx="1" />
              </svg>
            </div>
            <div class="hist-content">
              <div class="hist-title-row">
                <span class="hist-name">{{ project.project_id }}</span>
                <span v-if="project.project_id === projectId" class="hist-active-badge font-mono">ACTIVE</span>
                <span class="hist-dot" :style="{ background: statusColor(project.status) }"></span>
                <span class="hist-status font-mono" :style="{ color: statusColor(project.status) }">{{ project.status || 'unknown' }}</span>
              </div>
              <div class="hist-meta font-mono">
                <span style="color: var(--accent)">{{ project.scene_count || 0 }} scenes</span>
                <template v-if="project.style">
                  <span class="hist-sep">/</span>
                  <span class="hist-style">{{ project.style.replace(/_/g, ' ') }}</span>
                </template>
                <template v-if="project.timestamp">
                  <span class="hist-sep">/</span>
                  <span>{{ timeAgo(project.timestamp) }}</span>
                </template>
              </div>
            </div>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" stroke-width="1.5" class="hist-chevron"><path d="M9 18l6-6-6-6"/></svg>
          </div>
        </div>
      </div>
    </section>

    <!-- Lightbox -->
    <Teleport to="body">
      <div v-if="lightboxSrc" class="lightbox-overlay" @click.self="closeLightbox">
        <button class="lightbox-close" @click="closeLightbox">&times;</button>

        <!-- Left arrow -->
        <button
          v-if="lightboxScenes.findIndex(s => s.index === lightboxIndex) > 0"
          class="lightbox-arrow lightbox-arrow--left"
          @click.stop="lightboxNav(-1)"
        >&#8249;</button>

        <img :src="lightboxSrc" class="lightbox-img" />

        <!-- Right arrow -->
        <button
          v-if="lightboxScenes.findIndex(s => s.index === lightboxIndex) < lightboxScenes.length - 1"
          class="lightbox-arrow lightbox-arrow--right"
          @click.stop="lightboxNav(1)"
        >&#8250;</button>

        <!-- Scene indicator -->
        <div class="lightbox-info">
          <span class="lightbox-badge">Scene {{ lightboxIndex }}</span>
          <span class="lightbox-counter">{{ lightboxScenes.findIndex(s => s.index === lightboxIndex) + 1 }} / {{ lightboxScenes.length }}</span>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.storyboard-page {
  max-width: 1024px;
  margin: 0 auto;
  padding: 32px 24px;
}

/* ---- Header ---- */
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.page-title {
  font-size: 1.55rem;
  font-weight: 700;
  color: var(--text-primary, #e2e8f0);
  margin: 0;
}
.page-subtitle {
  font-size: 0.82rem;
  color: var(--text-muted, #4a5568);
  margin: 0 0 24px;
}
.project-badge {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  background: rgba(78, 205, 196, 0.1);
  padding: 3px 10px;
  border-radius: 8px;
}

/* ---- Card base ---- */
.card {
  padding: 20px;
}

/* ---- Source ---- */
.source-card { padding: 16px; }
.source-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.source-info-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.source-label {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}
.source-style { color: var(--accent); }
.source-actions { display: flex; gap: 6px; }
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
.action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
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
  font-family: 'JetBrains Mono', monospace;
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
.setting-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin: 0;
}

/* ---- Aspect Ratio ---- */
.aspect-ratio-section {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.aspect-select {
  padding: 5px 28px 5px 10px;
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--text);
  background: var(--bg-darkest, #0a0e13);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%236b7280' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
  transition: border-color 0.15s;
}
.aspect-select:hover,
.aspect-select:focus {
  border-color: var(--accent);
  outline: none;
}
.aspect-select option {
  background: var(--bg-card, #141a22);
  color: var(--text);
}

/* ---- Grab All button ---- */
.gen-btn.btn-grab-all {
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 11px;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
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
.gen-btn.btn-grab-all:hover:not(:disabled) {
  box-shadow: 0 6px 24px rgba(78, 205, 196, 0.35);
  transform: translateY(-1px);
}
.gen-btn.btn-grab-all:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ---- Progress ---- */
.progress-bar-wrap {
  margin-bottom: 14px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.progress-bar-track {
  flex: 1;
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
.progress-text {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}

/* ---- Image card body (prompt + actions) ---- */
.image-body {
  padding: 10px 14px;
}
.image-prompt {
  font-size: 10px;
  color: var(--text-secondary);
  font-style: italic;
  line-height: 1.4;
  margin: 6px 0 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.image-actions {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-top: 8px;
}
.btn-copy {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--text-muted);
  background: transparent;
  border: 1px solid var(--border);
  cursor: pointer;
  transition: all 0.15s;
}
.btn-copy:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.btn-download {
  padding: 5px 7px;
}
.btn-download:hover {
  border-color: #82aaff;
  color: #82aaff;
}
.btn-grab-one {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 10px;
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--text-muted);
  background: transparent;
  border: 1px solid var(--border);
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.btn-grab-one:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}
.btn-grab-one:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ---- Prompt editing ---- */
.prompt-edit-area {
  width: 100%;
  padding: 8px;
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text);
  background: var(--bg-darkest, #0a0e13);
  border: 1px solid var(--accent);
  border-radius: 6px;
  resize: vertical;
  outline: none;
  line-height: 1.5;
}
.edit-actions {
  display: flex;
  gap: 6px;
  margin-top: 6px;
}
.btn-edit-save {
  padding: 3px 12px;
  font-size: 10px;
  font-weight: 600;
  color: var(--bg-darkest);
  background: var(--accent);
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
.btn-edit-save:hover {
  filter: brightness(1.1);
}
.btn-edit-cancel {
  padding: 3px 10px;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
}
.btn-edit-cancel:hover {
  border-color: var(--text-secondary);
  color: var(--text);
}
.spinner-sm {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid var(--text-muted);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ---- Gallery ---- */
.gallery-section {
  margin-top: 24px;
}
.gallery-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 14px;
}
.gallery-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gallery-title {
  font-weight: 700;
  font-size: 13px;
  color: var(--text-primary);
}
.gallery-count {
  font-size: 11px;
  color: var(--accent);
}
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}
.image-card {
  background: var(--bg-surface, #161d2a);
  border: 1px solid var(--border, #1e2a3a);
  border-radius: 10px;
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.image-card:hover {
  border-color: var(--accent, #4ecdc4);
  box-shadow: 0 0 0 1px rgba(78, 205, 196, 0.15);
}
.image-preview {
  position: relative;
  aspect-ratio: 16/9;
  background: var(--bg-darkest, #0a0e13);
}
.image-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.image-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
}
.image-scene {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-primary, #e2e8f0);
}
.image-size {
  font-size: 10px;
  color: var(--text-muted, #4a5568);
}
.image-card--empty {
  opacity: 0.6;
}
.image-card--empty:hover {
  opacity: 1;
}
/* ---- Version badge ---- */
.version-badge {
  position: absolute;
  bottom: 6px;
  right: 6px;
  min-width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  font-family: var(--font-mono);
  color: #fff;
  background: rgba(78, 205, 196, 0.85);
  border-radius: 10px;
  padding: 0 6px;
  z-index: 2;
}

/* ---- Version strip ---- */
.version-strip {
  display: flex;
  gap: 4px;
  padding: 6px 8px;
  background: var(--bg-darkest, #0a0e13);
  overflow-x: auto;
}
.version-thumb {
  flex-shrink: 0;
  width: 48px;
  cursor: pointer;
  border-radius: 4px;
  overflow: hidden;
  border: 1.5px solid transparent;
  transition: border-color 0.15s;
  position: relative;
}
.version-thumb:hover {
  border-color: var(--accent);
}
.version-thumb--current {
  border-color: var(--accent);
}
.version-thumb img {
  width: 100%;
  aspect-ratio: 16/9;
  object-fit: cover;
  display: block;
}
.version-label {
  display: block;
  text-align: center;
  font-size: 8px;
  font-weight: 600;
  font-family: var(--font-mono);
  color: var(--text-muted);
  padding: 1px 0;
  background: var(--bg-darkest, #0a0e13);
}
.version-thumb--current .version-label {
  color: var(--accent);
}

.image-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
  justify-content: center;
}
.image-placeholder.is-loading {
  background: linear-gradient(135deg, rgba(240, 198, 116, 0.03) 0%, rgba(240, 198, 116, 0.08) 50%, rgba(240, 198, 116, 0.03) 100%);
  background-size: 200% 200%;
  animation: shimmer 3s ease-in-out infinite;
}
@keyframes shimmer {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}
.loading-visual {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
}
.loading-icon {
  position: relative;
  z-index: 1;
  color: #f0c674;
  opacity: 0.6;
  animation: icon-breathe 2s ease-in-out infinite;
}
@keyframes icon-breathe {
  0%, 100% { opacity: 0.4; transform: scale(1) rotate(0deg); }
  50% { opacity: 0.9; transform: scale(1.1) rotate(15deg); }
}
.pulse-ring {
  position: absolute;
  inset: 0;
  border: 1.5px solid #f0c674;
  border-radius: 50%;
  opacity: 0;
  animation: pulse-expand 2.4s ease-out infinite;
}
.pulse-ring.delay-1 { animation-delay: 0.8s; }
.pulse-ring.delay-2 { animation-delay: 1.6s; }
@keyframes pulse-expand {
  0% { transform: scale(0.5); opacity: 0.5; }
  100% { transform: scale(1.6); opacity: 0; }
}
.loading-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #f0c674;
  opacity: 0.8;
  animation: label-pulse 1.5s ease-in-out infinite;
}
@keyframes label-pulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}
.image-status {
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.status--pending { color: var(--text-muted); }
.status--generating { color: #f0c674; }
.status--downloading { color: #82aaff; }
.status--ready { color: var(--accent); }
.status--error { color: #ff6b6b; }

/* ---- Empty State ---- */
.empty-state {
  text-align: center;
  padding: 48px 20px;
  border: 1px solid var(--border, #1e2a3a);
  border-radius: 12px;
  margin-bottom: 24px;
}
.empty-icon {
  opacity: 0.3;
  margin-bottom: 16px;
}
.empty-title {
  font-weight: 600;
  font-size: 1rem;
  color: var(--text-primary, #e2e8f0);
  margin: 0 0 6px;
}
.empty-desc {
  font-size: 0.82rem;
  color: var(--text-muted, #4a5568);
  margin: 0;
  line-height: 1.5;
}

/* ---- History ---- */
.history-card {
  margin-top: 24px;
  padding: 16px 20px;
}
.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.history-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.history-title {
  font-weight: 700;
  font-size: 13px;
  color: var(--text-primary, #e2e8f0);
}
.history-refresh-btn {
  padding: 5px 8px;
}
.history-empty {
  text-align: center;
  padding: 24px 0;
  font-size: 12px;
  color: var(--text-muted);
}
.history-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.hist-item {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}
.hist-item:hover {
  background: rgba(78, 205, 196, 0.04);
}
.hist-item.active {
  background: rgba(78, 205, 196, 0.08);
  border: 1px solid rgba(78, 205, 196, 0.18);
}
.hist-inner {
  display: flex;
  align-items: center;
  gap: 12px;
}
.hist-thumb {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  background: var(--bg-darkest, #0a0e13);
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
  color: var(--text-muted);
}
.hist-thumb--active {
  border-color: var(--accent);
}
.hist-thumb--active svg { color: var(--accent); }
.hist-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.hist-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.hist-name {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
}
.hist-item.active .hist-name { color: var(--accent); }
.hist-active-badge {
  font-size: 8px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(78,205,196,0.12);
  color: var(--accent);
  letter-spacing: 0.06em;
}
.hist-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.hist-status {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.hist-meta {
  font-size: 11px;
  color: var(--text-muted);
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  align-items: center;
}
.hist-sep {
  color: var(--border);
  margin: 0 4px;
}
.hist-style {
  color: var(--text-secondary, #94a3b8);
  text-transform: capitalize;
}
.hist-chevron {
  flex-shrink: 0;
  opacity: 0.3;
  transition: opacity 0.15s;
}
.hist-item:hover .hist-chevron { opacity: 0.6; }
.hist-item.active .hist-chevron { opacity: 0.8; color: var(--accent); }

/* ---- Modal ---- */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-panel {
  background: var(--bg-surface, #161d2a);
  border: 1px solid var(--border, #1e2a3a);
  border-radius: 12px;
  width: 480px;
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 20px 60px rgba(0,0,0,0.5);
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}
.modal-header h3 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}
.modal-close {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  transition: color 0.15s;
}
.modal-close:hover { color: var(--text-primary); }
.modal-body {
  overflow-y: auto;
  padding: 8px;
}
.picker-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}
.picker-row:hover { background: rgba(78,205,196,0.06); }
.picker-icon { flex-shrink: 0; color: var(--text-muted); opacity: 0.5; margin-right: 10px; }
.picker-row:hover .picker-icon { color: var(--accent); opacity: 0.8; }
.picker-info { flex: 1; min-width: 0; }
.picker-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.picker-meta {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
  display: flex;
  gap: 2px;
  align-items: center;
}
.picker-sep { color: var(--border); margin: 0 4px; }
.picker-style { color: var(--text-secondary); text-transform: capitalize; }
.picker-empty {
  text-align: center;
  padding: 24px;
  font-size: 12px;
  color: var(--text-muted);
}

/* Image preview clickable */
.image-preview.clickable {
  cursor: pointer;
}
.image-preview.clickable:hover img {
  filter: brightness(1.1);
  transition: filter 0.2s;
}

/* Lightbox */
.lightbox-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.9);
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(4px);
}
.lightbox-img {
  max-width: 90vw;
  max-height: 90vh;
  object-fit: contain;
  border-radius: 6px;
  box-shadow: 0 8px 40px rgba(0,0,0,0.6);
}
.lightbox-close {
  position: absolute;
  top: 16px;
  right: 24px;
  background: none;
  border: none;
  color: #fff;
  font-size: 32px;
  cursor: pointer;
  opacity: 0.7;
  transition: opacity 0.2s;
  line-height: 1;
}
.lightbox-close:hover {
  opacity: 1;
}
.lightbox-arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #fff;
  font-size: 36px;
  width: 44px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-radius: 8px;
  opacity: 0.6;
  transition: all 0.2s;
  backdrop-filter: blur(4px);
  line-height: 1;
  padding: 0;
}
.lightbox-arrow:hover {
  opacity: 1;
  background: rgba(255, 255, 255, 0.15);
}
.lightbox-arrow--left { left: 16px; }
.lightbox-arrow--right { right: 16px; }
.lightbox-info {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(8px);
  padding: 6px 14px;
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}
.lightbox-badge {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent, #4ECDC4);
}
.lightbox-counter {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
  font-family: 'JetBrains Mono', monospace;
}
</style>
