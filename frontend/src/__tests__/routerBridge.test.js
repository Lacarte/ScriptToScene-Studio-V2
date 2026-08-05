import { describe, expect, it } from 'vitest'
import router from '@/app/router.js'

describe('step 6.5 legacy UI bridge — routing', () => {
  it('lands on the workflow builder by default', () => {
    const root = router.options.routes.find((route) => route.path === '/')
    expect(root).toBeTruthy()
    expect(root.redirect).toBe('/workflow')
  })

  it('keeps the legacy pipeline reachable behind explicit navigation', () => {
    const pipeline = router.options.routes.find((route) => route.path === '/pipeline')
    expect(pipeline?.name).toBe('pipeline')
  })

  it('has no dead routes left over from the legacy default', () => {
    const paths = router.options.routes.map((route) => route.path)
    expect(paths).not.toContain('/timing')
    // Every remaining route is either the root redirect or a page linked from a surface.
    const linked = [
      '/workflow', '/pipeline', '/tts', '/alignment', '/segmenter', '/scenes',
      '/storyboard', '/assets', '/editor', '/export-library', '/settings',
    ]
    for (const path of paths.filter((p) => p !== '/')) {
      expect(linked).toContain(path)
    }
  })
})
