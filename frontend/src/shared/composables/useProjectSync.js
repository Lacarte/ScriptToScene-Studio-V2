import { watch, onUnmounted } from 'vue'
import { useAppStore } from '@/shared/stores/appStore.js'

/**
 * Syncs a reactive project ID to the centralized app store.
 * Call in any page's setup to keep appStore.currentProject in sync.
 *
 * @param {import('vue').Ref<string>|import('vue').ComputedRef<string>} projectRef
 */
export function useProjectSync(projectRef) {
  const app = useAppStore()

  watch(projectRef, (id) => {
    app.setProject(id || null)
  }, { immediate: true })

  onUnmounted(() => {
    // Don't clear — let the next page set its own project
  })
}
