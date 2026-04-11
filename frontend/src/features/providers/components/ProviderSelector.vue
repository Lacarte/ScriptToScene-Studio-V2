<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useProviders } from '../composables/useProviders.js'

const props = defineProps({
  domain: { type: String, required: true },
  label: { type: String, default: 'Provider' },
  description: { type: String, default: '' },
})

const emit = defineEmits(['select', 'configure'])

const { loadProviders, getProvidersByDomain, getSelectedProvider, selectProvider, validateProviderSettings } = useProviders()

const selectedId = ref('')
const showModal = ref(false)
const healthStatus = ref('unknown')
const hasIssues = ref(false)
const providerList = ref([])
const loading = ref(true)

async function load() {
  loading.value = true
  await loadProviders()
  providerList.value = getProvidersByDomain(props.domain)
  const sel = getSelectedProvider(props.domain)
  selectedId.value = sel?.id || ''
  await checkHealth()
  loading.value = false
}

async function checkHealth() {
  if (!selectedId.value) {
    healthStatus.value = 'unknown'
    return
  }
  try {
    const result = await validateProviderSettings(props.domain, selectedId.value)
    hasIssues.value = !result.valid
    healthStatus.value = result.valid ? 'ok' : 'warn'
  } catch {
    healthStatus.value = 'fail'
    hasIssues.value = true
  }
}

async function onSelect(event) {
  const newId = event.target.value
  const result = await selectProvider(props.domain, newId)
  
  if (result?.needsConfiguration) {
    showModal.value = true
    emit('configure', { domain: props.domain, providerId: newId })
  } else {
    selectedId.value = newId
    emit('select', { domain: props.domain, providerId: newId })
  }
  
  await checkHealth()
}

function openSettings() {
  showModal.value = true
  emit('configure', { domain: props.domain, providerId: selectedId.value })
}

function getHealthColor(status) {
  if (status === 'ok') return '#22c55e'
  if (status === 'warn') return '#f59e0b'
  return '#6b7280'
}

watch(() => props.domain, load, { immediate: true })
onMounted(load)

defineExpose({ showModal, selectedId })
</script>

<template>
  <div class="provider-selector">
    <div class="selector-row">
      <div class="selector-info">
        <label class="selector-label">{{ label }}</label>
        <p v-if="description" class="selector-desc">{{ description }}</p>
      </div>
      <div class="selector-controls">
        <select
          class="selector-select"
          :value="selectedId"
          :disabled="loading"
          @change="onSelect"
        >
          <option v-for="p in providerList" :key="p.id" :value="p.id">
            {{ p.label }}
          </option>
        </select>
        <button
          class="gear-btn"
          :class="{ 'has-warning': hasIssues }"
          :disabled="!selectedId || loading"
          title="Configure provider"
          @click="openSettings"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3"/>
            <path d="M12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72l1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42M18.36 5.64l-1.42-1.42"/>
          </svg>
        </button>
        <span
          class="health-dot"
          :style="{ background: getHealthColor(healthStatus) }"
          :title="healthStatus"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.provider-selector {
  width: 100%;
}

.selector-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.selector-info {
  flex: 1;
}

.selector-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text, #e5e5e5);
  display: block;
}

.selector-desc {
  font-size: 12px;
  color: var(--text-secondary, #9ca3af);
  margin: 4px 0 0;
}

.selector-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.selector-select {
  padding: 10px 32px 10px 12px;
  border: 1px solid var(--border, #3f3f46);
  border-radius: 6px;
  background: var(--bg-surface, #1f1f23);
  color: var(--text, #e5e5e5);
  font-size: 14px;
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%239ca3af' d='M6 8L2 4h8z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  min-width: 140px;
}

.selector-select:focus {
  outline: none;
  border-color: var(--accent, #4ECDC4);
}

.gear-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--border, #3f3f46);
  border-radius: 6px;
  background: var(--bg-surface, #1f1f23);
  color: var(--text-secondary, #9ca3af);
  cursor: pointer;
  transition: all 0.15s;
}

.gear-btn:hover:not(:disabled) {
  background: var(--bg-surface-hover, #3a3a3f);
  color: var(--text, #e5e5e5);
}

.gear-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.gear-btn.has-warning {
  border-color: var(--accent-warning, #f59e0b);
}

.health-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
</style>