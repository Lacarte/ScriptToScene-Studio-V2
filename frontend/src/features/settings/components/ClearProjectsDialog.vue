<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
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
const errorMsg = ref('')

function generateCode() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  let code = ''
  for (let i = 0; i < 6; i++) {
    code += chars[Math.floor(Math.random() * chars.length)]
  }
  return code
}

const inputMatches = computed(() => userInput.value.toUpperCase().trim() === challengeCode.value)

onMounted(async () => {
  challengeCode.value = generateCode()
  try {
    preview.value = await fetchClearPreview()
  } catch {
    previewError.value = 'Failed to load preview'
  } finally {
    previewLoading.value = false
  }
})

function onEscape(e) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => document.addEventListener('keydown', onEscape))
onUnmounted(() => document.removeEventListener('keydown', onEscape))

async function confirmDelete() {
  if (!inputMatches.value || deleting.value) return
  deleting.value = true
  errorMsg.value = ''
  try {
    const result = await executeClearAll()
    if (result.status === 'cleared') {
      const exportsMsg = result.exports_deleted
        ? ` (${result.exports_deleted} export item${result.exports_deleted !== 1 ? 's' : ''} deleted)`
        : ''
      toast.success(`Cleared ${result.count ?? 0} project item${(result.count ?? 0) !== 1 ? 's' : ''}${exportsMsg}`)
      // Only clear STS keys, not all localStorage
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith('sts-')) localStorage.removeItem(key)
      }
      for (const key of Object.keys(sessionStorage)) {
        if (key.startsWith('sts-')) sessionStorage.removeItem(key)
      }
      emit('close')
      setTimeout(() => window.location.reload(), 600)
    } else {
      toast.error(result.error || 'Failed to clear projects')
      deleting.value = false
    }
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
        <!-- Centered header with warning icon -->
        <div class="dialog-header">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="1.5">
            <path d="M12 9v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <h3 class="dialog-title">Clear All Projects?</h3>
          <p class="dialog-desc">
            This will move <strong>all</strong> project folders across every module to trash. Type the characters below to confirm.
          </p>
        </div>

        <!-- Preview box -->
        <div class="preview-box">
          <template v-if="previewLoading">
            <p class="preview-loading-text">Loading modules to clear...</p>
          </template>
          <template v-else-if="previewError">
            <p class="preview-error-text">{{ previewError }}</p>
          </template>
          <template v-else-if="preview">
            <div class="preview-header">
              <span class="preview-label">Items that will be moved to TRASH</span>
              <span class="preview-total">{{ preview.total_items || 0 }} total</span>
            </div>
            <div
              v-for="mod in (preview.modules || [])"
              :key="mod.module"
              class="preview-row"
            >
              <div class="preview-row-top">
                <span class="preview-module-name">{{ mod.page }} - {{ mod.module }}</span>
                <span class="preview-module-count" :class="{ 'has-items': (mod.items || 0) > 0 }">{{ mod.items || 0 }}</span>
              </div>
              <div v-if="mod.entries && mod.entries.length" class="preview-entries">
                <span v-for="name in mod.entries" :key="name" class="preview-entry">{{ name }}</span>
              </div>
              <div v-else class="preview-entries">
                <span class="preview-entry">empty</span>
              </div>
            </div>
            <p v-if="!preview.modules || !preview.modules.length" class="preview-loading-text">Nothing to clear</p>
          </template>
        </div>

        <!-- Challenge code display -->
        <div class="challenge-display">
          <span class="challenge-chars">{{ challengeCode }}</span>
        </div>

        <!-- Input -->
        <input
          v-model="userInput"
          class="challenge-input"
          type="text"
          placeholder="Type the characters above"
          spellcheck="false"
          autocomplete="off"
        />

        <p v-if="errorMsg" class="error-text">{{ errorMsg }}</p>

        <!-- Buttons -->
        <div class="dialog-footer">
          <button class="btn btn-cancel" @click="emit('close')">Cancel</button>
          <button
            class="btn btn-delete"
            :disabled="!inputMatches || deleting"
            @click="confirmDelete"
          >
            {{ deleting ? 'Clearing...' : 'Delete All' }}
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
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(4px);
}

.dialog {
  background: var(--bg-surface);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 14px;
  padding: 28px 24px;
  max-width: 400px;
  width: 90%;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

/* ---- Header (centered) ---- */
.dialog-header {
  text-align: center;
  margin-bottom: 20px;
}

.dialog-header svg {
  margin-bottom: 12px;
}

.dialog-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 6px;
}

.dialog-desc {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
}

/* ---- Preview box ---- */
.preview-box {
  margin-bottom: 14px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--bg-darkest);
  border: 1px solid var(--border);
  max-height: 180px;
  overflow: auto;
}

.preview-loading-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
}

.preview-error-text {
  font-size: 11px;
  color: var(--coral);
  text-align: center;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.preview-label {
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  font-weight: 700;
}

.preview-total {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: #ef4444;
  font-weight: 700;
}

.preview-row {
  padding: 6px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.preview-row:last-child {
  border-bottom: none;
}

.preview-row-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.preview-module-name {
  font-size: 11px;
  color: var(--text-secondary);
}

.preview-module-count {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--text-muted);
}

.preview-module-count.has-items {
  color: #ef4444;
}

.preview-entries {
  margin-top: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.preview-entry {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--text-muted);
}

/* ---- Challenge display ---- */
.challenge-display {
  text-align: center;
  margin-bottom: 16px;
}

.challenge-chars {
  font-family: 'JetBrains Mono', monospace;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0.3em;
  color: #ef4444;
}

/* ---- Input ---- */
.challenge-input {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 14px;
  background: var(--bg-darkest);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  font-family: 'JetBrains Mono', monospace;
  font-size: 14px;
  text-align: center;
  letter-spacing: 0.2em;
  outline: none;
  transition: border-color 0.15s;
}

.challenge-input:focus {
  border-color: var(--accent);
}

.error-text {
  font-size: 11px;
  color: #ef4444;
  text-align: center;
  margin-top: 8px;
}

/* ---- Footer buttons ---- */
.dialog-footer {
  display: flex;
  gap: 10px;
  margin-top: 18px;
}

.btn {
  flex: 1;
  padding: 10px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-cancel {
  background: var(--bg-darkest);
  color: var(--text-muted);
  border: 1px solid var(--border);
}

.btn-cancel:hover {
  color: var(--text);
}

.btn-delete {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.btn-delete:hover:not(:disabled) {
  background: #ef4444;
  color: #fff;
}

.btn-delete:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
