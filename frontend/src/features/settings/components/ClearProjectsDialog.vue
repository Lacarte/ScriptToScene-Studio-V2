<script setup>
import { ref, computed, onMounted } from 'vue'
import { useSettings } from '../composables/useSettings.js'
import { useToast } from '@/shared/composables/useToast.js'

defineOptions({ name: 'ClearProjectsDialog' })

const emit = defineEmits(['close'])

const { fetchClearPreview, executeClearAll } = useSettings()
const toast = useToast()

const preview = ref(null)
const previewLoading = ref(true)
const previewError = ref(null)
const challengeCode = ref('')
const userInput = ref('')
const deleting = ref(false)

function generateCode() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  let code = ''
  for (let i = 0; i < 6; i++) {
    code += chars[Math.floor(Math.random() * chars.length)]
  }
  return code
}

const inputMatches = computed(() => userInput.value === challengeCode.value)

onMounted(async () => {
  challengeCode.value = generateCode()
  try {
    preview.value = await fetchClearPreview()
  } catch {
    previewError.value = 'Failed to load project data.'
  } finally {
    previewLoading.value = false
  }
})

async function confirmDelete() {
  if (!inputMatches.value || deleting.value) return
  deleting.value = true
  try {
    const result = await executeClearAll()
    toast.success(`Cleared ${result.count ?? 0} items and ${result.exports_deleted ?? 0} exports.`)
    emit('close')
    setTimeout(() => window.location.reload(), 800)
  } catch {
    toast.error('Failed to clear projects.')
    deleting.value = false
  }
}

function onOverlayClick(e) {
  if (e.target === e.currentTarget) emit('close')
}
</script>

<template>
  <Teleport to="body">
    <div class="overlay" @click="onOverlayClick">
      <div class="dialog">
        <div class="dialog-header">
          <h3 class="dialog-title">Clear All Projects</h3>
          <button class="close-btn" @click="emit('close')" aria-label="Close">&times;</button>
        </div>

        <div class="dialog-body">
          <p class="warning-text">
            This will permanently delete all generated project data. This action cannot be undone.
          </p>

          <!-- Preview -->
          <div v-if="previewLoading" class="preview-loading">Loading project data...</div>
          <div v-else-if="previewError" class="preview-error">{{ previewError }}</div>
          <div v-else-if="preview" class="preview">
            <div class="preview-total">
              <strong>{{ preview.total_items }}</strong> items will be deleted
            </div>
            <ul class="module-list">
              <li v-for="mod in preview.modules" :key="mod.module" class="module-item">
                <span class="module-page">{{ mod.page }}</span>
                <span class="module-name">{{ mod.module }}</span>
                <span class="module-count">{{ mod.entries }} entries</span>
              </li>
            </ul>
          </div>

          <!-- Challenge -->
          <div class="challenge">
            <label class="challenge-label">
              Type <code class="challenge-code">{{ challengeCode }}</code> to confirm:
            </label>
            <input
              v-model="userInput"
              class="challenge-input"
              type="text"
              :placeholder="challengeCode"
              spellcheck="false"
              autocomplete="off"
            />
          </div>
        </div>

        <div class="dialog-footer">
          <button class="btn btn-cancel" @click="emit('close')">Cancel</button>
          <button
            class="btn btn-delete"
            :disabled="!inputMatches || deleting"
            @click="confirmDelete"
          >
            {{ deleting ? 'Deleting...' : 'Delete Everything' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
}

.dialog {
  background: var(--bg-dark);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  width: 480px;
  max-width: 90vw;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 20px 0;
}

.dialog-title {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  color: var(--coral);
}

.close-btn {
  background: none;
  border: none;
  font-size: 22px;
  color: var(--text-secondary);
  cursor: pointer;
  line-height: 1;
  padding: 4px;
}

.close-btn:hover {
  color: var(--text);
}

.dialog-body {
  padding: 16px 20px;
  overflow-y: auto;
  flex: 1;
}

.warning-text {
  font-size: 13px;
  color: var(--coral);
  line-height: 1.5;
  margin-bottom: 16px;
}

.preview-loading,
.preview-error {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 12px 0;
}

.preview-error {
  color: var(--coral);
}

.preview {
  margin-bottom: 16px;
}

.preview-total {
  font-size: 13px;
  color: var(--text);
  margin-bottom: 8px;
}

.module-list {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.module-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding: 6px 10px;
  background: var(--bg-surface);
  border-radius: var(--radius-xs);
}

.module-page {
  color: var(--text-secondary);
  min-width: 70px;
}

.module-name {
  color: var(--text);
  flex: 1;
  font-family: var(--font-mono);
  font-size: 11px;
}

.module-count {
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.challenge {
  margin-top: 16px;
}

.challenge-label {
  display: block;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.challenge-code {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--coral);
  background: rgba(239, 68, 68, 0.1);
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  letter-spacing: 0.1em;
}

.challenge-input {
  width: 100%;
  padding: 8px 12px;
  font-family: var(--font-mono);
  font-size: 14px;
  letter-spacing: 0.15em;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text);
  outline: none;
  transition: border-color 0.15s;
}

.challenge-input:focus {
  border-color: var(--accent);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 20px;
  border-top: 1px solid var(--border);
}

.btn {
  padding: 8px 18px;
  font-size: 13px;
  font-weight: 600;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
  border: none;
}

.btn-cancel {
  background: var(--bg-surface);
  color: var(--text-secondary);
}

.btn-cancel:hover {
  background: var(--bg-surface-hover);
  color: var(--text);
}

.btn-delete {
  background: var(--coral);
  color: #fff;
}

.btn-delete:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-delete:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
