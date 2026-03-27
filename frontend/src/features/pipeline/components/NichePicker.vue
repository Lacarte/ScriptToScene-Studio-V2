<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  presets: { type: Object, default: () => ({}) },
  selected: { type: String, default: '' },
  templates: { type: Array, default: () => [] },
  currentConfig: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['select', 'save', 'delete'])

const expanded = ref(false)
const showSaveForm = ref(false)
const saveLabel = ref('')
const saveDescription = ref('')
const saving = ref(false)
const confirmDeleteId = ref('')

const presetList = computed(() =>
  Object.entries(props.presets).map(([id, p]) => ({ id, ...p }))
)

const count = computed(() => presetList.value.length)

const saveId = computed(() =>
  saveLabel.value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
)
const saveExists = computed(() => !!props.presets[saveId.value])

const canSave = computed(() => {
  const cfg = props.currentConfig
  return saveId.value.length >= 3 && !saveExists.value && cfg.visual_style && cfg.category && cfg.story_tone
})

function templateColor(visualStyleId) {
  const t = props.templates.find(tp => tp.id === visualStyleId)
  return t?.color || '#888'
}

function pick(preset) {
  emit('select', preset)
}

function clear() {
  emit('select', null)
}

function openSaveForm() {
  saveLabel.value = ''
  saveDescription.value = ''
  showSaveForm.value = true
}

async function saveNiche() {
  if (!canSave.value) return
  saving.value = true
  const cfg = props.currentConfig
  const preset = {
    id: saveId.value,
    label: saveLabel.value.trim(),
    description: saveDescription.value.trim() || '',
    category: cfg.category || 'motivation',
    niche: cfg.niche || cfg.category || saveId.value,
    visual_style: cfg.visual_style || 'cinematic',
    story_tone: cfg.story_tone || 'dramatic',
    voice: cfg.voice || 'af_heart',
    speed: cfg.speed || 1.0,
    tags: cfg.tags || [],
    custom: true,
  }
  emit('save', preset)
  showSaveForm.value = false
  saving.value = false
}

function requestDelete(presetId) {
  confirmDeleteId.value = presetId
}

function confirmDelete() {
  emit('delete', confirmDeleteId.value)
  confirmDeleteId.value = ''
}

function cancelDelete() {
  confirmDeleteId.value = ''
}

const TAG_ICONS = {
  tiktok: 'T',
  youtube: 'Y',
  shorts: 'S',
  trending: '\u2191',
}
</script>

<template>
  <div class="niche-picker" :class="{ 'is-expanded': expanded }">
    <div class="niche-header">
      <button type="button" class="niche-header-main" @click="expanded = !expanded">
        <span class="niche-header-left">
          <svg class="niche-chevron" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
          <span class="niche-title">Niche Presets</span>
          <span class="niche-count">{{ count }}</span>
        </span>
      </button>
      <span class="niche-header-right">
        <button
          v-if="expanded"
          type="button"
          class="niche-save-btn"
          @click.stop="openSaveForm"
          title="Save current config as niche"
        >+ Save as Niche</button>
        <button
          v-if="selected"
          type="button"
          class="niche-clear-btn"
          @click.stop="clear"
        >Clear</button>
        <span v-if="selected" class="niche-active-dot"></span>
        <span v-if="selected" class="niche-active-label">{{ presets[selected]?.label || selected }}</span>
      </span>
    </div>

    <!-- Save Form -->
    <div v-if="showSaveForm && expanded" class="save-form">
      <div class="save-form-row">
        <input
          v-model="saveLabel"
          class="save-input"
          placeholder="Niche name (e.g. Stickman Horror)"
          maxlength="60"
          @keydown.enter="saveNiche"
          @keydown.escape="showSaveForm = false"
        />
      </div>
      <div class="save-form-row">
        <input
          v-model="saveDescription"
          class="save-input"
          placeholder="Short description (optional)"
          maxlength="120"
          @keydown.enter="saveNiche"
          @keydown.escape="showSaveForm = false"
        />
      </div>
      <div class="save-form-row save-form-actions">
        <span class="save-id-preview" v-if="saveId">ID: {{ saveId }}</span>
        <span v-if="saveExists" class="save-id-error">Already exists</span>
        <span class="save-form-spacer"></span>
        <button type="button" class="save-cancel-btn" @click="showSaveForm = false">Cancel</button>
        <button
          type="button"
          class="save-confirm-btn"
          :disabled="!canSave"
          @click="saveNiche"
        >Save</button>
      </div>
    </div>

    <!-- Delete Confirmation -->
    <div v-if="confirmDeleteId && expanded" class="delete-confirm">
      <span class="delete-confirm-text">Delete "{{ presets[confirmDeleteId]?.label || confirmDeleteId }}"?</span>
      <button type="button" class="delete-yes-btn" @click="confirmDelete">Delete</button>
      <button type="button" class="delete-no-btn" @click="cancelDelete">Cancel</button>
    </div>

    <div v-show="expanded" class="niche-grid">
      <button
        type="button"
        v-for="p in presetList"
        :key="p.id"
        class="niche-card"
        :class="{ 'is-selected': p.id === selected }"
        :style="{
          '--card-accent': templateColor(p.visual_style),
          borderColor: p.id === selected ? templateColor(p.visual_style) : undefined,
          boxShadow: p.id === selected ? '0 0 16px ' + templateColor(p.visual_style) + '20' : undefined,
        }"
        @click="pick(p)"
      >
        <span class="card-accent-bar" :style="{ background: templateColor(p.visual_style) }"></span>
        <div class="card-body">
          <div class="card-top">
            <span class="card-label">{{ p.label }}</span>
            <span
              v-if="p.description"
              class="card-info"
              @click.stop
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
              <span class="card-tooltip">{{ p.description }}</span>
            </span>
            <span
              v-if="p.custom"
              class="card-delete"
              title="Delete niche"
              @click.stop="requestDelete(p.id)"
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </span>
          </div>
          <div class="card-bottom">
            <span class="card-niche">{{ p.category || p.niche }}</span>
            <span class="card-tags">
              <span
                v-for="tag in (p.tags || [])"
                :key="tag"
                class="card-tag"
                :class="'tag--' + tag"
              >{{ TAG_ICONS[tag] || tag }}</span>
            </span>
          </div>
        </div>
      </button>
    </div>
  </div>
