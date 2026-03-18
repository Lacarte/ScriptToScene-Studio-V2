<script setup>
import { ref, computed } from 'vue'
import { useStory } from '../composables/useStory.js'
import { useToast } from '@/shared/composables/useToast.js'

const props = defineProps({
  /** Current pipeline style ID — used as default for story generation */
  pipelineStyle: { type: String, default: 'cinematic' },
  /** Available style templates from pipeline */
  templates: { type: Array, default: () => [] },
})

const emit = defineEmits(['story-generated'])

const toast = useToast()
const story = useStory()

const open = ref(false)
const webhookOpen = ref(false)
const webhookInput = ref('')

// Sync pipeline style into story style on mount
if (props.pipelineStyle) {
  story.storyStyle.value = props.pipelineStyle
}

const categoryLabel = (cat) => {
  return cat.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

const resultStats = computed(() => {
  const r = story.result.value
  if (!r) return null
  return {
    projectId: r.project_id || '',
    wordCount: r.word_count || 0,
    estimatedDuration: r.estimated_duration || 0,
    language: r.language || '',
    category: r.story_category || '',
    style: r.preset_style || '',
    provider: r.provider || '',
    generationTime: r.generation_time || 0,
  }
})

async function handleGenerate() {
  try {
    const data = await story.generateStory(props.pipelineStyle)
    toast.success('Story generated')
    emit('story-generated', data.story_text)
  } catch (e) {
    toast.error(e.message || 'Story generation failed')
  }
}

function useStoryText() {
  const r = story.result.value
  if (!r?.story_text) return
  // Strip section labels for pipeline use
  const plain = r.story_text
    .replace(/^(Hook|Build|Climax|CTA):\s*/gim, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
  emit('story-generated', plain)
  toast.success('Story applied to pipeline')
}

function copyStory() {
  const text = story.result.value?.story_text
  if (!text) return
  navigator.clipboard.writeText(text)
    .then(() => toast.success('Story copied'))
    .catch(() => toast.error('Copy failed'))
}

function openWebhookSettings() {
  webhookInput.value = story.webhookUrl.value || ''
  webhookOpen.value = !webhookOpen.value
}

function saveWebhook() {
  story.saveWebhookUrl(webhookInput.value.trim())
  toast.success('Webhook URL saved')
  webhookOpen.value = false
}

function resetWebhook() {
  story.resetWebhookUrl()
  webhookInput.value = story.webhookUrl.value
  toast.info('Webhook URL reset')
}
</script>

<template>
  <div class="story-gen">
    <!-- Toggle header -->
    <button class="story-toggle" @click="open = !open">
      <div class="story-toggle-left">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
        </svg>
        <span class="story-toggle-label">Story Generator</span>
        <span v-if="story.result.value" class="story-toggle-badge">1 story</span>
      </div>
      <svg
        class="story-chevron"
        :class="{ open }"
        width="12" height="12" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round"
      >
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </button>

    <!-- Collapsible body -->
    <div v-show="open" class="story-body">
      <p class="story-desc">Generate a viral story with AI. The result will be inserted into the text input above.</p>

      <!-- Form grid -->
      <div class="story-form">
        <div class="sf-group">
          <label class="sf-label">Duration (sec)</label>
          <input
            v-model.number="story.storyDuration.value"
            type="number"
            class="sf-input sf-number"
            min="15"
            max="180"
            step="5"
          >
        </div>
        <div class="sf-group">
          <label class="sf-label">Category</label>
          <select v-model="story.storyCategory.value" class="sf-input sf-select">
            <option v-for="cat in story.categories.value" :key="cat" :value="cat">
              {{ categoryLabel(cat) }}
            </option>
          </select>
        </div>
        <div class="sf-group">
          <label class="sf-label">Language</label>
          <select v-model="story.storyLanguage.value" class="sf-input sf-select">
            <option v-for="lang in story.LANGUAGES" :key="lang.id" :value="lang.id">
              {{ lang.label }}
            </option>
          </select>
        </div>
        <div class="sf-group sf-group--action">
          <button
            class="story-gen-btn"
            :disabled="story.isGenerating.value"
            @click="handleGenerate"
          >
            <span v-if="story.isGenerating.value" class="sg-spinner"></span>
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
            </svg>
            {{ story.isGenerating.value ? 'Generating...' : 'Generate Story' }}
          </button>
        </div>
      </div>

      <!-- Webhook settings (compact) -->
      <div class="story-webhook-row">
        <button class="sw-toggle" @click="openWebhookSettings">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
          Webhook
        </button>
        <span v-if="story.webhookUrl.value" class="sw-status sw-status--on">connected</span>
        <span v-else class="sw-status sw-status--off">not configured</span>
      </div>

      <div v-if="webhookOpen" class="story-webhook-config">
        <div class="sw-url-row">
          <input
            type="text"
            v-model="webhookInput"
            class="sw-url-input"
            placeholder="https://your-n8n.app/webhook/story-generator"
          >
          <button class="sw-btn" @click="saveWebhook">Save</button>
          <button class="sw-btn sw-btn--ghost" @click="resetWebhook">Reset</button>
        </div>
      </div>

      <!-- Error -->
      <p v-if="story.error.value" class="story-error">{{ story.error.value }}</p>

      <!-- Result -->
      <div v-if="story.result.value" class="story-result">
        <div class="sr-header">
          <span class="sr-title">Generated Story</span>
          <div class="sr-actions">
            <button class="sr-btn" @click="copyStory">Copy</button>
            <button class="sr-btn sr-btn--accent" @click="useStoryText">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/><path d="M12 5l7 7-7 7"/></svg>
              Use in Pipeline
            </button>
          </div>
        </div>

        <!-- Stats -->
        <div v-if="resultStats" class="sr-stats">
          <span class="sr-stat sr-stat--id">{{ resultStats.projectId }}</span>
          <span class="sr-sep">&middot;</span>
          <span>{{ resultStats.wordCount }} words</span>
          <span class="sr-sep">&middot;</span>
          <span>~{{ resultStats.estimatedDuration }}s</span>
          <span class="sr-sep">&middot;</span>
          <span>{{ resultStats.language }}</span>
          <span class="sr-sep">&middot;</span>
          <span>{{ categoryLabel(resultStats.category) }}</span>
          <span class="sr-sep">&middot;</span>
          <span class="sr-stat--muted">{{ resultStats.generationTime.toFixed(1) }}s gen</span>
        </div>

        <!-- Story sections -->
        <div class="sr-sections">
          <div v-for="(text, key) in story.result.value.sections" :key="key" class="sr-section">
            <span class="sr-section-label">{{ key }}</span>
            <p class="sr-section-text">{{ text }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.story-gen {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-surface);
  overflow: hidden;
}

/* ---- Toggle ---- */
.story-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 12px 16px;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text);
  transition: background 0.15s;
}

