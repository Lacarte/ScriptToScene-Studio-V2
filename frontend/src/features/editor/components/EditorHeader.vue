<script setup>
import { useRouter } from 'vue-router'
import { useEditor } from '../composables/useEditor.js'

defineOptions({ name: 'EditorHeader' })

const router = useRouter()
const { projectName, saveStatus, canUndo, canRedo } = useEditor()

function goBack() {
  router.push({ path: '/scenes', query: projectName.value ? { project: projectName.value } : {} })
}

function undo() {
  if (typeof window.editorUndo === 'function') window.editorUndo()
}

function redo() {
  if (typeof window.editorRedo === 'function') window.editorRedo()
}
</script>

<template>
  <header class="app-header">
    <div class="header-left">
      <button class="back-link" title="Back to Scenes" @click="goBack">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5" />
          <path d="M12 19l-7-7 7-7" />
        </svg>
      </button>
      <h1>Video Editor</h1>
      <span class="project-name">{{ projectName }}</span>
      <span
        v-if="saveStatus"
        class="save-status"
        :class="saveStatus"
      >
        {{ saveStatus === 'saving' ? 'Saving...' : saveStatus === 'saved' ? 'Saved' : saveStatus === 'save-error' ? 'Save error' : '' }}
      </span>
    </div>
    <div class="header-right">
      <div class="history-controls">
        <div class="history-btn-group">
          <button
            class="history-action-btn"
            title="Undo (Ctrl+Z)"
            :disabled="!canUndo"
            @click="undo"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="1 4 1 10 7 10" />
              <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
            </svg>
          </button>
          <div class="history-btn-divider"></div>
          <button
            class="history-action-btn"
            title="Redo (Ctrl+Y)"
            :disabled="!canRedo"
            @click="redo"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 1 1-2.13-9.36L23 10" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </header>
</template>

<style scoped>
/* Header styles are provided by the parent EditorPage's unscoped style block.
   This scoped block only contains component-specific overrides if needed. */
.back-link {
  cursor: pointer;
}
</style>
