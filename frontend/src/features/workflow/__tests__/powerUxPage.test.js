import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'

vi.mock('vue-router', () => ({ onBeforeRouteLeave: vi.fn() }))
vi.mock('@/shared/api/client.js', () => ({
  api: {
    get: vi.fn(async (path) => path === '/api/workflows'
      ? { workflows: [] }
      : path === '/api/workflow/templates'
        ? { templates: [] }
        : {}),
    post: vi.fn(async () => ({})),
  },
}))

vi.mock('@vue-flow/core', () => ({
  MarkerType: { ArrowClosed: 'arrow' },
  useVueFlow: () => ({
    screenToFlowCoordinate: (point) => point,
    fitView: vi.fn(),
    setViewport: vi.fn(async () => {}),
  }),
  VueFlow: defineComponent({
    name: 'VueFlow',
    emits: ['nodeContextMenu', 'edgeContextMenu', 'paneContextMenu'],
    setup(_props, { emit, slots }) {
      return () => h('div', { class: 'vue-flow__pane' }, [
        h('button', {
          class: 'emit-node-menu',
          onContextmenu: (event) => emit('nodeContextMenu', { event, node: { id: 'n_1' } }),
        }),
        h('button', {
          class: 'emit-edge-menu',
          onContextmenu: (event) => emit('edgeContextMenu', { event, edge: { id: 'e_1' } }),
        }),
        h('button', {
          class: 'emit-pane-menu',
          onContextmenu: (event) => emit('paneContextMenu', event),
        }),
        slots.default?.(),
      ])
    },
  }),
}))
vi.mock('@vue-flow/background', () => ({ Background: defineComponent(() => () => h('div')) }))
vi.mock('@vue-flow/controls', () => ({ Controls: defineComponent(() => () => h('div')) }))
vi.mock('@vue-flow/minimap', () => ({ MiniMap: defineComponent(() => () => h('div')) }))

import WorkflowPage from '../views/WorkflowPage.vue'
import { useWorkflowStore } from '../stores/workflow.js'

const TYPES = {
  source: {
    type: 'source', type_version: 1, display_name: 'Source', category: 'input',
    inputs: [], outputs: [{ id: 'value', type: 'text' }], config_schema: [],
  },
  target: {
    type: 'target', type_version: 1, display_name: 'Target', category: 'output',
    inputs: [{ id: 'value', type: 'text', required: true, multiple: false }],
    outputs: [], config_schema: [],
  },
}

describe('step 5.2 context menus', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('renders node, edge, and pane actions and dispatches duplicate undoably', async () => {
    const store = useWorkflowStore()
    store.registryVersion = 1
    store.nodeTypes = TYPES
    store.portTypes = ['text']
    store.settings = { on_error: 'stop', auto_attach_stubs: false }
    const source = store.addNode('source', { x: 0, y: 0 })
    const target = store.addNode('target', { x: 200, y: 0 })
    store.connectNodes({ sourceNode: source.id, sourcePort: 'value', targetNode: target.id, targetPort: 'value' })
    store.clearCommandHistory()

    const wrapper = mount(WorkflowPage, {
      global: {
        stubs: {
          NodeLibrary: true,
          NodeInspector: true,
          NodeCard: true,
          ExecutionPanel: true,
        },
      },
    })
    expect(wrapper.find('.wf-toolbar-actions').text()).not.toContain('Add note')
    await wrapper.find('.emit-node-menu').trigger('contextmenu')
    expect(wrapper.text()).toContain('Copy')
    expect(wrapper.text()).toContain('Replace with…')
    expect(wrapper.text()).toContain('Delete')
    const duplicate = wrapper.findAll('.wf-context-item').find((button) => button.text() === 'Duplicate')
    await duplicate.trigger('click')
    expect(store.nodes).toHaveLength(3)
    expect(store.undoLabel).toBe('Duplicate node')

    await wrapper.find('.emit-edge-menu').trigger('contextmenu')
    expect(wrapper.text()).toContain('Disconnect')
    await wrapper.find('.wf-context-backdrop').trigger('click')
    await nextTick()

    await wrapper.find('.emit-pane-menu').trigger('contextmenu')
    expect(wrapper.text()).toContain('Paste here')
    expect(wrapper.text()).toContain('Add note')
    expect(wrapper.text()).toContain('Auto arrange')
    wrapper.unmount()
  })
})
