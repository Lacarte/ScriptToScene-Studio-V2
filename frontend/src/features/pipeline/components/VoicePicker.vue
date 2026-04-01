<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  voices: { type: Array, default: () => [] },
  favorites: { type: Array, default: () => [] },
  provider: { type: String, default: 'kokoro' },
})

const emit = defineEmits(['update:modelValue', 'toggle-favorite'])

const open = ref(false)
const search = ref('')
const listRef = ref(null)
const searchRef = ref(null)

const isInworld = computed(() => props.provider === 'inworld')

const favSet = computed(() => new Set(props.favorites))

const filtered = computed(() => {
  const q = search.value.toLowerCase().trim()
  let list = props.voices
  if (q) {
    list = list.filter(v =>
      v.label.toLowerCase().includes(q) ||
      (v.description || '').toLowerCase().includes(q) ||
      (v.tags || []).some(t => t.toLowerCase().includes(q))
    )
  }
  return list
})

const selectedVoice = computed(() =>
  props.voices.find(v => v.id === props.modelValue)
)

function select(v) {
  emit('update:modelValue', v.id)
  open.value = false
  search.value = ''
}

function toggle() {
  open.value = !open.value
  if (open.value) {
    nextTick(() => searchRef.value?.focus())
  }
}

function onClickOutside(e) {
  if (!e.target.closest('.voice-picker')) {
    open.value = false
    search.value = ''
  }
}

watch(open, (v) => {
  if (v) document.addEventListener('click', onClickOutside, true)
  else document.removeEventListener('click', onClickOutside, true)
})
</script>

<template>
  <div class="voice-picker" :class="{ open }">
    <!-- Trigger button -->
    <button class="vp-trigger" @click.stop="toggle">
      <span class="vp-trigger-label">
        <svg v-if="isInworld && favSet.has(modelValue)" class="vp-star filled" width="10" height="10" viewBox="0 0 24 24"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z" fill="currentColor"/></svg>
        {{ selectedVoice?.label || modelValue }}
      </span>
      <svg class="vp-chevron" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
    </button>

    <!-- Dropdown -->
    <div v-if="open" class="vp-dropdown" @click.stop>
      <!-- Search (Inworld only — too many voices) -->
      <div v-if="isInworld" class="vp-search-wrap">
        <input
          ref="searchRef"
          v-model="search"
          class="vp-search"
          placeholder="Search voices..."
          @keydown.escape="open = false"
        />
      </div>

      <div ref="listRef" class="vp-list">
        <button
          v-for="v in filtered"
          :key="v.id"
          class="vp-item"
          :class="{ active: v.id === modelValue, fav: favSet.has(v.id) }"
          @click="select(v)"
        >
          <!-- Star (Inworld only) -->
          <button
            v-if="isInworld"
            class="vp-fav-btn"
            :class="{ starred: favSet.has(v.id) }"
            @click.stop="emit('toggle-favorite', v.id)"
            title="Toggle favorite"
          >
            <svg width="12" height="12" viewBox="0 0 24 24">
              <path
                d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z"
                :fill="favSet.has(v.id) ? 'var(--accent)' : 'none'"
                :stroke="favSet.has(v.id) ? 'var(--accent)' : 'var(--text-muted)'"
                stroke-width="1.5"
              />
            </svg>
          </button>

          <!-- Name + Description -->
          <div class="vp-item-info">
            <span class="vp-item-name">{{ v.label }}</span>
            <span v-if="v.description" class="vp-item-desc">{{ v.description }}</span>
          </div>
        </button>

        <div v-if="!filtered.length" class="vp-empty">No voices found</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.voice-picker {
  position: relative;
}

.vp-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  width: 100%;
  padding: 6px 10px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-size: 12px;
  font-family: var(--font-mono);
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s;
}

.vp-trigger:hover,
.voice-picker.open .vp-trigger {
  border-color: var(--accent);
}

.vp-trigger-label {
  display: flex;
  align-items: center;
  gap: 5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.vp-chevron {
  flex-shrink: 0;
  opacity: 0.5;
  transition: transform 0.15s;
}

.voice-picker.open .vp-chevron {
  transform: rotate(180deg);
}

.vp-star.filled {
  color: var(--accent);
}

/* ── Dropdown ── */

.vp-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  min-width: 280px;
  max-width: 360px;
  background: var(--bg-darkest);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  z-index: 100;
  overflow: hidden;
}

.vp-search-wrap {
  padding: 8px 8px 4px;
}

.vp-search {
  width: 100%;
  padding: 6px 10px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 5px;
  color: var(--text);
  font-size: 11px;
  font-family: var(--font-mono);
  outline: none;
  box-sizing: border-box;
}

.vp-search:focus {
  border-color: var(--accent);
}

.vp-search::placeholder {
  color: var(--text-muted);
}

.vp-list {
  max-height: 320px;
  overflow-y: auto;
  padding: 4px;
}

/* ── Items ── */

.vp-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  width: 100%;
  padding: 7px 8px;
  background: none;
  border: none;
  border-radius: 5px;
  color: var(--text);
  cursor: pointer;
  text-align: left;
  transition: background 0.1s;
}

.vp-item:hover {
  background: var(--bg-surface);
}

.vp-item.active {
  background: rgba(78, 205, 196, 0.1);
}

.vp-item.fav {
  border-left: 2px solid var(--accent);
  padding-left: 6px;
}

.vp-fav-btn {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  margin-top: 1px;
  background: none;
  border: none;
  border-radius: 3px;
  cursor: pointer;
  opacity: 0.4;
  transition: opacity 0.15s;
}

.vp-fav-btn:hover,
.vp-fav-btn.starred {
  opacity: 1;
}

.vp-item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.vp-item-name {
  font-size: 12px;
  font-weight: 500;
  font-family: var(--font-mono);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.vp-item-desc {
  font-size: 10px;
  color: var(--text-muted);
  line-height: 1.3;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.vp-empty {
  padding: 16px;
  text-align: center;
  font-size: 11px;
  color: var(--text-muted);
}
</style>
