<script setup>
import { computed, markRaw, onMounted, ref } from 'vue'
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
import NodeInspector from '../components/NodeInspector.vue'

const store = useWorkflowStore()
const toast = useToast()
const { screenToFlowCoordinate, fitView, setViewport: setFlowViewport } = useVueFlow()
const importInput = ref(null)

onMounted(async () => {
  try {
    await Promise.all([
      store.loadNodeTypes(),
      store.refreshWorkflowList(),
      store.loadTemplates(),
    ])
  } catch (err) {
    toast.error(err?.message || 'Failed to load workflow data')
  }
})

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
    { nodes: store.nodes, edges: store.edges, nodeTypes: store.nodeTypes, portTypes: store.portTypes },
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

function confirmDiscard() {
  return !store.dirty || window.confirm('Discard unsaved workflow changes?')
}

async function restoreViewport() {
  await setFlowViewport(store.viewport)
  store.dirty = false
}

async function onNew() {
  if (!confirmDiscard()) return
  store.newWorkflow()
  await restoreViewport()
}

async function onOpen(event) {
  const id = event.target.value
  event.target.value = ''
  if (!id || !confirmDiscard()) return
  try {
    await store.openWorkflow(id)
    await restoreViewport()
    toast.success(`Opened ${store.workflowName}`)
  } catch (err) {
    toast.error(store.persistenceError || err.message)
  }
}

async function onSave() {
  try {
    if (!store.workflowId && store.workflowName === 'Untitled workflow') {
      const name = window.prompt('Workflow name', store.workflowName)
      if (!name?.trim()) return
      store.workflowName = name.trim()
    }
    await store.saveWorkflow()
    toast.success('Workflow saved')
  } catch (err) {
    toast.error(store.persistenceError || err.message)
  }
}

async function onSaveAs() {
  const name = window.prompt('Save workflow as', `${store.workflowName} copy`)
  if (!name?.trim()) return
  try {
    await store.saveAs(name)
    toast.success('Workflow copy saved')
  } catch (err) {
    toast.error(store.persistenceError || err.message)
  }
}

async function onDuplicate() {
  try {
    await store.saveAs(`${store.workflowName} copy`)
    toast.success('Workflow duplicated')
  } catch (err) {
    toast.error(store.persistenceError || err.message)
  }
}

async function onTemplate(event) {
  const templateId = event.target.value
  event.target.value = ''
  if (!templateId || !confirmDiscard()) return
  if (store.applyTemplate(templateId)) {
    requestAnimationFrame(() => fitView({ padding: 0.1 }))
    toast.info('Template loaded — add your script and save when ready')
  }
}

async function onImportFile(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file || !confirmDiscard()) return
  if (file.size > 2 * 1024 * 1024) {
    toast.error('Workflow JSON exceeds the 2 MiB limit')
    return
  }
  try {
    const document = JSON.parse(await file.text())
    await store.importDocument(document)
    await restoreViewport()
    toast.success('Workflow imported')
  } catch (err) {
    toast.error(store.persistenceError || err?.message || 'Invalid workflow JSON')
  }
}

function onExport() {
  if (!store.workflowId) {
    toast.warning('Save the workflow before exporting it')
    return
  }
  const anchor = document.createElement('a')
  anchor.href = `/api/workflows/${encodeURIComponent(store.workflowId)}/export`
  anchor.download = `${store.workflowId}.json`
  anchor.click()
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
        <button class="wf-btn" :disabled="store.persistenceLoading" @click="onNew">New</button>
        <select class="wf-select" :disabled="store.persistenceLoading" aria-label="Open workflow" @change="onOpen">
          <option value="">Open…</option>
          <option v-for="item in store.workflowList" :key="item.workflow_id" :value="item.workflow_id">
            {{ item.name }}
          </option>
        </select>
        <select class="wf-select" :disabled="store.persistenceLoading" aria-label="Workflow template" @change="onTemplate">
          <option value="">Template…</option>
          <option v-for="item in store.templates" :key="item.template_id" :value="item.template_id">
            {{ item.workflow.name }}
          </option>
        </select>
        <button class="wf-btn primary" :disabled="store.persistenceLoading || (!!store.workflowId && !store.dirty)" @click="onSave">
          Save
        </button>
        <button class="wf-btn" :disabled="store.persistenceLoading" @click="onSaveAs">Save As</button>
        <button class="wf-btn" :disabled="store.persistenceLoading" @click="onDuplicate">Duplicate</button>
        <button class="wf-btn" :disabled="store.persistenceLoading" @click="importInput?.click()">Import</button>
        <button class="wf-btn" :disabled="!store.workflowId" @click="onExport">Export</button>
        <input ref="importInput" class="wf-file-input" type="file" accept="application/json,.json" @change="onImportFile" />
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
          @node-click="({ node }) => store.selectNode(node.id)"
          @pane-click="store.clearSelection"
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
        <NodeInspector />
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

.wf-toolbar-actions {
  gap: 6px;
  min-width: 0;
  overflow-x: auto;
  padding-bottom: 2px;
}

.wf-toolbar-actions > * {
  flex: 0 0 auto;
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

.wf-btn.primary {
  color: var(--bg-darkest);
  background: var(--accent);
  border-color: var(--accent);
}

.wf-select {
  max-width: 150px;
  background: var(--bg-dark);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 12px;
  padding: 6px 8px;
}

.wf-file-input {
  display: none;
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
