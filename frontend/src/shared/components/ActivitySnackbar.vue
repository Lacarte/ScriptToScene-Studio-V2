<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useActivityFeed } from '@/shared/composables/useActivityFeed.js'
import { useAppStore } from '@/shared/stores/appStore.js'
import { usePipeline } from '@/features/pipeline/composables/usePipeline.js'
import { ALL_STEPS } from '@/features/pipeline/constants/steps.js'
import { stepColor, stepTextColor } from '@/features/pipeline/constants/colors.js'

defineOptions({ name: 'ActivitySnackbar' })

const { entries, latest, count, clear, urgentPing } = useActivityFeed()
const app = useAppStore()
const {
  running,
  stopping,
  globalStatus,
  stepStatus,
  sceneNotifications,
  log,
  failedStep,
  stoppedStep,
} = usePipeline()

const expanded = ref(false)
const confirmingClear = ref(false)
const sceneOpen = ref(true)
const logOpen = ref(false)
const listEl = ref(null)
const showScrollTop = ref(false)
const showScrollBottom = ref(false)

function onLogScroll() {
  if (!listEl.value) return
  const el = listEl.value
  showScrollTop.value = el.scrollTop > 80
  showScrollBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight > 80
}

function scrollToTop() {
  if (listEl.value) listEl.value.scrollTo({ top: 0, behavior: 'smooth' })
}

function scrollToBottom() {
  if (listEl.value) listEl.value.scrollTo({ top: listEl.value.scrollHeight, behavior: 'smooth' })
}

function toggle() {
  expanded.value = !expanded.value
}

function handleClear() {
  if (!confirmingClear.value) {
    confirmingClear.value = true
    return
  }
  confirmingClear.value = false
  clear()
  expanded.value = false
}

function cancelClear() {
  confirmingClear.value = false
}

function minimize() {
  expanded.value = false
}

function stripProjectPrefix(message) {
  return String(message || '').replace(/^\[[^\]]+\]\s*/, '').trim()
}

function extractProjectId(event) {
  if (!event) return ''
  if (event.project_id) return event.project_id
  const match = String(event.message || '').match(/\[(pp_[^\]]+)\]/)
  return match ? match[1] : ''
}

function entryIcon(type) {
  if (type === 'error') return '\u2717'
  if (type === 'success') return '\u2713'
  if (type === 'warning') return '\u26A0'
  return '\u2192'
}

function entryColor(type) {
  if (type === 'error') return '#FF6B6B'
  if (type === 'success') return '#26DE81'
  if (type === 'warning') return '#FFB347'
  if (type === 'info') return '#56CCF2'
  return 'var(--text-muted)'
}

