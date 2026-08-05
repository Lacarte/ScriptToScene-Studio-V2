<script setup>
import { computed, markRaw, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { VueFlow, useVueFlow, MarkerType } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import dagre from '@dagrejs/dagre'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'
import { api } from '@/shared/api/client.js'
import { useWorkflowStore } from '../stores/workflow.js'
import { DRAG_MIME } from '../constants.js'
import { validateConnection } from '../validation.js'
import { useToast } from '@/shared/composables/useToast.js'
import NodeLibrary from '../components/NodeLibrary.vue'
import NodeCard from '../components/NodeCard.vue'
import NodeInspector from '../components/NodeInspector.vue'
import ExecutionPanel from '../components/ExecutionPanel.vue'

const store = useWorkflowStore()
const toast = useToast()
const { screenToFlowCoordinate, fitView, setViewport: setFlowViewport } = useVueFlow()
const importInput = ref(null)
const canvasSelection = ref(new Set())
const runMode = ref('full')

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
  await maybeRecoverDraft()
  window.addEventListener('beforeunload', onBeforeUnload)
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('keydown', onKeydown)
  // The component is going away (in-app navigation): persist any pending
  // debounced edits so nothing is lost while the user is elsewhere.
  store.flushDraft()
})

function onKeydown(event) {
  if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'z') return
  const target = event.target
  if (target instanceof HTMLElement
    && (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)) {
    return
  }
  const changed = event.shiftKey ? store.redo() : store.undo()
  if (changed) {
    event.preventDefault()
    toast.info(event.shiftKey ? 'Redone' : 'Undone')
  }
}

// ── Draft autosave protection (step 2.4) ───────────────────────────────
async function maybeRecoverDraft() {
  const draft = store.peekDraft()
  if (!draft) return
  const name = draft.document?.name || 'Untitled workflow'
  const when = draft.saved_at ? ` (autosaved ${new Date(draft.saved_at).toLocaleString()})` : ''
  if (window.confirm(`Recover unsaved draft "${name}"${when}?`)) {
    store.recoverDraft()
    // Deliberately not restoreViewport(): the recovered document is unsaved
    // and must stay dirty until the user explicitly saves it.
    await setFlowViewport(store.viewport)
    toast.info('Draft recovered — save to keep it')
  } else {
    store.clearDraft()
  }
}

function onBeforeUnload(event) {
  // Synchronous flush: this is what makes a killed tab lose nothing.
  store.flushDraft()
  if (store.dirty) {
    event.preventDefault()
    event.returnValue = ''
  }
}

function onVisibilityChange() {
  if (document.visibilityState === 'hidden') store.flushDraft()
}

onBeforeRouteLeave(() => {
  if (!store.dirty) return true
  store.flushDraft()
  return window.confirm(
    'You have unsaved workflow changes. A draft has been kept — leave the workflow builder?',
  )
})

const nodeTypes = { sts: markRaw(NodeCard) }

// Store (persisted shape) → Vue Flow elements. Vue Flow runtime props stay here.
const flowNodes = computed(() =>
  store.nodes.map((n) => ({
    id: n.id,
    type: 'sts',
    position: { ...n.position },
    selected: canvasSelection.value.has(n.id),
    data: { nodeType: n.type, label: n.name, disabled: n.disabled },
  })),
)

const flowEdges = computed(() =>
  store.edges.map((e) => {
    const sourceExecution = store.nodeExecution(e.source_node)
    const summary = sourceExecution.status === 'succeeded'
      ? sourceExecution.outputs_summary?.[e.source_port]
      : undefined
    return {
      id: e.id,
      source: e.source_node,
      target: e.target_node,
      sourceHandle: e.source_port,
      targetHandle: e.target_port,
      markerEnd: MarkerType.ArrowClosed,
      animated: sourceExecution.status === 'running',
      label: summary === undefined ? '' : edgeSummary(summary),
      class: [
        e.edge_type === 'control' ? 'wf-edge-control' : 'wf-edge-data',
        `wf-edge-${sourceExecution.status}`,
        sourceExecution.from_sample_data ? 'wf-edge-sample' : '',
      ].filter(Boolean).join(' '),
    }
  }),
)

