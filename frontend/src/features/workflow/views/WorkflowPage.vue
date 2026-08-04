<script setup>
import { ref } from 'vue'
import { VueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import NodeLibrary from '../components/NodeLibrary.vue'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'

// Step 1.1 shell: empty canvas + the five layout regions.
// Nodes/edges arrive in 1.3–1.5; execution wiring in Phase 3.
const nodes = ref([])
const edges = ref([])
</script>

<template>
  <div class="workflow-page">
    <!-- Top — toolbar -->
    <header class="wf-toolbar">
      <div class="wf-toolbar-group">
        <span class="wf-title">Workflow</span>
        <span class="wf-badge">MVP</span>
      </div>
      <div class="wf-toolbar-group wf-toolbar-actions">
        <!-- New / Open / Save / Validate / Run land in steps 1.6+ -->
      </div>
    </header>

    <div class="wf-body">
      <!-- Left — node library -->
      <aside class="wf-library">
        <div class="wf-panel-header">Nodes</div>
        <NodeLibrary />
      </aside>

      <!-- Center — canvas -->
      <main class="wf-canvas">
        <VueFlow
          v-model:nodes="nodes"
          v-model:edges="edges"
          :min-zoom="0.1"
          :max-zoom="1.5"
          :snap-to-grid="true"
          :snap-grid="[20, 20]"
          fit-view-on-init
        >
          <Background pattern-color="rgba(255,255,255,0.12)" :gap="20" />
          <Controls position="bottom-left" />
          <MiniMap position="bottom-right" pannable zoomable />
        </VueFlow>
      </main>

      <!-- Right — node inspector -->
      <aside class="wf-inspector">
        <div class="wf-panel-header">Inspector</div>
        <div class="wf-panel-empty">Select a node to configure it (step 2.1)</div>
      </aside>
    </div>

    <!-- Bottom — execution inspector -->
    <footer class="wf-bottom">
      <div class="wf-panel-header">Executions</div>
    </footer>
  </div>
</template>

<style scoped>
.workflow-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--bg-dark);
  color: var(--text);
}

.wf-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-darkest);
}

.wf-toolbar-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.wf-title {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.wf-badge {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent);
  border: 1px solid rgba(78, 205, 196, 0.4);
  border-radius: 6px;
  padding: 2px 6px;
}

.wf-body {
  display: flex;
  flex: 1;
  min-height: 0;
}

.wf-library {
  width: 240px;
  min-width: 240px;
  border-right: 1px solid var(--border);
  background: var(--bg-darkest);
  display: flex;
  flex-direction: column;
}

.wf-inspector {
  width: 300px;
  min-width: 300px;
  border-left: 1px solid var(--border);
  background: var(--bg-darkest);
  display: flex;
  flex-direction: column;
}

.wf-canvas {
  flex: 1;
  min-width: 0;
  position: relative;
}

.wf-bottom {
  height: 140px;
  min-height: 140px;
  border-top: 1px solid var(--border);
  background: var(--bg-darkest);
}

.wf-panel-header {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--text-muted);
  padding: 10px 14px 6px;
}

.wf-panel-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 14px;
  opacity: 0.7;
}
</style>
