<script setup>
defineOptions({ name: 'PageLayout' })

defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  maxWidth: { type: String, default: '780px' },
  badge: { type: String, default: '' },
})
</script>

<template>
  <div class="page-layout" :style="{ maxWidth }">
    <div class="page-header">
      <div class="page-header-row">
        <h2 class="page-title">{{ title }}</h2>
        <span v-if="badge" class="project-badge">{{ badge }}</span>
        <slot name="header-right" />
      </div>
      <p v-if="subtitle" class="page-subtitle">{{ subtitle }}</p>
    </div>
    <slot />
  </div>
</template>

<style scoped>
.page-layout {
  margin: 0 auto;
  padding: 32px 24px 40px;
}

.page-header {
  margin-bottom: 16px;
}

.page-header-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
</style>
