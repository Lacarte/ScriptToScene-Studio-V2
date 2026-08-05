<script setup>
import { computed } from 'vue'
import { useWorkflowStore } from '../stores/workflow.js'

const props = defineProps({ id: { type: String, required: true } })
const store = useWorkflowStore()
const note = computed(() => store.noteById(props.id))
const colors = ['yellow', 'blue', 'green', 'pink']
</script>

<template>
  <article v-if="note" class="sticky-note" :class="`sticky-note--${note.color || 'yellow'}`">
    <textarea
      class="sticky-note-text nodrag nowheel"
      aria-label="Sticky note text"
      :value="note.text"
      maxlength="4000"
      placeholder="Write a note…"
      @change="store.updateNote(id, { text: $event.target.value })"
    />
    <footer class="sticky-note-footer nodrag">
      <button
        v-for="color in colors"
        :key="color"
        type="button"
        class="sticky-note-color"
        :class="`sticky-note-color--${color}`"
        :aria-label="`Use ${color} note`"
        :aria-pressed="note.color === color"
        @click="store.updateNote(id, { color })"
      />
    </footer>
  </article>
</template>

<style scoped>
.sticky-note {
  width: 220px;
  min-height: 150px;
  padding: 12px 12px 8px;
  border: 1px solid rgba(30, 41, 59, 0.22);
  border-radius: 4px;
  box-shadow: 0 7px 18px rgba(0, 0, 0, 0.22);
  color: #263043;
}

.sticky-note--yellow { background: #fff2a8; }
.sticky-note--blue { background: #bfe7ff; }
.sticky-note--green { background: #ccefc2; }
.sticky-note--pink { background: #ffd0df; }

.sticky-note-text {
  display: block;
  width: 100%;
  min-height: 112px;
  resize: vertical;
  border: 0;
  outline: 0;
  background: transparent;
  color: inherit;
  font: 500 13px/1.45 inherit;
}

.sticky-note-footer { display: flex; justify-content: flex-end; gap: 5px; margin-top: 6px; }
.sticky-note-color { width: 13px; height: 13px; padding: 0; border: 1px solid rgba(30, 41, 59, 0.3); border-radius: 50%; cursor: pointer; }
.sticky-note-color[aria-pressed='true'] { outline: 2px solid rgba(30, 41, 59, 0.7); outline-offset: 1px; }
.sticky-note-color--yellow { background: #fff2a8; }
.sticky-note-color--blue { background: #bfe7ff; }
.sticky-note-color--green { background: #ccefc2; }
.sticky-note-color--pink { background: #ffd0df; }
</style>
