<script setup>
import { ref, computed, watch } from 'vue'
import {
  VOICE_META, TOP_PICKS, BLEND_PRESETS, LANG_NAMES,
  LANG_SHORT, LANG_SHORT_COMPACT, LANG_ORDER,
} from '../composables/useTts.js'

const props = defineProps({
  voices: { type: Array, default: () => [] },
  selectedVoice: { type: String, default: 'af_heart' },
  selectedLang: { type: String, default: 'top-picks' },
  blendMode: { type: Boolean, default: false },
  blendVoiceA: { type: String, default: 'af_heart' },
  blendVoiceB: { type: String, default: 'am_adam' },
  blendRatio: { type: Number, default: 50 },
  blendMethod: { type: String, default: 'slerp' },
})

const emit = defineEmits([
  'select',
  'selectLang',
  'update:blendMode',
  'update:blendVoiceA',
  'update:blendVoiceB',
  'update:blendRatio',
  'update:blendMethod',
  'applyPreset',
  'randomBlend',
])

// Blend picker modal state
const pickerOpen = ref(false)
const pickerTarget = ref(null) // 'a' or 'b'
const pickerLang = ref('en-us')

// Build voice groups
const voiceGroups = computed(() => {
  const groups = {}
  const voiceList = props.voices.length ? props.voices : Object.keys(VOICE_META)
  voiceList.forEach(v => {
    const meta = VOICE_META[v] || { g: 'm', hue: '#AAB8CC', lang: 'en-us' }
    const lang = meta.lang || 'en-us'
    if (!groups[lang]) groups[lang] = []
    groups[lang].push(v)
  })
  return groups
})

const sortedLanguages = computed(() => {
  return Object.keys(voiceGroups.value).sort((a, b) => {
    const ia = LANG_ORDER.indexOf(a)
    const ib = LANG_ORDER.indexOf(b)
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
  })
})

const currentVoices = computed(() => {
  if (props.selectedLang === 'top-picks') return []
  return voiceGroups.value[props.selectedLang] || []
})

const blendVoiceAMeta = computed(() => VOICE_META[props.blendVoiceA] || { g: 'm', hue: '#AAB8CC', name: props.blendVoiceA })
const blendVoiceBMeta = computed(() => VOICE_META[props.blendVoiceB] || { g: 'm', hue: '#AAB8CC', name: props.blendVoiceB })

const methodDesc = computed(() => props.blendMethod === 'slerp' ? 'Spherical interpolation' : 'Linear interpolation')

const quickRatios = [0, 25, 50, 75, 100]

function getMeta(voiceId) {
  return VOICE_META[voiceId] || { g: 'm', hue: '#AAB8CC', name: voiceId, desc: '' }
}

function genderLabel(g) {
  return g === 'f' ? 'F' : 'M'
}

// Blend picker
function openPicker(target) {
  pickerTarget.value = target
  const currentVoice = target === 'a' ? props.blendVoiceA : props.blendVoiceB
  const meta = VOICE_META[currentVoice]
  if (meta) pickerLang.value = meta.lang
  pickerOpen.value = true
}

function closePicker() {
  pickerOpen.value = false
  pickerTarget.value = null
}

function selectPickerVoice(v) {
  if (pickerTarget.value === 'a') {
    emit('update:blendVoiceA', v)
  } else {
    emit('update:blendVoiceB', v)
  }
  closePicker()
}

const pickerVoices = computed(() => {
  const groups = voiceGroups.value
  return groups[pickerLang.value] || []
})

const pickerCurrentVoice = computed(() => {
  return pickerTarget.value === 'a' ? props.blendVoiceA : props.blendVoiceB
})

function onPickerKeydown(e) {
  if (e.key === 'Escape') closePicker()
}
</script>