function timeStr(value) {
  if (!value) return ''
  const date = value instanceof Date ? value : new Date(value)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function stepIcon(step) {
  const status = stepStatus.value?.[step.id] || 'pending'
  if (status === 'done') return '\u2713'
  if (status === 'stopped') return '\u23F8'
  if (status === 'skipped') return '\u2014'
  if (status === 'error') return '\u2717'
  return step.icon
}

function sceneBadge(step) {
  return step === 'assets' ? 'VIDEO' : 'IMAGE'
}

function latestSceneProgress(stepId) {
  const items = sceneNotifications.value || []
  for (let i = items.length - 1; i >= 0; i--) {
    if (items[i]?.step === stepId) return items[i]
  }
  return null
}

const isActive = computed(() => running.value || globalStatus.value === 'error' || globalStatus.value === 'stopped')
const hasEntries = computed(() => count.value > 0 || isActive.value)
const latestEntryMessage = computed(() => stripProjectPrefix(latest.value?.message || ''))
const latestPipelineEvent = computed(() => {
  const items = log.value || []
  return items.length ? items[items.length - 1] : null
})

const hasLiveOverview = computed(() => (
  running.value ||
  globalStatus.value === 'error' ||
  globalStatus.value === 'stopped' ||
  globalStatus.value === 'done' ||
  Object.keys(stepStatus.value || {}).length > 0
))

const activeProjectId = computed(() => extractProjectId(latestPipelineEvent.value))

const activeStepId = computed(() => {
  const statuses = stepStatus.value || {}

  if (running.value) {
    const runningStep = ALL_STEPS.find((step) => statuses[step.id] === 'running')
    return runningStep?.id || latestPipelineEvent.value?.step || ''
  }

  if (globalStatus.value === 'error') {
    const erroredStep = ALL_STEPS.find((step) => statuses[step.id] === 'error')
    return failedStep.value || erroredStep?.id || latestPipelineEvent.value?.error_step || latestPipelineEvent.value?.step || ''
  }

  if (globalStatus.value === 'stopped') {
    const stopped = ALL_STEPS.find((step) => statuses[step.id] === 'stopped')
    return stoppedStep.value || stopped?.id || latestPipelineEvent.value?.resume_from || latestPipelineEvent.value?.stopped_step || ''
  }

  const completed = [...ALL_STEPS].reverse().find((step) => statuses[step.id] === 'done')
  return completed?.id || ''
})

const activeStep = computed(() => ALL_STEPS.find((step) => step.id === activeStepId.value) || null)
const activeStepIndex = computed(() => ALL_STEPS.findIndex((step) => step.id === activeStepId.value))
const stepsCompleted = computed(() => ALL_STEPS.filter((step) => stepStatus.value?.[step.id] === 'done').length)

const stepPercent = computed(() => {
  const match = latestPipelineEvent.value?.message?.match(/(\d+)%/)
  return match ? parseInt(match[1], 10) : -1
})

const overviewProgress = computed(() => {
  const chunk = 100 / ALL_STEPS.length
  if (stepPercent.value >= 0 && activeStepIndex.value >= 0) {
    return Math.max(0, Math.min(100, Math.round(activeStepIndex.value * chunk + (stepPercent.value / 100) * chunk)))
  }
  if (running.value && activeStepIndex.value >= 0) {
    return Math.max(8, Math.min(96, Math.round(((activeStepIndex.value + 0.35) / ALL_STEPS.length) * 100)))
  }
  return Math.max(0, Math.min(100, Math.round((stepsCompleted.value / ALL_STEPS.length) * 100)))
})

const currentStepOrdinal = computed(() => {
  if (activeStepIndex.value < 0) return stepsCompleted.value
  return running.value ? activeStepIndex.value + 1 : Math.max(stepsCompleted.value, activeStepIndex.value + 1)
})

const pipelineStateLabel = computed(() => {
  if (stopping.value) return 'Stopping'
  if (running.value) return 'Running'
  if (globalStatus.value === 'error') return 'Attention'
  if (globalStatus.value === 'stopped') return 'Paused'
  if (globalStatus.value === 'done') return 'Complete'
  return 'Idle'
})

const pipelineStateClass = computed(() => {
  if (stopping.value) return 'is-stopping'
  if (running.value) return 'is-running'
  if (globalStatus.value === 'error') return 'is-error'
  if (globalStatus.value === 'stopped') return 'is-paused'
  if (globalStatus.value === 'done') return 'is-complete'
  return 'is-idle'
})

const currentStepMessage = computed(() => stripProjectPrefix(latestPipelineEvent.value?.message || ''))

const statusHeadline = computed(() => {
  if (running.value && activeStep.value) return activeStep.value.label
  if (globalStatus.value === 'error' && activeStep.value) return `${activeStep.value.label} needs attention`
  if (globalStatus.value === 'stopped' && activeStep.value) return `${activeStep.value.label} paused`
  if (globalStatus.value === 'done') return 'Pipeline complete'
  return latestEntryMessage.value ? 'Recent activity' : 'No activity'
})

const heroSubline = computed(() => {
  if (running.value) return currentStepMessage.value || 'Pipeline is actively processing.'
  if (globalStatus.value === 'error') return currentStepMessage.value || 'The latest run ended with an error.'
  if (globalStatus.value === 'stopped') return currentStepMessage.value || 'The latest run was stopped and can be resumed.'
  if (globalStatus.value === 'done') return currentStepMessage.value || 'The latest run finished successfully.'
  return latestEntryMessage.value || 'No active work right now.'
})

const imageProgress = computed(() => latestSceneProgress('storyboard'))
const videoProgress = computed(() => latestSceneProgress('assets'))

const sceneStats = computed(() => {
  const stats = []
  if (imageProgress.value) {
    stats.push({ key: 'images', label: 'Images', ready: imageProgress.value.scene || 0, total: imageProgress.value.total || 0, tone: 'image' })
  }
  if (videoProgress.value) {
    stats.push({ key: 'videos', label: 'Videos', ready: videoProgress.value.scene || 0, total: videoProgress.value.total || 0, tone: 'video' })
  }
  if (sceneNotifications.value.length) {
    stats.push({ key: 'events', label: 'Events', ready: sceneNotifications.value.length, total: 0, tone: 'neutral' })
  }
  return stats
})

const sceneSummaryText = computed(() => {
  const parts = []
  if (imageProgress.value?.total) parts.push(`Images ${imageProgress.value.scene}/${imageProgress.value.total}`)
  if (videoProgress.value?.total) parts.push(`Videos ${videoProgress.value.scene}/${videoProgress.value.total}`)
  return parts.join(' / ')
})

const showSceneSection = computed(() => (
  sceneNotifications.value.length > 0 ||
  (running.value && (activeStepId.value === 'storyboard' || activeStepId.value === 'assets'))
))

const recentSceneEvents = computed(() => [...(sceneNotifications.value || [])].slice(-5).reverse())

const scenePlaceholder = computed(() => {
  if (activeStepId.value === 'storyboard') return 'Waiting for the first storyboard image.'
  if (activeStepId.value === 'assets') return 'Waiting for the first animator video.'
  return 'No scene events yet.'
})

const snackbarStatusText = computed(() => {
  if (running.value && activeStep.value) return `${activeStep.value.label} ${currentStepOrdinal.value}/8`
  if (globalStatus.value === 'error' && activeStep.value) return `${activeStep.value.label} error`
  if (globalStatus.value === 'stopped' && activeStep.value) return `${activeStep.value.label} paused`
  if (globalStatus.value === 'done') return 'Pipeline complete'
  return ''
})

const snackbarBarText = computed(() => {
  if (running.value) {
    if (currentStepMessage.value && sceneSummaryText.value && (activeStepId.value === 'storyboard' || activeStepId.value === 'assets')) {
      return `${currentStepMessage.value} / ${sceneSummaryText.value}`
    }
    return currentStepMessage.value || sceneSummaryText.value || 'Pipeline running'
  }
  if (globalStatus.value === 'error' || globalStatus.value === 'stopped') return heroSubline.value
  return latestEntryMessage.value || 'No activity'
})

watch(urgentPing, () => {
  expanded.value = true
  sceneOpen.value = true
  logOpen.value = true
  nextTick(() => {
    if (listEl.value) listEl.value.scrollTop = 0
  })
})

watch(count, () => {
  if (expanded.value && (logOpen.value || !hasLiveOverview.value)) {
    nextTick(() => {
      if (listEl.value) listEl.value.scrollTop = 0
    })
  }
})

watch(() => sceneNotifications.value.length, (next, prev) => {
  if (next > prev && expanded.value) sceneOpen.value = true
})

watch(() => running.value, (isRunning) => {
  if (isRunning) {
    sceneOpen.value = true
    logOpen.value = false
  }
})
</script>

<template>
  <Teleport to="body">
    <div v-if="hasEntries" class="snackbar" :class="{ 'snackbar--collapsed': app.sidebarCollapsed }">
      <Transition name="feed">
        <div v-if="expanded" class="snackbar-feed">
          <div class="snackbar-feed-header">
            <div class="snackbar-feed-heading">
              <span class="snackbar-feed-title">Activity</span>
              <span v-if="hasLiveOverview" class="activity-state-pill" :class="pipelineStateClass">{{ pipelineStateLabel }}</span>
            </div>
            <div class="snackbar-feed-actions">
              <span class="snackbar-feed-count">{{ count }}</span>
              <template v-if="confirmingClear">
                <span class="snackbar-confirm-label">Clear all?</span>
                <button class="snackbar-confirm-yes" @click="handleClear">Yes</button>
                <button class="snackbar-confirm-no" @click="cancelClear">No</button>
              </template>
              <button v-else class="snackbar-clear" @click="handleClear">Clear</button>
              <button class="snackbar-minimize" @click="minimize" title="Minimize">&minus;</button>
            </div>
          </div>

          <div class="snackbar-feed-body">
            <section v-if="hasLiveOverview" class="activity-panel activity-panel--hero">
              <div class="activity-hero-top">
                <span class="activity-meta-pill">{{ stepsCompleted }}/8 done</span>
                <span v-if="activeProjectId" class="activity-meta-pill activity-meta-pill--project">{{ activeProjectId }}</span>
                <span v-if="sceneSummaryText" class="activity-meta-pill activity-meta-pill--quiet">{{ sceneSummaryText }}</span>
              </div>

              <div class="activity-hero-main">
                <div class="activity-hero-copy">
                  <div class="activity-hero-title-row">
                    <h4 class="activity-hero-title">{{ statusHeadline }}</h4>
                    <span v-if="activeStep" class="activity-hero-step">{{ currentStepOrdinal }}/8</span>
                  </div>
                  <p class="activity-hero-desc">{{ heroSubline }}</p>
                </div>
                <span class="activity-progress-label">{{ overviewProgress }}%</span>
              </div>

              <div class="activity-track">
                <div class="activity-track-fill" :style="{ width: overviewProgress + '%' }"></div>
              </div>

              <div class="activity-steps-strip">
                <div
                  v-for="step in ALL_STEPS"
                  :key="step.id"
                  class="activity-step"
                  :class="{
                    'activity-step--active': running && activeStepId === step.id,
                    'activity-step--done': stepStatus[step.id] === 'done',
                    'activity-step--error': stepStatus[step.id] === 'error',
                    'activity-step--paused': stepStatus[step.id] === 'stopped',
                  }"
                >
                  <span class="activity-step-icon" :style="{ borderColor: stepColor(stepStatus[step.id]), color: stepTextColor(stepStatus[step.id]) }">{{ stepIcon(step) }}</span>
                  <span class="activity-step-label">{{ step.label }}</span>
                </div>
              </div>
            </section>

            <section v-if="showSceneSection" class="activity-panel">
              <button class="activity-section-toggle" @click="sceneOpen = !sceneOpen">
                <div class="activity-section-heading">
                  <span class="activity-section-title">Scene Progress</span>
                  <span class="activity-section-sub">{{ sceneSummaryText || scenePlaceholder }}</span>
                </div>
                <svg class="activity-section-chevron" :class="{ open: sceneOpen }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>

              <div v-show="sceneOpen && (sceneStats.length || recentSceneEvents.length)" class="activity-section-body">
                <div v-if="sceneStats.length" class="activity-stats">
                  <div v-for="stat in sceneStats" :key="stat.key" class="activity-stat" :class="'activity-stat--' + stat.tone">
                    <span class="activity-stat-label">{{ stat.label }}</span>
                    <span class="activity-stat-value">{{ stat.total ? `${stat.ready}/${stat.total}` : stat.ready }}</span>
                  </div>
                </div>

                <div v-if="recentSceneEvents.length" class="activity-scene-list">
                  <div v-for="entry in recentSceneEvents" :key="entry.id" class="activity-scene-item" :class="'activity-scene-item--' + entry.step">
                    <span class="activity-scene-icon">{{ entry.type === 'error' ? '\u2717' : '\u2713' }}</span>
                    <span class="activity-scene-badge">{{ sceneBadge(entry.step) }}</span>
                    <span class="activity-scene-msg">{{ entry.message }}</span>
                    <span class="activity-scene-time">{{ timeStr(entry.time) }}</span>
                  </div>
                </div>
              </div>
            </section>

            <section class="activity-panel">
              <button class="activity-section-toggle" @click="logOpen = !logOpen">
                <div class="activity-section-heading">
                  <span class="activity-section-title">Recent Activity</span>
                  <span class="activity-section-sub">{{ latestEntryMessage || 'No logged events yet.' }}</span>
                </div>
                <div class="activity-section-right">
                  <span class="activity-section-count">{{ count }}</span>
                  <svg class="activity-section-chevron" :class="{ open: logOpen || !hasLiveOverview }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </div>
              </button>

              <div v-show="logOpen || !hasLiveOverview" class="snackbar-log-wrap">
                <div class="snackbar-log" ref="listEl" @scroll="onLogScroll">
                  <div v-for="entry in entries" :key="entry.id" class="log-entry" :style="{ color: entryColor(entry.type) }">
                    <span class="log-icon">{{ entryIcon(entry.type) }}</span>
                    <span class="log-msg">{{ stripProjectPrefix(entry.message) }}</span>
                    <span class="log-time">{{ timeStr(entry.time) }}</span>
                  </div>
                </div>

                <Transition name="fade">
                  <button v-if="showScrollTop" class="scroll-top-btn" @click="scrollToTop" title="Scroll to top">&#8593;</button>
                </Transition>
                <Transition name="fade">
                  <button v-if="showScrollBottom" class="scroll-bottom-btn" @click="scrollToBottom" title="Scroll to bottom">&#8595;</button>
                </Transition>
              </div>
            </section>
          </div>
        </div>
      </Transition>

      <button class="snackbar-bar" :class="{ 'snackbar-bar--urgent': latest?.type === 'error' || latest?.type === 'warning' }" @click="toggle">
        <span v-if="running" class="snackbar-dot snackbar-dot--pulse" style="background: #26DE81; box-shadow: 0 0 6px #26DE8166"></span>
        <span v-else-if="globalStatus === 'error'" class="snackbar-dot" style="background: #FF6B6B; box-shadow: 0 0 6px #FF6B6B66"></span>
        <span v-else class="snackbar-dot" :style="{ background: entryColor(latest?.type), boxShadow: '0 0 6px ' + entryColor(latest?.type) + '66' }"></span>

        <span v-if="snackbarStatusText" class="snackbar-status" :class="{ 'snackbar-status--error': globalStatus === 'error' }">{{ snackbarStatusText }}</span>

        <template v-if="latest || hasLiveOverview">
          <span class="snackbar-icon" :style="{ color: entryColor(latest?.type) }">{{ entryIcon(latest?.type || 'pipeline') }}</span>
          <span class="snackbar-text">{{ snackbarBarText }}</span>
        </template>
        <span v-else class="snackbar-text snackbar-text--idle">No activity</span>

        <span v-if="count > 1" class="snackbar-badge">{{ count }}</span>
        <svg class="snackbar-chevron" :class="{ open: expanded }" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="6 9 12 15 18 9" />
        </svg>
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

