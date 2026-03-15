import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * Staging store for cross-feature data passing.
 * Replaces the old localStorage/sessionStorage pattern used to pass
 * scene data between Scenes → Assets → Editor.
 *
 * Data is also persisted to localStorage so the editor (which still uses
 * legacy JS) can read it, and so data survives page reloads.
 */
export const useStagingStore = defineStore('staging', () => {
  const stagedProject = ref(null)

  function stage(data) {
    stagedProject.value = data
    // Persist for legacy editor compatibility and page reloads
    try {
      const json = JSON.stringify(data)
      sessionStorage.setItem('sts-staged-timeline', json)
      localStorage.setItem('sts-editor-boot-project', json)
      localStorage.setItem('sts-editor-scenes', json)
      if (data.source_folder) {
        localStorage.setItem('sts-editor-source-folder', data.source_folder)
      } else {
        localStorage.removeItem('sts-editor-source-folder')
      }
      if (data.project_id) {
        localStorage.setItem('sts-editor-last-project-id', data.project_id)
      }
      if (data.captions) {
        localStorage.setItem('sts-editor-captions', JSON.stringify(data.captions))
      } else {
        localStorage.removeItem('sts-editor-captions')
      }
    } catch {
      // Storage full or unavailable
    }
  }

  function load() {
    if (stagedProject.value) return stagedProject.value
    // Hydrate from storage
    try {
      const raw =
        sessionStorage.getItem('sts-staged-timeline') ||
        localStorage.getItem('sts-editor-boot-project') ||
        localStorage.getItem('sts-editor-scenes')
      if (raw) {
        stagedProject.value = JSON.parse(raw)
        return stagedProject.value
      }
    } catch {
      // Corrupt data
    }
    return null
  }

  function clear() {
    stagedProject.value = null
    try {
      sessionStorage.removeItem('sts-staged-timeline')
      localStorage.removeItem('sts-editor-boot-project')
      localStorage.removeItem('sts-editor-scenes')
      localStorage.removeItem('sts-editor-source-folder')
      localStorage.removeItem('sts-editor-captions')
    } catch {}
  }

  return { stagedProject, stage, load, clear }
})
