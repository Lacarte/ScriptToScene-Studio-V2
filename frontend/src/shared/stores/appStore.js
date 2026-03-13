import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const currentProject = ref(null)
  const sidebarCollapsed = ref(false)

  function setProject(project) {
    currentProject.value = project
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  return {
    currentProject,
    sidebarCollapsed,
    setProject,
    toggleSidebar,
  }
})
