<script setup>
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAudioRegistry } from '@/shared/composables/useAudioRegistry.js'
import { usePipeline } from '@/features/pipeline/composables/usePipeline.js'

const props = defineProps({ collapsed: Boolean })
const emit = defineEmits(['toggle'])
const route = useRoute()
const { playingSource, stopAll } = useAudioRegistry()
const { stepStatus, globalStatus, stopAfter } = usePipeline()

const audioPlaying = computed(() => !!playingSource.value)

const PATH_TO_STEP = {
  '/tts': 'tts', '/alignment': 'timing', '/segmenter': 'segment', '/scenes': 'scenes',
  '/storyboard': 'storyboard', '/assets': 'assets', '/editor': 'assemble', '/export-library': 'export',
}

function isActive(path) {
  return route.path === path
}

// Map stopAfter value → sidebar path for the target step
const STOP_TO_PATH = {
  tts: '/tts', timing: '/alignment', segment: '/segmenter', scenes: '/scenes',
  storyboard: '/storyboard', assets: '/assets', assemble: '/editor', export: '/export-library',
}

// Reactive pipeline class map — recomputes whenever stepStatus or globalStatus changes
const pipelineClasses = computed(() => {
  const classes = {}
  const status = globalStatus.value
  const steps = stepStatus.value
  const targetPath = STOP_TO_PATH[stopAfter.value] || '/export-library'

  for (const [path, step] of Object.entries(PATH_TO_STEP)) {
    if (status === 'done') {
      if (path === targetPath) { classes[path] = 'pipeline-done'; continue }
      if (steps[step] === 'done') { classes[path] = 'pipeline-step-done'; continue }
    }
    if (status === 'running') {
      if (steps[step] === 'running') {
        classes[path] = step === 'assets' ? 'pipeline-waiting' : 'pipeline-running'
        continue
      }
      if (steps[step] === 'done') { classes[path] = 'pipeline-step-done'; continue }
    }
    classes[path] = ''
  }
  return classes
})

function toggleAudio() {
  if (playingSource.value) {
    stopAll()
  }
}
</script>

