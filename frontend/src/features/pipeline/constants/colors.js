export const CATEGORY_COLORS = {
  psychology: '#8B5CF6',
  crime: '#EF4444',
  horror: '#FF6B6B',
  motivation: '#FACC15',
  philosophy: '#94A3B8',
  religion: '#D4AF37',
  mystery: '#7C3AED',
  science: '#38BDF8',
  history: '#C08457',
  nature: '#22C55E',
  romance: '#F472B6',
  comedy: '#F97316',
  children: '#F9A8D4',
  anecdote: '#FB7185',
  politics: '#DC2626',
  survival: '#84CC16',
  curiosity: '#2DD4BF',
  space: '#60A5FA',
}

export function withAlpha(hex, alpha = '18') {
  if (!hex || typeof hex !== 'string') return `rgba(78, 205, 196, 0.${alpha})`
  if (hex.startsWith('#') && hex.length === 7) return `${hex}${alpha}`
  return hex
}

export function categoryColor(categoryId) {
  return CATEGORY_COLORS[categoryId] || '#4ECDC4'
}

export function statusColor(status) {
  if (status === 'done') return '#26DE81'
  if (status === 'stopped') return '#FFB347'
  if (status === 'error') return '#FF6B6B'
  return 'var(--accent)'
}

export function stepColor(stepStatus) {
  const s = stepStatus || 'pending'
  if (s === 'running') return 'var(--accent)'
  if (s === 'done') return '#26DE81'
  if (s === 'stopped') return '#FFB347'
  if (s === 'skipped') return 'var(--text-muted)'
  if (s === 'error') return '#FF6B6B'
  return 'var(--border)'
}

export function stepTextColor(stepStatus) {
  const s = stepStatus || 'pending'
  if (s === 'running') return 'var(--accent)'
  if (s === 'done') return '#26DE81'
  if (s === 'stopped') return '#FFB347'
  if (s === 'skipped') return 'var(--text-muted)'
  if (s === 'error') return '#FF6B6B'
  return 'var(--text-muted)'
}

export function logEntryIcon(entry) {
  if (entry.step === 'error') return '\u2717'
  if (entry.status === 'done') return '\u2713'
  return '\u2192'
}

export function logEntryColor(entry) {
  if (entry.step === 'error') return '#FF6B6B'
  if (entry.status === 'done') return '#26DE81'
  return 'var(--text-muted)'
}
