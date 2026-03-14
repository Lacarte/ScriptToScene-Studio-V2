import { ref, readonly, shallowRef } from 'vue'

/* ------------------------------------------------------------------ */
/*  useEditor — singleton composable                                   */
/*  Wraps the imperative video-editor.js lifecycle.                    */
/*  Heavy lifting stays in the original JS; this is a thin bridge.    */
/* ------------------------------------------------------------------ */

const initialized = ref(false)
const projectName = ref('No project loaded')
const sceneCount = ref(0)
const saveStatus = ref('')      // '', 'saving', 'saved', 'save-error'
const canUndo = ref(false)
const canRedo = ref(false)

/** Raw boot payload read from storage (if any) */
const bootProject = shallowRef(null)

let _containerEl = null
let _destroyed = false

/* ---------- Storage helpers --------- */

function getStoredBootProject() {
  const candidates = [
    sessionStorage.getItem('sts-staged-timeline'),
    localStorage.getItem('sts-editor-boot-project'),
    localStorage.getItem('sts-editor-scenes'),
  ]

  for (const raw of candidates) {
    if (!raw) continue
    try {
      const data = JSON.parse(raw)
      if (data && Array.isArray(data.scenes) && data.scenes.length) {
        return data
      }
    } catch { /* ignore malformed bridge data */ }
  }

  return null
}

/* ---------- Public API -------------- */

/**
 * Initialize the imperative editor inside the given container element.
 * Dynamically imports video-editor.js and calls window.initEditor().
 */
async function init(containerEl) {
  if (initialized.value || _destroyed) return
  _containerEl = containerEl

  // Read boot data from storage
  bootProject.value = getStoredBootProject()
  if (bootProject.value) {
    projectName.value = bootProject.value.project_name
      || bootProject.value.source_folder
      || 'Untitled'
    sceneCount.value = bootProject.value.scenes?.length ?? 0
  }

  // The editor scripts are loaded as classic <script type="module"> tags in index.html.
  // In the Vue app we need to dynamically import them.
  // For now, we rely on the modules being already loaded (they expose onto window).
  // If not yet available, wait briefly then bail.
  if (typeof window.initEditor !== 'function') {
    // Try dynamic import — the editor entry point attaches to window
    try {
      const editorUrl = '/static/js/editor/video-editor.js'
      await import(/* @vite-ignore */ editorUrl)
    } catch {
      console.warn('[useEditor] Could not load video-editor.js')
    }
  }

  if (typeof window.initEditor === 'function') {
    // Set up the callback the editor uses to signal readiness
    window._onEditorReady = (state) => {
      if (state === 'ready') {
        _syncBridgeData()
      }
    }
    window.initEditor()
    initialized.value = true
  } else {
    console.warn('[useEditor] Editor module not available')
  }
}

/**
 * Sync scene / caption data into the running editor.
 */
function _syncBridgeData() {
  const data = bootProject.value || getStoredBootProject()
  if (!data) return

  if (typeof window.editorLoadScenes === 'function') {
    window.editorLoadScenes(data)
  }
}

/**
 * Load a project payload into the already-initialized editor.
 */
function loadProject(projectData) {
  if (!projectData) return
  bootProject.value = projectData

  projectName.value = projectData.project_name
    || projectData.source_folder
    || 'Untitled'
  sceneCount.value = projectData.scenes?.length ?? 0

  if (typeof window.editorLoadScenes === 'function') {
    window.editorLoadScenes(projectData)
  }
}

/**
 * Tear down the editor (called on unmount).
 */
function destroy() {
  _destroyed = true
  _containerEl = null
  // The imperative editor doesn't expose a destroy — it lives until page unload.
  // We just mark ourselves as destroyed so re-init is blocked until a fresh composable.
}

/**
 * Reset the singleton so it can be re-initialized (e.g. after route leave + return).
 */
function reset() {
  _destroyed = false
}

export function useEditor() {
  return {
    initialized: readonly(initialized),
    projectName: readonly(projectName),
    sceneCount: readonly(sceneCount),
    saveStatus: readonly(saveStatus),
    canUndo: readonly(canUndo),
    canRedo: readonly(canRedo),
    bootProject: readonly(bootProject),
    init,
    destroy,
    reset,
    loadProject,
  }
}