.snackbar-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 16px;
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
  border-top-color: rgba(255, 107, 107, 0.32);
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
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #26DE81;
}

.snackbar-status--error {
  color: #FF6B6B;
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

.snackbar-text--idle {
  opacity: 0.5;
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

.snackbar-feed {
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg-darkest) 94%, black);
  box-shadow: 0 -12px 30px rgba(0, 0, 0, 0.28);
}

.snackbar-feed-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px 8px;
  background: var(--bg-darkest);
}

.snackbar-feed-heading {
  display: flex;
  align-items: center;
  gap: 10px;
}

.snackbar-feed-title {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.14em;
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

.snackbar-confirm-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  font-weight: 600;
  color: var(--accent-error, #FF6B6B);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.snackbar-confirm-yes,
.snackbar-confirm-no {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 8px;
  cursor: pointer;
  transition: all 0.15s;
}

.snackbar-confirm-yes {
  color: var(--accent-error, #FF6B6B);
  background: rgba(255, 107, 107, 0.1);
  border-color: rgba(255, 107, 107, 0.4);
}
.snackbar-confirm-yes:hover {
  background: rgba(255, 107, 107, 0.2);
  border-color: var(--accent-error, #FF6B6B);
}

.snackbar-confirm-no {
  color: var(--text-muted);
  background: none;
}
.snackbar-confirm-no:hover {
  color: var(--text);
  border-color: var(--text-muted);
}

.snackbar-minimize {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-muted);
  background: none;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0 7px;
  line-height: 18px;
  cursor: pointer;
  transition: all 0.15s;
}
.snackbar-minimize:hover {
  color: var(--text);
  border-color: var(--text-muted);
}

.snackbar-feed-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: min(72vh, 560px);
  overflow-y: auto;
  padding: 0 12px 12px;
}

.snackbar-feed-body::-webkit-scrollbar {
  width: 6px;
}

.snackbar-feed-body::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 999px;
}

.activity-panel {
  background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01));
  border: 1px solid color-mix(in srgb, var(--border) 88%, transparent);
  border-radius: 12px;
  padding: 12px;
}

