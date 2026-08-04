<script setup>
import { computed, markRaw } from 'vue'
import { VueFlow, useVueFlow, MarkerType } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import dagre from '@dagrejs/dagre'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'
import { useWorkflowStore } from '../stores/workflow.js'
import { DRAG_MIME } from '../constants.js'
import { validateConnection } from '../validation.js'
import { useToast } from '@/shared/composables/useToast.js'
import NodeLibrary from '../components/NodeLibrary.vue'
import NodeCard from '../components/NodeCard.vue'

const store = useWorkflowStore()
const toast = useToast()
const { screenToFlowCoordinate, fitView } = useVueFlow()

const nodeTypes = { sts: markRaw(NodeCard) }

// Store (persisted shape) → Vue Flow elements. Vue Flow runtime props stay here.
const flowNodes = computed(() =>
  store.nodes.map((n) => ({
    id: n.id,
    type: 'sts',
    position: { ...n.position },
    data: { nodeType: n.type, label: n.name, disabled: n.disabled },
  })),
)

const flowEdges = computed(() =>
  store.edges.map((e) => ({
    id: e.id,
    source: e.source_node,
    target: e.target_node,
    sourceHandle: e.source_port,
    targetHandle: e.target_port,
    markerEnd: MarkerType.ArrowClosed,
    class: e.edge_type === 'control' ? 'wf-edge-control' : 'wf-edge-data',
  })),
)

// ── Palette drop → add node at canvas position ─────────────────────────
function onDragOver(event) {
  if (event.dataTransfer?.types?.includes(DRAG_MIME)) {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
  }
}

function onDrop(event) {
  const typeKey = event.dataTransfer?.getData(DRAG_MIME)
  if (!typeKey) return
  const position = screenToFlowCoordinate({ x: event.clientX, y: event.clientY })
  store.addNode(typeKey, position)
}

// ── Sync Vue Flow interactions back into the store ─────────────────────
function onNodeDragStop({ node }) {
  store.moveNode(node.id, { x: node.position.x, y: node.position.y })
}

function onNodesChange(changes) {
  const removed = changes.filter((c) => c.type === 'remove').map((c) => c.id)
  if (removed.length) store.removeNodes(removed)
}

function onEdgesChange(changes) {
  const removed = changes.filter((c) => c.type === 'remove').map((c) => c.id)
  if (removed.length) store.removeEdges(removed)
}

function onViewportChangeEnd(vp) {
  store.setViewport(vp)
}

// ── Connections (validated, contracts §3) ──────────────────────────────
function toConnectionShape(params) {
  return {
    sourceNode: params.source,
    sourcePort: params.sourceHandle,
    targetNode: params.target,
    targetPort: params.targetHandle,
  }
}

function onConnect(params) {
  const verdict = store.connectNodes(toConnectionShape(params))
  if (!verdict.ok) toast.error(verdict.reason)
}

// Live feedback while dragging a connection: valid targets highlight,
// invalid ones show the not-allowed cursor.
function isValidConnection(params) {
  return validateConnection(
    { nodes: store.nodes, edges: store.edges, nodeTypes: store.nodeTypes },
    toConnectionShape(params),
  ).ok
}

// ── Minimap colored by category ────────────────────────────────────────
function minimapColor(node) {
  const def = store.nodeTypes[node.data?.nodeType]
  return store.categories[def?.category]?.color || '#4b5563'
}

// ── Dagre tidy-up ──────────────────────────────────────────────────────
function tidyUp() {
  if (!store.nodes.length) return
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', nodesep: 40, ranksep: 90 })
  g.setDefaultEdgeLabel(() => ({}))
  for (const node of store.nodes) {
    g.setNode(node.id, { width: 200, height: 60 })
  }
  for (const edge of store.edges) {
    g.setEdge(edge.source_node, edge.target_node)
  }
  dagre.layout(g)
  for (const node of store.nodes) {
    const pos = g.node(node.id)
    if (pos) {
      store.moveNode(node.id, {
        x: Math.round((pos.x - 100) / 20) * 20,
        y: Math.round((pos.y - 30) / 20) * 20,
      })
    }
  }
  requestAnimationFrame(() => fitView({ padding: 0.15 }))
}
</script>

<template>
  <div class="workflow-page">
    <!-- Top — toolbar -->
    <header class="wf-toolbar">
      <div class="wf-toolbar-group">
        <span class="wf-title">{{ store.workflowName }}</span>
        <span v-if="store.dirty" class="wf-dirty" title="Unsaved changes">●</span>
        <span class="wf-badge">MVP</span>
      </div>
      <div class="wf-toolbar-group wf-toolbar-actions">
        <button class="wf-btn" :disabled="!store.nodeCount" title="Auto-arrange nodes" @click="tidyUp">
          Tidy up
        </button>
        <button class="wf-btn" :disabled="!store.nodeCount" title="Fit view" @click="fitView({ padding: 0.15 })">
          Fit
        </button>
      </div>
    </header>

    <div class="wf-body">
      <!-- Left — node library -->
      <aside class="wf-library">
        <div class="wf-panel-header">Nodes</div>
        <NodeLibrary />
      </aside>

      <!-- Center — canvas -->
      <main class="wf-canvas" @dragover="onDragOver" @drop="onDrop">
        <VueFlow
          :nodes="flowNodes"
          :edges="flowEdges"
          :node-types="nodeTypes"
          :min-zoom="0.1"
          :max-zoom="1.5"
          :snap-to-grid="true"
          :snap-grid="[20, 20]"
          :delete-key-code="'Delete'"
          :multi-selection-key-code="'Control'"
          :selection-key-code="'Shift'"
          :is-valid-connection="isValidConnection"
          fit-view-on-init
          @connect="onConnect"
          @node-drag-stop="onNodeDragStop"
          @nodes-change="onNodesChange"
          @edges-change="onEdgesChange"
          @viewport-change-end="onViewportChangeEnd"
        >
          <Background pattern-color="rgba(255,255,255,0.12)" :gap="20" />
          <Controls position="bottom-left" />
          <MiniMap position="bottom-right" pannable zoomable :node-color="minimapColor" />
          <div v-if="!store.nodeCount" class="wf-canvas-hint">
            Drag a node from the library to start building
          </div>
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

.wf-dirty {
  color: var(--accent-warning, #ffb347);
  font-size: 14px;
  line-height: 1;
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

.wf-btn {
  background: var(--bg-dark);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.wf-btn:hover:not(:disabled) {
  color: var(--text);
  border-color: var(--accent);
}

.wf-btn:disabled {
  opacity: 0.4;
  cursor: default;
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

.wf-canvas-hint {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: var(--text-muted);
  font-size: 13px;
  pointer-events: none;
  opacity: 0.6;
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

:deep(.wf-edge-control .vue-flow__edge-path) {
  stroke-dasharray: 5 4;
  opacity: 0.7;
}
</style>
