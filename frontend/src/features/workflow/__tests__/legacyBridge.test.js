import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

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
    setup(_props, { slots }) {
      return () => h('div', { class: 'vue-flow__pane' }, slots.default?.())
    },
  }),
}))
vi.mock('@vue-flow/background', () => ({ Background: defineComponent(() => () => h('div')) }))
vi.mock('@vue-flow/controls', () => ({ Controls: defineComponent(() => () => h('div')) }))
vi.mock('@vue-flow/minimap', () => ({ MiniMap: defineComponent(() => () => h('div')) }))

import WorkflowPage from '../views/WorkflowPage.vue'
import { useWorkflowStore } from '../stores/workflow.js'

describe('step 6.5 legacy UI bridge — workflow surface', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('links to the legacy pipeline dashboard from the toolbar', () => {
    const store = useWorkflowStore()
    store.settings = { on_error: 'stop', auto_attach_stubs: false }

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
    const link = wrapper.find('.wf-toolbar-actions a.wf-legacy-link')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('#/pipeline')
    wrapper.unmount()
  })
})
