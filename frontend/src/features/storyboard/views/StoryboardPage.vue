<script setup>
import { ref, computed, onMounted, watch } from 'vue'
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
  } catch {
    status.value = null
  }
}

async function loadProject() {
  await Promise.all([loadImages(), loadStatus()])
}

async function loadHistory() {
  try {
    const jobs = await api.get('/api/pipeline/jobs')
    history.value = (jobs || [])
      .filter(j => j.project_id)
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
      .filter(j => j.project_id)
      .sort((a, b) => (b.created || 0) - (a.created || 0))
    scenePickerOpen.value = true
  } catch {
    toast.error('Failed to load project list.')
  }
}

function pickProject(entry) {
  scenePickerOpen.value = false
  projectId.value = entry.project_id
  loadProject()
  toast.success(`Loaded ${entry.project_id}`)
}

function loadFromHistory(pid) {
  projectId.value = pid
  loadProject()
}

function statusColor(s) {
  if (s === 'done') return '#4ecdc4'
  if (s === 'running') return '#f0c674'
  if (s === 'error') return '#ff6b6b'
  return '#64748b'
}

watch(() => route.query.project, (pid) => {
  if (pid) {
    projectId.value = pid
    loadProject()
  }
})

onMounted(async () => {
  await loadHistory()
  if (projectId.value) loadProject()
})

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
          <button class="action-btn" style="padding:6px 14px;font-size:11px" @click="loadCurrentResult">
            Use Current Result
          </button>
          <button class="action-btn" style="padding:6px 14px;font-size:11px" @click="pickFromHistory">
            Pick from History
          </button>
        </div>
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

    <!-- Image Grid -->
    <section v-if="imageCount" class="image-grid">
      <div v-for="img in images" :key="img.filename" class="image-card">
        <div class="image-preview">
          <img :src="img.path" :alt="img.filename" loading="lazy" />
        </div>
        <div class="image-footer">
          <span class="image-scene">Scene {{ img.filename.replace(/\.\w+$/, '') }}</span>
          <span class="image-size">{{ (img.size_bytes / 1024).toFixed(0) }} KB</span>
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

/* ---- Image Grid ---- */
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
</style>
