<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useTts, VOICE_META, LANG_NAMES, LANG_ORDER } from '../composables/useTts.js'
import { useToast } from '@/shared/composables/useToast.js'
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
    <!-- Header -->
    <section class="header-section">
      <h2 class="page-title">Text to Speech</h2>
      <p class="page-subtitle">Kokoro TTS with 50+ voices and voice blending</p>
      <div class="model-status">
        <span v-if="tts.modelReady.value" class="status-badge ready">Model ready</span>
        <span v-else class="status-badge not-ready">Model not downloaded</span>
      </div>
    </section>

    <!-- Voice Selection -->
    <section class="card">
      <button class="voice-header" @click="toggleVoiceSection">
        <div class="voice-header-left">
          <span class="card-label">{{ tts.voiceSummaryLabel.value }}</span>
          <span class="voice-summary">{{ tts.voiceSummary.value }}</span>
        </div>
        <svg
          class="chevron"
          :class="{ open: voiceSectionOpen }"
          width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" viewBox="0 0 24 24"
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
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

    <!-- Voice Mode (Single / Multi) -->
    <section class="card">
      <div class="voice-mode-toggle">
        <span class="card-label">Voice Mode</span>
        <div class="mode-btns">
          <button
            class="mode-btn"
            :class="{ active: !tts.multiVoiceMode.value }"
            @click="tts.setVoiceMode('single')"
          >Single</button>
          <button
            class="mode-btn"
            :class="{ active: tts.multiVoiceMode.value }"
            @click="tts.setVoiceMode('multi')"
          >Multi</button>
        </div>
      </div>

      <!-- Multi-voice panel -->
      <div v-if="tts.multiVoiceMode.value" class="mv-panel">
        <div class="mv-actions">
          <button class="action-btn" @click="handleAutoDetect">Auto-detect</button>
          <button class="action-btn" @click="handleAddSegment">+ Add</button>
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
                class="mv-textarea"
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

    <!-- Text Input -->
    <section class="card">
      <div class="prompt-header">
        <span class="card-label">Text</span>
        <span class="text-count">{{ tts.wordCount.value }} words ~ {{ tts.tokenCount.value }} tokens</span>
      </div>
      <textarea
        class="prompt-textarea"
        rows="6"
        placeholder="Enter text to generate speech..."
        :value="tts.prompt.value"
        @input="onPromptInput"
      ></textarea>
      <div class="prompt-actions">
        <button class="action-btn" @click="handleNormalize">Format</button>
        <button class="action-btn" @click="handleCopy">Copy</button>
        <button class="action-btn" @click="handleRandom">Random</button>
        <span class="ctrl-hint">Ctrl+Enter to generate</span>
      </div>
    </section>

    <!-- Controls -->
    <section class="card controls-row">
      <div class="speed-control">
        <label class="card-label" for="tts-speed">Speed</label>
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
      <div class="gen-mode-toggle">
        <button
          class="mode-btn"
          :class="{ active: tts.genMode.value === 'generate' }"
          @click="tts.setGenMode('generate')"
        >Generate</button>
        <button
          class="mode-btn"
          :class="{ active: tts.genMode.value === 'listen' }"
          @click="tts.setGenMode('listen')"
        >Listen</button>
      </div>
    </section>

    <!-- Generate Button -->
    <div class="gen-row">
      <button
        class="gen-btn"
        :disabled="tts.isGenerating.value"
        @click="handleGenerate"
      >
        <svg
          v-if="tts.isGenerating.value"
          class="spinner"
          width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
        >
          <path d="M12 2a10 10 0 1 0 10 10" />
        </svg>
        <span>{{ genButtonLabel }}</span>
      </button>
      <button
        v-if="tts.isGenerating.value"
        class="abort-btn"
        @click="handleAbort"
      >
        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <rect x="3" y="3" width="18" height="18" rx="2" />
        </svg>
        Abort
      </button>
    </div>

    <!-- Progress -->
    <div v-if="tts.progressText.value" class="progress-text">
      {{ tts.progressText.value }}
    </div>

    <!-- Now Playing -->
    <NowPlaying
      :metadata="nowPlayingMeta"
      :audio-src="tts.audioSrc.value"
      @ended="() => {}"
    />

    <!-- History -->
    <section class="card" v-if="tts.history.value.length > 0">
      <div class="history-header">
        <div class="history-left">
          <span class="card-label">History</span>
          <span class="history-count">{{ tts.history.value.length }} files</span>
        </div>
        <button class="action-btn danger" @click="handleDeleteAll">Delete All</button>
      </div>
      <div class="history-list">
        <HistoryCard
          v-for="(item, i) in tts.history.value"
          :key="item.filename || i"
          :item="item"
          @play="handlePlayHistory"
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
  padding: 24px 32px 48px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Header */
.header-section {
  margin-bottom: 4px;
}

.page-title {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 700;
  margin-bottom: 4px;
}

.page-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.model-status {
  display: flex;
  align-items: center;
}

.status-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 10px;
}

.status-badge.ready {
  background: rgba(78, 205, 196, 0.12);
  color: var(--accent);
}

