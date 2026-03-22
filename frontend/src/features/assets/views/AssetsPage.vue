<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/shared/api/client.js'
import { useAssets } from '../composables/useAssets.js'
import { useToast } from '@/shared/composables/useToast.js'
import { useStagingStore } from '@/shared/stores/stagingStore.js'
import { timeAgo, formatElapsed } from '@/shared/utils/format.js'
import { useProjectSync } from '@/shared/composables/useProjectSync.js'
import { useAudioRegistry } from '@/shared/composables/useAudioRegistry.js'
import AssetCard from '../components/AssetCard.vue'
import AssetLightbox from '../components/AssetLightbox.vue'
import GrabberControls from '../components/GrabberControls.vue'

defineOptions({ name: 'AssetsPage' })

const route = useRoute()
const router = useRouter()
const toast = useToast()
const staging = useStagingStore()
const {
  scenes,
  provider,
  arguments: args,
  aspectRatio,
  providerOptions,
  grabberRunning,
  sceneStatuses,
  selectedScenes,
  history,
  analysisData,
  audioUrl,
  isPlaying,
  currentTime,
  lightboxOpen,
  lightboxScene,
  lightboxFile,
  sceneCount,
  selectedCount,
  progress,
  TYPE_COLORS,
  loadScenes,
  setProvider,
  setArguments,
  setAspectRatio,
  setProviderOption,
  startGrabber,
  stopGrabber,
  redownload,
  loadHistory,
  loadFromHistory,
  reconcile,
  editPrompt,
  savePrompt,
  copyPrompt,
  openFolder,
  downloadScene,
  downloadAll,
  toggleSelect,
  selectAll,
  selectNone,
  selectPending,
  resendSelected,
  openLightbox,
  closeLightbox,
  loadSceneHistory,
} = useAssets()

const projectId = ref(null)
useProjectSync(projectId)
const analysisOpen = ref(true)
const historyVisible = ref(true)
const scenePickerOpen = ref(false)
const scenePickerData = ref([])
const audioRef = ref(null)
const assemblingProject = ref(null)
const buildSteps = ref([])
const buildVisible = ref(false)
const { register: audioRegister } = useAudioRegistry()
watch(audioRef, (el) => { if (el) audioRegister('Assets', el) })

// Audio
function toggleAudio() {
  if (!audioRef.value) return
  if (isPlaying.value) {
    audioRef.value.pause()
    isPlaying.value = false
  } else {
    audioRef.value.play()
    isPlaying.value = true
  }
}

function onAudioTimeUpdate() {
  if (audioRef.value) currentTime.value = audioRef.value.currentTime
}

function onAudioEnded() {
  isPlaying.value = false
  currentTime.value = 0
}

function seekAudio(e) {
  if (!audioRef.value) return
  const rect = e.currentTarget.getBoundingClientRect()
  const pct = (e.clientX - rect.left) / rect.width
  audioRef.value.currentTime = pct * audioRef.value.duration
}

const audioDuration = computed(() => audioRef.value?.duration || 0)
const audioProgress = computed(() => {
  if (!audioDuration.value) return 0
  return (currentTime.value / audioDuration.value) * 100
})

