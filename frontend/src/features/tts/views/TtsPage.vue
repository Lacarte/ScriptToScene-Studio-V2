<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useTts, VOICE_META, LANG_NAMES, LANG_ORDER } from '../composables/useTts.js'
import { useToast } from '@/shared/composables/useToast.js'
import { lastPickedStory } from '@/shared/composables/useRandomStory.js'
import { STYLE_NAMES } from '@/shared/data/styleNames.js'
import VoiceSelector from '../components/VoiceSelector.vue'
import NowPlaying from '../components/NowPlaying.vue'
import HistoryCard from '../components/HistoryCard.vue'

defineOptions({ name: 'TtsPage' })

const tts = useTts()
const toast = useToast()

const voiceSectionOpen = ref(false)

// ── Voice Section Toggle ──

function toggleVoiceSection() {
  voiceSectionOpen.value = !voiceSectionOpen.value
}

// ── Text Input ──

function onPromptInput(e) {
  tts.setPrompt(e.target.value)
}

async function handleNormalize() {
  try {
    const result = await tts.normalize()
    if (result) toast.success('Text normalized for TTS')
  } catch {
    toast.error('Normalization failed')
  }
}

function handleCopy() {
  tts.copyPromptPlain()
    .then(() => toast.success('Plain text copied'))
    .catch(() => toast.error('Copy failed'))
}

function handleRandom() {
  tts.randomStory()
  toast.info('Random story loaded')
}

// ── Speed ──

function onSpeedInput(e) {
  const val = parseFloat(e.target.value)
  if (!isNaN(val) && val >= 0.5 && val <= 2.0) {
    tts.setSpeed(val)
  }
}

// ── Voice Selection ──

function onVoiceSelect(v) {
  tts.selectVoice(v)
}

function onLangSelect(lang) {
  tts.selectLang(lang)
}

function onBlendPreset(idx) {
  const label = tts.applyBlendPreset(idx)
  if (label) toast.info(label)
}

function onRandomBlend() {
  const label = tts.randomBlend()
  if (label) toast.info(label)
}

// ── Generate ──

async function handleGenerate() {
  try {
    await tts.handleAction()
  } catch (e) {
    toast.error(e.message || 'Generation failed')
  }
}

async function handleAbort() {
  await tts.abort()
  toast.info('Generation aborted')
}

async function handleDownloadModel() {
  try {
    await tts.downloadModel()
    toast.success('Model downloaded and ready')
  } catch (e) {
    toast.error(`Download failed: ${e.message}`)
  }
}

// ── Multi-Voice ──

function handleAutoDetect() {
  try {
    const count = tts.autoDetectRoles()
    toast.info(`Split into ${count} segments`)
  } catch (e) {
    toast.error(e.message)
  }
}

function handleAddSegment() {
  tts.addMvSegment()
}

// ── History ──

function handlePlayHistory(item) {
  const meta = { ...item, voiceName: (VOICE_META[item.voice] || {}).name || item.voice }
  tts.playAudio(meta)
}

async function handleOpenFolder(item) {
  try {
    await fetch('/api/tts/open-generation-folder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: item.filename }),
    })
  } catch { /* ignore */ }
}

async function handleDeleteItem(item) {
  try {
    await tts.deleteItem(item.filename)
    toast.success('Moved to trash')
  } catch {
    toast.error('Delete failed')
  }
}

async function handleDeleteAll() {
  if (tts.isGenerating.value) {
    toast.error('Wait for generation to finish')
    return
  }
  try {
    const count = await tts.deleteAll()
    toast.success(`Moved ${count} items to trash`)
  } catch {
    toast.error('Delete failed')
  }
}

// ── Now Playing metadata with voiceName ──

const nowPlayingMeta = computed(() => {
  const np = tts.nowPlaying.value
  if (!np) return null
  return {
    ...np,
    voiceName: (VOICE_META[np.voice] || {}).name || np.voice,
  }
})

// ── Keyboard Shortcut ──

function onKeydown(e) {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    e.preventDefault()
    handleGenerate()
  }
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
})

