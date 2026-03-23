<script setup>
defineOptions({ name: 'SceneCard' })

const props = defineProps({
  scene: { type: Object, required: true },
  index: { type: Number, required: true },
  isActive: { type: Boolean, default: false },
  segmentWords: { type: String, default: '' },
  storyboardThumb: { type: String, default: null },
})

const emit = defineEmits(['play'])

async function copyPrompt(text) {
  try {
    await navigator.clipboard.writeText(text)
  } catch {}
}

const typeColorMap = {
  video: '#4ECDC4',
  image: '#A78BFA',
  text_overlay: '#FFB347',
  text: '#FFB347',
}

const typeBgMap = {
  video: 'rgba(78, 205, 196, 0.1)',
  image: 'rgba(167, 139, 250, 0.1)',
  text_overlay: 'rgba(255, 179, 71, 0.1)',
  text: 'rgba(255, 179, 71, 0.1)',
}

function typeColor(type) {
  return typeColorMap[type] || '#6b7f93'
}

function typeBg(type) {
  return typeBgMap[type] || 'rgba(107, 127, 147, 0.1)'
}
</script>

<template>
  <div
    class="scene-card"
    :class="{ active: isActive }"
    :style="{ borderLeftColor: typeColor(scene.type_of_scene) }"
    @click="emit('play', index)"
  >
    <img
      v-if="storyboardThumb"
      class="storyboard-thumb"
      :src="storyboardThumb"
      :alt="`Storyboard ${index}`"
      loading="lazy"
    />
    <div v-else class="storyboard-thumb storyboard-thumb--empty">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <circle cx="8.5" cy="8.5" r="1.5" />
        <path d="M21 15l-5-5L5 21" />
      </svg>
    </div>
    <div class="scene-card-top">
      <span class="scene-card-index" :style="{ color: typeColor(scene.type_of_scene) }">
        #{{ index }}
        <template v-if="scene.title"> &middot; {{ scene.title }}</template>
        <template v-if="scene.timeline_start != null">
          &middot; <span class="scene-card-time">{{ scene.timeline_start?.toFixed(2) }}s - {{ scene.timeline_end?.toFixed(2) }}s</span>
        </template>
      </span>
      <div class="scene-card-badges">
        <span
          class="scene-type-badge"
          :style="{ background: typeBg(scene.type_of_scene), color: typeColor(scene.type_of_scene) }"
        >
          {{ scene.type_of_scene || 'video' }}
        </span>
        <span
          v-if="scene.narrative_role"
          class="scene-role-badge"
        >
          {{ scene.narrative_role }}
        </span>
        <span class="scene-dur-badge">
          {{ (scene.duration || 0).toFixed(1) }}s
        </span>
      </div>
    </div>

    <p v-if="segmentWords" class="scene-card-words">"{{ segmentWords }}"</p>
    <p
      v-if="scene.text_content"
      class="scene-card-text"
      :style="{ color: typeColor(scene.type_of_scene) }"
    >
      "{{ scene.text_content }}"
    </p>
    <p v-if="scene.image_prompt" class="scene-card-prompt">{{ scene.image_prompt }}</p>
    <button v-if="scene.image_prompt" class="btn-copy" @click.stop="copyPrompt(scene.image_prompt)" title="Copy prompt">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
      <span>Copy</span>
    </button>
  </div>
</template>

<style scoped>
.scene-card {
  position: relative;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-left-width: 4px;
  border-radius: 10px;
  padding: 14px 16px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.storyboard-thumb {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid var(--border);
  opacity: 0.85;
  transition: opacity 0.2s, transform 0.2s;
  z-index: 1;
}
.storyboard-thumb:hover {
  opacity: 1;
  transform: scale(2.5);
  border-color: var(--accent);
  box-shadow: 0 4px 16px rgba(0,0,0,0.5);
  z-index: 10;
}
.storyboard-thumb--empty {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-darkest, #0a0e13);
  color: var(--text-muted);
  opacity: 0.4;
}
.storyboard-thumb--empty:hover {
  transform: none;
  box-shadow: none;
  opacity: 0.6;
  border-color: var(--border);
}

.scene-card:hover {
  border-color: var(--text-muted);
}

.scene-card.active {
  border-color: var(--accent);
  box-shadow: 0 0 12px rgba(78, 205, 196, 0.3);
}

.scene-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  gap: 8px;
  flex-wrap: wrap;
}

.scene-card-index {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 500;
}

.scene-card-time {
  color: var(--text-muted);
}

.scene-card-badges {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-shrink: 0;
}

.scene-type-badge {
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.scene-role-badge {
  font-family: var(--font-mono);
  font-size: 9px;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(78, 205, 196, 0.08);
  color: var(--accent);
}

.scene-dur-badge {
  font-family: var(--font-mono);
  font-size: 9px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--bg-darkest);
  color: var(--text-muted);
}

.scene-card-words {
  font-size: 12px;
  color: var(--text);
  line-height: 1.5;
  margin: 0 0 6px;
}

.scene-card-text {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 8px;
}

.scene-card-prompt {
  font-size: 11px;
  color: var(--text-secondary);
  font-style: italic;
  line-height: 1.5;
  margin: 0;
}
.btn-copy {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  padding: 2px 8px;
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
</style>
