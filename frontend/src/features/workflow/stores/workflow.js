import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/shared/api/client.js'
import { validateConnection } from '../validation.js'
import { nodeIssues } from '../schema.js'

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
   */
  function connectNodes({ sourceNode, sourcePort, targetNode, targetPort }) {
    const verdict = validateConnection(
      { nodes: nodes.value, edges: edges.value, nodeTypes: nodeTypes.value, portTypes: portTypes.value },
      { sourceNode, sourcePort, targetNode, targetPort },
    )
    if (!verdict.ok) return verdict
    edges.value.push({
      id: nextEdgeId(),
      source_node: sourceNode,
      source_port: sourcePort,
      target_node: targetNode,
      target_port: targetPort,
      edge_type: verdict.edgeType,
    })
    markDocumentDirty()
    return verdict
  }

  function removeEdges(edgeIds) {
    const doomed = new Set(edgeIds)
    if (!doomed.size) return
    edges.value = edges.value.filter((e) => !doomed.has(e.id))
    markDocumentDirty()
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

  function applyDocument(document, { markDirty = false, preserveSelection = false } = {}) {
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
      applyDocument(data.workflow, { preserveSelection: true })
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
    node.configuration[name] = value
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
    registryVersion, nodeTypes, categories, portTypes,
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
  }
})
