<script setup>
import { ref, onMounted } from 'vue'
import ExportCard from '../components/ExportCard.vue'
import {
  useExportLibrary,
  formatBytes,
  formatDuration,
} from '../composables/useExportLibrary.js'

defineOptions({ name: 'ExportLibraryPage' })

const {
  items,
  loading,
  error,
  sortBy,
  filterStyle,
  filterRatio,
  filterDuration,
  filteredItems,
  SORT_OPTIONS,
  DURATION_FILTERS,
  styleOptions,
  ratioOptions,
  stats,
  fetchLibrary,
  downloadVideo,
  downloadZip,
} = useExportLibrary()

const cardRefs = ref([])

function setCardRef(el, idx) {
  if (el) cardRefs.value[idx] = el
}

/** Single-playback: pause all other cards when one starts */
function handlePlay(videoEl) {
  for (const card of cardRefs.value) {
    if (card && card.videoEl !== videoEl) {
      card.stopPlayback()
    }
  }
}

function clearFilters() {
  filterStyle.value = ''
  filterRatio.value = ''
  filterDuration.value = ''
}

const hasActiveFilters = () =>
  filterStyle.value || filterRatio.value || filterDuration.value

onMounted(() => {
  fetchLibrary()
})
</script>

<template>
  <div class="page">
    <!-- ── Header ─────────────────────────────── -->
    <div class="page-header">
      <div>
        <h2 class="page-title">Export Library</h2>
        <p class="page-subtitle">Browse all exported videos and download video or project ZIP</p>
      </div>
      <button class="btn-refresh" :disabled="loading" @click="fetchLibrary">
        <svg
          :class="{ spinning: loading }"
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <polyline points="23 4 23 10 17 10" />
          <polyline points="1 20 1 14 7 14" />
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10" />
          <path d="M20.49 15a9 9 0 0 1-14.85 3.36L1 14" />
        </svg>
        Refresh
      </button>
    </div>

    <!-- ── Error ──────────────────────────────── -->
    <div v-if="error" class="error-banner">
      {{ error }}
      <button class="error-retry" @click="fetchLibrary">Retry</button>
    </div>

    <!-- ── Info bar ───────────────────────────── -->
    <div class="info-bar">
      <div class="info-row">
        <span class="info-source">Source: <code>output/exports</code></span>
        <span class="info-count">{{ items.length }} videos</span>
      </div>

      <!-- Filter toolbar -->
      <div v-if="items.length > 0" class="filter-toolbar">
        <div class="filter-controls">
          <select v-model="sortBy" class="filter-select">
            <option v-for="opt in SORT_OPTIONS" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>

          <select v-model="filterStyle" class="filter-select">
            <option value="">All styles</option>
            <option v-for="s in styleOptions.filter(v => v)" :key="s" :value="s">
              {{ s }}
            </option>
          </select>

          <select v-model="filterRatio" class="filter-select">
            <option value="">All ratios</option>
            <option v-for="r in ratioOptions.filter(v => v)" :key="r" :value="r">
              {{ r }}
            </option>
          </select>

          <select v-model="filterDuration" class="filter-select">
            <option v-for="d in DURATION_FILTERS" :key="d.value" :value="d.value">
              {{ d.label }}
            </option>
          </select>

          <button v-if="hasActiveFilters()" class="btn-clear-filters" @click="clearFilters">
            Clear
          </button>
        </div>

        <span class="filter-count">
          {{ filteredItems.length }} of {{ items.length }} shown
        </span>
      </div>
    </div>

    <!-- ── Stats ──────────────────────────────── -->
    <div v-if="items.length > 0" class="stats-section">
      <div class="stat-card">
        <span class="stat-value">{{ formatDuration(stats.totalDuration) }}</span>
        <span class="stat-label">Total Duration</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ formatBytes(stats.totalSize) }}</span>
        <span class="stat-label">Total Size</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ stats.today }}</span>
        <span class="stat-label">Today</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ stats.week }}</span>
        <span class="stat-label">This Week</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ stats.month }}</span>
        <span class="stat-label">This Month</span>
      </div>
      <div v-if="stats.topStyles.length" class="stat-card stat-card-wide">
        <span class="stat-label">Top Styles</span>
        <div class="stat-tags">
          <span v-for="[style, count] in stats.topStyles" :key="style" class="stat-tag">
            {{ style }} <em>{{ count }}</em>
          </span>
        </div>
      </div>
      <div v-if="stats.topRatios.length" class="stat-card stat-card-wide">
        <span class="stat-label">Top Ratios</span>
        <div class="stat-tags">
          <span v-for="[ratio, count] in stats.topRatios" :key="ratio" class="stat-tag">
            {{ ratio }} <em>{{ count }}</em>
          </span>
        </div>
      </div>
    </div>

    <!-- ── Loading ────────────────────────────── -->
    <div v-if="loading && items.length === 0" class="loading-state">
      <div class="spinner" />
      <span>Loading export library...</span>
    </div>

    <!-- ── Empty ──────────────────────────────── -->
    <div v-else-if="!loading && items.length === 0 && !error" class="empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/>
        <line x1="7" y1="2" x2="7" y2="22"/>
        <line x1="17" y1="2" x2="17" y2="22"/>
        <line x1="2" y1="12" x2="22" y2="12"/>
        <line x1="2" y1="7" x2="7" y2="7"/>
        <line x1="2" y1="17" x2="7" y2="17"/>
        <line x1="17" y1="7" x2="22" y2="7"/>
        <line x1="17" y1="17" x2="22" y2="17"/>
      </svg>
      <p>No exports found. Export a video from the Editor to see it here.</p>
    </div>

    <!-- ── No filter results ──────────────────── -->
    <div v-else-if="!loading && items.length > 0 && filteredItems.length === 0" class="empty-state">
      <p>No exports match your current filters.</p>
      <button class="btn-clear-filters" @click="clearFilters">Clear Filters</button>
    </div>

    <!-- ── Grid ───────────────────────────────── -->
    <div v-else class="export-grid">
      <ExportCard
        v-for="(item, idx) in filteredItems"
        :key="item.project_id + item.video_relpath"
        :item="item"
        :ref="(el) => setCardRef(el, idx)"
        @play="handlePlay"
        @download-video="downloadVideo"
        @download-zip="downloadZip"
      />
    </div>
  </div>
