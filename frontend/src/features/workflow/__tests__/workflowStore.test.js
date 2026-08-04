import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useWorkflowStore } from '../stores/workflow.js'

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
})
