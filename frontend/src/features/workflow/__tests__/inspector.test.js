import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import ConfigField from '../components/ConfigField.vue'
import NodeInspector from '../components/NodeInspector.vue'
import { useWorkflowStore } from '../stores/workflow.js'

function mountField(field, value) {
  return mount(ConfigField, { props: { field, value } })
}

describe('ConfigField widgets', () => {
  it('renders string input and emits updates', async () => {
    const wrapper = mountField({ name: 'channel_name', label: 'Channel', type: 'string', default: '' }, 'Acme')
    const input = wrapper.get('input[type="text"]')
    expect(input.element.value).toBe('Acme')
    await input.setValue('New name')
    expect(wrapper.emitted('update').at(-1)).toEqual(['New name'])
  })

  it('renders textarea', async () => {
    const wrapper = mountField({ name: 'text', label: 'Script', type: 'textarea', default: '' }, 'hello')
    const area = wrapper.get('textarea')
    await area.setValue('changed')
    expect(wrapper.emitted('update').at(-1)).toEqual(['changed'])
  })

  it('renders number with clamping to min/max', async () => {
    const wrapper = mountField(
      { name: 'speed', label: 'Speed', type: 'number', default: 1, min: 0.5, max: 2, step: 0.1 },
      1.0,
    )
    const input = wrapper.get('input[type="number"]')
    input.element.value = '5'
    await input.trigger('change')
    expect(wrapper.emitted('update').at(-1)).toEqual([2])
    expect(wrapper.find('input[type="range"]').exists()).toBe(true)
  })

  it('renders boolean checkbox', async () => {
    const wrapper = mountField({ name: 'enabled', label: 'On', type: 'boolean', default: false }, false)
    const box = wrapper.get('input[type="checkbox"]')
    await box.setValue(true)
    expect(wrapper.emitted('update').at(-1)).toEqual([true])
  })

  it('renders static options select', async () => {
    const wrapper = mountField(
      { name: 'mode', label: 'Mode', type: 'options', options: ['video', 'image'], default: 'video' },
      'video',
    )
    const select = wrapper.get('select')
    await select.setValue('image')
    expect(wrapper.emitted('update').at(-1)).toEqual(['image'])
  })

  it('disables async options until step 2.3 without losing the value', () => {
    const wrapper = mountField(
      { name: 'voice', label: 'Voice', type: 'options', options_source: 'tts_voices', default: 'af_heart' },
      'af_heart',
    )
    const select = wrapper.get('select')
    expect(select.element.disabled).toBe(true)
    expect(select.element.value).toBe('af_heart')
  })

  it('json widget validates before emitting', async () => {
    const wrapper = mountField({ name: 'opts', label: 'Opts', type: 'json', default: {} }, { a: 1 })
    const area = wrapper.get('textarea')
    await area.setValue('{ bad json')
    await area.trigger('blur')
    expect(wrapper.text()).toContain('Invalid JSON')
    expect(wrapper.emitted('update')).toBeUndefined()
    await area.setValue('{"b": 2}')
    await area.trigger('blur')
    expect(wrapper.emitted('update').at(-1)).toEqual([{ b: 2 }])
  })
})

const TYPES = {
  'tts.generate': {
    type_version: 1,
    display_name: 'Text to Speech',
    description: 'Generate narration audio.',
    category: 'audio',
    icon: 'mic',
    inputs: [],
    outputs: [],
    config_schema: [
      { name: 'engine', label: 'Engine', type: 'options', options: ['kokoro', 'inworld'], default: 'kokoro' },
      { name: 'speed', label: 'Speed', type: 'number', default: 1, min: 0.5, max: 2, step: 0.1 },
      { name: 'provider_options', label: 'Options', type: 'json', default: {} },
    ],
  },
}

describe('NodeInspector', () => {
  beforeEach(() => setActivePinia(createPinia()))

  function seeded() {
    const store = useWorkflowStore()
    store.registryVersion = 1
    store.nodeTypes = TYPES
    store.categories = { audio: { label: 'Audio', color: '#A78BFA' } }
    const node = store.addNode('tts.generate', { x: 0, y: 0 })
    store.selectNode(node.id)
    return { store, node }
  }

  it('shows the empty state without a selection', () => {
    const store = useWorkflowStore()
    store.nodeTypes = TYPES
    const wrapper = mount(NodeInspector)
    expect(wrapper.text()).toContain('Select a node')
  })

  it('renders every schema field generically and writes config updates', async () => {
    const { store, node } = seeded()
    const wrapper = mount(NodeInspector)
    expect(wrapper.findAllComponents(ConfigField)).toHaveLength(3)
    const select = wrapper.get('select')
    await select.setValue('inworld')
    expect(store.nodeById(node.id).configuration.engine).toBe('inworld')
    expect(store.dirty).toBe(true)
  })

  it('rename, disable, duplicate, delete actions work', async () => {
    const { store, node } = seeded()
    const wrapper = mount(NodeInspector)

    const name = wrapper.get('.inspector-name')
    await name.setValue('Narration A')
    await name.trigger('change')
    expect(store.nodeById(node.id).name).toBe('Narration A')

    const buttons = wrapper.findAll('.ins-btn')
    await buttons[0].trigger('click') // disable
    expect(store.nodeById(node.id).disabled).toBe(true)

    await buttons[1].trigger('click') // duplicate
    expect(store.nodes).toHaveLength(2)
    expect(store.selectedNodeId).not.toBe(node.id)

    store.selectNode(node.id)
    const del = mount(NodeInspector).findAll('.ins-btn')[2]
    await del.trigger('click')
    expect(store.nodeById(node.id)).toBeNull()
    expect(store.selectedNodeId).toBeNull()
  })

  it('clears stale selection when a node is removed or a document is replaced', () => {
    const { store, node } = seeded()
    store.removeNodes([node.id])
    expect(store.selectedNodeId).toBeNull()

    const replacement = store.addNode('tts.generate', { x: 0, y: 0 })
    store.selectNode(replacement.id)
    store.applyDocument({
      schema_version: 1,
      name: 'Replacement',
      nodes: [{ ...replacement, name: 'Same ID, different document' }],
      edges: [],
      variables: {},
      viewport: { x: 0, y: 0, zoom: 1 },
      settings: { on_error: 'stop' },
      extensions: {},
    })
    expect(store.selectedNodeId).toBeNull()
  })

  it('preserves selection only when reapplying the same saved graph', () => {
    const { store, node } = seeded()
    const saved = store.toDocument()
    store.applyDocument(saved, { preserveSelection: true })
    expect(store.selectedNodeId).toBe(node.id)

    saved.nodes = []
    store.applyDocument(saved, { preserveSelection: true })
    expect(store.selectedNodeId).toBeNull()
  })

  it('duplicates bounded node data without dropping extensions', () => {
    const { store, node } = seeded()
    node.name = 'N'.repeat(120)
    node.position = { x: 999_990, y: 999_990 }
    node.extensions = { plugin: { value: 1 } }

    const copy = store.duplicateNode(node.id)
    expect(copy.name).toHaveLength(120)
    expect(copy.name.endsWith(' copy')).toBe(true)
    expect(copy.position).toEqual({ x: 1_000_000, y: 1_000_000 })
    expect(copy.extensions).toEqual(node.extensions)
    expect(copy.extensions).not.toBe(node.extensions)
  })
})