function formatTime(secs) {
  if (!secs || isNaN(secs)) return '0:00'
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

// Scene loading — load the latest project directly
async function loadCurrentScenes() {
  try {
    const data = await loadSceneHistory()
    if (data && data.length) {
      const latest = data[0]
      const sceneData = await api.get(`/api/scenes/${latest.project_id}`)
      if (sceneData?.scenes) {
        loadScenes(sceneData)
        projectId.value = latest.project_id
        toast.success(`Loaded ${sceneData.scenes.length} scenes from ${latest.project_id}`)
      }
    } else {
      toast.warning('No scene history found.')
    }
  } catch (e) {
    console.warn('[Assets] Failed to load current scenes:', e.message)
    toast.error('Failed to load scene history.')
  }
}

async function pickSceneProject(entry) {
  scenePickerOpen.value = false
  const pid = entry.project_id
  try {
    const data = await api.get(`/api/scenes/${pid}`)
    if (data?.scenes) {
      loadScenes(data)
      projectId.value = pid
      toast.success(`Loaded ${data.scenes.length} scenes from ${pid}`)
    }
  } catch {
    toast.error(`Failed to load project ${pid}`)
  }
}

async function loadFromHistoryProject(pid) {
  try {
    await loadFromHistory(pid)
    projectId.value = pid
    historyVisible.value = false
    toast.success('Project loaded.')
  } catch {
    toast.error('Failed to load project.')
  }
}

function setStep(label, status) {
  const existing = buildSteps.value.find(s => s.label === label)
  if (existing) {
    existing.status = status
  } else {
    buildSteps.value.push({ label, status })
  }
}

const STEP_DELAY = 400

async function validateAndBuild(project) {
  const pid = project.project_id
  assemblingProject.value = pid
  buildSteps.value = []
  buildVisible.value = true

  try {
    // Step 1: Reconcile disk files with metadata
    setStep('Reconciling assets', 'running')
    await api.post(`/api/assets/reconcile/${pid}`)
    setStep('Reconciling assets', 'done')
    await new Promise(r => setTimeout(r, STEP_DELAY))

    // Step 2: Validate each scene folder has at least one asset
    setStep('Validating scene assets', 'running')
    const assetData = await api.get(`/api/assets/project/${pid}`)
    if (!assetData || assetData.error) {
      setStep('Validating scene assets', 'error')
      setStep('Error: could not load asset data', 'error')
      await new Promise(r => setTimeout(r, 5000))
      buildVisible.value = false
      return
    }

    const sceneStatuses = assetData.scene_statuses || {}
    const sceneKeys = Object.keys(sceneStatuses)
    const totalScenes = sceneKeys.length || project.scene_count || 0
    let readyCount = 0
    const missingScenes = []

    for (const key of sceneKeys) {
      const s = sceneStatuses[key]
      if (s.status === 'ready' && s.local_files?.length) {
        readyCount++
      } else {
        missingScenes.push(key)
      }
    }

    setStep(`Validated: ${readyCount}/${totalScenes} scenes have assets`, readyCount === totalScenes ? 'done' : 'error')
    await new Promise(r => setTimeout(r, STEP_DELAY))

    if (missingScenes.length) {
      setStep(`Missing assets: scene${missingScenes.length > 1 ? 's' : ''} ${missingScenes.join(', ')}`, 'error')
      await new Promise(r => setTimeout(r, 5000))
      buildVisible.value = false
      return
    }

    // Step 3: Generate thumbnails
    setStep('Generating thumbnails', 'running')
    const thumbResult = await api.post(`/api/thumbnails/${pid}/generate?modules=assets`)
    const thumbGen = thumbResult?.total_generated || 0
    const thumbSkip = thumbResult?.total_skipped || 0
    const thumbErr = thumbResult?.total_errors || 0
    setStep(`Thumbnails: ${thumbGen} generated, ${thumbSkip} cached${thumbErr ? `, ${thumbErr} errors` : ''}`, thumbErr ? 'error' : 'done')
    await new Promise(r => setTimeout(r, STEP_DELAY))

    // Step 4: Proceed to assemble & edit
    setStep('Validation passed — assembling project', 'done')
    await new Promise(r => setTimeout(r, STEP_DELAY))
  } catch (e) {
    setStep('Error: ' + (e.message || 'Unknown error'), 'error')
    await new Promise(r => setTimeout(r, 5000))
    buildVisible.value = false
    return
  }

  // Clear the overlay and delegate to the regular assembleAndEdit flow
  buildVisible.value = false
  assemblingProject.value = null
  await assembleAndEdit(project)
}

async function assembleAndEdit(project) {
  const pid = project.project_id
  assemblingProject.value = pid
  buildSteps.value = []
  buildVisible.value = true
  const forceParam = project.has_build ? '?force=1' : ''
  let hasErrors = false

  try {
    setStep('Assembling project', 'running')
    const data = await api.post(`/api/projects/${pid}/assemble${forceParam}`)

    if (!data || data.error) {
      setStep('Assembling project', 'error')
      hasErrors = true
      return
    }
    setStep('Assembling project', 'done')
    await new Promise(r => setTimeout(r, STEP_DELAY))

    // Report warnings from the API
    if (data.warnings?.length) {
      for (const w of data.warnings) {
        setStep(w, 'error')
        hasErrors = true
        await new Promise(r => setTimeout(r, STEP_DELAY))
      }
    }

    const mediaCount = (data.scenes || []).filter(s => s.mediaUrl || s.image_url).length
    const sceneTotal = data.scene_count || 0
    const missingMedia = sceneTotal - mediaCount
    setStep(`Scenes: ${sceneTotal} total, ${mediaCount} with media`, mediaCount > 0 ? 'done' : 'error')
    if (mediaCount <= 0) hasErrors = true
    await new Promise(r => setTimeout(r, STEP_DELAY))

    if (missingMedia > 0) {
      setStep(`${missingMedia} scene${missingMedia !== 1 ? 's' : ''} missing media`, 'error')
      hasErrors = true
      await new Promise(r => setTimeout(r, STEP_DELAY))
    }

    const totalDur = data.total_duration ? data.total_duration.toFixed(1) + 's' : '0s'
    setStep(`Timeline: ${totalDur} total duration`, data.total_duration > 0 ? 'done' : 'error')
    if (!data.total_duration) hasErrors = true
    await new Promise(r => setTimeout(r, STEP_DELAY))

    const hasAudio = data.audio_tracks && data.audio_tracks.length > 0
    setStep('Audio track', hasAudio ? 'done' : 'skip')
    await new Promise(r => setTimeout(r, STEP_DELAY))

    const hasCaps = data.captions?.captions?.length > 0
    setStep(`Captions${hasCaps ? ` (${data.captions.captions.length})` : ''}`, hasCaps ? 'done' : 'skip')
    await new Promise(r => setTimeout(r, STEP_DELAY))

    setStep(`Saved to projects/${pid}/`, 'done')
    await new Promise(r => setTimeout(r, STEP_DELAY))

    if (hasErrors) {
      setStep('Build completed with issues', 'error')
      await new Promise(r => setTimeout(r, 5000))
      buildVisible.value = false
      return
    }

    setStep('Launching editor', 'running')

    const bootData = {
      project_id: data.project_id,
      project_name: data.project_name || data.project_id,
      source_folder: data.source_folder || '',
      style: data.style || '',
      total_duration: data.total_duration || 0,
      scene_count: data.scene_count || 0,
      staged_at: data.saved_at || new Date().toISOString(),
      scenes: data.scenes || [],
      audio_tracks: data.audio_tracks || [],
      grain_overlay: data.grain_overlay || {},
      captionsEnabled: data.captionsEnabled || false,
      edit_history: data.edit_history || [],
      history_index: data.history_index ?? -1,
      disabled_tracks: data.disabled_tracks || [],
      ...(data.audio ? { audio: data.audio } : {}),
      ...(data.captions ? { captions: data.captions, captionsEnabled: true } : {}),
    }

    staging.stage(bootData)
    sessionStorage.setItem('sts-editor-entry-source', 'internal')

    setStep('Launching editor', 'done')
    await new Promise(r => setTimeout(r, 600))

    buildVisible.value = false
    router.push({ path: '/editor', query: { project: pid } })
  } catch (e) {
    setStep('Error: ' + (e.message || 'Unknown error'), 'error')
    hasErrors = true
    await new Promise(r => setTimeout(r, 5000))
    buildVisible.value = false
  } finally {
    assemblingProject.value = null
  }
}

async function showHistory() {
  await loadHistory()
  historyVisible.value = true
}

async function pickFromSceneHistory() {
  try {
    const data = await loadSceneHistory()
    if (data && data.length) {
      scenePickerData.value = data
      scenePickerOpen.value = true
    } else {
      toast.warning('No scene history found.')
    }
  } catch {
    toast.error('Failed to load scene history.')
  }
}

// Provider URLs for auto-open
const PROVIDER_URLS = {
  midjourney: 'https://www.midjourney.com/imagine',
  grok: 'https://grok.com/imagine',
  'meta-ai': 'https://www.meta.ai/media',
}

// Grabber actions
async function onStart() {
  if (!projectId.value) projectId.value = `project_${Date.now()}`
  try {
    await startGrabber(projectId.value)
    toast.success('Grabber started.')
    // Open the provider website
    const url = PROVIDER_URLS[provider.value]
    if (url) window.open(url, 'sts-provider-tab')
  } catch {
    toast.error('Failed to start grabber.')
  }
}

async function onStop() {
  stopGrabber()
  toast.info('Grabber stopped.')
}

async function onResendSelected() {
  if (!projectId.value) projectId.value = `project_${Date.now()}`
  try {
    await resendSelected(projectId.value)
    toast.success('Resending selected scenes.')
  } catch {
    toast.error('Failed to resend.')
  }
}

// Card actions
function onSavePrompt(idx, text) {
  savePrompt(idx, text)
  toast.success('Prompt updated.')
}

function onCopyPrompt(idx) {
  copyPrompt(idx)
  toast.success('Prompt copied.')
}

async function onOpenFolder(idx) {
  if (!projectId.value) return
  try {
    await openFolder(idx, projectId.value)
  } catch {
    toast.error('Failed to open folder.')
  }
}

function onDownloadScene(idx) {
  downloadScene(idx, projectId.value)
}

function onValidateAndBuild() {
  if (!projectId.value) {
    toast.error('No project loaded')
    return
  }
  validateAndBuild({
    project_id: projectId.value,
    scene_count: sceneCount.value,
  })
}

function onOpenLightbox(scene, file) {
  const status = sceneStatuses.value[scene.index]
  const files = status?.local_files || status?.urls || []
  if (!files.length) return
  const fileIdx = file ? files.indexOf(file) : 0
  openLightbox(scene, file)
}

// Analysis chips
const analysisChips = computed(() => {
  if (!analysisData.value) return []
  const data = analysisData.value
  const chips = []
  if (data.core_theme || data.theme) chips.push({ label: 'Theme', value: data.core_theme || data.theme, color: '#F7DC6F' })
  if (data.mood) chips.push({ label: 'Mood', value: data.mood, color: '#FF6B6B' })
  if (data.environment) chips.push({ label: 'Env', value: data.environment, color: '#4ECDC4' })
  if (data.color_palette) chips.push({ label: 'Palette', value: data.color_palette, color: '#A78BFA' })
  if (data.tone) chips.push({ label: 'Tone', value: data.tone, color: '#FFB347' })
  if (data.visual_style || data.style) chips.push({ label: 'Style', value: data.visual_style || data.style, color: '#45B7D1' })
  return chips
})

// Lightbox file list
const lightboxFiles = computed(() => {
  if (!lightboxScene.value) return []
  const status = sceneStatuses.value[lightboxScene.value.index]
  return status?.local_files || status?.urls || []
})

const lightboxInitialIndex = computed(() => {
  if (!lightboxFile.value || !lightboxFiles.value.length) return 0
  const idx = lightboxFiles.value.indexOf(lightboxFile.value)
  return idx >= 0 ? idx : 0
})

const STATUS_COLORS = { done: '#4ECDC4', downloading: '#FFB347', error: '#FF6B6B', waiting: '#8B8B8B', grabbing: '#A78BFA' }
function statusColor(status) {
  return STATUS_COLORS[status] || '#8B8B8B'
}

onMounted(async () => {
  await loadHistory()
  const projectParam = route.query.project
  if (projectParam) {
    // Try loading from asset history first, fallback to scenes data
    try {
      await loadFromHistory(projectParam)
      projectId.value = projectParam
    } catch {
      try {
        const data = await api.get(`/api/scenes/${projectParam}`)
        if (data?.scenes) {
          loadScenes(data)
          projectId.value = projectParam
        }
      } catch {
        toast.error(`Project ${projectParam} not found`)
      }
    }
  }
})
</script>

<template>
  <div class="assets-page">
    <!-- Header -->
    <div class="page-header">
      <h2 class="page-title">Animator</h2>
      <span v-if="projectId" class="project-badge">{{ projectId }}</span>
    </div>
    <p class="page-subtitle">Generate and animate visual assets for each scene</p>

    <!-- Source Info -->
    <section class="card source-card">
      <div class="source-row">
        <div class="source-info-left">
          <span class="source-label">
            <template v-if="sceneCount && projectId">
              {{ projectId }} &middot; {{ sceneCount }} scenes
              <template v-if="analysisData?.style">
                &middot; <span class="source-style">&bullet;{{ analysisData.style }}</span>
              </template>
            </template>
            <template v-else>No scenes loaded</template>
          </span>
        </div>
        <div class="source-actions">
          <button class="action-btn" style="padding:6px 14px;font-size:11px" @click="loadCurrentScenes">
            Use Current Result
          </button>
          <button class="action-btn" style="padding:6px 14px;font-size:11px" @click="pickFromSceneHistory">
            Pick from History
          </button>
        </div>
      </div>
    </section>

    <!-- Analysis Bar -->
    <section
      v-if="analysisChips.length"
      class="card analysis-card"
    >
      <div class="analysis-header">
        <span class="analysis-toggle-label" @click="analysisOpen = !analysisOpen">
          <span class="analysis-arrow" :class="{ open: analysisOpen }">▼</span> ANALYSIS
        </span>
      </div>
      <div v-if="analysisOpen" class="analysis-chips">
        <template v-for="(chip, i) in analysisChips" :key="chip.label">
          <div class="analysis-item" :class="{ 'has-border': i > 0 }">
            <span class="analysis-label" :style="{ color: chip.color }">{{ chip.label }}</span>
            <span class="analysis-value">{{ chip.value }}</span>
          </div>
        </template>
      </div>
      <div v-if="analysisOpen && analysisData?.script" class="analysis-script">
        <span class="analysis-script-label">Script</span>
        <p class="analysis-script-text">{{ analysisData.script }}</p>
      </div>
    </section>

    <!-- Scene Picker Modal -->
    <div v-if="scenePickerOpen" class="modal-backdrop" @click.self="scenePickerOpen = false">
      <div class="modal-panel">
        <div class="modal-header">
          <h3>Pick Storyboard</h3>
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
            @click="pickSceneProject(entry)"
          >
            <div class="picker-info">
              <span class="picker-label">{{ entry.project_id || `Set ${i + 1}` }}</span>
              <div class="picker-meta font-mono">
                <span style="color: var(--accent)">{{ entry.scene_count || entry.scenes?.length || 0 }} scenes</span>
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
          <div v-if="!scenePickerData.length" class="picker-empty">No scene projects found.</div>
        </div>
      </div>
    </div>

    <!-- Audio Player -->
    <section v-if="audioUrl" class="card audio-card">
      <audio
        ref="audioRef"
        :src="audioUrl"
        preload="metadata"
        @timeupdate="onAudioTimeUpdate"
        @ended="onAudioEnded"
      />
      <div class="audio-player">
        <button class="audio-play-btn" @click="toggleAudio">
          <svg v-if="!isPlaying" width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <path d="M8 5v14l11-7z" />
          </svg>
          <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
            <rect x="6" y="4" width="4" height="16" /><rect x="14" y="4" width="4" height="16" />
          </svg>
        </button>
        <div class="audio-progress" @click="seekAudio">
          <div class="audio-track">
            <div class="audio-fill" :style="{ width: audioProgress + '%' }" />
            <!-- Scene markers -->
            <template v-if="audioDuration">
              <span
                v-for="scene in scenes"
                :key="'marker-' + scene.index"
                class="scene-marker"
                :style="{ left: ((scene.start_time || 0) / audioDuration * 100) + '%' }"
                :title="'Scene ' + (scene.index + 1)"
              />
            </template>
          </div>
        </div>
        <span class="audio-time">
          {{ formatTime(currentTime) }} / {{ formatTime(audioDuration) }}
        </span>
      </div>
    </section>

    <!-- Controls -->
    <GrabberControls
      v-if="sceneCount"
      :provider="provider"
      :arguments="args"
      :aspect-ratio="aspectRatio"
      :provider-options="providerOptions"
      :grabber-running="grabberRunning"
      :progress="progress"
      :selected-count="selectedCount"
      :scene-count="sceneCount"
      @update:provider="setProvider"
      @update:arguments="setArguments"
      @update:aspect-ratio="setAspectRatio"
      @update:provider-option="(k, v) => setProviderOption(k, v)"
      @update:auto-type="(v) => setProviderOption('auto_type', v)"
      @start="onStart"
      @stop="onStop"
      @select-all="selectAll"
      @select-pending="selectPending"
      @select-none="selectNone"
      @resend-selected="onResendSelected"
      @validate-and-build="onValidateAndBuild"
    />

    <!-- Asset Grid -->
    <section v-if="sceneCount" class="asset-grid">
      <AssetCard
        v-for="scene in scenes"
        :key="scene.index"
        :scene="scene"
        :scene-index="scene.index"
        :status="sceneStatuses[scene.index] || {}"
        :selected="selectedScenes.has(scene.index)"
        :provider="provider"
        @toggle-select="toggleSelect"
        @edit-prompt="editPrompt"
        @save-prompt="onSavePrompt"
        @copy-prompt="onCopyPrompt"
        @download="onDownloadScene"
        @open-folder="onOpenFolder"
        @open-lightbox="onOpenLightbox"
      />
    </section>

    <!-- Empty State -->
    <section v-else class="empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" class="empty-icon">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <circle cx="8.5" cy="8.5" r="1.5" />
        <path d="m21 15-5-5L5 21" />
      </svg>
      <p class="empty-title">No scenes loaded</p>
      <p class="empty-desc">Load scenes from the scene blueprint or pick from history to get started.</p>
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
          @click="loadFromHistoryProject(project.project_id)"
        >
          <div class="hist-inner">
            <!-- Preview thumbnail -->
            <div class="hist-thumb" :class="{ 'hist-thumb--active': project.project_id === projectId }">
              <img v-if="project.preview" :src="project.preview" alt="" />
              <svg v-else width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
                <rect x="3" y="3" width="18" height="18" rx="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <path d="M21 15l-5-5L5 21" />
              </svg>
            </div>

            <!-- Info -->
            <div class="hist-content">
              <div class="hist-title-row">
                <span class="hist-name">{{ project.project_id }}</span>
                <span
                  v-if="project.project_id === projectId"
                  class="hist-active-badge font-mono"
                >ACTIVE</span>
                <span class="hist-dot" :style="{ background: statusColor(project.status) }"></span>
                <span class="hist-status font-mono" :style="{ color: statusColor(project.status) }">{{ project.status || 'unknown' }}</span>
              </div>
              <div class="hist-meta font-mono">
                <span style="color: var(--accent)">{{ project.scene_count || 0 }} scene{{ (project.scene_count || 0) !== 1 ? 's' : '' }}</span>
                <template v-if="project.ready_count">
                  <span class="hist-sep">/</span>
                  <span style="color: var(--accent-ready)">{{ project.ready_count }} ready</span>
                </template>
                <template v-if="project.disk_files">
                  <span class="hist-sep">/</span>
                  <span style="color: var(--text-secondary)">{{ project.disk_files }} files</span>
                </template>
                <template v-if="formatElapsed(project.generation_time)">
                  <span class="hist-sep">/</span>
                  <span style="color: var(--accent-warning)">elapsed {{ formatElapsed(project.generation_time) }}</span>
                </template>
                <span class="hist-sep">/</span>
                <span style="color: var(--text-muted)">{{ timeAgo(project.created_at || project.timestamp) }}</span>
                <template v-if="project.provider">
                  <span class="hist-sep">/</span>
                  <span class="hist-provider-badge">{{ project.provider }}</span>
                </template>
              </div>
            </div>

            <!-- Actions -->
            <div v-if="project.status === 'done' && project.ready_count" class="hist-actions">
              <button
                class="hist-action-btn hist-action-btn--validate"
                :disabled="assemblingProject === project.project_id"
                @click.stop="validateAndBuild(project)"
              >{{ assemblingProject === project.project_id ? 'Validating...' : 'Validate, Build &amp; Edit' }}</button>
              <button
                class="hist-action-btn"
                :disabled="assemblingProject === project.project_id"
                @click.stop="assembleAndEdit(project)"
              >{{ assemblingProject === project.project_id ? 'Building...' : (project.has_build ? 'Rebuild &amp; Edit' : 'Build &amp; Edit') }}</button>
            </div>
            <svg v-else width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" class="hist-chevron">
              <path d="M9 18l6-6-6-6" />
            </svg>
          </div>
        </div>
      </div>
    </section>

    <!-- Lightbox -->
    <AssetLightbox
      v-if="lightboxOpen && lightboxScene"
      :scene="lightboxScene"
      :files="lightboxFiles"
      :initial-index="lightboxInitialIndex"
      @close="closeLightbox"
    />

    <!-- Build Progress Overlay -->
    <Teleport to="body">
      <div v-if="buildVisible" class="build-overlay">
        <div class="build-modal">
          <div class="build-title">
            <svg width="16" height="16" fill="none" stroke="var(--accent)" stroke-width="2" viewBox="0 0 24 24">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
            </svg>
            <span>{{ assemblingProject }}</span>
          </div>
          <div class="build-steps">
            <div
              v-for="step in buildSteps"
              :key="step.label"
              class="build-step"
            >
              <span class="build-step-icon">
                <span v-if="step.status === 'running'" class="build-spinner" />
                <span v-else-if="step.status === 'done'" style="color: var(--accent)">&#10003;</span>
                <span v-else-if="step.status === 'error'" style="color: var(--coral)">&#10007;</span>
                <span v-else style="opacity: 0.3">&#8212;</span>
              </span>
              <span
                class="build-step-label"
                :style="{ color: step.status === 'error' ? 'var(--coral)' : step.status === 'done' ? 'var(--accent)' : step.status === 'skip' ? 'var(--text-muted)' : 'var(--text)' }"
              >{{ step.label }}</span>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.assets-page {
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

/* ---- Analysis ---- */
.analysis-card {
  padding: 12px 16px;
  overflow: hidden;
}

.analysis-header {
  display: flex;
  align-items: center;
}

.analysis-toggle-label {
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--accent);
  cursor: pointer;
}

.analysis-arrow {
  display: inline-block;
  font-size: 8px;
  transition: transform 0.2s;
  transform: rotate(-90deg);
}

.analysis-arrow.open {
  transform: rotate(0deg);
}

.analysis-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  align-items: center;
  margin-top: 10px;
}

