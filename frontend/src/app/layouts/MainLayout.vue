<script setup>
import { ref } from 'vue'
import SidebarNav from '../SidebarNav.vue'

const collapsed = ref(false)
const toggle = () => { collapsed.value = !collapsed.value }
</script>

<template>
  <div class="layout" :class="{ collapsed }">
    <SidebarNav :collapsed="collapsed" @toggle="toggle" />
    <main class="content">
      <router-view v-slot="{ Component }">
        <keep-alive :include="['PipelinePage']">
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