// ── Multi-voice voice options (grouped by language) ──

const mvVoiceOptions = computed(() => {
  const groups = []
  for (const lang of LANG_ORDER) {
    const langVoices = (tts.voices.value.length ? tts.voices.value : Object.keys(VOICE_META))
      .filter(v => (VOICE_META[v] || {}).lang === lang)
    if (!langVoices.length) continue
    groups.push({
      label: LANG_NAMES[lang] || lang,
      voices: langVoices.map(v => ({
        id: v,
        name: `${(VOICE_META[v] || {}).name || v} (${(VOICE_META[v] || {}).g === 'f' ? 'F' : 'M'})`,
      })),
    })
  }
  return groups
})

// ── Gen button label ──

const genButtonLabel = computed(() => {
  if (tts.isGenerating.value) return 'Processing...'
  return tts.genMode.value === 'generate' ? 'Generate' : 'Listen'
})
</script>

<template>
  <div class="tts-page">
    <div class="page-header">
      <div>
        <div class="title-row">
          <h2 class="page-title">Text to Speech</h2>
        </div>
        <p class="page-subtitle">Kokoro TTS with 50+ voices and voice blending</p>
      </div>
      <div class="model-status">
        <span v-if="tts.modelReady.value" class="status-text status-text--ready">Model ready</span>
        <template v-else>
          <span v-if="tts.progressText.value" class="status-text status-text--downloading">{{ tts.progressText.value }}</span>
          <button v-else class="download-model-btn" @click="handleDownloadModel">
            <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Download Model
          </button>
        </template>
      </div>
    </div>

    <section class="card legacy-card">
      <button class="section-toggle" @click="toggleVoiceSection">
        <label class="section-label">{{ tts.voiceSummaryLabel.value }}</label>
        <div class="section-toggle-summary">
          <span class="section-summary">{{ tts.voiceSummary.value }}</span>
          <svg
            class="toggle-chevron"
            :class="{ open: voiceSectionOpen }"
            width="14"
            height="14"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            viewBox="0 0 24 24"
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </div>
      </button>

      <div v-show="voiceSectionOpen" class="voice-grid">
        <VoiceSelector
          :voices="tts.voices.value"
          :selected-voice="tts.selectedVoice.value"
          :selected-lang="tts.selectedLang.value"
          :blend-mode="tts.blendMode.value"
          :blend-voice-a="tts.blendVoiceA.value"
          :blend-voice-b="tts.blendVoiceB.value"
          :blend-ratio="tts.blendRatio.value"
          :blend-method="tts.blendMethod.value"
          @select="onVoiceSelect"
          @select-lang="onLangSelect"
          @update:blend-mode="tts.setBlendMode"
          @update:blend-voice-a="tts.setBlendVoiceA"
          @update:blend-voice-b="tts.setBlendVoiceB"
          @update:blend-ratio="tts.setBlendRatio"
          @update:blend-method="tts.setBlendMethod"
          @apply-preset="onBlendPreset"
          @random-blend="onRandomBlend"
        />
      </div>
    </section>

    <section class="card legacy-card">
      <div class="inline-header">
        <label class="section-label">Voice Mode</label>
        <div class="pill-toggle">
          <button
            class="pill-btn"
            :class="{ active: !tts.multiVoiceMode.value }"
            @click="tts.setVoiceMode('single')"
          >Single Voice</button>
          <button
            class="pill-btn"
            :class="{ active: tts.multiVoiceMode.value }"
            @click="tts.setVoiceMode('multi')"
          >Multi-Voice</button>
        </div>
      </div>

      <div v-if="tts.multiVoiceMode.value" class="mv-panel">
        <div class="inline-header inline-header--tight">
          <span class="section-label section-label--compact">Segments</span>
          <div class="inline-actions">
            <button class="action-btn compact-btn hover-accent" @click="handleAutoDetect">Auto-detect</button>
            <button class="action-btn compact-btn hover-accent" @click="handleAddSegment">+ Add</button>
          </div>
        </div>

        <div class="mv-segments">
          <p v-if="!tts.mvSegments.value.length" class="mv-empty">
            No segments. Click "Auto-detect" to split your prompt, or "+ Add" to add manually.
          </p>
          <div
            v-for="(seg, i) in tts.mvSegments.value"
            :key="i"
            class="mv-segment"
          >
            <span class="mv-index">{{ i + 1 }}</span>
            <div class="mv-segment-body">
              <textarea
                rows="2"
                class="input-field mv-textarea"
                :value="seg.text"
                @change="tts.updateMvSegment(i, 'text', $event.target.value)"
              ></textarea>
              <div class="mv-segment-controls">
                <select
                  class="mv-select"
                  :value="seg.role"
                  @change="tts.updateMvSegment(i, 'role', $event.target.value)"
                >
                  <option value="narrator">Narrator</option>
                  <option value="dialogue">Dialogue</option>
                  <option value="character">Character</option>
                </select>
                <select
                  class="mv-select mv-voice-select"
                  :value="seg.voice"
                  @change="tts.updateMvSegment(i, 'voice', $event.target.value)"
                >
                  <optgroup
                    v-for="group in mvVoiceOptions"
                    :key="group.label"
                    :label="group.label"
                  >
                    <option
                      v-for="v in group.voices"
                      :key="v.id"
                      :value="v.id"
                    >{{ v.name }}</option>
                  </optgroup>
                </select>
                <span
                  class="mv-voice-dot"
                  :style="{ background: (VOICE_META[seg.voice] || {}).hue || 'var(--text-muted)' }"
                  :title="(VOICE_META[seg.voice] || {}).name || seg.voice"
                ></span>
              </div>
            </div>
            <button class="mv-remove" @click="tts.removeMvSegment(i)" title="Remove">
              <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </section>

    <section class="card legacy-card">
      <label class="section-label section-label--spaced">Prompt</label>
      <textarea
        class="input-field prompt-textarea"
        rows="4"
        placeholder="Type or paste something to speak aloud..."
        :value="tts.prompt.value"
        @input="onPromptInput"
      ></textarea>
      <div class="prompt-footer">
        <div class="prompt-actions">
          <p class="meta-text">{{ tts.wordCount.value }} words ~ {{ tts.tokenCount.value }} tokens</p>
          <button class="action-btn compact-btn hover-accent" @click="handleNormalize">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" style="vertical-align:-1px"><path d="M4 7h16M4 12h10M4 17h14"/></svg>
            Format
          </button>
          <button class="action-btn compact-btn hover-accent" @click="handleCopy">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-1px"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
            Copy
          </button>
          <button class="action-btn compact-btn hover-accent" @click="handleRandom">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="vertical-align:-1px"><rect x="2" y="2" width="20" height="20" rx="3"/><circle cx="8" cy="8" r="1.5" fill="currentColor"/><circle cx="16" cy="16" r="1.5" fill="currentColor"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/></svg>
            Random
          </button>
          <span v-if="lastPickedStory?.type" class="story-type-badge">{{ lastPickedStory.type }}</span>
        </div>
        <div v-if="lastPickedStory?.styles?.length" class="story-recommended-styles">
          <span class="rec-label">Recommended:</span>
          <span v-for="sid in lastPickedStory.styles" :key="sid" class="rec-style-tag">{{ STYLE_NAMES[sid] || sid }}</span>
        </div>
        <div class="shortcut-hint">
          <kbd>Ctrl</kbd>
          <span>+</span>
          <kbd>Enter</kbd>
        </div>
      </div>
    </section>

    <section class="card legacy-card">
      <div class="controls-row">
        <div class="speed-group">
          <label class="section-label section-label--inline" for="tts-speed">Speed</label>
          <input
            id="tts-speed"
            type="number"
            class="speed-input"
            min="0.5"
            max="2.0"
            step="0.1"
            :value="tts.speed.value"
            @input="onSpeedInput"
          />
        </div>
        <div class="pill-toggle pill-toggle--right">
          <button
            class="pill-btn"
            :class="{ active: tts.genMode.value === 'generate' }"
            @click="tts.setGenMode('generate')"
          >Generate</button>
          <button
            class="pill-btn"
            :class="{ active: tts.genMode.value === 'listen' }"
            @click="tts.setGenMode('listen')"
          >Listen</button>
        </div>
      </div>
    </section>

    <div class="generate-row">
      <button
        class="gen-btn generate-btn"
        :disabled="tts.isGenerating.value"
        @click="handleGenerate"
      >
        <span v-if="tts.isGenerating.value" class="spinner-ring"></span>
        <span>{{ genButtonLabel }}</span>
      </button>
      <button
        v-if="tts.isGenerating.value"
        class="abort-btn"
        @click="handleAbort"
      >Abort</button>
    </div>

    <div v-if="tts.progressText.value" class="progress-text">
      {{ tts.progressText.value }}
    </div>

    <NowPlaying
      :metadata="nowPlayingMeta"
      :audio-src="tts.audioSrc.value"
      @ended="() => {}"
    />

    <section class="history-section">
      <div class="history-header">
        <h3 class="history-title">History</h3>
        <div class="history-tools">
          <span class="meta-text">{{ tts.history.value.length }} files</span>
          <button
            class="action-btn compact-btn hover-coral-border"
            :disabled="!tts.history.value.length"
            @click="handleDeleteAll"
          >Delete All</button>
        </div>
      </div>
      <div class="history-list">
        <p v-if="!tts.history.value.length" class="empty-history">No generations yet</p>
        <HistoryCard
          v-for="(item, i) in tts.history.value"
          :key="item.filename || i"
          :item="item"
          @play="handlePlayHistory"
          @open-folder="handleOpenFolder"
          @delete="handleDeleteItem"
        />
      </div>
    </section>
  </div>