.story-toggle:hover {
  background: rgba(255, 255, 255, 0.02);
}

.story-toggle-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.story-toggle-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.story-toggle-badge {
  font-size: 9px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 4px;
  background: rgba(78, 205, 196, 0.12);
  color: var(--accent);
}

.story-chevron {
  transition: transform 0.2s;
  color: var(--text-muted);
}

.story-chevron.open {
  transform: rotate(180deg);
}

/* ---- Body ---- */
.story-body {
  padding: 0 16px 16px;
}

.story-desc {
  font-size: 11px;
  color: var(--text-muted);
  margin: 0 0 12px;
}

/* ---- Form ---- */
.story-form {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.sf-group {
  flex-shrink: 1;
  min-width: 0;
}

.sf-group--action {
  flex-shrink: 0;
  margin-left: auto;
}

.sf-label {
  display: block;
  font-size: 8px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.sf-input {
  background: var(--bg-darkest);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  padding: 6px 10px;
  font-size: 11px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.15s;
}

.sf-input:focus {
  border-color: var(--accent);
}

.sf-number {
  width: 72px;
  font-family: var(--font-mono);
  text-align: center;
}

.sf-select {
  min-width: 110px;
  cursor: pointer;
}

/* ---- Generate Button ---- */
.story-gen-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border-radius: 8px;
  font-size: 11px;
  font-weight: 700;
  font-family: var(--font-mono);
  border: none;
  cursor: pointer;
  color: white;
  background: linear-gradient(135deg, #A78BFA, #7C3AED);
  box-shadow: 0 2px 12px rgba(167, 139, 250, 0.25);
  transition: all 0.2s;
  white-space: nowrap;
}

.story-gen-btn:hover:not(:disabled) {
  box-shadow: 0 4px 16px rgba(167, 139, 250, 0.4);
  transform: translateY(-1px);
}

.story-gen-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

.sg-spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: sg-spin 0.6s linear infinite;
}

@keyframes sg-spin {
  to { transform: rotate(360deg); }
}

/* ---- Webhook ---- */
.story-webhook-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}