<template>
  <nav class="sidebar" :class="{ collapsed }">
    <!-- Brand -->
    <div class="brand">
      <div class="brand-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.2" stroke-linecap="round">
          <rect x="2" y="2" width="20" height="20" rx="2" />
          <path d="M7 2v20" /><path d="M2 12h5" />
          <circle cx="14.5" cy="12" r="3" />
        </svg>
      </div>
      <div v-show="!collapsed" class="brand-text">
        <h1>ScriptToScene</h1>
        <p>Studio</p>
      </div>
    </div>

    <!-- Nav items -->
    <div class="nav-list">
      <!-- Group 1: Build surfaces — workflow builder is the primary surface -->
      <router-link to="/workflow" class="nav-item" :class="{ active: isActive('/workflow') }" title="Workflow Builder">
        <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="7" height="7" rx="1.5"/><rect x="15" y="15" width="7" height="7" rx="1.5"/><rect x="15" y="2" width="7" height="7" rx="1.5"/><path d="M9 5.5h6M18.5 9v6M5.5 9v4a2 2 0 002 2H15"/></svg>
        <span v-show="!collapsed" class="nav-label">WORKFLOW</span>
      </router-link>

      <router-link to="/pipeline" class="nav-item" :class="{ active: isActive('/pipeline') }" title="Legacy Pipeline Dashboard">
        <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
        <span v-show="!collapsed" class="nav-label">PIPELINE</span>
      </router-link>

      <div class="nav-divider" />

      <!-- Group 2: Audio Processing -->
      <div class="nav-group">
        <span v-show="!collapsed" class="nav-group-label">AUDIO</span>
        <router-link to="/tts" class="nav-item" :class="[{ active: isActive('/tts') }, pipelineClasses['/tts']]" title="Text to Speech">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v2a7 7 0 01-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>
          <span v-show="!collapsed" class="nav-label">TTS</span>
        </router-link>

        <router-link to="/alignment" class="nav-item" :class="[{ active: isActive('/alignment') }, pipelineClasses['/alignment']]" title="Force Alignment">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h10"/><circle cx="19" cy="17" r="2"/></svg>
          <span v-show="!collapsed" class="nav-label">ALIGNMENT</span>
        </router-link>

        <router-link to="/segmenter" class="nav-item" :class="[{ active: isActive('/segmenter') }, pipelineClasses['/segmenter']]" title="Scene Segmenter">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/></svg>
          <span v-show="!collapsed" class="nav-label">SEGMENTER</span>
        </router-link>
      </div>

      <div class="nav-divider" />

      <!-- Group 3: Visual Production -->
      <div class="nav-group">
        <span v-show="!collapsed" class="nav-group-label">VISUAL</span>
        <router-link to="/scenes" class="nav-item" :class="[{ active: isActive('/scenes') }, pipelineClasses['/scenes']]" title="Scene Blueprint">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><path d="M4 11V7a2 2 0 012-2h12a2 2 0 012 2v4"/><path d="M4 11h16"/></svg>
          <span v-show="!collapsed" class="nav-label">SCENES</span>
        </router-link>

        <router-link to="/storyboard" class="nav-item" :class="[{ active: isActive('/storyboard') }, pipelineClasses['/storyboard']]" title="Storyboard">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
          <span v-show="!collapsed" class="nav-label">STORYBOARD</span>
        </router-link>

        <router-link to="/assets" class="nav-item" :class="[{ active: isActive('/assets') }, pipelineClasses['/assets']]" title="Animator">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>
          <span v-show="!collapsed" class="nav-label">ANIMATOR</span>
        </router-link>

        <router-link to="/editor" class="nav-item" :class="[{ active: isActive('/editor') }, pipelineClasses['/editor']]" title="Timeline Editor">
          <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="8.5" y1="7.5" x2="20" y2="18"/><line x1="8.5" y1="16.5" x2="20" y2="6"/></svg>
          <span v-show="!collapsed" class="nav-label">EDITOR</span>
        </router-link>
      </div>

      <div class="nav-divider" />

      <!-- Group 4: Output -->
      <router-link to="/export-library" class="nav-item" :class="[{ active: isActive('/export-library') }, pipelineClasses['/export-library']]" title="Export Library">
        <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="10,8 16,12 10,16" fill="currentColor" stroke="none"/></svg>
        <span v-show="!collapsed" class="nav-label">EXPORTS</span>
      </router-link>
    </div>

    <!-- Bottom -->
    <div class="nav-bottom">
      <button class="nav-item audio-btn" :class="{ 'audio-playing': audioPlaying }" :title="audioPlaying ? `Playing: ${playingSource} — click to stop` : 'No audio playing'" @click="toggleAudio">
        <svg class="nav-icon audio-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="10" width="3" height="4" rx="1.5" fill="currentColor" stroke="none"/>
          <rect x="8" y="7" width="3" height="10" rx="1.5" fill="currentColor" stroke="none"/>
          <rect x="13" y="4" width="3" height="16" rx="1.5" fill="currentColor" stroke="none"/>
          <rect x="18" y="8" width="3" height="8" rx="1.5" fill="currentColor" stroke="none"/>
        </svg>
        <span v-show="!collapsed" class="nav-label">AUDIO <span v-if="playingSource" class="audio-source-label">{{ playingSource }}</span></span>
      </button>
      <router-link to="/settings" class="nav-item" :class="{ active: isActive('/settings') }" title="Settings">
        <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
        <span v-show="!collapsed" class="nav-label">SETTINGS</span>
      </router-link>
      <button class="nav-item" @click="emit('toggle')" title="Toggle sidebar">
        <svg class="nav-icon collapse-icon" :class="{ flipped: collapsed }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M15 18l-6-6 6-6"/></svg>
        <span v-show="!collapsed" class="nav-label">COLLAPSE</span>
      </button>
    </div>
  </nav>
</template>

<style scoped>
.sidebar {
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  width: var(--sidebar-w);
  background: var(--bg-darkest);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 40;
  overflow: hidden;
}

.sidebar.collapsed {
  width: var(--sidebar-collapsed);
}

.sidebar.collapsed .nav-label {
  opacity: 0;
  width: 0;
  overflow: hidden;
}