<template>
  <div class="voice-selector">
    <!-- Voice / Blend Mode Tabs -->
    <div class="mode-tabs">
      <button
        class="mode-tab"
        :class="{ active: !blendMode }"
        @click="emit('update:blendMode', false)"
      >
        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" viewBox="0 0 24 24">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
        Voice
      </button>
      <button
        class="mode-tab"
        :class="{ active: blendMode }"
        @click="emit('update:blendMode', true)"
      >
        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" viewBox="0 0 24 24">
          <circle cx="6" cy="6" r="3" />
          <circle cx="18" cy="18" r="3" />
          <path d="M6 21V9a9 9 0 0 1 9 9" />
          <path d="M18 3v12a9 9 0 0 1-9-9" />
        </svg>
        Voice Blend
      </button>
    </div>

    <!-- Single Voice Mode -->
    <template v-if="!blendMode">
      <!-- Language Tabs -->
      <div class="lang-tabs">
        <button
          class="lang-tab"
          :class="{ active: selectedLang === 'top-picks' }"
          @click="emit('selectLang', 'top-picks')"
        >
          <span style="margin-right:3px">&#9733;</span>Top Picks
          <span class="lang-count">{{ TOP_PICKS.length }}</span>
        </button>
        <button
          v-for="lang in sortedLanguages"
          :key="lang"
          class="lang-tab"
          :class="{ active: selectedLang === lang }"
          @click="emit('selectLang', lang)"
        >
          {{ LANG_SHORT[lang] || lang }}
          <span class="lang-count">{{ voiceGroups[lang]?.length || 0 }}</span>
        </button>
      </div>

      <!-- Top Picks -->
      <div v-if="selectedLang === 'top-picks'" class="top-picks-list">
        <button
          v-for="pick in TOP_PICKS"
          :key="pick.voice"
          class="rec-card"
          :class="{ active: pick.voice === selectedVoice }"
          @click="emit('select', pick.voice)"
        >
          <span class="voice-dot" :style="{ background: getMeta(pick.voice).hue }"></span>
          <div class="rec-info">
            <div class="rec-name-row">
              <span class="rec-name" :style="{ color: pick.voice === selectedVoice ? 'var(--accent)' : 'var(--text)' }">
                {{ getMeta(pick.voice).name }}
              </span>
              <span class="gender-tag" :class="'gender-' + getMeta(pick.voice).g">
                {{ genderLabel(getMeta(pick.voice).g) }}
              </span>
              <span
                class="rec-badge"
                :style="{
                  background: getMeta(pick.voice).g === 'f' ? 'rgba(255,155,155,0.12)' : 'rgba(111,227,218,0.12)',
                  color: getMeta(pick.voice).hue,
                }"
              >
                {{ pick.badge }}
              </span>
            </div>
            <div class="rec-desc">{{ getMeta(pick.voice).desc }} &middot; {{ LANG_NAMES[getMeta(pick.voice).lang] || getMeta(pick.voice).lang }}</div>
            <div class="rec-best">{{ pick.bestFor }}</div>
          </div>
          <span class="rec-id">{{ pick.voice }}</span>
        </button>
      </div>

      <!-- Voice Chips Grid -->
      <div v-else class="voice-chips">
        <button
          v-for="v in currentVoices"
          :key="v"
          class="voice-chip"
          :class="{ active: selectedVoice === v }"
          :style="{
            borderColor: selectedVoice === v ? getMeta(v).hue : undefined,
            background: selectedVoice === v ? getMeta(v).hue + '14' : undefined,
            color: selectedVoice === v ? getMeta(v).hue : undefined,
          }"
          :title="getMeta(v).desc"
          @click="emit('select', v)"
        >
          <span class="chip-dot" :style="{ background: getMeta(v).hue }"></span>
          {{ getMeta(v).name }}
          <span class="gender-tag" :class="'gender-' + getMeta(v).g" style="margin-left:2px">
            {{ genderLabel(getMeta(v).g) }}
          </span>
        </button>
      </div>
    </template>

    <!-- Blend Mode -->
    <template v-else>
      <!-- Voice A / B Selectors -->
      <div class="blend-voices-grid">
        <div>
          <label class="field-label">Voice A</label>
          <button class="blend-voice-btn" @click="openPicker('a')">
            <span class="chip-dot" :style="{ background: blendVoiceAMeta.hue }"></span>
            <span>{{ blendVoiceAMeta.name }}</span>
            <span class="gender-tag" :class="'gender-' + blendVoiceAMeta.g" style="margin-left:auto">
              {{ genderLabel(blendVoiceAMeta.g) }}
            </span>
          </button>
        </div>
        <div class="blend-swap-icon">
          <svg width="18" height="18" fill="none" stroke="var(--text-muted)" stroke-width="1.5" stroke-linecap="round" viewBox="0 0 24 24" style="opacity:0.4">
            <path d="M17 1l4 4-4 4" />
            <path d="M3 11V9a4 4 0 0 1 4-4h14" />
            <path d="M7 23l-4-4 4-4" />
            <path d="M21 13v2a4 4 0 0 1-4 4H3" />
          </svg>
        </div>
        <div>
          <label class="field-label">Voice B</label>
          <button class="blend-voice-btn" @click="openPicker('b')">
            <span class="chip-dot" :style="{ background: blendVoiceBMeta.hue }"></span>
            <span>{{ blendVoiceBMeta.name }}</span>
            <span class="gender-tag" :class="'gender-' + blendVoiceBMeta.g" style="margin-left:auto">
              {{ genderLabel(blendVoiceBMeta.g) }}
            </span>
          </button>
        </div>
      </div>

      <!-- Blend Ratio -->
      <div class="blend-ratio-section">
        <div class="blend-ratio-header">
          <label class="field-label">Blend Ratio</label>
          <span class="ratio-display">{{ blendRatio }} / {{ 100 - blendRatio }}</span>
        </div>
        <div
          class="ratio-gradient"
          :style="{
            background: `linear-gradient(to right, ${blendVoiceAMeta.hue}, #A78BFA, ${blendVoiceBMeta.hue})`,
          }"
        ></div>
        <input
          type="range"
          min="0"
          max="100"
          :value="blendRatio"
          class="ratio-slider"
          @input="emit('update:blendRatio', parseInt($event.target.value))"
        />
        <div class="quick-ratios">
          <button
            v-for="val in quickRatios"
            :key="val"
            class="quick-ratio-btn"
            :class="{ active: val === blendRatio }"
            @click="emit('update:blendRatio', val)"
          >
            {{ val }}%
          </button>
        </div>
      </div>

      <!-- Method Toggle -->
      <div class="blend-method-section">
        <label class="field-label">Method</label>
        <div class="method-toggle">
          <button
            class="method-btn"
            :class="{ active: blendMethod === 'slerp' }"
            @click="emit('update:blendMethod', 'slerp')"
          >SLERP</button>
          <button
            class="method-btn"
            :class="{ active: blendMethod === 'lerp' }"
            @click="emit('update:blendMethod', 'lerp')"
          >LERP</button>
        </div>
        <span class="method-desc">{{ methodDesc }}</span>
      </div>

      <!-- Presets -->
      <div class="presets-section">
        <label class="field-label">Presets</label>
        <div class="presets-grid">
          <button
            v-for="(p, i) in BLEND_PRESETS"
            :key="i"
            class="preset-btn"
            :title="`${getMeta(p.a).name} + ${getMeta(p.b).name} at ${p.ratio}%`"
            @click="emit('applyPreset', i)"
          >
            <div class="preset-name">{{ p.name }}</div>
            <div class="preset-desc">{{ p.desc }}</div>
          </button>
          <button
            class="preset-btn random-preset"
            title="Random female + male SLERP blend"
            @click="emit('randomBlend')"
          >
            <div class="preset-name">&#127922; Random</div>
            <div class="preset-desc">Random F+M SLERP blend</div>
          </button>
        </div>
      </div>
    </template>

    <!-- Blend Picker Modal -->
    <Teleport to="body">
      <div
        v-if="pickerOpen"
        class="picker-overlay"
        @click.self="closePicker"
        @keydown="onPickerKeydown"
      >
        <div class="picker-modal">
          <div class="picker-header">
            <h4 class="picker-title">Select Voice {{ pickerTarget?.toUpperCase() }}</h4>
            <button class="picker-close" @click="closePicker">
              <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div class="picker-tabs">
            <button
              v-for="lang in sortedLanguages"
              :key="lang"
              class="lang-tab"
              :class="{ active: lang === pickerLang }"
              @click="pickerLang = lang"
            >
              {{ LANG_SHORT_COMPACT[lang] || lang }}
              <span class="lang-count">{{ voiceGroups[lang]?.length || 0 }}</span>
            </button>
          </div>

          <div class="picker-grid">
            <button
              v-for="v in pickerVoices"
              :key="v"
              class="voice-chip"
              :class="{ active: v === pickerCurrentVoice }"
              :style="{
                borderColor: v === pickerCurrentVoice ? getMeta(v).hue : undefined,
                background: v === pickerCurrentVoice ? getMeta(v).hue + '14' : undefined,
                color: v === pickerCurrentVoice ? getMeta(v).hue : undefined,
              }"
              :title="getMeta(v).desc"
              @click="selectPickerVoice(v)"
            >
              <span class="chip-dot" :style="{ background: getMeta(v).hue }"></span>
              {{ getMeta(v).name }}
              <span class="gender-tag" :class="'gender-' + getMeta(v).g" style="margin-left:2px">
                {{ genderLabel(getMeta(v).g) }}
              </span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