</template>

<style scoped>
.tts-page {
  max-width: 780px;
  margin: 0 auto;
  padding: 32px 24px 40px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.page-title {
  letter-spacing: -0.02em;
}

.model-status {
  padding-top: 6px;
  font-size: 11px;
  font-family: "JetBrains Mono", monospace;
  white-space: nowrap;
}

.status-text--ready {
  color: var(--accent);
}

.status-text--not-ready {
  color: var(--coral);
}

.status-text--downloading {
  color: var(--accent);
  animation: pulse-text 1.5s ease-in-out infinite;
}

@keyframes pulse-text {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.download-model-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  font-size: 11px;
  font-weight: 600;
  font-family: var(--font-mono);
  color: var(--accent);
  background: rgba(78, 205, 196, 0.1);
  border: 1px solid rgba(78, 205, 196, 0.3);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.download-model-btn:hover {
  background: rgba(78, 205, 196, 0.2);
  border-color: var(--accent);
}

.legacy-card {
  padding: 20px;
  margin-bottom: 16px;
}

.section-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  padding: 0;
  border: none;
  background: none;
  color: inherit;
  text-align: left;
  cursor: pointer;
  font: inherit;
}

.section-toggle-summary {
  display: flex;
  align-items: center;
  gap: 6px;
}

.section-label--spaced {
  margin-bottom: 10px;
}

.section-label--compact {
  font-size: 9px;
  letter-spacing: 0.12em;
}

.section-label--inline {
  margin: 0;
}

.section-summary {
  font-size: 11px;
  color: var(--text-secondary);
}

.toggle-chevron {
  color: var(--text-muted);
  transition: transform 0.2s;
}

.toggle-chevron.open {
  transform: rotate(180deg);
}

.voice-grid {
  margin-top: 10px;
}

.inline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.inline-header--tight {
  margin-bottom: 8px;
}

.inline-actions {
  display: flex;
  gap: 4px;
}

.pill-toggle {
  display: flex;
  gap: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}

.pill-toggle--right {
  margin-left: auto;
}

.pill-btn {
  padding: 6px 12px;
  border: none;
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.15s;
}

.pill-btn + .pill-btn {
  border-left: 1px solid var(--border);
}

.pill-btn.active {
  background: rgba(78, 205, 196, 0.08);
  color: var(--accent);
}

.mv-panel {
  margin-top: 12px;
}

.mv-segments {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.mv-empty {
  margin: 0;
  padding: 12px 0;
  font-size: 10px;
  color: var(--text-muted);
  text-align: center;
}

.mv-segment {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-darkest);
}

.mv-index {
  min-width: 16px;
  padding-top: 6px;
  font-size: 10px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.mv-segment-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mv-textarea {
  width: 100%;
  padding: 6px 8px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text);
  resize: vertical;
  box-sizing: border-box;
}

.mv-segment-controls {
  display: flex;
  align-items: center;
  gap: 4px;
}

.mv-select {
  padding: 2px 6px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg-darkest);
  color: var(--text-muted);
  font-size: 10px;
  font-family: inherit;
}

