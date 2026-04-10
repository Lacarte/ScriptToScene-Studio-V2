<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useActivityFeed } from '@/shared/composables/useActivityFeed.js'
import { useAppStore } from '@/shared/stores/appStore.js'
import { usePipeline } from '@/features/pipeline/composables/usePipeline.js'

defineOptions({ name: 'ActivitySnackbar' })

const { entries, latest, count, clear, urgentPing } = useActivityFeed()
const app = useAppStore()
const { running, globalStatus } = usePipeline()
const expanded = ref(false)
const listEl = ref(null)
const showScrollTop = ref(false)
const showScrollBottom = ref(false)

function onLogScroll() {
  if (listEl.value) {
    const el = listEl.value
    showScrollTop.value = el.scrollTop > 80
    showScrollBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight > 80
  }
}

function scrollToTop() {
  if (listEl.value) {
    listEl.value.scrollTo({ top: 0, behavior: 'smooth' })
  }
}

function scrollToBottom() {
  if (listEl.value) {
    listEl.value.scrollTo({ top: listEl.value.scrollHeight, behavior: 'smooth' })
  }
}

const isActive = computed(() => running.value || globalStatus.value === 'error' || globalStatus.value === 'stopped')
const hasEntries = computed(() => count.value > 0 || isActive.value)

// Auto-expand on urgent events (error / warning)
watch(urgentPing, () => {
  expanded.value = true
  nextTick(() => {
    if (listEl.value) listEl.value.scrollTop = 0
  })
})

// Auto-scroll to top when new entries arrive while expanded
watch(count, () => {
  if (expanded.value) {
    nextTick(() => {
      if (listEl.value) listEl.value.scrollTop = 0
    })
  }
})

function entryIcon(type) {
  if (type === 'error')   return '\u2717'
  if (type === 'success') return '\u2713'
  if (type === 'warning') return '\u26A0'
  return '\u2192'
}

function entryColor(type) {
  if (type === 'error')   return '#FF6B6B'
  if (type === 'success') return '#26DE81'
  if (type === 'warning') return '#FFB347'
  if (type === 'info')    return '#56CCF2'
  return 'var(--text-muted)'
}

function toggle() {
  expanded.value = !expanded.value
}

function handleClear() {
  clear()
  expanded.value = false
}
</script>

<template>
  <Teleport to="body">
    <div v-if="hasEntries" class="snackbar" :class="{ 'snackbar--collapsed': app.sidebarCollapsed }">

      <!-- Expanded log feed (above the bar) -->
      <Transition name="feed">
        <div v-if="expanded" class="snackbar-feed">
          <div class="snackbar-feed-header">
            <span class="snackbar-feed-title">Activity</span>
            <div class="snackbar-feed-actions">
              <span class="snackbar-feed-count">{{ count }}</span>
              <button class="snackbar-clear" @click="handleClear">Clear</button>
            </div>
          </div>
          <div class="snackbar-log-wrap">
          <div class="snackbar-log" ref="listEl" @scroll="onLogScroll">
            <div
              v-for="entry in entries"
              :key="entry.id"
              class="log-entry"
              :style="{ color: entryColor(entry.type) }"
            >
              <span class="log-icon">{{ entryIcon(entry.type) }}</span>
              <span class="log-msg">{{ entry.message }}</span>
            </div>
          </div>
          <Transition name="fade">
            <button v-if="showScrollTop" class="scroll-top-btn" @click="scrollToTop" title="Scroll to top">&#8593;</button>
          </Transition>
          <Transition name="fade">
            <button v-if="showScrollBottom" class="scroll-bottom-btn" @click="scrollToBottom" title="Scroll to bottom">&#8595;</button>
          </Transition>
          </div>
        </div>
      </Transition>

      <!-- Bottom bar: latest entry -->
      <button class="snackbar-bar" :class="{ 'snackbar-bar--urgent': latest?.type === 'error' || latest?.type === 'warning' }" @click="toggle">
        <span v-if="running" class="snackbar-dot snackbar-dot--pulse" style="background: #26DE81; box-shadow: 0 0 6px #26DE8166"></span>
        <span v-else-if="globalStatus === 'error'" class="snackbar-dot" style="background: #FF6B6B; box-shadow: 0 0 6px #FF6B6B66"></span>
        <span v-else class="snackbar-dot" :style="{ background: entryColor(latest?.type), boxShadow: '0 0 6px ' + entryColor(latest?.type) + '66' }"></span>
        <span v-if="running" class="snackbar-status">STS: pipeline</span>
        <span v-else-if="globalStatus === 'error' && !latest" class="snackbar-status" style="color: #FF6B6B">Pipeline error</span>
        <template v-if="latest">
          <span class="snackbar-icon" :style="{ color: entryColor(latest?.type) }">{{ entryIcon(latest?.type) }}</span>
          <span class="snackbar-text">{{ latest?.message }}</span>
        </template>
        <span v-else-if="!running && globalStatus !== 'error'" class="snackbar-text" style="opacity:0.5">No activity</span>
        <span v-if="count > 1" class="snackbar-badge">{{ count }}</span>
        <svg class="snackbar-chevron" :class="{ open: expanded }" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
      </button>
    </div>
  </Teleport>