</template>

<style scoped>
.page {
  padding: 32px 24px;
  max-width: 1152px;
  margin: 0 auto;
}

/* ── Header ─────────────────────────── */

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}

.page-title {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 700;
  color: var(--text);
  margin: 0 0 4px;
}

.page-subtitle {
  font-size: 14px;
  color: var(--text-secondary);
}

.btn-refresh {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 600;
  background: var(--bg-surface);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  flex-shrink: 0;
}

.btn-refresh:hover:not(:disabled) {
  border-color: var(--border-hover);
  background: var(--bg-surface-hover);
}

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinning {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── Error ───────────────────────────── */

.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  margin-bottom: 20px;
  background: rgba(255, 107, 107, 0.08);
  border: 1px solid rgba(255, 107, 107, 0.25);
  border-radius: 10px;
  color: var(--accent-error);
  font-size: 13px;
}

.error-retry {
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 600;
  background: transparent;
  border: 1px solid var(--accent-error);
  color: var(--accent-error);
  border-radius: 6px;
  cursor: pointer;
}

.error-retry:hover {
  background: rgba(255, 107, 107, 0.1);
}

/* ── Info bar ────────────────────────── */

.info-bar {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 18px;
  margin-bottom: 20px;
}

.info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.info-source {
  font-size: 13px;
  color: var(--text-secondary);
}

.info-source code {
  font-family: var(--font-mono);
  color: var(--text);
  background: var(--bg-dark);
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 12px;
}

.info-count {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--accent);
  font-weight: 600;
}

/* ── Filter toolbar ──────────────────── */

.filter-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
  flex-wrap: wrap;
}

.filter-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-select {
  padding: 6px 10px;
  font-size: 12px;
  font-family: var(--font-body);
  background: var(--bg-dark);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s;
}

.filter-select:hover,
.filter-select:focus {
  border-color: var(--border-hover);
}

.btn-clear-filters {
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  background: transparent;
  color: var(--accent);
  border: 1px solid var(--accent);
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-clear-filters:hover {
  background: var(--accent-dim);
}

.filter-count {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
  flex-shrink: 0;
}

/* ── Stats ───────────────────────────── */

.stats-section {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  flex-wrap: wrap;
}

.stat-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 110px;
}

.stat-card-wide {
  min-width: 180px;
  flex: 1;
}

.stat-value {
  font-family: var(--font-mono);
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
}

.stat-label {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
}

.stat-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.stat-tag {
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--bg-dark);
  padding: 2px 8px;
  border-radius: 4px;
  font-family: var(--font-mono);
}

.stat-tag em {
  font-style: normal;
  color: var(--accent);
  margin-left: 3px;
}

/* ── Loading / Empty ─────────────────── */

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 64px 20px;
  color: var(--text-muted);
  font-size: 14px;
  text-align: center;
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

/* ── Grid ────────────────────────────── */

.export-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}
</style>