.sidebar.collapsed .brand-text {
  opacity: 0;
  width: 0;
  overflow: hidden;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.brand-icon {
  width: 36px;
  height: 36px;
  min-width: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, #4ECDC4, #2FB8AE);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 12px rgba(78, 205, 196, 0.3);
}

.brand-text h1 {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  line-height: 1.1;
  letter-spacing: -0.025em;
  white-space: nowrap;
}

.brand-text p {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--accent);
  margin-top: 1px;
}

.nav-label,
.brand-text {
  transition: opacity 0.2s, width 0.2s;
  white-space: nowrap;
}

.nav-list {
  flex: 1;
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
  overflow-y: auto;
}

.nav-group {
  display: flex;
  flex-direction: column;
}

.nav-group-label {
  font-size: 8px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--text-muted);
  padding: 3px 20px 2px;
  opacity: 0.5;
}

.nav-group .nav-item {
  margin: 0;
  width: 100%;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 20px;
  margin: 1px 8px;
  border-radius: 10px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.2s;
  font-size: 13px;
  font-weight: 500;
  position: relative;
  border: none;
  background: none;
  width: calc(100% - 16px);
  text-align: left;
  font-family: inherit;
  text-decoration: none;
}

.nav-item:hover {
  color: var(--text);
  background: rgba(78, 205, 196, 0.06);
}

.nav-item.active {
  color: var(--accent);
  background: rgba(78, 205, 196, 0.1);
}

.nav-item.active::before {
  content: '';
  position: absolute;
  left: -8px;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--accent);
}

.nav-icon {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
}

.nav-divider {
  height: 1px;
  background: var(--border);
  margin: 5px 16px;
  opacity: 0.5;
}

.nav-bottom {
  border-top: 1px solid var(--border);
  padding: 6px 12px;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.nav-bottom .nav-item {
  margin: 0;
  width: 100%;
}

/* Audio button */
@keyframes audio-playing-pulse {
  0%, 100% { background: rgba(167, 139, 250, 0.05); }
  50%      { background: rgba(167, 139, 250, 0.25); }
}

.audio-btn.audio-playing {
  color: var(--accent-secondary);
  animation: audio-playing-pulse 1.2s ease-in-out infinite;
  box-shadow: inset 0 0 0 1px rgba(167, 139, 250, 0.4);
}

.audio-btn.audio-playing .audio-icon {
  animation: audio-icon-bounce 0.6s ease-in-out infinite alternate;
}

@keyframes audio-icon-bounce {
  0%   { transform: scale(1); }
  100% { transform: scale(1.15); }
}

.audio-source-label {
  font-size: 0.7em;
  opacity: 0.7;
  margin-left: 4px;
}

.collapse-icon {
  transition: transform 0.3s;
}

.collapse-icon.flipped {
  transform: rotate(180deg);
}

/* ---- Pipeline step highlighting ---- */
@keyframes pipeline-pulse {
  0%, 100% { background: rgba(78, 205, 196, 0.05); }
  50% { background: rgba(78, 205, 196, 0.25); }
}

@keyframes pipeline-done-pulse {
  0%, 100% { background: rgba(255, 215, 0, 0.05); }
  50% { background: rgba(255, 215, 0, 0.25); }
}

.nav-item.pipeline-running {
  color: var(--accent) !important;
  animation: pipeline-pulse 1.5s ease-in-out infinite;
  box-shadow: inset 0 0 0 1px rgba(78, 205, 196, 0.3);
}

.nav-item.pipeline-step-done {
  color: var(--accent) !important;
  background: rgba(78, 205, 196, 0.08);
  box-shadow: inset 3px 0 0 var(--accent);
  margin: 0.15rem 0;
}

@keyframes pipeline-waiting-pulse {
  0%, 100% { background: rgba(255, 179, 71, 0.05); }
  50% { background: rgba(255, 179, 71, 0.25); }
}

.nav-item.pipeline-waiting {
  color: var(--accent-warning) !important;
  animation: pipeline-waiting-pulse 2s ease-in-out infinite;
  box-shadow: inset 0 0 0 1px rgba(255, 179, 71, 0.3);
}

.nav-item.pipeline-done {
  color: #FFD700 !important;
  animation: pipeline-done-pulse 1.5s ease-in-out infinite;
  box-shadow: inset 0 0 0 1px rgba(255, 215, 0, 0.3);
}
</style>
