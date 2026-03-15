<script setup>
/**
 * Shared history section wrapper used across all feature pages.
 * Provides consistent header (title + count/tools), scrollable list,
 * and empty state.
 *
 * Usage:
 *   <HistorySection title="History" :count="items.length" count-label="files" empty-text="No items yet">
 *     <template #tools>
 *       <button>Delete All</button>
 *     </template>
 *     <MyHistoryCard v-for="item in items" :key="item.id" :item="item" />
 *   </HistorySection>
 */
defineOptions({ name: 'HistorySection' })

defineProps({
  title: { type: String, default: 'History' },
  count: { type: Number, default: 0 },
  countLabel: { type: String, default: '' },
  emptyText: { type: String, default: 'No items yet' },
  maxHeight: { type: String, default: '400px' },
})
</script>

<template>
  <div class="history-section">
    <div class="history-header">
      <h3 class="history-title">{{ title }}</h3>
      <div class="history-header-right">
        <span class="history-count">
          {{ count }} {{ countLabel || (count === 1 ? 'item' : 'items') }}
        </span>
        <slot name="tools" />
      </div>
    </div>

    <p v-if="!count" class="history-empty">{{ emptyText }}</p>

    <div v-else class="history-list" :style="{ maxHeight }">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.history-section {
  margin-top: 16px;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.history-title {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
}

.history-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.history-count {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-muted);
}

.history-empty {
  text-align: center;
  padding: 32px 0;
  font-size: 13px;
  color: var(--text-muted);
}

.history-list {
  overflow-y: auto;
}
</style>
