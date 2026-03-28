<script setup>
import { ref, computed } from 'vue'

defineOptions({ name: 'AssetCard' })

const props = defineProps({
  scene: { type: Object, required: true },
  sceneIndex: { type: Number, required: true },
  status: { type: Object, default: () => ({}) },
  selected: { type: Boolean, default: false },
  provider: { type: String, default: 'grok' },
  storyboardThumb: { type: String, default: null },
})

const emit = defineEmits([
  'toggle-select',
  'play',
  'edit-prompt',
  'save-prompt',
  'copy-prompt',
  'download',
  'open-folder',
  'open-lightbox',
])

const TYPE_COLORS = {
  video: '#4ECDC4',
  image: '#A78BFA',
  text: '#FFB347',
}

const editing = ref(false)
const editText = ref('')

const statusLabel = computed(() => {
  const s = props.status?.status
  if (s === 'ready') return 'Ready'
  if (s === 'generating') return 'Generating'
  if (s === 'downloading') return 'Downloading'
  if (s === 'error') return 'Error'
  return 'Pending'
})

const statusClass = computed(() => {
  return `status-${props.status?.status || 'pending'}`
})

const typeColor = computed(() => TYPE_COLORS[props.scene.type] || TYPE_COLORS.image)

const files = computed(() => props.status?.local_files || [])
const urls = computed(() => props.status?.urls || [])

const previewFiles = computed(() => {
  const all = files.value.length ? files.value : urls.value
  return all.slice(0, 4)
})

const hasPreview = computed(() => previewFiles.value.length > 0)

const isVideo = computed(() => props.scene.type === 'video')

const promptText = computed(() => props.scene.image_prompt || props.scene.text_content || '')

function startEdit() {
  editText.value = promptText.value
  editing.value = true
  emit('edit-prompt', props.sceneIndex)
}

function cancelEdit() {
  editing.value = false
}

function saveEdit() {
  emit('save-prompt', props.sceneIndex, editText.value)
  editing.value = false
}

function onCopy() {
  emit('copy-prompt', props.sceneIndex)
}

function onDownload() {
  emit('download', props.sceneIndex)
}

function onOpenFolder() {
  emit('open-folder', props.sceneIndex)
}

function onToggleSelect() {
  emit('toggle-select', props.sceneIndex)
}

function onOpenLightbox(file) {
  emit('open-lightbox', props.scene, file)
}

function fileSrc(file) {
  if (file.startsWith('http')) return file
  if (file.startsWith('/')) return file
  return `/output/animator/${file}`
}

function isImageFile(file) {
  const ext = file.split('.').pop().toLowerCase()
  return ['jpg', 'jpeg', 'png', 'gif', 'webp', 'avif'].includes(ext)
}

function isVideoFile(file) {
  const ext = file.split('.').pop().toLowerCase()
  return ['mp4', 'webm', 'mov'].includes(ext)
}
</script>

