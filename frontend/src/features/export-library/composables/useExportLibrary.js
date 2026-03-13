import { ref, computed, watch } from 'vue'
import { api } from '@/shared/api/client.js'
import { useToast } from '@/shared/composables/useToast.js'

/* ── Helpers ───────────────────────────────────────── */

export function formatBytes(bytes) {
  if (bytes == null || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  const val = bytes / Math.pow(1024, i)
  return `${val.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

export function formatDuration(seconds) {
  if (seconds == null || seconds <= 0) return '0s'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.round(seconds % 60)
  if (h > 0) return `${h}h ${m}m ${s}s`
  if (m > 0) return `${m}m ${s}s`
  return `${s}s`
}

export function timeAgo(timestamp) {
  if (!timestamp) return ''
  const now = Date.now()
  const date = new Date(timestamp)
  const diff = Math.max(0, now - date.getTime()) / 1000

  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`
  if (diff < 2592000) return `${Math.floor(diff / 604800)}w ago`
  return date.toLocaleDateString()
}

export function ratioLabel(ratio) {
  if (!ratio) return ''
  const map = {
    '16:9': '16:9', '9:16': '9:16', '1:1': '1:1',
    '4:3': '4:3', '3:4': '3:4', '4:5': '4:5',
    '21:9': '21:9',
  }
  return map[ratio] || ratio
}

/* ── Duration filter buckets ───────────────────────── */

const DURATION_FILTERS = [
  { label: 'All durations', value: '' },
  { label: 'Under 15s',     value: '0-15' },
  { label: '15s – 30s',     value: '15-30' },
  { label: '30s – 1m',      value: '30-60' },
  { label: '1m – 3m',       value: '60-180' },
  { label: 'Over 3m',       value: '180+' },
]

/* ── Sort options ──────────────────────────────────── */

const SORT_OPTIONS = [
  { label: 'Newest first',   value: 'newest' },
  { label: 'Oldest first',   value: 'oldest' },
  { label: 'Longest first',  value: 'longest' },
  { label: 'Shortest first', value: 'shortest' },
  { label: 'Largest first',  value: 'largest' },
  { label: 'Smallest first', value: 'smallest' },
]

/* ── Composable ────────────────────────────────────── */

export function useExportLibrary() {
  const toast = useToast()

  const items = ref([])
  const loading = ref(false)
  const error = ref(null)

  // Filters
  const sortBy = ref('newest')
  const filterStyle = ref('')
  const filterRatio = ref('')
  const filterDuration = ref('')

  /* ── Derived option lists from data ──────────────── */

  const styleOptions = computed(() => {
    const set = new Set()
    for (const item of items.value) {
      if (item.style) set.add(item.style)
    }
    return ['', ...Array.from(set).sort()]
  })

  const ratioOptions = computed(() => {
    const set = new Set()
    for (const item of items.value) {
      const r = item.video_ratio || item.ratio
      if (r) set.add(r)
    }
    return ['', ...Array.from(set).sort()]
  })

  /* ── Filtered + sorted items ─────────────────────── */

  const filteredItems = computed(() => {
    let list = [...items.value]

    // Style filter
    if (filterStyle.value) {
      list = list.filter(i => i.style === filterStyle.value)
    }

    // Ratio filter
    if (filterRatio.value) {
      list = list.filter(i => (i.video_ratio || i.ratio) === filterRatio.value)
    }

    // Duration filter
    if (filterDuration.value) {
      const f = filterDuration.value
      list = list.filter(i => {
        const d = i.duration ?? 0
        if (f === '0-15')   return d < 15
        if (f === '15-30')  return d >= 15 && d < 30
        if (f === '30-60')  return d >= 30 && d < 60
        if (f === '60-180') return d >= 60 && d < 180
        if (f === '180+')   return d >= 180
        return true
      })
    }

    // Sort
    const s = sortBy.value
    list.sort((a, b) => {
      if (s === 'newest')   return new Date(b.modified_at) - new Date(a.modified_at)
      if (s === 'oldest')   return new Date(a.modified_at) - new Date(b.modified_at)
      if (s === 'longest')  return (b.duration ?? 0) - (a.duration ?? 0)
      if (s === 'shortest') return (a.duration ?? 0) - (b.duration ?? 0)
      if (s === 'largest')  return (b.size_bytes ?? 0) - (a.size_bytes ?? 0)
      if (s === 'smallest') return (a.size_bytes ?? 0) - (b.size_bytes ?? 0)
      return 0
    })

    return list
  })

  /* ── Stats ───────────────────────────────────────── */

  const stats = computed(() => {
    const all = items.value
    const now = Date.now()
    const dayMs  = 86400000
    const weekMs = 7 * dayMs
    const monthMs = 30 * dayMs

    let totalDuration = 0
    let totalSize = 0
    let today = 0, week = 0, month = 0
    const styleCounts = {}
    const ratioCounts = {}

    for (const item of all) {
      totalDuration += item.duration ?? 0
      totalSize += item.size_bytes ?? 0

      const age = now - new Date(item.modified_at).getTime()
      if (age < dayMs)   today++
      if (age < weekMs)  week++
      if (age < monthMs) month++

      if (item.style) styleCounts[item.style] = (styleCounts[item.style] || 0) + 1
      const r = item.video_ratio || item.ratio
      if (r) ratioCounts[r] = (ratioCounts[r] || 0) + 1
    }

    const topStyles = Object.entries(styleCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)

    const topRatios = Object.entries(ratioCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)

    return {
      totalDuration,
      totalSize,
      today,
      week,
      month,
      topStyles,
      topRatios,
    }
  })

  /* ── Fetch ───────────────────────────────────────── */

  async function fetchLibrary() {
    loading.value = true
    error.value = null
    try {
      const data = await api.get('/api/export/library')
      items.value = data.items || []
    } catch (e) {
      error.value = e.message || 'Failed to load export library'
      toast.error('Failed to load export library')
    } finally {
      loading.value = false
    }
  }

  /* ── Download helpers ────────────────────────────── */

  async function downloadFile(url, filename) {
    try {
      const res = await fetch(url)
      if (!res.ok) throw new Error(`Download failed: ${res.status}`)
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = filename
      document.body.appendChild(a)
      a.click()
      setTimeout(() => {
        URL.revokeObjectURL(a.href)
        document.body.removeChild(a)
      }, 100)
      toast.success(`Downloaded ${filename}`)
    } catch (e) {
      toast.error(`Download failed: ${e.message}`)
    }
  }

  function downloadVideo(item) {
    if (!item.video_download_url) {
      toast.error('No video download URL available')
      return
    }
    const name = item.video_name || 'video.mp4'
    downloadFile(item.video_download_url, name)
  }

  function downloadZip(item) {
    const url = item.zip_download_url
    if (!url) {
      toast.error('No ZIP download available for this export')
      return
    }
    const name = (item.video_name || 'project').replace(/\.[^.]+$/, '') + '.zip'
    downloadFile(url, name)
  }

  return {
    // State
    items,
    loading,
    error,

    // Filters
    sortBy,
    filterStyle,
    filterRatio,
    filterDuration,
    filteredItems,

    // Options
    SORT_OPTIONS,
    DURATION_FILTERS,
    styleOptions,
    ratioOptions,

    // Stats
    stats,

    // Actions
    fetchLibrary,
    downloadVideo,
    downloadZip,
  }
}