.mv-voice-select {
  flex: 1;
  color: var(--text);
}

.mv-voice-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.mv-remove {
  padding: 4px;
  border: none;
  background: none;
  color: var(--text-muted);
  cursor: pointer;
}

.mv-remove:hover {
  color: var(--coral);
}

.prompt-textarea {
  width: 100%;
  min-height: 120px;
  padding: 12px 14px;
  box-sizing: border-box;
  font-size: 13px;
  line-height: 1.7;
  font-family: inherit;
  resize: none;
}

.prompt-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.prompt-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.meta-text {
  margin: 0;
  font-size: 12px;
  color: var(--text-muted);
  font-family: "JetBrains Mono", monospace;
}

.compact-btn {
  padding: 2px 8px;
  border-radius: 5px;
  font-size: 9px;
}

.shortcut-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--text-muted);
}

.shortcut-hint span {
  font-size: 9px;
}

.shortcut-hint kbd {
  padding: 2px 5px;
  border: 1px solid var(--border);
  border-radius: 3px;
  font-size: 9px;
  font-family: "JetBrains Mono", monospace;
  font-weight: 500;
}

.controls-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.speed-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.speed-input {
  width: 60px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-darkest);
  color: var(--text);
  font-size: 12px;
  font-family: "JetBrains Mono", monospace;
  text-align: center;
}

