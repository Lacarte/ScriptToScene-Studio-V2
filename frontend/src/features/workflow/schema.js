/**
 * Schema helpers shared by the inspector and node cards (step 2.2).
 * Mirrors the backend rules in studio/workflows/validation.py for the
 * checks that matter while editing; the server stays authoritative.
 */

/** n8n-style display_options: {show: {field: [values]}, hide: {...}}. */
export function shouldDisplayField(field, configuration) {
  const display = field.display_options
  if (!display) return true
  const config = configuration || {}
  for (const [ref, values] of Object.entries(display.show || {})) {
    if (!values.includes(config[ref])) return false
  }
  for (const [ref, values] of Object.entries(display.hide || {})) {
    if (values.includes(config[ref])) return false
  }
  return true
}

/**
 * Issues for one node: empty required config fields (only when visible)
 * and required data inputs with no incoming edge.
 * @returns {Array<{kind: 'config'|'input', name: string, message: string}>}
 */
export function nodeIssues(node, def, edges) {
  if (!def) {
    return [{ kind: 'config', name: node.type, message: `Unknown node type: ${node.type}` }]
  }
  const issues = []

  for (const field of def.config_schema || []) {
    if (!field.required) continue
    if (!shouldDisplayField(field, node.configuration)) continue
    const value = node.configuration?.[field.name]
    if (value === null || value === undefined || value === '') {
      issues.push({
        kind: 'config',
        name: field.name,
        message: `${field.label || field.name} is required`,
      })
    }
  }

  for (const port of def.inputs || []) {
    if (!port.required || port.type === 'control') continue
    const connected = edges.some(
      (e) => e.target_node === node.id && e.target_port === port.id,
    )
    if (!connected) {
      issues.push({
        kind: 'input',
        name: port.id,
        message: `The ${port.id} input needs a connection`,
      })
    }
  }

  return issues
}