.status-badge.not-ready {
  background: rgba(239, 68, 68, 0.12);
  color: var(--coral);
}

/* Card */
.card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}

.card-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--text-muted);
}

/* Voice Header (collapsible) */
.voice-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  font-family: inherit;
}

.voice-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.voice-summary {
  font-size: 13px;
  color: var(--text);
  font-weight: 500;
}

.chevron {
  color: var(--text-muted);
  transition: transform 0.2s;
}

.chevron.open {
  transform: rotate(180deg);
}

.voice-grid {
  margin-top: 14px;
}

/* Voice Mode Toggle */
.voice-mode-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.mode-btns {
  display: flex;
  border-radius: 6px;
  border: 1.5px solid var(--border);
  overflow: hidden;
}

.mode-btn {
  padding: 6px 16px;
  font-size: 11px;
  font-weight: 700;
  font-family: inherit;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  border: none;
  cursor: pointer;
  transition: all 0.15s;
  background: transparent;
  color: var(--text-muted);
}

.mode-btn.active {
  background: rgba(78, 205, 196, 0.08);
  color: var(--accent);
}

/* Multi-voice panel */
.mv-panel {
  margin-top: 14px;
}

.mv-actions {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}

.mv-empty {
  text-align: center;
  color: var(--text-muted);
  font-size: 10px;
  padding: 12px 0;
}

.mv-segments {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.mv-segment {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  padding: 8px;
  background: var(--bg-darkest);
  border-radius: 8px;
  border: 1px solid var(--border);
}

.mv-index {
  font-size: 10px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  padding-top: 6px;
  min-width: 16px;
}

.mv-segment-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mv-textarea {
  width: 100%;
  font-size: 11px;
  line-height: 1.5;
  resize: vertical;
  padding: 6px 8px;
  background: var(--bg-darker, var(--bg-darkest));
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-family: inherit;
}

.mv-segment-controls {
  display: flex;
  gap: 4px;
  align-items: center;
}

.mv-select {
  font-size: 10px;
  padding: 2px 6px;
  background: var(--bg-darker, var(--bg-darkest));
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-muted);
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
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-muted);
  padding: 4px;
  transition: color 0.15s;
}

.mv-remove:hover {
  color: var(--coral);
}

/* Text Input */
.prompt-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.text-count {
  font-size: 10px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.prompt-textarea {
  width: 100%;
  min-height: 120px;
  padding: 12px;
  font-size: 13px;
  line-height: 1.6;
  background: var(--bg-darkest);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  font-family: inherit;
  resize: vertical;
  transition: border-color 0.15s;
}

.prompt-textarea:focus {
  outline: none;
  border-color: var(--accent);
}

.prompt-textarea::placeholder {
  color: var(--text-muted);
}

.prompt-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
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

.action-btn.danger {
  border-color: rgba(239, 68, 68, 0.3);
  color: var(--coral);
}

.action-btn.danger:hover {
  border-color: var(--coral);
}

.ctrl-hint {
  margin-left: auto;
  font-size: 9px;
  color: var(--text-muted);
  opacity: 0.5;
  font-family: var(--font-mono);
}

/* Controls Row */
.controls-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.speed-control {
  display: flex;
  align-items: center;
  gap: 8px;
}

.speed-input {
  width: 64px;
  padding: 6px 8px;
  font-size: 13px;
  font-family: var(--font-mono);
  background: var(--bg-darkest);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  text-align: center;
}

.speed-input:focus {
  outline: none;
  border-color: var(--accent);
}

.gen-mode-toggle {
  display: flex;
  border-radius: 6px;
  border: 1.5px solid var(--border);
  overflow: hidden;
}

/* Generate Button */
.gen-row {
  display: flex;
  gap: 8px;
  align-items: stretch;
}

.gen-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 14px 24px;
  background: linear-gradient(135deg, #4ECDC4, #2FB8AE);
  border: none;
  border-radius: 12px;
  font-family: 'JetBrains Mono', var(--font-mono);
  font-weight: 700;
  font-size: 14px;
  color: #0a0f14;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.1s;
}

.gen-btn:hover:not(:disabled) {
  opacity: 0.92;
}

.gen-btn:active:not(:disabled) {
  transform: scale(0.99);
}

.gen-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.spinner {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.abort-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 14px 20px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 12px;
  font-family: var(--font-mono);
  font-weight: 600;
  font-size: 12px;
  color: var(--coral);
  cursor: pointer;
  transition: background 0.15s;
}

.abort-btn:hover {
  background: rgba(239, 68, 68, 0.18);
}

/* Progress */
.progress-text {
  font-size: 12px;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  padding: 8px 0;
  text-align: center;
}

/* History */
.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.history-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.history-count {
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 400px;
  overflow-y: auto;
}

/* Responsive */
@media (max-width: 600px) {
  .tts-page {
    padding: 16px 16px 32px;
  }

  .controls-row {
    flex-direction: column;
    gap: 12px;
    align-items: stretch;
  }

  .speed-control {
    justify-content: space-between;
  }

  .gen-mode-toggle {
    align-self: flex-end;
  }
}
</style>
