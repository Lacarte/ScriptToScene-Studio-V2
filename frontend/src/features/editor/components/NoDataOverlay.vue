<script setup>
defineOptions({ name: 'NoDataOverlay' })
defineProps({ visible: Boolean })
</script>

<template>
  <div v-if="visible" id="no-data-overlay" class="no-data-overlay" style="display:flex">
    <div class="no-data-content" id="no-data-empty" style="display:none">
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="12" y1="18" x2="12" y2="12" />
        <line x1="9" y1="15" x2="15" y2="15" />
      </svg>
      <h2>No Timeline Data</h2>
      <p>No asset projects found. Generate assets first in the Asset Manager.</p>
    </div>
    <div style="max-width:440px;width:100%;padding:0 20px">
      <div id="no-data-asset-list"
          style="max-height:70vh;background:var(--bg-darker, #1a1a2e);border:1px solid var(--border, #2a2a3e);border-radius:12px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,0.5)">
        <div style="padding:16px 20px;border-bottom:1px solid var(--border, #2a2a3e)">
          <h3 style="margin:0;font-size:14px;font-weight:600;color:var(--text, #e0e0e0)">Projects</h3>
          <p style="margin:2px 0 0;font-size:11px;color:var(--text-muted, #666)">Select a project to load into the editor</p>
        </div>
        <div id="no-data-asset-items" style="flex:1;overflow-y:auto;padding:8px">
          <p style="text-align:center;color:var(--text-muted,#666);font-size:12px;padding:24px 0">Loading...</p>
        </div>
      </div>
    </div>
  </div>
</template>