/* Mode tabs (Voice / Voice Blend) */
.mode-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 14px;
  border-radius: 8px;
  border: 1.5px solid var(--border);
  overflow: hidden;
  background: var(--bg-darkest);
}

.mode-tab {
  flex: 1;
  padding: 9px 0;
  font-size: 11px;
  font-weight: 700;
  font-family: inherit;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  border: none;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: transparent;
  color: var(--text-muted);
}

.mode-tab.active {
  background: rgba(78, 205, 196, 0.08);
  color: var(--accent);
}

/* Language tabs */
.lang-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 10px;
}

.lang-tab {
  padding: 5px 10px;
  font-size: 10px;
  font-weight: 600;
  font-family: inherit;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  gap: 4px;
}

.lang-tab:hover {
  border-color: var(--text-secondary);
}

.lang-tab.active {
  background: rgba(78, 205, 196, 0.08);
  border-color: var(--accent);
  color: var(--accent);
}

.lang-count {
  font-size: 9px;
  opacity: 0.6;
  font-family: var(--font-mono);
}

/* Top Picks */
.top-picks-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.rec-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1.5px solid var(--border);
  background: transparent;
  cursor: pointer;
  text-align: left;
  width: 100%;
  transition: all 0.15s;
  font-family: inherit;
}

.rec-card:hover {
  border-color: var(--text-secondary);
}

