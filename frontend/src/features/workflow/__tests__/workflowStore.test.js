import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useWorkflowStore } from '../stores/workflow.js'
import { api } from '@/shared/api/client.js'

const FAKE_TYPES = {
  'script.input': {
    type: 'script.input',
    type_version: 1,
    display_name: 'Script Input',
    category: 'input',
    config_schema: [
      { name: 'text', type: 'textarea', default: '' },
    ],
  },
  'tts.generate': {
    type: 'tts.generate',
    type_version: 1,
    display_name: 'Text to Speech',
    category: 'audio',
    config_schema: [
      { name: 'engine', type: 'options', default: 'kokoro' },
      { name: 'provider_options', type: 'json', default: {} },
    ],
  },
}

function seededStore() {
  const store = useWorkflowStore()
  store.registryVersion = 1
  store.nodeTypes = FAKE_TYPES
  return store
}

describe('workflow store', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.restoreAllMocks())

  it('adds a node with registry defaults and snapped position', () => {
    const store = seededStore()
    const node = store.addNode('tts.generate', { x: 33, y: 47 })
    expect(node.id).toMatch(/^n_\d+$/)
    expect(node.type_version).toBe(1)
    expect(node.name).toBe('Text to Speech')
    expect(node.position).toEqual({ x: 40, y: 40 })
    expect(node.configuration).toEqual({ engine: 'kokoro', provider_options: {} })
    expect(node.disabled).toBe(false)
    expect(store.dirty).toBe(true)
  })

  it('deep-copies config defaults per node', () => {
    const store = seededStore()
    const a = store.addNode('tts.generate', { x: 0, y: 0 })
    const b = store.addNode('tts.generate', { x: 0, y: 0 })
    a.configuration.provider_options.key = 'x'
    expect(b.configuration.provider_options).toEqual({})
  })

  it('rejects unknown node types', () => {
    const store = seededStore()
    expect(store.addNode('nope.missing', { x: 0, y: 0 })).toBeNull()
    expect(store.nodes).toHaveLength(0)
  })

  it('generates unique ids even after deletions', () => {
    const store = seededStore()
    const a = store.addNode('script.input', { x: 0, y: 0 })
    const b = store.addNode('script.input', { x: 0, y: 0 })
    store.removeNodes([a.id])
    const c = store.addNode('script.input', { x: 0, y: 0 })
    expect(c.id).not.toBe(b.id)
    const ids = store.nodes.map((n) => n.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('moves and renames nodes', () => {
    const store = seededStore()
    const node = store.addNode('script.input', { x: 0, y: 0 })
    store.moveNode(node.id, { x: 120, y: 80 })
    store.renameNode(node.id, 'My script')
    expect(store.nodeById(node.id).position).toEqual({ x: 120, y: 80 })
    expect(store.nodeById(node.id).name).toBe('My script')
  })

  it('removing a node removes its edges', () => {
    const store = seededStore()
    const a = store.addNode('script.input', { x: 0, y: 0 })
    const b = store.addNode('tts.generate', { x: 200, y: 0 })
    store.edges.push({
      id: 'e_1',
      source_node: a.id, source_port: 'script',
      target_node: b.id, target_port: 'script',
      edge_type: 'data',
    })
    store.removeNodes([a.id])
    expect(store.edges).toHaveLength(0)
    expect(store.nodes.map((n) => n.id)).toEqual([b.id])
  })

  it('removeEdges removes only the named edges', () => {
    const store = seededStore()
    store.edges.push(
      { id: 'e_1', source_node: 'a', source_port: 'x', target_node: 'b', target_port: 'y', edge_type: 'data' },
      { id: 'e_2', source_node: 'a', source_port: 'x', target_node: 'c', target_port: 'y', edge_type: 'data' },
    )
    store.removeEdges(['e_1'])
    expect(store.edges.map((e) => e.id)).toEqual(['e_2'])
  })

  it('round-trips only the persisted document shape', () => {
    const store = seededStore()
    const node = store.addNode('script.input', { x: 10, y: 20 })
    const document = store.toDocument()
    expect(document).toMatchObject({
      schema_version: 1,
      name: 'Untitled workflow',
      variables: {},
      settings: { on_error: 'stop' },
    })
    expect(document.nodes[0].id).toBe(node.id)
    expect(document.nodes[0]).not.toHaveProperty('data')
    expect(document.nodes[0]).not.toHaveProperty('selected')

    store.applyDocument({
      ...document,
      workflow_id: 'wf_ABC123',
      name: 'Reloaded',
      created_at: '2026-08-04T00:00:00Z',
      updated_at: '2026-08-04T00:00:00Z',
    })
    expect(store.workflowId).toBe('wf_ABC123')
    expect(store.workflowName).toBe('Reloaded')
    expect(store.dirty).toBe(false)
  })

  it('creates then updates using optimistic timestamps', async () => {
    const store = seededStore()
    store.addNode('script.input', { x: 0, y: 0 })
    const created = {
      ...store.toDocument(),
      workflow_id: 'wf_ABC123',
      created_at: 'created',
      updated_at: 'v1',
    }
    vi.spyOn(api, 'post').mockResolvedValue({ workflow: created })
    vi.spyOn(api, 'get').mockResolvedValue({ workflows: [], total: 0 })
    await store.saveWorkflow()
    expect(api.post).toHaveBeenCalledWith('/api/workflows', expect.objectContaining({ body: expect.any(Object) }))
    expect(store.workflowId).toBe('wf_ABC123')

    store.renameNode(store.nodes[0].id, 'Renamed')
    const updated = { ...store.toDocument(), updated_at: 'v2' }
    vi.spyOn(api, 'put').mockResolvedValue({ workflow: updated })
    await store.saveWorkflow()
    expect(api.put).toHaveBeenCalledWith('/api/workflows/wf_ABC123', {
      body: expect.objectContaining({ expected_updated_at: 'v1' }),
    })
    expect(store.updatedAt).toBe('v2')
    expect(store.dirty).toBe(false)
  })

  it('loads the built-in template as a dirty unsaved workflow', () => {
    const store = seededStore()
    store.templates = [{
      template_id: 'full_video',
      workflow: {
        schema_version: 1,
        name: 'Full Video',
        nodes: [], edges: [], variables: {},
        viewport: { x: 0, y: 0, zoom: 1 },
        settings: { on_error: 'stop' }, extensions: {},
      },
    }]
    expect(store.applyTemplate('full_video')).toBe(true)
    expect(store.workflowId).toBeNull()
    expect(store.workflowName).toBe('Full Video')
    expect(store.dirty).toBe(true)
  })
})