.analysis-item {
  display: flex;
  align-items: baseline;
  gap: 5px;
}

.analysis-item.has-border {
  padding-left: 16px;
  border-left: 1px solid var(--border);
}

.analysis-label {
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  white-space: nowrap;
}

.analysis-value {
  font-size: 11px;
  color: var(--text-secondary);
}

.analysis-script {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--bg-darkest);
  border: 1px solid var(--border);
}

.analysis-script-label {
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  display: block;
  margin-bottom: 6px;
}

.analysis-script-text {
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin: 0;
  white-space: pre-wrap;
}

/* ---- Source ---- */
.source-card {
  padding: 16px;
}

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

.source-style {
  color: var(--accent);
}

.source-actions {
  display: flex;
  gap: 6px;
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

/* ---- Audio Player ---- */
.audio-card {
  padding: 14px 20px;
}

.audio-player {
  display: flex;
  align-items: center;
  gap: 12px;
}

.audio-play-btn {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent);
  color: #0d1117;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  transition: opacity 0.15s;
}

.audio-play-btn:hover {
  opacity: 0.85;
}

.audio-progress {
  flex: 1;
  cursor: pointer;
  padding: 8px 0;
}

.audio-track {
  position: relative;
  width: 100%;
  height: 4px;
  background: var(--bg-deeper, #0a0a0a);
  border-radius: 2px;
}

.audio-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
  transition: width 0.1s linear;
}

