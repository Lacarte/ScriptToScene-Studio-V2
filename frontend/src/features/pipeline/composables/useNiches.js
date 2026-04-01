import { ref, readonly } from 'vue'
import { api } from '@/shared/api/client.js'
import { usePipelineForm } from './usePipelineForm.js'

// ── Singleton state ──

const nichePreset = ref(localStorage.getItem('sts-niche-preset') || '')
const visualStyle = ref(localStorage.getItem('sts-visual-style') || '')
const storyTone = ref(localStorage.getItem('sts-story-tone') || '')
const nicheCategory = ref(localStorage.getItem('sts-niche-category') || '')
const nichePresets = ref({})
const storyTones = ref({})
const nicheCategories = ref([])
const visualStyles = ref([])
const nichesLoaded = ref(false)

function persistNicheState() {
  const entries = [
    ['sts-niche-preset', nichePreset.value],
    ['sts-visual-style', visualStyle.value],
    ['sts-story-tone', storyTone.value],
    ['sts-niche-category', nicheCategory.value],
  ]
  for (const [key, value] of entries) {
    if (value) localStorage.setItem(key, value)
    else localStorage.removeItem(key)
  }
}

function setVisualStyleOverride(styleId) {
  const { style } = usePipelineForm()
  visualStyle.value = styleId || ''
  if (styleId) style.value = styleId
  persistNicheState()
}

function setStoryTone(toneId) {
  storyTone.value = toneId || ''
  persistNicheState()
}

function setNicheCategory(categoryId) {
  nicheCategory.value = categoryId || ''
  persistNicheState()
}

function selectNiche(preset) {
  const { kokoroVoice, inworldVoice, speed, style } = usePipelineForm()
  nichePreset.value = preset.id || ''
  visualStyle.value = preset.visual_style || ''
  storyTone.value = preset.story_tone || ''
  nicheCategory.value = preset.category || ''
  // Each provider gets its own voice from the preset
  kokoroVoice.value = preset.voice || kokoroVoice.value
  if (preset.inworld_voice) inworldVoice.value = preset.inworld_voice
  speed.value = preset.speed || speed.value
  style.value = preset.visual_style || style.value
  persistNicheState()
}

function clearNiche() {
  const { kokoroVoice, speed } = usePipelineForm()
  nichePreset.value = ''
  visualStyle.value = ''
  storyTone.value = ''
  nicheCategory.value = ''
  kokoroVoice.value = 'af_heart'
  speed.value = 1.0
  persistNicheState()
}

async function loadNiches() {
  if (nichesLoaded.value) return
  const { style, kokoroVoice, inworldVoice, speed, templates } = usePipelineForm()
  try {
    const data = await api.get('/api/niches')
    nichePresets.value = data.presets || {}
    storyTones.value = data.story_tones || {}
    nicheCategories.value = data.categories || []
    visualStyles.value = data.visual_styles || []
    nichesLoaded.value = true

    if (nichePreset.value && nichePresets.value[nichePreset.value]) {
      const preset = nichePresets.value[nichePreset.value]
      if (!visualStyle.value) visualStyle.value = preset.visual_style || ''
      if (!storyTone.value) storyTone.value = preset.story_tone || ''
      if (!nicheCategory.value) nicheCategory.value = preset.category || ''
      if (!style.value && preset.visual_style) style.value = preset.visual_style
      if (preset.voice) kokoroVoice.value = preset.voice
      if (preset.inworld_voice) inworldVoice.value = preset.inworld_voice
      if (preset.speed) speed.value = preset.speed
    } else if (nichePreset.value) {
      clearNiche()
    }

    if (visualStyle.value && !visualStyles.value.some(v => v.id === visualStyle.value)) {
      visualStyle.value = ''
    }
    if (storyTone.value && !Object.prototype.hasOwnProperty.call(storyTones.value, storyTone.value)) {
      storyTone.value = ''
    }
    if (nicheCategory.value && !nicheCategories.value.includes(nicheCategory.value)) {
      nicheCategory.value = ''
    }
    persistNicheState()
  } catch (e) {
    console.warn('[Pipeline] Failed to load niches:', e.message)
  }
}

async function saveNichePreset(presetData) {
  try {
    const res = await api.post('/api/niches', { body: presetData })
    nichePresets.value = res.presets || {}
    const savedId = res.saved_id || presetData.id
    const savedPreset = nichePresets.value[savedId]
    if (savedPreset) selectNiche({ id: savedId, ...savedPreset })
    return { ok: true, savedId }
  } catch (e) {
    console.warn('[Pipeline] Failed to save niche:', e.message)
    return { ok: false, error: e.message || 'Failed to save niche' }
  }
}

async function deleteNichePreset(presetId) {
  try {
    const res = await api.delete(`/api/niches/${presetId}`)
    nichePresets.value = res.presets || {}
    if (nichePreset.value === presetId) clearNiche()
    return { ok: true }
  } catch (e) {
    console.warn('[Pipeline] Failed to delete niche:', e.message)
    return { ok: false, error: e.message || 'Failed to delete niche' }
  }
}

function _buildNicheConfig() {
  const { style } = usePipelineForm()
  const cfg = {}
  if (nichePreset.value) cfg.niche_preset = nichePreset.value
  if (visualStyle.value || style.value) cfg.visual_style = visualStyle.value || style.value
  if (storyTone.value) cfg.story_tone = storyTone.value
  if (nicheCategory.value) cfg.category = nicheCategory.value
  return cfg
}

export function useNiches() {
  return {
    nichePreset,
    visualStyle,
    storyTone,
    nicheCategory,
    nichePresets: readonly(nichePresets),
    storyTones: readonly(storyTones),
    nicheCategories: readonly(nicheCategories),
    visualStyles: readonly(visualStyles),
    nichesLoaded: readonly(nichesLoaded),

    selectNiche,
    clearNiche,
    loadNiches,
    saveNichePreset,
    deleteNichePreset,
    setVisualStyleOverride,
    setStoryTone,
    setNicheCategory,
    _buildNicheConfig,
  }
}