<template>
  <div
    class="asset-card"
    :class="{ selected }"
  >
    <!-- Preview area -->
    <div class="preview-area" @click="hasPreview && onOpenLightbox(previewFiles[0])">
      <template v-if="hasPreview">
        <div class="preview-grid" :class="`grid-${Math.min(previewFiles.length, 4)}`">
          <template v-for="(file, fi) in previewFiles" :key="fi">
            <img
              v-if="isImageFile(file)"
              :src="fileSrc(file)"
              class="preview-img"
              loading="lazy"
              alt=""
            />
            <div v-else-if="isVideoFile(file)" class="preview-video-wrap">
              <video :src="fileSrc(file)" class="preview-img" preload="metadata" />
              <div class="play-overlay">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="white">
                  <path d="M8 5v14l11-7z" />
                </svg>
              </div>
            </div>
            <div v-else class="preview-placeholder-cell" />
          </template>
        </div>
      </template>
      <div v-else class="preview-placeholder">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <path d="m21 15-5-5L5 21" />
        </svg>
        <span>No preview</span>
      </div>

      <!-- Status badge (hide when ready) -->
      <span v-if="status?.status && status.status !== 'ready'" class="status-badge" :class="statusClass">{{ statusLabel }}</span>

      <!-- Checkbox -->
      <label class="select-check" @click.stop>
        <input
          type="checkbox"
          :checked="selected"
          @change="onToggleSelect"
        />
      </label>

      <!-- File count -->
      <span v-if="files.length" class="file-count">{{ files.length }} file{{ files.length !== 1 ? 's' : '' }}</span>

      <!-- Storyboard thumbnail -->
      <img
        v-if="storyboardThumb"
        class="sb-thumb"
        :src="storyboardThumb"
        alt="Storyboard"
        loading="lazy"
        @click.stop
      />
      <div v-else class="sb-thumb sb-thumb--empty" @click.stop>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <path d="M21 15l-5-5L5 21" />
        </svg>
      </div>
    </div>

    <!-- Header -->
    <div class="card-header">
      <div class="scene-title">
        <span class="scene-number">#{{ sceneIndex }}</span>
        <span class="scene-name">{{ scene.title || `Scene ${sceneIndex + 1}` }}</span>
      </div>
      <div class="card-meta">
        <span class="type-badge" :style="{ background: typeColor + '22', color: typeColor }">
          {{ (scene.type || 'image').toUpperCase() }}
        </span>
        <span v-if="scene.narrative_role" class="role-badge">{{ scene.narrative_role }}</span>
        <span v-if="scene.duration" class="duration">{{ scene.duration }}s</span>
      </div>
    </div>

    <!-- Text content for text_overlay -->
    <div v-if="scene.type === 'text_overlay' && scene.text_content" class="text-content">
      {{ scene.text_content }}
    </div>

    <!-- Prompt -->
    <div class="prompt-section">
      <div v-if="!editing" class="prompt-display">
        <p class="prompt-text">{{ promptText || 'No prompt' }}</p>
        <div class="prompt-actions">
          <button class="btn-icon" title="Edit prompt" @click="startEdit">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
            </svg>
          </button>
          <button class="btn-icon" title="Copy prompt" @click="onCopy">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" />
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
            </svg>
          </button>
        </div>
      </div>
      <div v-else class="prompt-edit">
        <textarea
          v-model="editText"
          class="prompt-textarea"
          rows="3"
        />
        <div class="edit-actions">
          <button class="action-btn accent" @click="saveEdit">Save</button>
          <button class="action-btn" @click="cancelEdit">Cancel</button>
        </div>
      </div>
    </div>

    <!-- Actions -->
    <div class="card-actions">
      <button
        class="btn-action"
        :disabled="!files.length"
        @click="onDownload"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="7,10 12,15 17,10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
        Download{{ files.length ? ` (${files.length})` : '' }}
      </button>
      <button class="btn-icon-action" @click="onOpenFolder" title="Open folder">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
        </svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.asset-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  transition: box-shadow 0.2s, border-color 0.2s;
  display: flex;
  flex-direction: column;
}

.asset-card:hover {
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

.asset-card.selected {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(78, 205, 196, 0.25);
}

/* ---- Preview ---- */
.preview-area {
  position: relative;
  height: 180px;
  background: var(--bg-deeper, #0a0a0a);
  overflow: hidden;
  cursor: pointer;
}

.preview-grid {
  width: 100%;
  height: 100%;
  display: grid;
  gap: 2px;
}

.preview-grid.grid-1 {
  grid-template-columns: 1fr;
}

.preview-grid.grid-2 {
  grid-template-columns: 1fr 1fr;
}

.preview-grid.grid-3 {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
}

.preview-grid.grid-3 > :first-child {
  grid-row: 1 / 3;
}

.preview-grid.grid-4 {
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
}

.preview-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.preview-video-wrap {
  position: relative;
  width: 100%;
  height: 100%;
}

.play-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.3);
  opacity: 0;
  transition: opacity 0.2s;
}