.activity-panel--hero {
  padding: 14px;
}

.activity-state-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 22px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  border: 1px solid var(--border);
}

.activity-state-pill.is-running {
  color: #26DE81;
  border-color: rgba(38, 222, 129, 0.35);
  background: rgba(38, 222, 129, 0.12);
}

.activity-state-pill.is-stopping,
.activity-state-pill.is-paused {
  color: #FFB347;
  border-color: rgba(255, 179, 71, 0.35);
  background: rgba(255, 179, 71, 0.12);
}

.activity-state-pill.is-error {
  color: #FF6B6B;
  border-color: rgba(255, 107, 107, 0.35);
  background: rgba(255, 107, 107, 0.12);
}

.activity-state-pill.is-complete {
  color: #56CCF2;
  border-color: rgba(86, 204, 242, 0.34);
  background: rgba(86, 204, 242, 0.12);
}

.activity-state-pill.is-idle {
  color: var(--text-muted);
  background: rgba(255,255,255,0.03);
}

.activity-hero-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.activity-meta-pill {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 9px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-secondary);
  background: rgba(255,255,255,0.04);
  border: 1px solid color-mix(in srgb, var(--border) 86%, transparent);
}

.activity-meta-pill--project {
  color: var(--accent);
}

.activity-meta-pill--quiet {
  color: var(--text-muted);
}

