<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useWorkflowStore } from '../stores/workflow.js'

const store = useWorkflowStore()
const router = useRouter()

const executionNodes = computed(() => {
  const execution = store.currentExecution
  if (!execution) return []
  const snapshotNodes = execution.workflow_snapshot?.nodes || store.nodes
  return snapshotNodes.map((node) => ({
    id: node.id,
    name: node.name,
    record: execution.nodes?.[node.id] || store.nodeExecution(node.id),
  }))
})

function duration(value) {
  if (!Number.isFinite(value)) return '—'
  if (value < 1000) return `${value} ms`
  return `${(value / 1000).toFixed(value < 10_000 ? 1 : 0)} s`
}

function errorText(error) {
  if (!error) return ''
  return error.message || error.code || 'Node failed'
}

function openEditor() {
  if (store.editorProjectId) {
    router.push({ path: '/editor', query: { project: store.editorProjectId } })
  }
}
</script>

<template>
  <footer class="execution-panel">
    <div class="execution-head">
      <div>
        <span class="execution-title">Current run</span>
        <span v-if="store.currentExecution" class="execution-id">
          {{ store.currentExecution.execution_id }} · {{ store.currentExecution.status }}
        </span>
      </div>
      <button
        v-if="store.editorProjectId"
        class="execution-open"
        @click="openEditor"
      >Open in Timeline Editor</button>
    </div>

    <div v-if="store.executionError" class="execution-stream-error" role="status">
      {{ store.executionError }}
    </div>

    <div v-if="!store.currentExecution" class="execution-empty">
      Run the workflow to inspect node results.
    </div>
    <div v-else class="execution-content">
      <div class="execution-list" aria-label="Current execution nodes">
        <button
          v-for="item in executionNodes"
          :key="item.id"
          class="execution-row"
          :class="[
            `status-${item.record.status}`,
            { selected: store.selectedExecutionNodeId === item.id },
          ]"
          :disabled="!['succeeded', 'failed', 'cancelled', 'skipped'].includes(item.record.status)"
          @click="store.selectExecutionNode(item.id)"
        >
          <span class="execution-dot" />
          <span class="execution-name">{{ item.name }}</span>
          <span v-if="item.record.from_sample_data" class="execution-sample">sample</span>
          <span class="execution-status">{{ item.record.status }}</span>
          <span class="execution-duration">{{ duration(item.record.duration_ms) }}</span>
          <span v-if="item.record.error" class="execution-error" :title="errorText(item.record.error)">
            {{ errorText(item.record.error) }}
          </span>
        </button>
      </div>
      <div class="execution-output">
        <template v-if="store.selectedExecutionNode">
          <div class="output-title">Output JSON</div>
          <pre>{{ JSON.stringify(store.selectedExecutionNode.outputs_summary || {}, null, 2) }}</pre>
        </template>
        <div v-else class="output-empty">Click a finished node to view its output.</div>
      </div>
    </div>
  </footer>
</template>

<style scoped>
.execution-panel { position: relative; height: 190px; min-height: 190px; border-top: 1px solid var(--border); background: var(--bg-darkest); display: flex; flex-direction: column; }
.execution-head { min-height: 34px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 5px 14px; border-bottom: 1px solid var(--border); }
.execution-title { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .15em; color: var(--text-muted); }
.execution-id { margin-left: 10px; font-size: 10px; color: var(--text-secondary); }
.execution-open { border: 1px solid rgba(78,205,196,.45); border-radius: 7px; background: rgba(78,205,196,.1); color: var(--accent); font-size: 11px; font-weight: 650; padding: 5px 9px; cursor: pointer; }
.execution-empty { padding: 20px 14px; font-size: 12px; color: var(--text-muted); }
.execution-stream-error { position: absolute; right: 14px; margin-top: 35px; z-index: 2; max-width: 360px; border: 1px solid rgba(251,113,133,.35); border-radius: 5px; background: rgba(68,20,30,.95); color: #fecdd3; font-size: 9px; padding: 3px 7px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.execution-content { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(430px, 1.45fr) minmax(280px, 1fr); }
.execution-list { min-width: 0; overflow: auto; border-right: 1px solid var(--border); padding: 4px 7px; }
.execution-row { width: 100%; display: grid; grid-template-columns: 9px minmax(120px, 1fr) auto 68px 62px minmax(0, 1fr); align-items: center; gap: 7px; border: 0; border-radius: 5px; background: transparent; color: var(--text-secondary); font-size: 10px; padding: 4px 7px; text-align: left; }
.execution-row:not(:disabled) { cursor: pointer; }
.execution-row:not(:disabled):hover, .execution-row.selected { background: rgba(255,255,255,.055); color: var(--text); }
.execution-row:disabled { opacity: .85; }
.execution-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--status-color, #64748b); }
.execution-name, .execution-error { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.execution-status { color: var(--status-color, var(--text-muted)); text-transform: capitalize; }
.execution-duration { color: var(--text-muted); text-align: right; font-variant-numeric: tabular-nums; }
.execution-error { color: #fca5a5; }
.execution-sample { color: #c4b5fd; border: 1px solid rgba(196,181,253,.35); border-radius: 4px; padding: 0 3px; font-size: 8px; text-transform: uppercase; }
.execution-output { min-width: 0; overflow: auto; padding: 7px 10px; }
.output-title { font-size: 9px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: .1em; margin-bottom: 5px; }
pre { margin: 0; color: #cbd5e1; font: 10px/1.45 var(--font-mono, monospace); white-space: pre-wrap; overflow-wrap: anywhere; }
.output-empty { color: var(--text-muted); font-size: 11px; padding-top: 12px; }
.status-idle, .status-queued { --status-color: #64748b; }
.status-running { --status-color: #38bdf8; }
.status-waiting { --status-color: #a78bfa; }
.status-succeeded { --status-color: #34d399; }
.status-failed { --status-color: #fb7185; }
.status-cancelled { --status-color: #f59e0b; }
.status-skipped { --status-color: #94a3b8; }
.status-stale { --status-color: #fb923c; }
</style>
