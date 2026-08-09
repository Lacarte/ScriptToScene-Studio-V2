import { ref } from 'vue'
import { api } from '@/shared/api/client.js'

/** Last picked story metadata (reactive) — { text, type, styles } */
export const lastPickedStory = ref(null)

/**
 * Pick a random story via the backend `random_template` script provider.
 * Shared between Pipeline and TTS so they use the same catalog and anti-repeat.
 * @param {{ category?: string, seed?: number }} [opts]
 * @returns {Promise<string>} The story text
 */
export async function pickRandomStory(opts = {}) {
  const body = {}
  if (opts.category) body.category = opts.category
  if (opts.seed !== undefined && opts.seed !== null) body.seed = opts.seed

  const data = await api.post('/api/story/random', { body })
  const text = typeof data?.text === 'string' ? data.text : ''
  lastPickedStory.value = {
    text,
    type: data?.type || '',
    styles: Array.isArray(data?.styles) ? data.styles : [],
  }
  return text
}