.sw-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 10px;
  color: var(--text-muted);
  transition: color 0.15s;
}

.sw-toggle:hover {
  color: var(--text-secondary);
}

.sw-status {
  font-size: 9px;
  font-weight: 600;
  font-family: var(--font-mono);
}

.sw-status--on { color: #26DE81; }
.sw-status--off { color: var(--text-muted); opacity: 0.5; }

.story-webhook-config {
  margin-top: 8px;
}

.sw-url-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.sw-url-input {
  flex: 1;
  padding: 6px 10px;
  font-size: 10px;
  font-family: var(--font-mono);
  color: var(--text);
  background: var(--bg-darkest);
  border: 1px solid var(--border);
  border-radius: 6px;
  outline: none;
  transition: border-color 0.15s;
}

.sw-url-input:focus {
  border-color: var(--accent);
}

.sw-btn {
  padding: 5px 10px;
  font-size: 10px;
  font-weight: 600;
  border-radius: 5px;
  border: 1px solid var(--accent);
  background: rgba(78, 205, 196, 0.1);
  color: var(--accent);
  cursor: pointer;
  white-space: nowrap;
}

.sw-btn--ghost {
  border-color: var(--border);
  background: transparent;
  color: var(--text-muted);
}

/* ---- Error ---- */
.story-error {
  margin-top: 10px;
  font-size: 11px;
  color: #FF6B6B;
  font-family: var(--font-mono);
}

/* ---- Result ---- */
.story-result {
  margin-top: 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-darkest);
  overflow: hidden;
}

.sr-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
}

.sr-title {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
}

.sr-actions {
  display: flex;
  gap: 6px;
}

.sr-btn {
  padding: 3px 8px;
  border-radius: 5px;
  font-size: 9px;
  font-weight: 600;
  font-family: var(--font-mono);
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 0.15s;
}

.sr-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.sr-btn--accent {
  border-color: var(--accent);
  color: var(--accent);
}

.sr-btn--accent:hover {
  background: rgba(78, 205, 196, 0.1);
}

/* Stats */
.sr-stats {
  padding: 8px 14px;
  font-size: 10px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
  font-family: var(--font-mono);
  border-bottom: 1px solid var(--border);
}

.sr-stat--id {
  color: var(--accent);
  font-weight: 600;
}

.sr-sep {
  color: var(--text-muted);
  opacity: 0.4;
}

.sr-stat--muted {
  color: var(--text-muted);
}

/* Sections */
.sr-sections {
  padding: 12px 14px;
}

.sr-section {
  margin-bottom: 10px;
}

.sr-section:last-child {
  margin-bottom: 0;
}

.sr-section-label {
  display: inline-block;
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #A78BFA;
  margin-bottom: 3px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(167, 139, 250, 0.1);
}

.sr-section-text {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.7;
  margin: 0;
  white-space: pre-wrap;
}
</style>
