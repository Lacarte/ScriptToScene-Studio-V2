<script setup>
import { computed } from 'vue'
import { useWorkflowStore } from '../stores/workflow.js'
import { shouldDisplayField } from '../schema.js'
import ConfigField from './ConfigField.vue'
import NodeIcon from './NodeIcon.vue'

const store = useWorkflowStore()

const node = computed(() => store.selectedNode)
const def = computed(() => (node.value ? store.nodeTypes[node.value.type] : null))
const category = computed(() => store.categories[def.value?.category] || {})
const errorPolicy = computed(() => node.value?.on_error || { policy: 'stop' })
const errorPolicies = computed(() => {
  const capabilities = def.value?.capabilities || {}
  return [
    { value: 'stop', label: 'Stop workflow' },
    ...(capabilities.retry ? [{ value: 'retry', label: 'Retry' }] : []),
    ...(capabilities.error_output ? [{ value: 'continue_error', label: 'Use error output' }] : []),
    ...(capabilities.skip_optional ? [{ value: 'skip_optional', label: 'Skip optional node' }] : []),
  ]
})

// display_options re-evaluated on every config change (n8n NDV pattern).
const visibleFields = computed(() =>
  (def.value?.config_schema || []).filter((field) =>
    shouldDisplayField(field, node.value?.configuration),
  ),
)

const issues = computed(() => store.issuesByNode[node.value?.id] || [])

function onUpdate(name, value) {
  store.updateNodeConfig(node.value.id, name, value)
}

function onDelete() {
  store.removeNodes([node.value.id])
  store.clearSelection()
}


function updateErrorPolicy(patch) {
  store.updateNodeErrorPolicy(node.value.id, patch)
}
</script>

<template>
  <div v-if="!node || !def" class="wf-panel-empty">
    Select a node to configure it
  </div>

  <div v-else class="inspector">
    <header class="inspector-head">
      <span class="inspector-icon" :style="{ color: category.color }">
        <NodeIcon :icon="def.icon" />
      </span>
      <input
        class="inspector-name"
        :value="node.name"
        :maxlength="120"
        title="Rename node"
        @change="store.renameNode(node.id, $event.target.value.trim() || def.display_name)"
      />
    </header>
    <div class="inspector-sub">
      <span class="inspector-type">{{ def.display_name }} · v{{ node.type_version }}</span>
      <span class="inspector-actions">
        <button
          class="ins-btn"
          :class="{ off: node.disabled }"
          :title="node.disabled ? 'Enable node' : 'Disable node'"
          @click="store.setNodeDisabled(node.id, !node.disabled)"
        >{{ node.disabled ? 'Enable' : 'Disable' }}</button>
        <button class="ins-btn" title="Duplicate node" @click="store.duplicateNode(node.id)">Duplicate</button>
        <button class="ins-btn danger" title="Delete node" @click="onDelete">Delete</button>
      </span>
    </div>

    <p v-if="def.description" class="inspector-desc">{{ def.description }}</p>

    <section v-if="errorPolicies.length > 1" class="error-policy">
      <label>
        <span>On error</span>
        <select
          :value="errorPolicy.policy"
          @change="updateErrorPolicy({ policy: $event.target.value })"
        >
          <option v-for="option in errorPolicies" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
      <div v-if="errorPolicy.policy === 'retry'" class="retry-grid">
        <label>
          <span>Max attempts</span>
          <input type="number" min="1" max="10" :value="errorPolicy.max_attempts ?? 3"
            @change="updateErrorPolicy({ max_attempts: Number($event.target.value) })" />
        </label>
        <label>
          <span>Delay (ms)</span>
          <input type="number" min="0" max="60000" :value="errorPolicy.delay_ms ?? 1000"
            @change="updateErrorPolicy({ delay_ms: Number($event.target.value) })" />
        </label>
        <label>
          <span>Backoff</span>
          <input type="number" min="1" max="10" step="0.1" :value="errorPolicy.backoff_multiplier ?? 2"
            @change="updateErrorPolicy({ backoff_multiplier: Number($event.target.value) })" />
        </label>
      </div>
    </section>

    <ul v-if="issues.length" class="inspector-issues">
      <li v-for="issue in issues" :key="issue.kind + issue.name">{{ issue.message }}</li>
    </ul>

    <div v-if="!visibleFields.length" class="wf-panel-empty">
      This node has no settings.
    </div>

    <div v-else class="inspector-fields">
      <ConfigField
        v-for="field in visibleFields"
        :key="field.name"
        :field="field"
        :value="node.configuration[field.name]"
        @update="(value) => onUpdate(field.name, value)"
      />
    </div>
  </div>
</template>

<style scoped>
.inspector {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
}

.inspector-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 14px 0;
}

.inspector-icon {
  width: 18px;
  height: 18px;
  min-width: 18px;
}

.inspector-icon svg {
  width: 100%;
  height: 100%;
}

.inspector-name {
  flex: 1;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  color: var(--text);
  font-size: 13px;
  font-weight: 700;
  padding: 4px 6px;
  outline: none;
  min-width: 0;
}

.inspector-name:hover,
.inspector-name:focus {
  border-color: var(--border);
  background: var(--bg-dark);
}

.inspector-sub {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 14px 0;
  flex-wrap: wrap;
}

.inspector-type {
  font-size: 10px;
  color: var(--text-muted);
}

.inspector-actions {
  display: flex;
  gap: 5px;
}

.ins-btn {
  background: var(--bg-dark);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 10.5px;
  font-weight: 600;
  padding: 3px 8px;
  cursor: pointer;
}

.ins-btn:hover {
  color: var(--text);
  border-color: var(--accent);
}

.ins-btn.off {
  color: var(--accent-warning, #ffb347);
}

.ins-btn.danger:hover {
  color: #f87171;
  border-color: #f87171;
}

.inspector-desc {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
  padding: 6px 14px 2px;
}

.error-policy {
  margin: 8px 14px 2px;
  padding: 9px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-dark);
}

.error-policy label { display: grid; gap: 4px; font-size: 10.5px; color: var(--text-muted); }
.error-policy select,
.error-policy input {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 5px;
  background: var(--bg-panel);
  color: var(--text);
  padding: 5px 6px;
  font-size: 11px;
}
.retry-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-top: 7px; }

.inspector-issues {
  margin: 6px 14px 0;
  padding: 8px 10px 8px 24px;
  border: 1px solid rgba(255, 179, 71, 0.35);
  border-radius: 8px;
  background: rgba(255, 179, 71, 0.07);
  font-size: 11px;
  color: var(--accent-warning, #ffb347);
  line-height: 1.5;
}

.inspector-fields {
  flex: 1;
  overflow-y: auto;
  padding-bottom: 12px;
}

.wf-panel-empty {
  font-size: 12px;
  color: var(--text-muted);
  padding: 8px 14px;
  opacity: 0.7;
}
</style>