.activity-hero-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.activity-hero-copy {
  min-width: 0;
}

.activity-hero-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 4px;
}

.activity-hero-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
}

.activity-hero-step,
.activity-progress-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  font-weight: 700;
  color: var(--accent);
  flex-shrink: 0;
}

.activity-hero-desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
}

.activity-track {
  position: relative;
  height: 8px;
  margin-top: 12px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255,255,255,0.05);
}

.activity-track-fill {
  position: absolute;
  inset: 0 auto 0 0;
  border-radius: inherit;
  background: linear-gradient(90deg, #26DE81, #56CCF2);
  box-shadow: 0 0 20px rgba(86, 204, 242, 0.25);
}

.activity-steps-strip {
  display: flex;
  align-items: flex-start;
  gap: 0;
  padding-top: 14px;
}

.activity-step {
  position: relative;
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  padding: 0;
  background: none;
  border: none;
}

.activity-step:not(:last-child)::after {
  content: '';
  position: absolute;
  top: 7px;
  left: calc(50% + 10px);
  right: calc(-50% + 10px);
  height: 1px;
  background: color-mix(in srgb, var(--border) 70%, transparent);
  z-index: 0;
}

.activity-step--done:not(:last-child)::after,
.activity-step--active:not(:last-child)::after {
  background: linear-gradient(90deg, rgba(38, 222, 129, 0.55), rgba(86, 204, 242, 0.35));
}

.activity-step-icon {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: 1px solid var(--border);
  border-radius: 50%;
  font-size: 9px;
  line-height: 1;
  background: var(--bg-darkest);
}

.activity-step--active .activity-step-icon {
  box-shadow: 0 0 0 3px rgba(86, 204, 242, 0.14);
}

.activity-step-label {
  max-width: 100%;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.activity-step--active .activity-step-label,
.activity-step--done .activity-step-label {
  color: var(--text-secondary);
}

.activity-step--error .activity-step-label {
  color: #FF6B6B;
}

.activity-step--paused .activity-step-label {
  color: #FFB347;
}

.activity-section-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 0;
  background: none;
  border: none;
  color: inherit;
  text-align: left;
  cursor: pointer;
  gap: 10px;
}

.activity-section-heading {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.activity-section-title {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--text-muted);
}

.activity-section-sub {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.activity-section-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.activity-section-count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  font-weight: 700;
  color: var(--text-muted);
  background: rgba(255,255,255,0.04);
  border: 1px solid color-mix(in srgb, var(--border) 86%, transparent);
  border-radius: 999px;
  padding: 2px 8px;
}

.activity-section-chevron {
  color: var(--text-muted);
  transition: transform 0.2s ease, color 0.15s ease;
  flex-shrink: 0;
}

.activity-section-toggle:hover .activity-section-chevron {
  color: var(--accent);
}

.activity-section-chevron.open {
  transform: rotate(180deg);
}

.activity-section-body {
  margin-top: 8px;
}

.activity-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.activity-stat {
  min-width: 76px;
  padding: 6px 9px;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--border) 86%, transparent);
  background: rgba(255,255,255,0.03);
}

