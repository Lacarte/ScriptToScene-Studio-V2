import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { api } from '@/shared/api/client.js'

/**
 * Workflow builder store — the domain model behind the canvas.
 * Nodes/edges are stored in the persisted document shape (contracts.md §4);
 * WorkflowPage maps them to Vue Flow elements. Vue Flow runtime props never
 * enter this store.
 */
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
  const nodes = ref([])   // {id, type, type_version, name, position, configuration, disabled}
  const edges = ref([])   // {id, source_node, source_port, target_node, target_port, edge_type}
  const viewport = ref({ x: 0, y: 0, zoom: 1 })
  const dirty = ref(false)

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
    dirty.value = true
    return node
  }

  function moveNode(nodeId, position) {
    const node = nodes.value.find((n) => n.id === nodeId)
    if (!node) return
    node.position = { x: position.x, y: position.y }
    dirty.value = true
  }

  function renameNode(nodeId, name) {
    const node = nodes.value.find((n) => n.id === nodeId)
    if (!node) return
    node.name = name
    dirty.value = true
  }

  function removeNodes(nodeIds) {
    const doomed = new Set(nodeIds)
    if (!doomed.size) return
    nodes.value = nodes.value.filter((n) => !doomed.has(n.id))
    edges.value = edges.value.filter(
      (e) => !doomed.has(e.source_node) && !doomed.has(e.target_node),
    )
    dirty.value = true
  }

  function removeEdges(edgeIds) {
    const doomed = new Set(edgeIds)
    if (!doomed.size) return
    edges.value = edges.value.filter((e) => !doomed.has(e.id))
    dirty.value = true
  }

  function setViewport(vp) {
    viewport.value = { x: vp.x, y: vp.y, zoom: vp.zoom }
  }

  function nodeById(nodeId) {
    return nodes.value.find((n) => n.id === nodeId) || null
  }

  const nodeCount = computed(() => nodes.value.length)

  return {
    // registry
    registryVersion, nodeTypes, categories, portTypes,
    registryLoading, registryError, loadNodeTypes,
    // document
    workflowId, workflowName, nodes, edges, viewport, dirty, nodeCount,
    addNode, moveNode, renameNode, removeNodes, removeEdges,
    setViewport, nodeById, defaultsFor,
  }
})