</template>

<style scoped>
.niche-picker {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--card-bg);
  overflow: hidden;
}

.niche-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
}

.niche-header-main {
  display: flex;
  align-items: center;
  min-width: 0;
  padding: 0;
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.15s;
}

.niche-header-main:hover {
  color: var(--text);
}

.niche-header-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.niche-chevron {
  transition: transform 0.2s;
  flex-shrink: 0;
}

.is-expanded .niche-chevron {
  transform: rotate(0);
}

.niche-picker:not(.is-expanded) .niche-chevron {
  transform: rotate(-90deg);
}

.niche-title {
  font: 600 11px/1 var(--font-mono, monospace);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.niche-count {
  font: 500 10px/1 var(--font-mono, monospace);
  color: var(--text-muted);
  background: rgba(255,255,255,0.06);
  padding: 2px 5px;
  border-radius: 4px;
}

.niche-header-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.niche-active-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
}

.niche-active-label {
  font: 500 10px/1 var(--font-mono, monospace);
  color: var(--accent);
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.niche-clear-btn {
  font: 600 9px/1 var(--font-mono, monospace);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-muted);
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 4px;
  padding: 3px 7px;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.niche-clear-btn:hover {
  color: #FF9C9C;
  border-color: rgba(255, 107, 107, 0.3);
}

.niche-save-btn {
  font: 600 9px/1 var(--font-mono, monospace);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--accent);
  background: rgba(78, 205, 196, 0.08);
  border: 1px solid rgba(78, 205, 196, 0.2);
  border-radius: 4px;
  padding: 3px 7px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.niche-save-btn:hover {
  background: rgba(78, 205, 196, 0.15);
  border-color: rgba(78, 205, 196, 0.4);
}

/* ── Save Form ── */
.save-form {
  padding: 8px 10px;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  background: rgba(78, 205, 196, 0.03);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.save-form-row {
  display: flex;
  gap: 6px;
}

.save-input {
  flex: 1;
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 5px 8px;
  font: 400 11px/1.3 var(--font-mono, monospace);
  color: var(--text);
  outline: none;
  transition: border-color 0.15s;
}

.save-input:focus {
  border-color: var(--accent);
}

.save-input::placeholder {
  color: var(--text-muted);
  opacity: 0.5;
}

.save-form-actions {
  align-items: center;
}

.save-id-preview {
  font: 400 9px/1 var(--font-mono, monospace);
  color: var(--text-muted);
  opacity: 0.6;
}

.save-form-spacer {
  flex: 1;
}

.save-id-error {
  font: 600 10px/1 var(--font-mono, monospace);
  color: #FF8F8F;
}

.save-cancel-btn {
  font: 600 9px/1 var(--font-mono, monospace);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-muted);
  background: none;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 4px;
  padding: 4px 8px;
  cursor: pointer;
}

.save-cancel-btn:hover {
  color: var(--text);
}

.save-confirm-btn {
  font: 600 9px/1 var(--font-mono, monospace);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: #0d1117;
  background: var(--accent);
  border: none;
  border-radius: 4px;
  padding: 4px 10px;
  cursor: pointer;
  transition: opacity 0.15s;
}

.save-confirm-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.save-confirm-btn:not(:disabled):hover {
  opacity: 0.85;
}

/* ── Delete Confirm ── */
.delete-confirm {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  background: rgba(255, 107, 107, 0.05);
}

.delete-confirm-text {
  font: 500 10px/1.3 var(--font-mono, monospace);
  color: #FF9C9C;
  flex: 1;
}

.delete-yes-btn {
  font: 600 9px/1 var(--font-mono, monospace);
  text-transform: uppercase;
  color: #fff;
  background: #DC2626;
  border: none;
  border-radius: 4px;
  padding: 4px 8px;
  cursor: pointer;
}

.delete-yes-btn:hover {
  background: #EF4444;
}

.delete-no-btn {
  font: 600 9px/1 var(--font-mono, monospace);
  text-transform: uppercase;
  color: var(--text-muted);
  background: none;
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 4px;
  padding: 4px 8px;
  cursor: pointer;
}

/* ── Grid ── */
.niche-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  padding: 8px 10px 10px;
}