.scene-marker {
  position: absolute;
  top: -3px;
  width: 2px;
  height: 10px;
  background: rgba(255, 255, 255, 0.3);
  border-radius: 1px;
  pointer-events: none;
}

.audio-time {
  flex-shrink: 0;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-secondary);
  min-width: 80px;
  text-align: right;
}

/* ---- Asset Grid ---- */
.asset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

/* ---- Empty State ---- */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 20px;
  text-align: center;
}

.empty-icon {
  color: var(--text-secondary);
  opacity: 0.4;
  margin-bottom: 16px;
}

.empty-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 6px;
}

.empty-desc {
  font-size: 13px;
  color: var(--text-secondary);
  max-width: 360px;
}

/* ---- History ---- */
.history-card {
  margin-top: 16px;
  overflow: hidden;
  padding: 0;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
}

.history-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.history-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}

.history-refresh-btn {
  font-size: 10px;
  padding: 4px 10px;
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
  padding: 8px;
}

.hist-item {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 6px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s, background 0.15s;
}

.hist-item:hover {
  border-color: var(--border-hover);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
  background: var(--bg-darkest);
}

.hist-item.active {
  border-color: var(--accent-active);
  box-shadow: inset 3px 0 0 var(--accent-active), 0 0 12px rgba(255, 159, 67, 0.15);
}