.activity-stat--image {
  background: rgba(86, 204, 242, 0.08);
}

.activity-stat--video {
  background: rgba(38, 222, 129, 0.08);
}

.activity-stat-label {
  display: block;
  margin-bottom: 2px;
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

.activity-stat-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
}

.activity-scene-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.activity-scene-item {
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(0,0,0,0.18);
  border: 1px solid color-mix(in srgb, var(--border) 82%, transparent);
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
}

.activity-scene-item--storyboard {
  border-color: rgba(86, 204, 242, 0.2);
}

.activity-scene-item--assets {
  border-color: rgba(38, 222, 129, 0.2);
}

.activity-scene-icon {
  color: #26DE81;
}

.activity-scene-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 52px;
  padding: 2px 6px;
  border-radius: 999px;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--text);
  background: rgba(255,255,255,0.06);
}

.activity-scene-msg {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
}

.activity-scene-time {
  color: var(--text-muted);
  font-size: 10px;
}

.activity-empty {
  padding: 10px 0 2px;
  font-size: 12px;
  color: var(--text-muted);
}

.snackbar-log-wrap {
  position: relative;
  margin-top: 12px;
}

.snackbar-log {
  max-height: 220px;
  overflow-y: auto;
  padding: 8px 12px;
  background: rgba(0,0,0,0.2);
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--border) 84%, transparent);
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  line-height: 1.55;
}