.preview-video-wrap:hover .play-overlay {
  opacity: 1;
}

.preview-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}

.preview-placeholder-cell {
  background: var(--bg-surface);
}

/* ---- Status badge ---- */
.status-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 8px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.status-pending {
  background: rgba(156, 163, 175, 0.2);
  color: #9CA3AF;
}

.status-generating {
  background: rgba(245, 158, 11, 0.2);
  color: #F59E0B;
}

.status-downloading {
  background: rgba(59, 130, 246, 0.2);
  color: #3B82F6;
}

.status-ready {
  background: rgba(34, 197, 94, 0.2);
  color: #22C55E;
}

.status-error {
  background: rgba(239, 68, 68, 0.2);
  color: #EF4444;
}

/* ---- Select checkbox ---- */
.select-check {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 2;
}

.select-check input {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--accent);
}

/* ---- File count ---- */
.file-count {
  position: absolute;
  bottom: 8px;
  right: 8px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  padding: 2px 8px;
  border-radius: 8px;
}

/* ---- Storyboard thumbnail ---- */
.sb-thumb {
  position: absolute;
  bottom: 8px;
  left: 8px;
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: 5px;
  border: 1px solid rgba(255,255,255,0.15);
  opacity: 0.8;
  transition: opacity 0.2s, transform 0.2s;
  z-index: 1;
}
.sb-thumb:hover {
  opacity: 1;
  transform: scale(2.5);
  transform-origin: bottom left;
  border-color: var(--accent);
  box-shadow: 0 4px 16px rgba(0,0,0,0.5);
  z-index: 10;
}
.sb-thumb--empty {
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,0.5);
  color: var(--text-muted);
  opacity: 0.35;
}
.sb-thumb--empty:hover {
  transform: none;
  box-shadow: none;
  opacity: 0.5;
  border-color: rgba(255,255,255,0.15);
}

/* ---- Header ---- */
.card-header {
  padding: 12px 14px 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.scene-title {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.scene-number {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
  color: var(--accent);
  background: rgba(78, 205, 196, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

.scene-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.type-badge {
  font-family: var(--font-mono);
  font-size: 8px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.role-badge {
  font-family: var(--font-mono);
  font-size: 8px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--bg-darkest);
  color: var(--text-muted);
  letter-spacing: 0.03em;
}

.duration {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-secondary);
}

/* ---- Text content ---- */
.text-content {
  padding: 8px 14px 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
  font-style: italic;
  max-height: 40px;
  overflow: hidden;
}

/* ---- Prompt ---- */
.prompt-section {
  padding: 10px 14px;
  flex: 1;
}

.prompt-display {
  display: flex;
  gap: 6px;
}

.prompt-text {
  flex: 1;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  max-height: 54px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  margin: 0;
}

.prompt-actions {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex-shrink: 0;
}

.btn-icon {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: color 0.15s, background 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-icon:hover {
  color: var(--accent);
  background: rgba(78, 205, 196, 0.08);
}

/* ---- Prompt edit ---- */
.prompt-edit {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.prompt-textarea {
  width: 100%;
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--text);
  background: var(--bg-deeper, #0a0a0a);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
  resize: vertical;
  line-height: 1.5;
}

.prompt-textarea:focus {
  outline: none;
  border-color: var(--accent);
}

.edit-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
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
.action-btn.accent {
  border-color: var(--accent);
  color: var(--accent);
}

/* ---- Actions ---- */
.card-actions {
  padding: 0 14px 12px;
  display: flex;
  gap: 8px;
}

.btn-action {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
  background: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 10px;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.btn-action:hover:not(:disabled) {
  color: var(--accent);
  border-color: var(--accent);
}

.btn-action:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-icon-action {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  background: none;
  border: none;
  padding: 6px 10px;
  cursor: pointer;
  transition: color 0.15s;
}

.btn-icon-action:hover {
  color: var(--accent);
}
</style>
