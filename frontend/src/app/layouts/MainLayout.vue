<script setup>
import SidebarNav from '../SidebarNav.vue'
import { useAppStore } from '@/shared/stores/appStore.js'

const app = useAppStore()
</script>

<template>
  <div class="layout" :class="{ collapsed: app.sidebarCollapsed }">
    <SidebarNav :collapsed="app.sidebarCollapsed" @toggle="app.toggleSidebar" />
    <main class="content">
      <router-view v-slot="{ Component }">
        <keep-alive :include="['PipelinePage', 'TtsPage', 'ScenesPage']">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-darkest);
}

.content {
  flex: 1;
  overflow-y: auto;
  margin-left: var(--sidebar-w);
  transition: margin-left 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  min-height: 100vh;
  background: var(--bg-dark);
}

.layout.collapsed .content {
  margin-left: var(--sidebar-collapsed);
}
</style>
