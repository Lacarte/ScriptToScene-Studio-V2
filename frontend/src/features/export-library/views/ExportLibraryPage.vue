<script setup>
import { ref, computed, onMounted } from 'vue'
import ExportCard from '../components/ExportCard.vue'
import { useExportLibrary } from '../composables/useExportLibrary.js'
import { formatBytes, timeAgo, fmtDuration } from '@/shared/utils/format.js'

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

const hasActiveFilters = computed(() =>
  filterStyle.value || filterRatio.value || filterDuration.value
)

onMounted(() => {
  fetchLibrary()
})


// --- Style helpers ---
function styleLabel(id) {
  if (!id) return ''
  return id.replace(/[_-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

function styleColor(id) {
  if (!id) return 'var(--text-muted)'
  const map = {
    cinematic_realistic: '#4ECDC4',
    anime_manga: '#FF6B6B',
    watercolor_dreamy: '#A78BFA',
    pop_art_bold: '#FFB347',
    minimalist_clean: '#56CCF2',
  }
  return map[id] || 'var(--text-muted)'
}

// --- Extended stats matching original ---
const extendedStats = computed(() => {
  const all = items.value
  const now = Date.now()
  const DAY = 86400000

  const totalDur = all.reduce((s, i) => s + (i.duration || 0), 0)
  const totalSize = all.reduce((s, i) => s + (i.size_bytes || 0), 0)
  const today = all.filter(i => i.modified_at && (now - new Date(i.modified_at).getTime()) < DAY).length
  const week = all.filter(i => i.modified_at && (now - new Date(i.modified_at).getTime()) < 7 * DAY).length
  const month = all.filter(i => i.modified_at && (now - new Date(i.modified_at).getTime()) < 30 * DAY).length

  // Top style
  const styleCounts = {}
  all.forEach(i => { if (i.style) styleCounts[i.style] = (styleCounts[i.style] || 0) + 1 })
  const topStyle = Object.entries(styleCounts).sort((a, b) => b[1] - a[1])[0]

  // Top ratio
  const ratioCounts = {}
  all.forEach(i => {
    const r = i.video_ratio || i.ratio
    if (r) ratioCounts[r] = (ratioCounts[r] || 0) + 1
  })
  const topRatio = Object.entries(ratioCounts).sort((a, b) => b[1] - a[1])[0]

  // Avg per week
  const dates = all.map(i => new Date(i.modified_at).getTime()).filter(Boolean)
  const firstExport = dates.length ? Math.min(...dates) : now
  const daysSinceFirst = Math.max(1, Math.ceil((now - firstExport) / DAY))
  const avgPerWeek = all.length >= 2 ? (all.length / (daysSinceFirst / 7)).toFixed(1) : '—'

  // Streak
  const daySet = new Set()
  all.forEach(i => {
    if (i.modified_at) {
      const d = new Date(i.modified_at)
      daySet.add(`${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`)
    }
  })
  let streak = 0
  for (let d = 0; d < 365; d++) {
    const dt = new Date(now - d * DAY)
    const key = `${dt.getFullYear()}-${dt.getMonth()}-${dt.getDate()}`
    if (daySet.has(key)) { streak++ } else if (d > 0) break
  }

  return {
    total: all.length,
    today,
    week,
    month,
    avgPerWeek,
    streak,
    totalDur,
    totalSize,
    topStyle,
    topRatio,
  }
})
</script>

<template>
  <div class="export-page">
    <!-- Header -->
    <div class="page-header">
      <div>
        <h2 class="page-title">Export Library</h2>
        <p class="page-subtitle">Browse all exported videos and download video or project ZIP</p>
      </div>
      <button class="action-btn" style="padding:7px 14px;font-size:11px" :disabled="loading" @click="fetchLibrary">
        Refresh
      </button>
    </div>

    <!-- Source info card -->
    <section class="card card-pad">
      <div class="source-row">
        <span class="source-label">Source: output/exports</span>
        <span class="source-count">{{ items.length }} video{{ items.length !== 1 ? 's' : '' }}</span>
      </div>

      <!-- Filter toolbar -->
      <div v-if="items.length > 0" class="filter-toolbar">
        <select v-model="sortBy" class="filter-select">
          <option v-for="opt in SORT_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <select v-model="filterStyle" class="filter-select">
          <option value="">All styles</option>
          <option v-for="s in styleOptions.filter(v => v)" :key="s" :value="s">{{ styleLabel(s) }}</option>
        </select>
        <select v-model="filterRatio" class="filter-select">
          <option value="">All ratios</option>
          <option v-for="r in ratioOptions.filter(v => v)" :key="r" :value="r">{{ r }}</option>
        </select>
        <select v-model="filterDuration" class="filter-select">
          <option v-for="d in DURATION_FILTERS" :key="d.value" :value="d.value">{{ d.label }}</option>
        </select>
        <span class="filter-count">
          <template v-if="filteredItems.length < items.length">Showing {{ filteredItems.length }} of {{ items.length }}</template>
        </span>
      </div>
    </section>

    <!-- Stats -->
    <section v-if="items.length > 0" class="card card-pad stats-card">
      <div class="stats-row">
        <div class="stat-item">
          <span class="stat-value" style="color: var(--accent)">{{ extendedStats.total }}</span>
          <span class="stat-label">Total</span>
        </div>
        <div class="stat-item">
          <span class="stat-value" :style="{ color: extendedStats.today > 0 ? '#26DE81' : 'var(--text-muted)' }">{{ extendedStats.today }}</span>
          <span class="stat-label">Today</span>
        </div>
        <div class="stat-item">
          <span class="stat-value" style="color: var(--accent-warning)">{{ extendedStats.week }}</span>
          <span class="stat-label">This Week</span>
        </div>
        <div class="stat-item">
          <span class="stat-value" style="color:var(--text-secondary)">{{ extendedStats.month }}</span>
          <span class="stat-label">This Month</span>
        </div>
        <div class="stat-item">
          <span class="stat-value" style="color:var(--text-secondary)">{{ extendedStats.avgPerWeek }}</span>
          <span class="stat-label">Avg / Week</span>
        </div>
        <div class="stat-item">
          <span class="stat-value" :style="{ color: extendedStats.streak > 0 ? '#FF6B6B' : 'var(--text-muted)' }">{{ extendedStats.streak > 0 ? extendedStats.streak + 'd' : '—' }}</span>
          <span class="stat-label">Streak</span>
        </div>
        <div class="stat-item">
          <span class="stat-value" style="color: var(--accent-secondary)">{{ fmtDuration(extendedStats.totalDur) }}</span>
          <span class="stat-label">Duration</span>
        </div>
        <div class="stat-item">
          <span class="stat-value" style="color:var(--text-secondary)">{{ formatBytes(extendedStats.totalSize) }}</span>
          <span class="stat-label">Size</span>
        </div>
        <div v-if="extendedStats.topStyle" class="stat-item">
          <span class="stat-value" :style="{ color: styleColor(extendedStats.topStyle[0]) }">{{ styleLabel(extendedStats.topStyle[0]) }}</span>
          <span class="stat-label">Top Style</span>
        </div>
        <div v-if="extendedStats.topRatio" class="stat-item">
          <span class="stat-value" style="color: var(--accent-secondary)">{{ extendedStats.topRatio[0] }}</span>
          <span class="stat-label">Top Ratio</span>
        </div>
      </div>
    </section>

    <!-- Loading -->
    <section v-if="loading && items.length === 0" class="card card-pad">
      <p class="loading-text">Loading export library...</p>
    </section>

    <!-- Error -->
    <section v-else-if="error" class="card card-pad error-card">
      <p class="error-text">{{ error }}</p>
    </section>

    <!-- Empty -->
    <section v-else-if="!loading && items.length === 0" class="card card-pad-lg">
      <p class="empty-text">No exported videos found yet.</p>
    </section>

    <!-- No filter results -->
    <section v-else-if="items.length > 0 && filteredItems.length === 0" class="card card-pad-lg">
      <p class="empty-text">No videos match the current filters.</p>
    </section>

    <!-- Grid -->
    <div v-else class="export-grid">
      <ExportCard
        v-for="(item, idx) in filteredItems"
        :key="item.project_id + (item.video_relpath || idx)"
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
.export-page {
  max-width: 1152px;
  margin: 0 auto;
  padding: 32px 24px;
}

/* ---- Header ---- */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.card-pad {
  padding: 16px;
}

.card-pad-lg {
  padding: 24px;
}

/* ---- Action button (shared) ---- */
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

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ---- Source info ---- */
.source-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.source-label {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}

.source-count {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}

/* ---- Filter toolbar ---- */
.filter-toolbar {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.filter-select {
  background: var(--bg-darkest);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 8px;
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s;
}

.filter-select:hover,
.filter-select:focus {
  border-color: var(--border-hover);
}

.filter-count {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--text-muted);
  margin-left: auto;
}

/* ---- Stats ---- */
.stats-card {
  margin-bottom: 16px;
}

.stats-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  justify-content: space-around;
  font-family: 'JetBrains Mono', monospace;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-width: 70px;
}

.stat-value {
  font-size: 18px;
  font-weight: 700;
  line-height: 1;
}

.stat-label {
  font-size: 9px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* ---- States ---- */
.loading-text {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
  margin: 0;
}

.error-card {
  border-color: rgba(255, 107, 107, 0.35);
}

.error-text {
  font-size: 13px;
  color: var(--coral);
  text-align: center;
  margin: 0;
}

.empty-text {
  text-align: center;
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}

/* ---- Grid ---- */
.export-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
}
</style>
