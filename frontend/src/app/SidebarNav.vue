<script setup>
import { useRoute } from 'vue-router'

const props = defineProps({ collapsed: Boolean })
const emit = defineEmits(['toggle'])
const route = useRoute()

function isActive(path) {
  return route.path === path
}
</script>

<template>
  <nav class="sidebar" :class="{ collapsed }">
    <!-- Brand -->
    <div class="brand">
      <div class="brand-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round" width="28" height="28">
          <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18" />
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
      <!-- Pipeline -->
      <router-link to="/pipeline" class="nav-item" :class="{ active: isActive('/pipeline') }" title="Pipeline Dashboard">
        <span class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="20" height="20"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg></span>
        <span v-show="!collapsed" class="nav-label">PIPELINE</span>
      </router-link>

      <!-- TTS / Alignment / Segmenter group -->
      <div class="nav-group">
        <router-link to="/tts" class="nav-item" :class="{ active: isActive('/tts') }" title="Text to Speech">
          <span class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" width="20" height="20"><path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/><path d="M19 10v2a7 7 0 01-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg></span>
          <span v-show="!collapsed" class="nav-label">TTS</span>
        </router-link>

        <router-link to="/timing" class="nav-item" :class="{ active: isActive('/timing') }" title="Force Alignment">
          <span class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" width="20" height="20"><path d="M4 7h16M4 12h16M4 17h10"/><circle cx="19" cy="17" r="2"/></svg></span>
          <span v-show="!collapsed" class="nav-label">ALIGNMENT</span>
        </router-link>

        <router-link to="/segmenter" class="nav-item" :class="{ active: isActive('/segmenter') }" title="Scene Segmenter">
          <span class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="20" height="20"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/></svg></span>
          <span v-show="!collapsed" class="nav-label">SEGMENTER</span>
        </router-link>
      </div>

      <!-- Scenes -->
      <router-link to="/scenes" class="nav-item" :class="{ active: isActive('/scenes') }" title="Scene Generator">
        <span class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="20" height="20"><path d="M4 11v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><path d="M4 11V7a2 2 0 012-2h12a2 2 0 012 2v4"/><path d="M4 11h16"/><path d="M7 5l3 6"/><path d="M11 5l3 6"/><path d="M15 5l3 6"/></svg></span>
        <span v-show="!collapsed" class="nav-label">SCENES</span>
      </router-link>

      <!-- Assets -->
      <router-link to="/assets" class="nav-item" :class="{ active: isActive('/assets') }" title="Asset Manager">
        <span class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" width="20" height="20"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg></span>
        <span v-show="!collapsed" class="nav-label">ASSETS</span>
      </router-link>

      <!-- Editor -->
      <router-link to="/editor" class="nav-item" :class="{ active: isActive('/editor') }" title="Timeline Editor">
        <span class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="20" height="20"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/><path d="M7 2v20"/><path d="M17 2v20"/><path d="M2 12h20"/><path d="M2 7h5"/><path d="M2 17h5"/><path d="M17 17h5"/><path d="M17 7h5"/></svg></span>
        <span v-show="!collapsed" class="nav-label">EDITOR</span>
      </router-link>

      <!-- Exports -->
      <router-link to="/export-library" class="nav-item" :class="{ active: isActive('/export-library') }" title="Export Library">
        <span class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="20" height="20"><circle cx="12" cy="12" r="10"/><polygon points="10,8 16,12 10,16" fill="currentColor" stroke="none"/></svg></span>
        <span v-show="!collapsed" class="nav-label">EXPORTS</span>
      </router-link>
    </div>

    <!-- Bottom -->
    <div class="nav-bottom">
      <router-link to="/settings" class="nav-item" :class="{ active: isActive('/settings') }" title="Settings">
        <span class="nav-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" width="18" height="18"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg></span>
        <span v-show="!collapsed" class="nav-label">SETTINGS</span>
      </router-link>
      <button class="nav-item" @click="emit('toggle')" title="Toggle sidebar">
        <span class="nav-icon collapse-icon" :class="{ flipped: collapsed }">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" width="18" height="18"><path d="M15 18l-6-6 6-6"/></svg>
        </span>
        <span v-show="!collapsed" class="nav-label">Collapse</span>
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
  gap: 10px;
  padding: 16px;
  border-bottom: 1px solid var(--border);
  min-height: 62px;
}

.brand-icon {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-text h1 {
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  line-height: 1.1;
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
  padding: 12px 0;
  display: flex;
  flex-direction: column;
  gap: 0;
  overflow-y: auto;
}

.nav-group {
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 10px;
  margin: 4px 8px;
  padding: 4px 0;
}

.nav-group .nav-item {
  margin: 2px 0;
  width: 100%;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 20px;
  margin: 2px 8px;
  border-radius: 10px;
  color: var(--text-secondary);
  text-decoration: none;
  font-family: inherit;
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.02em;
  border: none;
  background: none;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  width: calc(100% - 16px);
  text-align: left;
  position: relative;
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
  display: flex;
  align-items: center;
  justify-content: center;
}

.nav-bottom {
  border-top: 1px solid var(--border);
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.collapse-icon {
  transition: transform 0.3s;
}

.collapse-icon.flipped {
  transform: rotate(180deg);
}
</style>
