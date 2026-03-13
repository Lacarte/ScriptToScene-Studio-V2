<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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
}

.content {
  flex: 1;
  overflow-y: auto;
  padding: 32px;
  margin-left: var(--sidebar-w);
  transition: margin-left 0.3s ease;
}

.layout.collapsed .content {
  margin-left: var(--sidebar-collapsed);
}
</style>