.hist-inner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
}

.hist-thumb {
  width: 48px;
  height: 48px;
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
  background: var(--bg-darkest);
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  color: var(--text-muted);
}

.hist-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.hist-thumb svg {
  opacity: 0.4;
}

.hist-thumb--active {
  border-color: var(--accent-active);
}

.hist-thumb--active svg {
  stroke: var(--accent-active);
  opacity: 0.8;
}

.hist-content {
  flex: 1;
  min-width: 0;
}

.hist-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 3px;
}

.hist-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hist-item.active .hist-name {
  color: var(--accent-active);
}

.hist-active-badge {
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(255, 159, 67, 0.15);
  color: var(--accent-active);
  font-size: 8px;
  letter-spacing: 0.05em;
}

.hist-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.hist-status {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.hist-meta {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
  font-size: 10px;
}

.hist-sep {
  opacity: 0.3;
}

.hist-provider-badge {
  font-size: 8px;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(167, 139, 250, 0.1);
  color: #A78BFA;
}

.hist-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.hist-action-btn {
  flex-shrink: 0;
  padding: 5px 12px;
  background: var(--accent);
  color: var(--bg-darkest);
  border: none;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: opacity 0.15s, box-shadow 0.3s;
}

.hist-action-btn--validate {
  background: #A78BFA;
}

.hist-action-btn:hover {
  opacity: 0.85;
}

.hist-chevron {
  flex-shrink: 0;
  opacity: 0.4;
  color: var(--text-muted);
}

.hist-item.active .hist-chevron {
  stroke: var(--accent-active);
  opacity: 0.8;
}

/* ---- Scene Picker Modal ---- */
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-panel {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  width: 480px;
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

.modal-header h3 {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.modal-close {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
}

.modal-close:hover {
  color: var(--text);
}

.modal-body {
  padding: 12px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.picker-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.15s;
}

.picker-row:hover {
  background: var(--bg-darkest);
  border-color: var(--border);
}

.picker-info {
  flex: 1;
  min-width: 0;
}

.picker-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 3px;
}

.picker-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  color: var(--text-muted);
}

.picker-sep {
  opacity: 0.3;
}

.picker-style {
  text-transform: capitalize;
  color: var(--text-secondary);
}

.picker-empty {
  font-size: 13px;
  color: var(--text-muted);
  padding: 24px;
  text-align: center;
}

/* ---- Build Progress Overlay ---- */
.build-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
}

.build-modal {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px 28px;
  min-width: 360px;
  max-width: 480px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.build-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 18px;
  font-family: var(--font-mono);
}

.build-steps {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.build-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding: 2px 0;
}

.build-step-icon {
  width: 16px;
  text-align: center;
  flex-shrink: 0;
  font-size: 13px;
}

.build-step-label {
  font-weight: 500;
}

.build-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 1.5px solid rgba(255, 255, 255, 0.08);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: build-spin 0.6s linear infinite;
}

@keyframes build-spin {
  to { transform: rotate(360deg); }
}
</style>