.speed-input:focus {
  outline: none;
  border-color: var(--accent);
}

.generate-row {
  display: flex;
  gap: 8px;
  margin-bottom: 4px;
}

.generate-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 24px;
  border: none;
  border-radius: 12px;
  color: white;
  font-size: 14px;
  font-weight: 700;
  font-family: "JetBrains Mono", "Fira Code", monospace;
  letter-spacing: 0.02em;
  overflow: hidden;
}

.spinner-ring {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

.abort-btn {
  padding: 14px 16px;
  border: 1.5px solid rgba(255, 107, 107, 0.3);
  border-radius: 12px;
  background: rgba(255, 107, 107, 0.15);
  color: var(--coral);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
}

.progress-text {
  margin: 6px 0 12px;
  font-size: 11px;
  color: var(--text-secondary);
  font-family: "JetBrains Mono", monospace;
}

.history-section {
  margin-top: 16px;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.history-title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  font-family: var(--font-display);
  color: var(--text);
}

.history-tools {
  display: flex;
  align-items: center;
  gap: 8px;
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 400px;
  overflow-y: auto;
}

.empty-history {
  margin: 0;
  padding: 24px 0;
  text-align: center;
  font-size: 11px;
  color: var(--text-muted);
}

@media (max-width: 720px) {
  .tts-page {
    padding: 24px 16px 32px;
  }

  .page-header {
    flex-direction: column;
  }

  .inline-header,
  .controls-row,
  .history-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .pill-toggle--right {
    margin-left: 0;
  }

  .generate-row {
    flex-direction: column;
  }

  .history-tools,
  .prompt-actions {
    width: 100%;
  }
}

.story-type-badge {
  font-size: 9px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(167, 139, 250, 0.12);
  color: var(--accent-secondary, #A78BFA);
  white-space: nowrap;
}

.story-recommended-styles {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 4px;
  flex-wrap: wrap;
}

.rec-label {
  font-size: 9px;
  color: var(--text-muted);
  font-weight: 600;
}

.rec-style-tag {
  font-size: 9px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-secondary);
}
</style>
