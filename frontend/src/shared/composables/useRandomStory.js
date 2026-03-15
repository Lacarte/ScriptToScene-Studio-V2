import { RANDOM_STORIES } from '@/shared/data/stories.js'

let lastIdx = -1

/**
 * Pick a random story, avoiding the previously selected one.
 * Shared between Pipeline and TTS so they use the same pool and index.
 */
export function pickRandomStory() {
  if (!RANDOM_STORIES.length) return ''
  let idx
  do {
    idx = Math.floor(Math.random() * RANDOM_STORIES.length)
  } while (idx === lastIdx && RANDOM_STORIES.length > 1)
  lastIdx = idx
  return RANDOM_STORIES[idx]
}