</template>

<style scoped>
.snackbar {
  position: fixed;
  bottom: 0;
  left: var(--sidebar-w);
  right: 0;
  z-index: 9000;
  display: flex;
  flex-direction: column;
  transition: left 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.snackbar--collapsed {
  left: var(--sidebar-collapsed);
}

/* ── Bottom bar ── */
.snackbar-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 16px;
  background: var(--bg-darkest);
  border-top: 1px solid var(--border);
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  text-align: left;
  border-left: none;
  border-right: none;
  border-bottom: none;
}
.snackbar-bar:hover {
  background: var(--bg-surface);
}
.snackbar-bar--urgent {
  border-top-color: rgba(255, 107, 107, 0.3);
}

.snackbar-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.snackbar-dot--pulse {
  animation: dot-pulse 1.5s ease-in-out infinite;
}
@keyframes dot-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.snackbar-status {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #26DE81;
}

.snackbar-icon {
  flex-shrink: 0;
  font-size: 11px;
  opacity: 0.7;
}

.snackbar-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
}

.snackbar-badge {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 16px;
  padding: 0 5px;
  font-size: 9px;
  font-weight: 700;
  color: var(--text);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.snackbar-chevron {
  flex-shrink: 0;
  transition: transform 0.2s;
  color: var(--text-muted);
}
.snackbar-chevron.open {
  transform: rotate(180deg);
}

/* ── Expanded feed (log-style) ── */
.snackbar-feed {
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--border);
}

.snackbar-feed-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px 4px;
  background: var(--bg-darkest);
}

.snackbar-feed-title {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--text-muted);
}

.snackbar-feed-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.snackbar-feed-count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 6px;
}

.snackbar-clear {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
  background: none;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 8px;
  cursor: pointer;
  transition: all 0.15s;
}
.snackbar-clear:hover {
  color: var(--accent-error);
  border-color: var(--accent-error);
}

/* ── Log wrapper (relative anchor for scroll-top btn) ── */
.snackbar-log-wrap {
  position: relative;
}

.scroll-top-btn {
  position: absolute;
  bottom: 16px;
  right: 24px;
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  opacity: 0.85;
  transition: all 0.15s;
  z-index: 2;
}
.scroll-top-btn:hover,
.scroll-bottom-btn:hover {
  opacity: 1;
  border-color: var(--accent);
  color: var(--accent);
}

.scroll-bottom-btn {
  position: absolute;
  top: 16px;
  right: 24px;
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  opacity: 0.85;
  transition: all 0.15s;
  z-index: 2;
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* ── Log container (mirrors PipelineLog) ── */
.snackbar-log {
  max-height: 200px;
  overflow-y: auto;
  font-size: 11px;
  line-height: 1.6;
  padding: 8px 12px;
  margin: 0 12px 8px;
  background: var(--bg-darkest);
  border-radius: 8px;
  border: 1px solid var(--border);
  font-family: 'JetBrains Mono', monospace;
}

.log-entry {
  padding: 3px 0;
}

.log-icon {
  opacity: 0.6;
}

.log-msg {
  margin-left: 2px;
}

/* ── Slide transition ── */
.feed-enter-active,
.feed-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}
.feed-enter-from,
.feed-leave-to {
  max-height: 0;
  opacity: 0;
}
.feed-enter-to,
.feed-leave-from {
  max-height: 300px;
  opacity: 1;
}

/* ── Scrollbar ── */
.snackbar-log::-webkit-scrollbar { width: 4px; }
.snackbar-log::-webkit-scrollbar-track { background: transparent; }
.snackbar-log::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
</style>
