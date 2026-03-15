import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const currentProject = ref(null)
  const sidebarCollapsed = ref(localStorage.getItem('sts-sidebar-collapsed') === 'true')

  function setProject(projectId) {
    currentProject.value = projectId
  }

  function clearProject() {
    currentProject.value = null
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
    localStorage.setItem('sts-sidebar-collapsed', sidebarCollapsed.value)
  }

  return {
    currentProject,
    sidebarCollapsed,
    setProject,
    clearProject,
    toggleSidebar,
  }
})
