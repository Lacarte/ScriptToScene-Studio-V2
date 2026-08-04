import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

const Hello = defineComponent({
  props: { name: { type: String, default: 'world' } },
  template: '<p>hello {{ name }}</p>',
})

describe('test infrastructure', () => {
  it('mounts a component with props', () => {
    const wrapper = mount(Hello, { props: { name: 'studio' } })
    expect(wrapper.text()).toBe('hello studio')
  })
})