function edgeSummary(value) {
  let text
  if (typeof value === 'string') text = value
  else if (value === null) text = 'null'
  else if (Array.isArray(value)) text = `${value.length} items`
  else if (typeof value === 'object') {
    const keys = Object.keys(value)
    text = keys.length ? keys.slice(0, 3).join(', ') : '{}'
  } else text = String(value)
  return text.length > 42 ? `${text.slice(0, 39)}…` : text
}

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
  // Auto-spawns pre-connected sample stubs when the workflow setting is on.
  store.addNodeWithStubs(typeKey, position)
}

// ── Sync Vue Flow interactions back into the store ─────────────────────
function onNodeDragStop({ node, nodes: draggedNodes }) {
  // Multi-select/box drags carry every moved node in `nodes`; persisting
  // only the grab target would snap the rest back on the next re-render.
  const moved = draggedNodes?.length ? draggedNodes : [node]
  store.moveNodes(moved.map((dragged) => ({
    id: dragged.id,
    position: { x: dragged.position.x, y: dragged.position.y },
  })))
}

function onNodesChange(changes) {
  const selectionChanges = changes.filter((change) => change.type === 'select')
  if (selectionChanges.length) {
    const next = new Set(canvasSelection.value)
    for (const change of selectionChanges) {
      if (change.selected) next.add(change.id)
      else next.delete(change.id)
    }
    canvasSelection.value = next
  }
  const removed = changes.filter((c) => c.type === 'remove').map((c) => c.id)
  if (removed.length) {
    store.removeNodes(removed)
    canvasSelection.value = new Set(
      [...canvasSelection.value].filter((nodeId) => !removed.includes(nodeId)),
    )
  }
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
    // Present only when Vue Flow re-validates an existing edge; interactive
    // connection params carry no id.
    edgeId: params.id,
  }
}

function onConnect(params) {
  const verdict = store.connectNodes(toConnectionShape(params))
  if (!verdict.ok) {
    toast.error(verdict.reason)
  } else if (verdict.detachedStub) {
    toast.info('Sample input replaced by the real connection — Ctrl+Z restores it')
  }
}

// ── Node context menu: manual stub attachment (step 2.5) ───────────────
const contextMenu = ref(null) // {nodeId, x, y}

function onNodeContextMenu({ event, node }) {
  event.preventDefault()
  // Fixed positioning: viewport coordinates work regardless of panel layout.
  contextMenu.value = { nodeId: node.id, x: event.clientX, y: event.clientY }
}

function closeContextMenu() {
  contextMenu.value = null
}

function onAttachSampleInputs() {
  const created = store.attachSampleInputs(contextMenu.value.nodeId)
  closeContextMenu()
  toast.info(created.length
    ? `Attached ${created.length} sample input${created.length > 1 ? 's' : ''}`
    : 'Every required input is already connected')
}

function onAttachResultViewer() {
  const stub = store.attachResultViewer(contextMenu.value.nodeId)
  closeContextMenu()
  toast.info(stub ? 'Result viewer attached' : 'This node has no data output to view')
}

function isFailedNode(nodeId) {
  return store.nodeExecution(nodeId).status === 'failed'
}

function targetsForMode(mode, nodeId = store.selectedNodeId) {
  if (mode === 'full') return []
  if (mode === 'selected') return [...canvasSelection.value]
  return nodeId ? [nodeId] : []
}

function canRun(mode, nodeId = store.selectedNodeId) {
  if (!store.nodeCount || store.executionLoading || store.executionActive) return false
  const targets = targetsForMode(mode, nodeId)
  if (mode === 'full') return true
  if (mode === 'selected') return targets.length > 0
  if (targets.length !== 1) return false
  if (mode === 'retry_failed' || mode === 'retry_failed_desc') {
    return isFailedNode(targets[0])
  }
  return true
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
  const moves = []
  for (const node of store.nodes) {
    const pos = g.node(node.id)
    if (pos) {
      moves.push({
        id: node.id,
        position: {
          x: Math.round((pos.x - 100) / 20) * 20,
          y: Math.round((pos.y - 30) / 20) * 20,
        },
      })
    }
  }
  store.moveNodes(moves)
  requestAnimationFrame(() => fitView({ padding: 0.15 }))
}

