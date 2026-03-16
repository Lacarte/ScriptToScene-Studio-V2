import { ref } from 'vue'
import { RANDOM_STORIES } from '@/shared/data/stories.js'

let lastIdx = -1

/** Last picked story metadata (reactive) */
export const lastPickedStory = ref(null)

/**
 * Pick a random story, avoiding the previously selected one.
 * Shared between Pipeline and TTS so they use the same pool and index.
 * @returns {string} The story text
 */
export function pickRandomStory() {
  if (!RANDOM_STORIES.length) return ''
  let idx
  do {
    idx = Math.floor(Math.random() * RANDOM_STORIES.length)
  } while (idx === lastIdx && RANDOM_STORIES.length > 1)
  lastIdx = idx

  const entry = RANDOM_STORIES[idx]
  // Support both plain strings (legacy) and objects { text, type, styles }
  if (typeof entry === 'string') {
    lastPickedStory.value = { text: entry, type: '', styles: [] }
    return entry
  }
  lastPickedStory.value = entry
  return entry.text
}