.snackbar-log::-webkit-scrollbar {
  width: 4px;
}

.snackbar-log::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 999px;
}

.log-entry {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  padding: 5px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 38%, transparent);
}

.log-entry:last-child {
  border-bottom: none;
}

.log-icon {
  opacity: 0.7;
}

.log-msg {
  min-width: 0;
  color: var(--text-secondary);
}

.log-time {
  color: var(--text-muted);
  font-size: 10px;
}

.scroll-top-btn,
.scroll-bottom-btn {
  position: absolute;
  right: 14px;
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
  opacity: 0.88;
  transition: all 0.15s;
  z-index: 2;
}

.scroll-top-btn {
  bottom: 16px;
}

.scroll-bottom-btn {
  top: 16px;
}

.scroll-top-btn:hover,
.scroll-bottom-btn:hover {
  opacity: 1;
  border-color: var(--accent);
  color: var(--accent);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.feed-enter-active,
.feed-leave-active {
  transition: all 0.22s ease;
  overflow: hidden;
}

.feed-enter-from,
.feed-leave-to {
  max-height: 0;
  opacity: 0;
}

.feed-enter-to,
.feed-leave-from {
  max-height: 640px;
  opacity: 1;
}

@media (max-width: 900px) {
  .activity-hero-main {
    flex-direction: column;
  }

  .activity-progress-label {
    align-self: flex-start;
  }

  .activity-scene-item {
    grid-template-columns: auto auto minmax(0, 1fr);
  }

  .activity-scene-time {
    grid-column: 3;
    justify-self: start;
  }
}

@media (max-width: 640px) {
  .snackbar-bar {
    padding-inline: 12px;
  }

  .snackbar-feed-header,
  .snackbar-feed-body {
    padding-inline: 10px;
  }

  .activity-panel,
  .activity-panel--hero {
    padding: 11px;
  }

  .activity-steps-strip {
    padding-top: 12px;
  }

  .activity-step-label {
    font-size: 8px;
  }
}
</style>
