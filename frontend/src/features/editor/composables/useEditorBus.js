/**
 * Editor event bus — lightweight pub/sub for editor component communication.
 * Replaces window.dispatchEvent(new CustomEvent(...)) pattern.
 *
 * Usage:
 *   const bus = useEditorBus()
 *   bus.emit('scene-selected', { index: 3 })
 *   bus.on('scene-selected', (data) => { ... })
 */

const listeners = {}

function on(event, fn) {
  if (!listeners[event]) listeners[event] = []
  listeners[event].push(fn)
}

function off(event, fn) {
  if (!listeners[event]) return
  listeners[event] = listeners[event].filter(f => f !== fn)
}

function emit(event, data) {
  if (listeners[event]) {
    for (const fn of listeners[event]) fn(data)
  }
}

export function useEditorBus() {
  return { on, off, emit }
}
