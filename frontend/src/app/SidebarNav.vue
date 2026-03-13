<script setup>
import { useRoute, useRouter } from 'vue-router'

const props = defineProps({ collapsed: Boolean })
const emit = defineEmits(['toggle'])

const route = useRoute()
const router = useRouter()

const navItems = [
  { to: '/pipeline', label: 'PIPELINE', icon: 'bolt', group: 'top' },
  { divider: true },
  { to: '/tts', label: 'TTS', icon: 'mic', group: 'process' },
  { to: '/timing', label: 'ALIGNMENT', icon: 'align', group: 'process' },
  { to: '/segmenter', label: 'SEGMENTER', icon: 'cut', group: 'process' },
  { to: '/scenes', label: 'SCENES', icon: 'film' },
  { to: '/assets', label: 'ASSETS', icon: 'image' },
  { to: '/editor', label: 'EDITOR', icon: 'editor' },
  { to: '/export-library', label: 'EXPORTS', icon: 'play' },
]

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
          stroke-linecap="round" stroke-linejoin="round" width="24" height="24">
          <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18" />
          <path d="M7 2v20" /><path d="M2 12h5" />
          <circle cx="14.5" cy="12" r="3" />
        </svg>
      </div>
      <div class="brand-text" v-show="!collapsed">
        <h1>ScriptToScene</h1>
        <p>Studio</p>
      </div>
    </div>

    <!-- Nav items -->
    <div class="nav-list">
      <template v-for="(item, i) in navItems" :key="i">
        <div v-if="item.divider" class="divider" />
        <router-link
          v-else
          :to="item.to"
          class="nav-item"
          :class="{ active: isActive(item.to) }"
          :title="item.label"
        >
          <span class="nav-icon">
            <component :is="'Icon' + item.icon" />
          </span>
          <span class="nav-label" v-show="!collapsed">{{ item.label }}</span>
        </router-link>
      </template>
    </div>

    <!-- Bottom -->
    <div class="nav-bottom">
      <router-link to="/settings" class="nav-item" :class="{ active: isActive('/settings') }" title="Settings">
        <span class="nav-icon"><IconSettings /></span>
        <span class="nav-label" v-show="!collapsed">SETTINGS</span>
      </router-link>
      <button class="nav-item" @click="emit('toggle')" title="Toggle sidebar">
        <span class="nav-icon collapse-icon" :class="{ flipped: collapsed }">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" width="18" height="18">
            <path d="M15 18l-6-6 6-6" />
          </svg>
        </span>
        <span class="nav-label" v-show="!collapsed">Collapse</span>
      </button>
    </div>
  </nav>
</template>

<!-- Inline icon components (avoids external dependency) -->
<script>
import { h } from 'vue'

const svg = (paths) => ({
  render: () => h('svg', {
    viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
    'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round',
    width: '18', height: '18',
  }, paths.map(d => typeof d === 'string' ? h('path', { d }) : h(d.tag, d.attrs)))
})

const Iconbolt = svg(['M13 2L3 14h9l-1 8 10-12h-9l1-8z'])
const Iconmic = svg([
  'M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z',
  'M19 10v2a7 7 0 01-14 0v-2',
  { tag: 'line', attrs: { x1: 12, y1: 19, x2: 12, y2: 23 } },
  { tag: 'line', attrs: { x1: 8, y1: 23, x2: 16, y2: 23 } },
])
const Iconalign = svg([
  'M4 7h16', 'M4 12h16', 'M4 17h10',
  { tag: 'circle', attrs: { cx: 19, cy: 17, r: 2 } },
])
const Iconcut = svg([
  { tag: 'circle', attrs: { cx: 6, cy: 6, r: 3 } },
  { tag: 'circle', attrs: { cx: 6, cy: 18, r: 3 } },
  { tag: 'line', attrs: { x1: 20, y1: 4, x2: 8.12, y2: 15.88 } },
  { tag: 'line', attrs: { x1: 14.47, y1: 14.48, x2: 20, y2: 20 } },
  { tag: 'line', attrs: { x1: 8.12, y1: 8.12, x2: 12, y2: 12 } },
])
const Iconfilm = svg([
  'M4 11v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8',
  'M4 11V7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v4',
  'M4 11h16', 'M7 5l3 6', 'M11 5l3 6', 'M15 5l3 6',
])
const Iconimage = svg([
  { tag: 'rect', attrs: { x: 3, y: 3, width: 18, height: 18, rx: 2 } },
  { tag: 'circle', attrs: { cx: 8.5, cy: 8.5, r: 1.5 } },
  'M21 15l-5-5L5 21',
])
const Iconeditor = svg([
  { tag: 'rect', attrs: { x: 2, y: 2, width: 20, height: 20, rx: 2.18, ry: 2.18 } },
  'M7 2v20', 'M17 2v20', 'M2 12h20', 'M2 7h5', 'M2 17h5', 'M17 17h5', 'M17 7h5',
])
const Iconplay = svg([
  { tag: 'circle', attrs: { cx: 12, cy: 12, r: 10 } },
  { tag: 'polygon', attrs: { points: '10,8 16,12 10,16', fill: 'currentColor', stroke: 'none' } },
])
const IconSettings = svg([
  { tag: 'circle', attrs: { cx: 12, cy: 12, r: 3 } },
  'M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z',
])

export default {
  components: { Iconbolt, Iconmic, Iconalign, Iconcut, Iconfilm, Iconimage, Iconeditor, Iconplay, IconSettings },
}
</script>

<style scoped>
.sidebar {
  position: fixed;
  top: 0;
  left: 0;
  height: 100vh;
  width: var(--sidebar-w);
  background: var(--bg-dark);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease;
  z-index: 100;
  overflow: hidden;
}

.sidebar.collapsed {
  width: var(--sidebar-collapsed);
}

/* Brand */
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px;
  border-bottom: 1px solid var(--border);
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

/* Nav */
.nav-list {
  flex: 1;
  padding: 12px 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  color: var(--text-secondary);
  text-decoration: none;
  font-family: var(--font-body);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.05em;
  border: none;
  background: none;
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
  white-space: nowrap;
  width: 100%;
  text-align: left;
}

.nav-item:hover {
  color: var(--text);
  background: var(--bg-surface-hover);
}

.nav-item.active {
  color: var(--accent);
  background: var(--accent-dim);
}

.nav-icon {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.nav-label {
  white-space: nowrap;
}

.divider {
  height: 1px;
  background: var(--border);
  margin: 8px 16px;
}

/* Bottom */
.nav-bottom {
  border-top: 1px solid var(--border);
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.collapse-icon {
  transition: transform 0.3s;
}

.collapse-icon.flipped {
  transform: rotate(180deg);
}
</style>