.rec-card.active {
  border-color: var(--accent);
  background: rgba(78, 205, 196, 0.06);
}

.voice-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.rec-info {
  flex: 1;
  min-width: 0;
}

.rec-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.rec-name {
  font-size: 13px;
  font-weight: 600;
}

.rec-badge {
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 9px;
  font-weight: 600;
}

.rec-desc {
  font-size: 10px;
  color: var(--text-muted);
  margin-top: 2px;
}

.rec-best {
  font-size: 9px;
  color: var(--text-muted);
  margin-top: 1px;
  opacity: 0.7;
}

.rec-id {
  font-size: 9px;
  font-family: var(--font-mono);
  color: var(--text-muted);
  opacity: 0.5;
  flex-shrink: 0;
}

/* Voice Chips */
.voice-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.voice-chip {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 10px;
  border-radius: 8px;
  border: 1.5px solid var(--border);
  background: transparent;
  cursor: pointer;
  transition: all 0.15s;
  font-size: 12px;
  color: var(--text-secondary);
  font-family: inherit;
}

.voice-chip:hover {
  border-color: var(--text-secondary);
}

.voice-chip.active {
  font-weight: 600;
}

.chip-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* Gender tag */
.gender-tag {
  font-size: 8px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.gender-f {
  background: rgba(255, 155, 155, 0.15);
  color: #FF9B9B;
}

.gender-m {
  background: rgba(111, 227, 218, 0.15);
  color: #6FE3DA;
}

/* Blend Voice Grid */
.blend-voices-grid {
  display: grid;
  grid-template-columns: 1fr 28px 1fr;
  gap: 6px;
  align-items: end;
  margin-bottom: 14px;
}

.blend-swap-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  padding-bottom: 8px;
}