const validating = ref(false)

async function onValidate() {
  validating.value = true
  try {
    const data = await api.post('/api/workflow/validate', {
      body: { workflow: store.toDocument() },
    })
    if (data.valid && !data.warnings.length) {
      toast.success('Workflow is valid')
    } else if (data.valid) {
      toast.warning(`Valid, with ${data.warnings.length} warning(s): ${data.warnings[0]?.message}`)
    } else {
      const first = data.problems[0]?.message || 'see node badges'
      toast.error(`${data.problems.length} problem(s) — ${first}`)
    }
  } catch (err) {
    toast.error(err?.message || 'Validation request failed')
  } finally {
    validating.value = false
  }
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

async function onRun(mode = runMode.value, nodeId = store.selectedNodeId) {
  const targets = targetsForMode(mode, nodeId)
  if (!canRun(mode, nodeId)) {
    const message = mode === 'selected'
      ? 'Select one or more canvas nodes first'
      : mode.startsWith('retry_')
        ? 'Choose a node that failed in the current execution'
        : 'Choose a node first'
    toast.warning(message)
    return
  }
  try {
    await store.runWorkflow({ runMode: mode, targetNodeIds: targets })
    toast.success('Workflow run started')
  } catch (err) {
    toast.error(store.executionError || err?.message || 'Failed to run workflow')
  }
}

async function onContextRun(mode) {
  const nodeId = contextMenu.value?.nodeId
  closeContextMenu()
  await onRun(mode, nodeId)
}

async function onStop() {
  try {
    await store.stopExecution()
    toast.info('Stopping workflow…')
  } catch (err) {
    toast.error(store.executionError || err?.message || 'Failed to stop workflow')
  }
}
</script>

<template>
  <div class="workflow-page">
    <!-- Top — toolbar -->
    <header class="wf-toolbar">
      <div class="wf-toolbar-group">
        <span class="wf-title">{{ store.workflowName }}</span>
        <span v-if="store.dirty" class="wf-dirty" title="Unsaved changes">●</span>
        <span
          v-if="store.dirty && store.draftSavedAt"
          class="wf-draft-hint"
          :title="`Draft autosaved ${new Date(store.draftSavedAt).toLocaleTimeString()}`"
        >
          draft saved
        </span>
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
        <button
          class="wf-btn"
          :disabled="!store.canUndo"
          :title="store.undoLabel ? `Undo ${store.undoLabel} (Ctrl+Z)` : 'Nothing to undo'"
          @click="store.undo()"
        >Undo</button>
        <button
          class="wf-btn"
          :disabled="!store.canRedo"
          :title="store.redoLabel ? `Redo ${store.redoLabel} (Ctrl+Shift+Z)` : 'Nothing to redo'"
          @click="store.redo()"
        >Redo</button>
        <input ref="importInput" class="wf-file-input" type="file" accept="application/json,.json" @change="onImportFile" />
        <button class="wf-btn" :disabled="!store.nodeCount || validating" title="Validate workflow on the server" @click="onValidate">
          Validate
        </button>
        <select
          v-if="!store.executionActive"
          v-model="runMode"
          class="wf-select"
          aria-label="Run mode"
          title="Choose which part of the workflow to run"
        >
          <option value="full">Full workflow</option>
          <option value="node_with_deps">Node + dependencies</option>
          <option value="node_isolated">Node in isolation</option>
          <option value="selected">Selected + dependencies</option>
          <option value="from_node">From node downstream</option>
          <option value="retry_failed">Retry failed node</option>
          <option value="retry_failed_desc">Retry failed + downstream</option>
        </select>
        <button
          v-if="!store.executionActive"
          class="wf-btn run"
          :disabled="!canRun(runMode)"
          :title="`Run mode: ${runMode}`"
          @click="onRun()"
        >Run</button>
        <button
          v-else
          class="wf-btn stop"
          :disabled="store.currentExecution?.status === 'cancelling'"
          title="Cooperatively stop the current run"
          @click="onStop"
        >{{ store.currentExecution?.status === 'cancelling' ? 'Stopping…' : 'Stop' }}</button>
        <button class="wf-btn" :disabled="!store.nodeCount" title="Auto-arrange nodes" @click="tidyUp">
          Tidy up
        </button>
        <button class="wf-btn" :disabled="!store.nodeCount" title="Fit view" @click="fitView({ padding: 0.15 })">
          Fit
        </button>
        <label class="wf-toggle" title="Auto-attach editable sample stubs when dropping unconnected nodes">
          <input
            type="checkbox"
            :checked="store.autoAttachStubs"
            @change="store.setAutoAttachStubs($event.target.checked)"
          />
          Auto-stubs
        </label>
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
          @node-context-menu="onNodeContextMenu"
          @pane-click="store.clearSelection(); closeContextMenu()"
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

        <!-- Node context menu: sample helpers and partial run modes. -->
        <template v-if="contextMenu">
          <div class="wf-context-backdrop" @click="closeContextMenu" @contextmenu.prevent="closeContextMenu" />
          <div class="wf-context-menu" :style="{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }">
            <button class="wf-context-item" @click="onContextRun('node_with_deps')">Run node + dependencies</button>
            <button class="wf-context-item" @click="onContextRun('node_isolated')">Run node in isolation</button>
            <button class="wf-context-item" @click="onContextRun('from_node')">Run from node downstream</button>
            <button
              class="wf-context-item"
              :disabled="!isFailedNode(contextMenu.nodeId)"
              @click="onContextRun('retry_failed')"
            >Retry failed node</button>
            <button
              class="wf-context-item"
              :disabled="!isFailedNode(contextMenu.nodeId)"
              @click="onContextRun('retry_failed_desc')"
            >Retry failed + downstream</button>
            <template v-if="!store.isStubType(store.nodeById(contextMenu.nodeId)?.type)">
              <button class="wf-context-item" @click="onAttachSampleInputs">Attach sample inputs</button>
              <button class="wf-context-item" @click="onAttachResultViewer">Attach result viewer</button>
            </template>
          </div>
        </template>
      </main>

      <!-- Right — node inspector -->
      <aside class="wf-inspector">
        <div class="wf-panel-header">Inspector</div>
        <NodeInspector />
      </aside>
    </div>

    <!-- Bottom — live execution inspector (step 3.6) -->
    <ExecutionPanel />
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

.wf-draft-hint {
  font-size: 10px;
  color: var(--text-muted);
  white-space: nowrap;
  opacity: 0.8;
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

.wf-btn.run { color: #a7f3d0; border-color: rgba(52,211,153,.45); background: rgba(52,211,153,.09); }
.wf-btn.stop { color: #fda4af; border-color: rgba(251,113,133,.5); background: rgba(251,113,133,.09); }

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

.wf-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  white-space: nowrap;
  cursor: pointer;
  padding: 0 4px;
}

.wf-toggle input {
  accent-color: var(--accent);
}

.wf-context-backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
}

.wf-context-menu {
  position: fixed;
  z-index: 41;
  min-width: 180px;
  background: var(--bg-darkest);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
  padding: 4px;
  display: flex;
  flex-direction: column;
}

.wf-context-item {
  background: transparent;
  border: none;
  border-radius: 7px;
  color: var(--text-secondary);
  font-size: 12px;
  text-align: left;
  padding: 7px 10px;
  cursor: pointer;
}

.wf-context-item:hover {
  background: rgba(255, 255, 255, 0.06);
  color: var(--text);
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

:deep(.wf-edge-running .vue-flow__edge-path) { stroke: #38bdf8; }
:deep(.wf-edge-succeeded .vue-flow__edge-path) { stroke: rgba(52,211,153,.8); }
:deep(.wf-edge-failed .vue-flow__edge-path) { stroke: #fb7185; }
:deep(.wf-edge-cancelled .vue-flow__edge-path) { stroke: #f59e0b; }
:deep(.wf-edge-sample .vue-flow__edge-path) { stroke-dasharray: 3 4; }
:deep(.vue-flow__edge-text) { fill: var(--text-secondary); font-size: 9px; }
:deep(.vue-flow__edge-textbg) { fill: var(--bg-darkest); fill-opacity: .88; }
</style>
