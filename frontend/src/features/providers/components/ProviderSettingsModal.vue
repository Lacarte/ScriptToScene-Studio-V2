<script setup>
import { ref, computed, watch } from 'vue'
import { useProviders } from '../composables/useProviders.js'

const props = defineProps({
  domain: { type: String, required: true },
  providerId: { type: String, required: true },
  visible: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'saved'])

const { getProviderSettings, saveProviderSettings, validateProviderSettings, testProvider } = useProviders()

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const formData = ref({})
const schema = ref(null)
const manifest = ref(null)
const errors = ref([])
const testResult = ref(null)
const originalData = ref({})

const isValid = computed(() => errors.value.filter(e => e.severity === 'error').length === 0)

async function loadProviderData() {
  loading.value = true
  try {
    const data = await getProviderSettings(props.domain, props.providerId)
    schema.value = data.schema
    manifest.value = data.manifest
    formData.value = { ...data.settings }
    originalData.value = { ...data.settings }
    errors.value = []
    testResult.value = null
  } catch (e) {
    console.error('[Modal] Failed to load provider data:', e)
  } finally {
    loading.value = false
  }
}

async function validateForm() {
  try {
    const result = await validateProviderSettings(props.domain, props.providerId, formData.value)
    errors.value = result.issues || []
    return result.valid
  } catch {
    errors.value = [{ field: 'root', severity: 'error', message: 'Validation failed' }]
    return false
  }
}

async function handleSave() {
  const valid = await validateForm()
  if (!valid) return

  saving.value = true
  try {
    await saveProviderSettings(props.domain, props.providerId, formData.value)
    emit('saved', { domain: props.domain, providerId: props.providerId, settings: formData.value })
    emit('close')
  } catch (e) {
    errors.value = [{ field: 'root', severity: 'error', message: e.message }]
  } finally {
    saving.value = false
  }
}

async function handleTest() {
  testing.value = true
  testResult.value = null
  try {
    const result = await testProvider(props.domain, props.providerId, formData.value)
    testResult.value = result.health
  } catch (e) {
    testResult.value = { status: 'fail', message: e.message }
  } finally {
    testing.value = false
  }
}

function handleReset() {
  formData.value = { ...originalData.value }
  errors.value = []
  testResult.value = null
}

function handleCancel() {
  emit('close')
}

function getHealthColor(status) {
  if (status === 'ok') return '#22c55e'
  if (status === 'warn') return '#f59e0b'
  return '#ef4444'
}

watch(() => props.visible, (val) => {
  if (val) {
    loadProviderData()
  }
})
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="handleCancel">
      <div class="modal-content">
        <div class="modal-header">
          <h3>Configure {{ manifest?.label || providerId }}</h3>
          <button class="close-btn" @click="handleCancel">&times;</button>
        </div>

        <div class="modal-body">
          <div v-if="loading" class="loading-state">
            Loading...
          </div>

          <div v-else-if="errors.length" class="validation-banner error">
            <span>⚠️</span>
            <span>This provider needs configuration before it can be used.</span>
          </div>

          <div v-if="testResult" class="test-result" :style="{ borderColor: getHealthColor(testResult.status) }">
            <span class="status-dot" :style="{ background: getHealthColor(testResult.status) }"></span>
            <span>{{ testResult.message || testResult.status }}</span>
            <span v-if="testResult.latency_ms">({{ testResult.latency_ms }}ms)</span>
          </div>

          <slot
            name="form"
            :formData="formData"
            :schema="schema"
            :errors="errors"
            :updateField="(key, val) => formData[key] = val"
          />
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="handleReset" :disabled="saving || testing">
            Reset
          </button>
          <button class="btn btn-secondary" @click="handleTest" :disabled="saving || testing">
            {{ testing ? 'Testing...' : 'Test Connection' }}
          </button>
          <button class="btn btn-secondary" @click="handleCancel">
            Cancel
          </button>
          <button class="btn btn-primary" @click="handleSave" :disabled="saving || !isValid">
            {{ saving ? 'Saving...' : 'Save' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.modal-content {
  background: var(--bg-surface, #1f1f23);
  border: 1px solid var(--border, #3f3f46);
  border-radius: 12px;
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border, #3f3f46);
}

.modal-header h3 {
  margin: 0;
  font-size: 18px;
  color: var(--text, #e5e5e5);
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  color: var(--text-secondary, #9ca3af);
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.close-btn:hover {
  color: var(--text, #e5e5e5);
}

.modal-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}

.modal-footer {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  border-top: 1px solid var(--border, #3f3f46);
  justify-content: flex-end;
}

.loading-state {
  text-align: center;
  padding: 40px;
  color: var(--text-secondary, #9ca3af);
}

.validation-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 14px;
}

.validation-banner.error {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.test-result {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 14px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.btn {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  border: none;
  transition: opacity 0.15s;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: var(--accent, #4ECDC4);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-secondary {
  background: var(--bg-elevated, #2a2a2f);
  color: var(--text, #e5e5e5);
  border: 1px solid var(--border, #3f3f46);
}

.btn-secondary:hover:not(:disabled) {
  background: var(--bg-surface-hover, #3a3a3f);
}
</style>
