import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/shared/api/client.js'
import { validateConnection } from '../validation.js'
import { nodeIssues } from '../schema.js'
import { createExecutionEventStream } from '../composables/useExecutionEvents.js'

/**
 * Workflow builder store — the domain model behind the canvas.
 * Nodes/edges are stored in the persisted document shape (contracts.md §4);
 * WorkflowPage maps them to Vue Flow elements. Vue Flow runtime props never
 * enter this store.
 */

// Draft autosave (step 2.4). Drafts live in localStorage — not the backend —
// so a synchronous flush during beforeunload/visibilitychange can never be
// lost to an in-flight network call, and the frozen API surface stays intact.
export const DRAFT_STORAGE_KEY = 'sts-workflow-draft'
export const DRAFT_DEBOUNCE_MS = 1000

export const useWorkflowStore = defineStore('workflow', () => {
  // ── Registry (served by the backend, loaded once) ─────────────────────
  const registryVersion = ref(null)
  const nodeTypes = ref({})
  const categories = ref({})
  const portTypes = ref([])
  const samplePayloads = ref({})
  const registryLoading = ref(false)
  const registryError = ref('')

  async function loadNodeTypes() {
    if (registryLoading.value || registryVersion.value !== null) return
    registryLoading.value = true
    registryError.value = ''
    try {
      const data = await api.get('/api/workflow/node-types')
      registryVersion.value = data.registry_version
      nodeTypes.value = data.node_types || {}
      categories.value = data.categories || {}
      portTypes.value = data.port_types || []
      samplePayloads.value = data.sample_payloads || {}
    } catch (err) {
      registryError.value = err?.message || 'Failed to load node types'
    } finally {
      registryLoading.value = false
    }
  }

  // ── Document state (persisted shape only) ─────────────────────────────
  const workflowId = ref(null)
  const workflowName = ref('Untitled workflow')
  const workflowDescription = ref('')
  const nodes = ref([])   // {id, type, type_version, name, position, configuration, disabled}
  const edges = ref([])   // {id, source_node, source_port, target_node, target_port, edge_type}
  const viewport = ref({ x: 0, y: 0, zoom: 1 })
  const variables = ref({})
  const settings = ref({ on_error: 'stop' })
  const extensions = ref({})
  const createdAt = ref(null)
  const updatedAt = ref(null)
  const dirty = ref(false)
  const draftSavedAt = ref(null)

  // Live execution state (step 3.6). This is deliberately separate from the
  // persisted workflow document, so status updates never make a graph dirty.
  const currentExecution = ref(null)
  const executionLoading = ref(false)
  const executionError = ref('')
  const selectedExecutionNodeId = ref(null)
  let executionStream = null

  const executionActive = computed(() =>
    ['queued', 'running', 'cancelling'].includes(currentExecution.value?.status),
  )

  function emptyNodeExecution(status = 'idle') {
    return {
      status,
      attempts: 0,
      duration_ms: null,
      from_sample_data: false,
      resolved_inputs_summary: {},
      outputs_summary: {},
      artifact_refs: [],
      logs: [],
      error: null,
    }
  }

  function nodeExecution(nodeId) {
    return currentExecution.value?.nodes?.[nodeId] || emptyNodeExecution()
  }

  function closeExecutionStream() {
    executionStream?.close()
    executionStream = null
  }

  function clearExecution() {
    closeExecutionStream()
    currentExecution.value = null
    selectedExecutionNodeId.value = null
    executionError.value = ''
  }

  function applyExecutionSnapshot(snapshot) {
    if (!snapshot || typeof snapshot !== 'object') return
    currentExecution.value = plain(snapshot)
    if (
      selectedExecutionNodeId.value
      && !currentExecution.value.nodes?.[selectedExecutionNodeId.value]
    ) selectedExecutionNodeId.value = null
  }

  async function refreshExecution(executionId = currentExecution.value?.execution_id) {
    if (!executionId) return null
    try {
      const data = await api.get(`/api/workflow/executions/${encodeURIComponent(executionId)}`)
      applyExecutionSnapshot(data.execution)
      return data.execution
    } catch (err) {
      executionError.value = err?.message || 'Failed to refresh execution'
      throw err
    }
  }

  function applyExecutionEvent(event) {
    if (!event || typeof event !== 'object') return
    if (event.snapshot) applyExecutionSnapshot(event.snapshot)
    const execution = currentExecution.value
    if (!execution) return

    if (event.node_id) {
      execution.nodes ||= {}
      const record = execution.nodes[event.node_id] ||= emptyNodeExecution('queued')
      if (event.status) record.status = event.status
      if (Number.isFinite(event.attempt)) record.attempts = event.attempt
      if (Number.isFinite(event.duration_ms)) record.duration_ms = event.duration_ms
      if (typeof event.from_sample_data === 'boolean') {
        record.from_sample_data = event.from_sample_data
      }
      if (event.error) record.error = plain(event.error)
    } else if (event.status && event.status !== 'reset') {
      execution.status = event.status
    }

    if (['succeeded', 'failed', 'cancelled'].includes(event.status) && !event.node_id) {
      closeExecutionStream()
      // The terminal record contains output summaries/artifact refs that are
      // intentionally not repeated in every SSE event.
      void refreshExecution(execution.execution_id).catch(() => {})
    }
  }

  function watchExecution(executionId, { EventSourceImpl } = {}) {
    closeExecutionStream()
    executionStream = createExecutionEventStream(executionId, {
      onEvent: applyExecutionEvent,
      onError: (err) => {
        // EventSource reports transient reconnects through onerror too. Keep
        // the current state visible and expose a small, non-destructive hint.
        executionError.value = err?.message || 'Execution event stream interrupted'
      },
      ...(EventSourceImpl ? { EventSourceImpl } : {}),
    })
    return executionStream
  }

  async function runWorkflow({ EventSourceImpl } = {}) {
    executionLoading.value = true
    executionError.value = ''
    selectedExecutionNodeId.value = null
    closeExecutionStream()
    try {
      const payload = workflowId.value && !dirty.value
        ? { workflow_id: workflowId.value }
        : { workflow: toDocument() }
      const data = await api.post('/api/workflow/run', {
        body: { ...payload, run_mode: 'full', target_node_ids: [], force: false },
      })
      currentExecution.value = {
        schema_version: 1,
        execution_id: data.execution_id,
        workflow_id: workflowId.value || '',
        workflow_snapshot: plain(toDocument()),
        project_id: data.project_id,
        run_mode: 'full',
        scope_node_ids: nodes.value.map((node) => node.id),
        status: data.status || 'queued',
        started_at: new Date().toISOString(),
        finished_at: null,
        nodes: Object.fromEntries(nodes.value.map((node) => [node.id, emptyNodeExecution('queued')])),
      }
      watchExecution(data.execution_id, { EventSourceImpl })
      return data
    } catch (err) {
      executionError.value = err?.message || 'Failed to start workflow'
      throw err
    } finally {
      executionLoading.value = false
    }
  }

  async function stopExecution() {
    const executionId = currentExecution.value?.execution_id
    if (!executionId || !executionActive.value) return null
    executionError.value = ''
    try {
      const data = await api.post(
        `/api/workflow/executions/${encodeURIComponent(executionId)}/stop`,
        { body: {} },
      )
      currentExecution.value.status = data.status || 'cancelling'
      return data
    } catch (err) {
      executionError.value = err?.message || 'Failed to stop execution'
      throw err
    }
  }

  function selectExecutionNode(nodeId) {
    const record = currentExecution.value?.nodes?.[nodeId]
    selectedExecutionNodeId.value = record && ['succeeded', 'failed', 'cancelled', 'skipped'].includes(record.status)
      ? nodeId
      : null
  }

  const selectedExecutionNode = computed(() =>
    selectedExecutionNodeId.value
      ? currentExecution.value?.nodes?.[selectedExecutionNodeId.value] || null
      : null,
  )

  const editorProjectId = computed(() => {
    const execution = currentExecution.value
    if (!execution) return null
    for (const node of execution.workflow_snapshot?.nodes || nodes.value) {
      const def = nodeTypes.value[node.type]
      const editorPorts = (def?.outputs || []).filter((port) => port.type === 'editor_project')
      const outputs = execution.nodes?.[node.id]?.outputs_summary || {}
      for (const port of editorPorts) {
        // String values are intentionally reduced to {chars:n} in persisted
        // summaries. The exact, validated project ID lives at record level.
        if (outputs[port.id] !== undefined && execution.project_id) return execution.project_id
      }
    }
    return null
  })

  // ── Draft autosave (step 2.4) ─────────────────────────────────────────
  let draftTimer = null

  function cancelDraftAutosave() {
    if (draftTimer !== null) {
      clearTimeout(draftTimer)
      draftTimer = null
    }
  }

  function scheduleDraftAutosave() {
    cancelDraftAutosave()
    draftTimer = setTimeout(() => {
      draftTimer = null
      flushDraft()
    }, DRAFT_DEBOUNCE_MS)
  }

  /** Every mutation that makes the document diverge from disk funnels here. */
  function markDocumentDirty() {
    dirty.value = true
    scheduleDraftAutosave()
  }

  /** Write the draft immediately (no-op when there is nothing unsaved). */
  function flushDraft() {
    cancelDraftAutosave()
    if (!dirty.value) return false
    try {
      const payload = {
        version: 1,
        saved_at: new Date().toISOString(),
        document: toDocument(),
      }
      globalThis.localStorage?.setItem(DRAFT_STORAGE_KEY, JSON.stringify(payload))
      draftSavedAt.value = payload.saved_at
      return true
    } catch {
      // Quota exceeded / storage disabled: autosave is best-effort, the
      // explicit Save path and dirty indicator still protect the user.
      return false
    }
  }

  /** Read the stored draft without applying it. Corrupt drafts are dropped. */
  function peekDraft() {
    let raw = null
    try {
      raw = globalThis.localStorage?.getItem(DRAFT_STORAGE_KEY)
    } catch {
      return null
    }
    if (!raw) return null
    try {
      const draft = JSON.parse(raw)
      if (!draft || typeof draft !== 'object') throw new Error('not an object')
      if (!draft.document || typeof draft.document !== 'object') throw new Error('no document')
      return draft
    } catch {
      clearDraft()
      return null
    }
  }

  function clearDraft() {
    cancelDraftAutosave()
    draftSavedAt.value = null
    try {
      globalThis.localStorage?.removeItem(DRAFT_STORAGE_KEY)
    } catch {
      /* storage unavailable — nothing to clear */
    }
  }

  /** Apply the stored draft as the (still unsaved) working document. */
  function recoverDraft() {
    const draft = peekDraft()
    if (!draft) return false
    applyDocument(draft.document, { markDirty: true })
    draftSavedAt.value = draft.saved_at || null
    return true
  }

  const workflowList = ref([])
  const templates = ref([])
  const persistenceLoading = ref(false)
  const persistenceError = ref('')

  let idCounter = 0
  function nextNodeId() {
    idCounter += 1
    let candidate = `n_${idCounter}`
    while (nodes.value.some((n) => n.id === candidate)) {
      idCounter += 1
      candidate = `n_${idCounter}`
    }
    return candidate
  }

  function defaultsFor(typeKey) {
    const def = nodeTypes.value[typeKey]
    const configuration = {}
    for (const field of def?.config_schema || []) {
      const value = field.default ?? null
      // Registry defaults are plain JSON; structuredClone would choke on
      // the reactive proxies wrapping them.
      configuration[field.name] = value === null ? null : JSON.parse(JSON.stringify(value))
    }
    return configuration
  }

  function addNode(typeKey, position) {
    const def = nodeTypes.value[typeKey]
    if (!def) return null
    const node = {
      id: nextNodeId(),
      type: typeKey,
      type_version: def.type_version,
      name: def.display_name,
      position: {
        x: Math.round((position?.x ?? 0) / 20) * 20,
        y: Math.round((position?.y ?? 0) / 20) * 20,
      },
      configuration: defaultsFor(typeKey),
      disabled: false,
    }
    nodes.value.push(node)
    markDocumentDirty()
    return node
  }

  function moveNode(nodeId, position) {
    const node = nodes.value.find((n) => n.id === nodeId)
    if (!node) return
    node.position = { x: position.x, y: position.y }
    markDocumentDirty()
  }

  function renameNode(nodeId, name) {
    const node = nodes.value.find((n) => n.id === nodeId)
    if (!node) return
    node.name = name
    markDocumentDirty()
  }

  function removeNodes(nodeIds) {
    const doomed = new Set(nodeIds)
    if (!doomed.size) return
    nodes.value = nodes.value.filter((n) => !doomed.has(n.id))
    edges.value = edges.value.filter(
      (e) => !doomed.has(e.source_node) && !doomed.has(e.target_node),
    )
    if (doomed.has(selectedNodeId.value)) selectedNodeId.value = null
    markDocumentDirty()
  }

  let edgeCounter = 0
  function nextEdgeId() {
    edgeCounter += 1
    let candidate = `e_${edgeCounter}`
    while (edges.value.some((e) => e.id === candidate)) {
      edgeCounter += 1
      candidate = `e_${edgeCounter}`
    }
    return candidate
  }

  /**
   * Validate + create a connection. Returns the validation result;
   * on success the edge is appended in the persisted shape.
   *
   * Step 2.5: when a REAL edge lands on an input currently fed by a Sample
   * Input stub, the stub edge (and the stub itself, unless it still feeds
   * other inputs) is removed first — undoably via undoStubDetach().
   */
  function connectNodes({ sourceNode, sourcePort, targetNode, targetPort }) {
    const sourceIsStub = nodeById(sourceNode)?.type === 'stub.input'
    const stubEdge = sourceIsStub
      ? null
      : edges.value.find(
        (e) => e.target_node === targetNode && e.target_port === targetPort
          && nodeById(e.source_node)?.type === 'stub.input',
      )
    // Validate against the graph as it would look after the stub detaches,
    // so replacing sample data with a real edge is never "input occupied".
    const candidateEdges = stubEdge
      ? edges.value.filter((e) => e.id !== stubEdge.id)
      : edges.value
    const verdict = validateConnection(
      { nodes: nodes.value, edges: candidateEdges, nodeTypes: nodeTypes.value, portTypes: portTypes.value },
      { sourceNode, sourcePort, targetNode, targetPort },
    )
    if (!verdict.ok) return verdict

    let undoEntry = null
    if (stubEdge) {
      const stubNode = nodeById(stubEdge.source_node)
      const stillFeedsOthers = edges.value.some(
        (e) => e.source_node === stubNode.id && e.id !== stubEdge.id,
      )
      undoEntry = {
        stubNode: stillFeedsOthers ? null : plain(stubNode),
        stubEdge: plain(stubEdge),
      }
      edges.value = edges.value.filter((e) => e.id !== stubEdge.id)
      if (!stillFeedsOthers) {
        nodes.value = nodes.value.filter((n) => n.id !== stubNode.id)
        if (selectedNodeId.value === stubNode.id) selectedNodeId.value = null
      }
    }

    const edge = {
      id: nextEdgeId(),
      source_node: sourceNode,
      source_port: sourcePort,
      target_node: targetNode,
      target_port: targetPort,
      edge_type: verdict.edgeType,
    }
    edges.value.push(edge)
    if (undoEntry) {
      undoEntry.realEdgeId = edge.id
      stubDetachUndo.value.push(undoEntry)
    }
    markDocumentDirty()
    return { ...verdict, detachedStub: Boolean(undoEntry) }
  }

  function removeEdges(edgeIds) {
    const doomed = new Set(edgeIds)
    if (!doomed.size) return
    edges.value = edges.value.filter((e) => !doomed.has(e.id))
    markDocumentDirty()
  }

  // ── Sample-data stubs (step 2.5) ──────────────────────────────────────
  // {stubNode|null, stubEdge, realEdgeId} entries, newest last. Replaced by
  // the full command stack in Phase 5.1.
  const stubDetachUndo = ref([])
  const canUndoStubDetach = computed(() => stubDetachUndo.value.length > 0)

  const autoAttachStubs = computed(() => settings.value.auto_attach_stubs !== false)

  function setAutoAttachStubs(enabled) {
    settings.value = { ...settings.value, auto_attach_stubs: Boolean(enabled) }
    markDocumentDirty()
  }

  function isStubType(typeKey) {
    return nodeTypes.value[typeKey]?.category === 'testing'
  }

  function samplePayloadFor(portType) {
    const sample = samplePayloads.value[portType]
    return sample === undefined ? {} : plain(sample)
  }

  /** Resolve one endpoint's port type, honouring dynamic stub ports. */
  function endpointPortType(node, kind, portId) {
    const port = (nodeTypes.value[node?.type]?.[kind] || []).find((p) => p.id === portId)
    if (!port) return null
    if (port.type !== 'dynamic') return port.type
    return node.configuration?.port_type || 'generic_json'
  }

  /**
   * Spawn one pre-connected Sample Input per still-unconnected required
   * data input of `nodeId`. Returns the created stub nodes.
   */
  function attachSampleInputs(nodeId) {
    const node = nodeById(nodeId)
    const def = nodeTypes.value[node?.type]
    if (!node || !def || !nodeTypes.value['stub.input']) return []
    const created = []
    let slot = 0
    for (const port of def.inputs || []) {
      if (!port.required || port.type === 'control') continue
      const connected = edges.value.some(
        (e) => e.target_node === nodeId && e.target_port === port.id,
      )
      if (connected) continue
      const stub = addNode('stub.input', {
        x: node.position.x - 260,
        y: node.position.y + slot * 80,
      })
      stub.name = `Sample ${port.id}`
      stub.configuration.port_type = port.type
      stub.configuration.payload = samplePayloadFor(port.type)
      edges.value.push({
        id: nextEdgeId(),
        source_node: stub.id,
        source_port: 'value',
        target_node: nodeId,
        target_port: port.id,
        edge_type: 'data',
      })
      created.push(stub)
      slot += 1
    }
    if (created.length) markDocumentDirty()
    return created
  }

  /** Attach a Result Viewer to the node's principal (first data) output. */
  function attachResultViewer(nodeId) {
    const node = nodeById(nodeId)
    const def = nodeTypes.value[node?.type]
    if (!node || !def || !nodeTypes.value['stub.output']) return null
    const port = (def.outputs || []).find((p) => p.type !== 'control')
    if (!port) return null
    const stub = addNode('stub.output', {
      x: node.position.x + 260,
      y: node.position.y,
    })
    stub.name = `View ${port.id}`
    stub.configuration.port_type = port.type
    edges.value.push({
      id: nextEdgeId(),
      source_node: nodeId,
      source_port: port.id,
      target_node: stub.id,
      target_port: 'value',
      edge_type: 'data',
    })
    markDocumentDirty()
    return stub
  }

  /**
   * Palette-drop entry point: add the node and — when the workflow-level
   * auto-attach setting is on and the node is not itself a testing stub —
   * wire up sample inputs and a result viewer.
   */
  function addNodeWithStubs(typeKey, position) {
    const node = addNode(typeKey, position)
    if (!node) return null
    if (autoAttachStubs.value && !isStubType(typeKey)) {
      attachSampleInputs(node.id)
      attachResultViewer(node.id)
    }
    return node
  }

  /** Undo the most recent stub detach: drop the real edge, restore the stub. */
  function undoStubDetach() {
    const entry = stubDetachUndo.value.pop()
    if (!entry) return false
    edges.value = edges.value.filter((e) => e.id !== entry.realEdgeId)
    if (entry.stubNode && !nodeById(entry.stubNode.id)) {
      const restored = plain(entry.stubNode)
      if (nodes.value.some((n) => n.id === restored.id)) restored.id = nextNodeId()
      nodes.value.push(restored)
      entry.stubEdge.source_node = restored.id
    }
    const stubEdge = plain(entry.stubEdge)
    const occupied = edges.value.some(
      (e) => e.target_node === stubEdge.target_node && e.target_port === stubEdge.target_port,
    )
    if (!occupied && nodeById(stubEdge.source_node) && nodeById(stubEdge.target_node)) {
      if (edges.value.some((e) => e.id === stubEdge.id)) stubEdge.id = nextEdgeId()
      edges.value.push(stubEdge)
    }
    markDocumentDirty()
    return true
  }

  function setViewport(vp) {
    // Viewport is cosmetic state: remember it for the next save, but merely
    // panning/zooming must not flag unsaved changes or arm discard prompts.
    viewport.value = { x: vp.x, y: vp.y, zoom: vp.zoom }
  }

  function plain(value) {
    return JSON.parse(JSON.stringify(value))
  }

  function toDocument() {
    const document = {
      schema_version: 1,
      name: workflowName.value.trim() || 'Untitled workflow',
      description: workflowDescription.value,
      nodes: plain(nodes.value),
      edges: plain(edges.value),
      variables: plain(variables.value),
      viewport: plain(viewport.value),
      settings: plain(settings.value),
      extensions: plain(extensions.value),
    }
    if (workflowId.value) document.workflow_id = workflowId.value
    if (createdAt.value) document.created_at = createdAt.value
    if (updatedAt.value) document.updated_at = updatedAt.value
    return document
  }

  function resetCounters() {
    idCounter = 0
    edgeCounter = 0
  }

  function applyDocument(document, {
    markDirty = false,
    preserveSelection = false,
    preserveExecution = false,
  } = {}) {
    if (!preserveExecution) clearExecution()
    workflowId.value = document.workflow_id || null
    workflowName.value = document.name || 'Untitled workflow'
    workflowDescription.value = document.description || ''
    nodes.value = plain(document.nodes || [])
    edges.value = plain(document.edges || [])
    variables.value = plain(document.variables || {})
    viewport.value = plain(document.viewport || { x: 0, y: 0, zoom: 1 })
    settings.value = plain(document.settings || { on_error: 'stop' })
    extensions.value = plain(document.extensions || {})
    createdAt.value = document.created_at || null
    updatedAt.value = document.updated_at || null
    resetCounters()
    stubDetachUndo.value = []
    if (!preserveSelection || !nodeById(selectedNodeId.value)) selectedNodeId.value = null
    if (markDirty) {
      // Unsaved content (template/import-as-draft, draft recovery): keep the
      // autosave loop armed so the new document is protected too.
      markDocumentDirty()
    } else {
      // A clean document from disk supersedes any stored draft.
      dirty.value = false
      clearDraft()
    }
  }

  function newWorkflow(name = 'Untitled workflow') {
    applyDocument({
      schema_version: 1,
      name,
      description: '',
      nodes: [],
      edges: [],
      variables: {},
      viewport: { x: 0, y: 0, zoom: 1 },
      settings: { on_error: 'stop' },
      extensions: {},
    })
  }

  async function refreshWorkflowList() {
    const data = await api.get('/api/workflows', { params: { limit: 200 } })
    workflowList.value = data.workflows || []
    return workflowList.value
  }

  async function loadTemplates() {
    const data = await api.get('/api/workflow/templates')
    templates.value = data.templates || []
    return templates.value
  }

  async function openWorkflow(id) {
    persistenceLoading.value = true
    persistenceError.value = ''
    try {
      const data = await api.get(`/api/workflows/${encodeURIComponent(id)}`)
      applyDocument(data.workflow)
      return data.workflow
    } catch (err) {
      persistenceError.value = err?.message || 'Failed to open workflow'
      throw err
    } finally {
      persistenceLoading.value = false
    }
  }

  async function saveWorkflow() {
    persistenceLoading.value = true
    persistenceError.value = ''
    try {
      const document = toDocument()
      const data = workflowId.value
        ? await api.put(`/api/workflows/${encodeURIComponent(workflowId.value)}`, {
          body: { workflow: document, expected_updated_at: updatedAt.value },
        })
        : await api.post('/api/workflows', { body: { workflow: document } })
      applyDocument(data.workflow, { preserveSelection: true, preserveExecution: true })
      await refreshWorkflowList()
      return data.workflow
    } catch (err) {
      persistenceError.value = err?.message || 'Failed to save workflow'
      throw err
    } finally {
      persistenceLoading.value = false
    }
  }

  async function saveAs(name) {
    persistenceLoading.value = true
    persistenceError.value = ''
    try {
      const document = toDocument()
      delete document.workflow_id
      delete document.created_at
      delete document.updated_at
      document.name = name?.trim() || `${workflowName.value} copy`
      const data = await api.post('/api/workflows', { body: { workflow: document } })
      applyDocument(data.workflow, { preserveSelection: true })
      await refreshWorkflowList()
      return data.workflow
    } catch (err) {
      persistenceError.value = err?.message || 'Failed to save workflow copy'
      throw err
    } finally {
      persistenceLoading.value = false
    }
  }

  async function importDocument(document) {
    persistenceLoading.value = true
    persistenceError.value = ''
    try {
      const data = await api.post('/api/workflows/import', {
        body: { workflow: document, on_conflict: 'new_id' },
      })
      applyDocument(data.workflow)
      await refreshWorkflowList()
      return data.workflow
    } catch (err) {
      persistenceError.value = err?.message || 'Failed to import workflow'
      throw err
    } finally {
      persistenceLoading.value = false
    }
  }

  function applyTemplate(templateId) {
    const template = templates.value.find((item) => item.template_id === templateId)
    if (!template) return false
    applyDocument(template.workflow, { markDirty: true })
    return true
  }

  function nodeById(nodeId) {
    return nodes.value.find((n) => n.id === nodeId) || null
  }

  const nodeCount = computed(() => nodes.value.length)

  // Per-node editing issues (step 2.2) — recomputed on every graph change.
  const issuesByNode = computed(() => {
    const map = {}
    for (const node of nodes.value) {
      const issues = nodeIssues(node, nodeTypes.value[node.type], edges.value)
      if (issues.length) map[node.id] = issues
    }
    return map
  })

  // ── Selection + inspector editing (step 2.1) ──────────────────────────
  const selectedNodeId = ref(null)
  const selectedNode = computed(() => nodeById(selectedNodeId.value))

  function selectNode(nodeId) {
    selectedNodeId.value = nodeById(nodeId) ? nodeId : null
  }

  function clearSelection() {
    selectedNodeId.value = null
  }

  function updateNodeConfig(nodeId, name, value) {
    const node = nodeById(nodeId)
    if (!node) return
    const previous = node.configuration[name]
    node.configuration[name] = value
    // Retyping a stub retargets its dynamic port: reseed the editable sample
    // payload and drop edges that no longer type-match (contracts §3 —
    // dynamic ports obey exact-match once resolved).
    if (
      name === 'port_type' && value !== previous
      && (node.type === 'stub.input' || node.type === 'stub.output')
    ) {
      if (node.type === 'stub.input') {
        node.configuration.payload = samplePayloadFor(value)
      }
      edges.value = edges.value.filter((e) => {
        if (e.source_node === nodeId && e.source_port === 'value') {
          const target = nodeById(e.target_node)
          return endpointPortType(target, 'inputs', e.target_port) === value
        }
        if (e.target_node === nodeId && e.target_port === 'value') {
          const source = nodeById(e.source_node)
          return endpointPortType(source, 'outputs', e.source_port) === value
        }
        return true
      })
    }
    markDocumentDirty()
  }

  function setNodeDisabled(nodeId, disabled) {
    const node = nodeById(nodeId)
    if (!node) return
    node.disabled = Boolean(disabled)
    markDocumentDirty()
  }

  function duplicateNode(nodeId) {
    const source = nodeById(nodeId)
    if (!source) return null
    const suffix = ' copy'
    const copyName = `${source.name.slice(0, 120 - suffix.length).trimEnd()}${suffix}`
    const copy = {
      id: nextNodeId(),
      type: source.type,
      type_version: source.type_version,
      name: copyName,
      position: {
        x: Math.min(1_000_000, source.position.x + 40),
        y: Math.min(1_000_000, source.position.y + 40),
      },
      configuration: plain(source.configuration),
      disabled: source.disabled,
      ...(source.extensions ? { extensions: plain(source.extensions) } : {}),
    }
    nodes.value.push(copy)
    markDocumentDirty()
    selectedNodeId.value = copy.id
    return copy
  }

  return {
    // registry
    registryVersion, nodeTypes, categories, portTypes, samplePayloads,
    registryLoading, registryError, loadNodeTypes,
    // document
    workflowId, workflowName, workflowDescription, nodes, edges, viewport,
    variables, settings, extensions, createdAt, updatedAt, dirty, nodeCount,
    workflowList, templates, persistenceLoading, persistenceError,
    addNode, moveNode, renameNode, removeNodes, removeEdges, connectNodes,
    setViewport, nodeById, defaultsFor, toDocument, applyDocument, newWorkflow,
    refreshWorkflowList, loadTemplates, openWorkflow, saveWorkflow, saveAs,
    importDocument, applyTemplate,
    // draft autosave (step 2.4)
    draftSavedAt, markDocumentDirty, flushDraft, peekDraft, clearDraft, recoverDraft,
    // selection + inspector
    selectedNodeId, selectedNode, selectNode, clearSelection,
    updateNodeConfig, setNodeDisabled, duplicateNode,
    // validation (step 2.2)
    issuesByNode,
    // sample-data stubs (step 2.5)
    autoAttachStubs, setAutoAttachStubs, isStubType, samplePayloadFor,
    addNodeWithStubs, attachSampleInputs, attachResultViewer,
    canUndoStubDetach, undoStubDetach,
    // live execution (step 3.6)
    currentExecution, executionLoading, executionError, executionActive,
    selectedExecutionNodeId, selectedExecutionNode, editorProjectId,
    nodeExecution, runWorkflow, stopExecution, refreshExecution,
    applyExecutionEvent, watchExecution, closeExecutionStream, clearExecution,
    selectExecutionNode,
  }
})