@media (max-width: 640px) {
  .niche-grid { grid-template-columns: repeat(2, 1fr); }
}

/* ── Card ── */
.niche-card {
  display: flex;
  overflow: hidden;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255,255,255,0.02);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.2s, background 0.2s, box-shadow 0.2s, transform 0.15s;
  padding: 0;
}

.niche-card:hover {
  background: rgba(255,255,255,0.05);
  border-color: var(--card-accent, rgba(255,255,255,0.12));
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}

.niche-card.is-selected {
  background: color-mix(in srgb, var(--card-accent, var(--accent)) 8%, transparent);
}

.card-accent-bar {
  width: 3px;
  flex-shrink: 0;
  border-radius: 3px 0 0 3px;
  transition: width 0.15s;
}

.niche-card:hover .card-accent-bar,
.niche-card.is-selected .card-accent-bar {
  width: 4px;
}

.card-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  flex: 1;
  min-width: 0;
}

.card-top {
  display: flex;
  align-items: center;
  gap: 6px;
}

.card-label {
  font: 600 11px/1.3 var(--font-mono, monospace);
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
  transition: color 0.15s;
}

.niche-card.is-selected .card-label {
  color: var(--card-accent, var(--accent));
}

.card-info {
  position: relative;
  flex-shrink: 0;
  color: var(--text-muted);
  opacity: 0.4;
  cursor: help;
  transition: opacity 0.15s, color 0.15s;
  display: flex;
  align-items: center;
}

.card-info:hover {
  opacity: 1;
  color: var(--accent);
}

.card-tooltip {
  display: none;
  position: absolute;
  bottom: calc(100% + 8px);
  right: -8px;
  width: 220px;
  padding: 8px 10px;
  border-radius: 6px;
  background: #1a1f2e;
  border: 1px solid rgba(78, 205, 196, 0.2);
  box-shadow: 0 8px 24px rgba(0,0,0,0.5);
  font: 400 10px/1.5 system-ui, sans-serif;
  color: var(--text);
  white-space: normal;
  z-index: 50;
  pointer-events: none;
}

.card-tooltip::after {
  content: '';
  position: absolute;
  top: 100%;
  right: 12px;
  border: 5px solid transparent;
  border-top-color: #1a1f2e;
}

.card-info:hover .card-tooltip {
  display: block;
}

.card-delete {
  flex-shrink: 0;
  color: var(--text-muted);
  opacity: 0;
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 2px;
  border-radius: 3px;
  transition: opacity 0.15s, color 0.15s, background 0.15s;
}

.niche-card:hover .card-delete {
  opacity: 0.3;
}

.card-delete:hover {
  opacity: 1 !important;
  color: #FF6B6B;
  background: rgba(255, 107, 107, 0.1);
}

.card-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.card-niche {
  font: 500 9px/1 system-ui, sans-serif;
  color: var(--text-muted);
  letter-spacing: 0.02em;
}

.card-tags {
  display: flex;
  gap: 3px;
  flex-shrink: 0;
}

.card-tag {
  font: 700 8px/1 var(--font-mono, monospace);
  padding: 2px 4px;
  border-radius: 3px;
  background: rgba(255,255,255,0.06);
  color: var(--text-muted);
  letter-spacing: 0.02em;
}

.tag--trending {
  color: #FFD93D;
  background: rgba(255, 217, 61, 0.1);
}

.tag--tiktok {
  color: #E879F9;
  background: rgba(232, 121, 249, 0.1);
}

.tag--youtube {
  color: #FF6B6B;
  background: rgba(255, 107, 107, 0.1);
}

.tag--shorts {
  color: #38BDF8;
  background: rgba(56, 189, 248, 0.1);
}
</style>