.blend-voice-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1.5px solid var(--border);
  background: var(--bg-darkest);
  cursor: pointer;
  font-size: 12px;
  color: var(--text);
  font-family: inherit;
  width: 100%;
  transition: border-color 0.15s;
}

.blend-voice-btn:hover {
  border-color: var(--accent);
}

.field-label {
  display: block;
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--text-muted);
  margin-bottom: 4px;
}

/* Blend Ratio */
.blend-ratio-section {
  margin-bottom: 14px;
}

.blend-ratio-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.ratio-display {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  color: #A78BFA;
}

.ratio-gradient {
  height: 6px;
  border-radius: 3px;
  margin-bottom: 4px;
}

.ratio-slider {
  width: 100%;
  accent-color: var(--accent);
}

.quick-ratios {
  display: flex;
  gap: 4px;
  margin-top: 6px;
}

.quick-ratio-btn {
  flex: 1;
  padding: 4px 0;
  font-size: 9px;
  font-weight: 600;
  font-family: var(--font-mono);
  border: 1px solid var(--border);
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
}

.quick-ratio-btn:hover {
  border-color: var(--text-secondary);
}

.quick-ratio-btn.active {
  background: rgba(78, 205, 196, 0.08);
  border-color: var(--accent);
  color: var(--accent);
}

/* Blend Method */
.blend-method-section {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.method-toggle {
  display: flex;
  border-radius: 6px;
  border: 1.5px solid var(--border);
  overflow: hidden;
}

.method-btn {
  padding: 5px 12px;
  font-size: 10px;
  font-weight: 700;
  font-family: var(--font-mono);
  letter-spacing: 0.05em;
  border: none;
  cursor: pointer;
  transition: all 0.15s;
  background: transparent;
  color: var(--text-muted);
}

.method-btn.active {
  background: rgba(78, 205, 196, 0.08);
  color: var(--accent);
}

.method-desc {
  font-size: 9px;
  color: var(--text-muted);
  opacity: 0.6;
}

/* Presets */
.presets-section {
  margin-bottom: 0;
}

.presets-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
}

.preset-btn {
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: transparent;
  cursor: pointer;
  text-align: left;
  font-family: inherit;
  transition: border-color 0.15s;
}

.preset-btn:hover {
  border-color: var(--accent);
}

.random-preset {
  grid-column: 1 / -1;
  border-style: dashed;
}

.preset-name {
  font-weight: 600;
  font-size: 11px;
  color: var(--text);
}

.preset-desc {
  font-size: 9px;
  color: var(--text-muted);
  margin-top: 1px;
}

/* Picker Modal */
.picker-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.picker-modal {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px;
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  overflow-y: auto;
}

.picker-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.picker-title {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  margin: 0;
}

.picker-close {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-muted);
  padding: 4px;
}

.picker-close:hover {
  color: var(--text);
}

.picker-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 12px;
}

.picker-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
