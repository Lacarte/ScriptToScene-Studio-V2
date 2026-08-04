# Upgrade Prompt — Node-Based Workflow Editor for ScriptToScene Studio

> Refined prompt, ready to paste into Claude Code. Based on architecture research of
> n8n (github.com/n8n-io/n8n) and Automa (github.com/automaapp/automa), both of which
> build their canvas on Vue Flow — the same Vue 3 + Pinia stack this app already uses.

---

## THE PROMPT

Upgrade ScriptToScene Studio into a **node-based visual workflow builder**, in the style of n8n and Automa. Instead of the fixed 7-step pipeline (TTS → Alignment → Segmentation → Scenes → Assets → Assemble → Export), the user builds the pipeline visually: drag module nodes from a palette onto a canvas, connect them, configure each node, save the graph as a project, and run it — with live per-node execution status.

### Context — what exists today

- Frontend: Vue 3.5 + Pinia + Vue Router + Vite in `frontend/`, feature-based modules under `frontend/src/features/`.
- Backend: Flask (`app.py`, port 5050), modules under `studio/` (tts, timing, segmenter, scenes, assets, editor, captions, music, thumbnails).
- The pipeline today is a hardcoded chain of `_step_tts`, `_step_timing`, `_step_segment`, `_step_scenes`, `_step_storyboard`, `_step_assets`, `_step_assemble`, `_step_export` functions in `studio/pipeline/routes.py`, each consuming the previous step's result dict. Progress streams over SSE (`/api/pipeline/progress/:job_id`).
- Every step already persists its output as JSON under `output/` (voice.json, alignment.json, segmented.json, scenes.json, …) — these are the natural payloads that flow along edges.
- Do NOT break the existing pipeline page, individual step pages, timeline editor, or export library. The node editor is a new feature (`frontend/src/features/workflow/`, `studio/workflow/`) that reuses the same step functions.

### 1. Canvas (frontend)

Use **Vue Flow** (`@vue-flow/core` + `@vue-flow/background` + `@vue-flow/minimap` + `@vue-flow/controls`) — this is what both n8n and Automa use, and it's native Vue 3. Add `@dagrejs/dagre` for an optional "tidy up" auto-layout button.

- New route/page `WorkflowPage.vue` with: dot-grid background, zoom/pan (minZoom 0.1, maxZoom 1.5), minimap colored by node category, snap-to-grid (20px), multi-select (Ctrl), `Delete` key removes selection.
- Custom node component(s) registered as Vue Flow `nodeTypes`: rounded card showing category color strip, icon, node label, status badge (idle / running / success / error), and input/output handles. One generic `NodeCard.vue` driven by the registry (Automa's `BlockBasic` pattern) rather than one component per node type.
- Custom edge with arrowhead, hover state showing a delete button, and a "running" animation while data flows.

### 2. Node registry (single source of truth — the highest-leverage idea from both apps)

Create a **declarative node registry** that drives everything: the palette, node rendering, default config, config panel forms, and backend validation. One entry per node type:

```js
// frontend/src/features/workflow/registry/nodes.js
export const nodeTypes = {
  'tts': {
    name: 'Text to Speech',
    icon: 'mic',
    category: 'audio',            // categories: input, audio, timing, ai, assets, video, output
    inputs:  [{ id: 'text',      type: 'script' }],
    outputs: [{ id: 'audio',     type: 'tts_result' }],
    properties: [                 // n8n-style schema-driven config
      { name: 'engine', label: 'Engine', type: 'options', options: ['kokoro', 'inworld'], default: 'kokoro' },
      { name: 'voice',  label: 'Voice',  type: 'options', optionsFrom: '/api/tts/voices', default: 'af_heart' },
      { name: 'speed',  label: 'Speed',  type: 'number', min: 0.5, max: 2.0, step: 0.1, default: 1.0 },
      // displayOptions: conditional visibility, e.g. only show kokoro-only fields when engine === 'kokoro'
      { name: 'blend',  label: 'Voice blend', type: 'string', default: '', displayOptions: { show: { engine: ['kokoro'] } } },
    ],
    endpoint: '/api/workflow/nodes/tts/run',   // backend executor
  },
  // ... one entry per module
}
```

Initial node set (map 1:1 to existing `studio/` modules — reuse their functions, do not rewrite them):

| Node | Inputs → Outputs | Wraps |
|---|---|---|
| **Script Input** (trigger) | — → script text | pipeline form / story gen |
| **TTS** | script → voice.wav + voice.json | `studio/tts` |
| **Force Alignment** | tts_result → alignment.json | `studio/timing` |
| **Segmenter** | alignment → segmented.json | `studio/segmenter` |
| **Scene Generator (AI)** | segments → scenes.json | `studio/scenes` |
| **Storyboard** | scenes → storyboard | storyboard step |
| **Asset Grabber** | scenes → asset files | `studio/assets` (provider is a node property) |
| **Assemble** | scenes + assets + audio → project JSON | assemble step |
| **Export** | project → video.mp4 | `studio/editor` export engine |
| Utility: **Note/Comment**, **Merge**, **Branch/If** (e.g. route by scene type), **Delay** | | |

**Typed ports:** each handle has a data type (`script`, `tts_result`, `alignment`, `segments`, `scenes`, `assets`, `project`). `onConnect` must reject type-incompatible connections (and reject output→output / cycles), with a toast explaining why. Color handles by data type.

### 3. Workflow JSON schema (save/load)

Persist workflows as plain JSON (n8n/Automa hybrid), stored via new endpoints `GET/POST /api/workflows`, `GET/PUT/DELETE /api/workflows/:id`, files under `output/workflows/{workflow_id}.json`:

```jsonc
{
  "id": "wf_AB12CD",
  "name": "Standard Shorts Pipeline",
  "version": 1,
  "nodes": [
    { "id": "n1", "type": "tts", "label": "Narration",
      "position": { "x": 120, "y": 240 },
      "data": { "engine": "kokoro", "voice": "af_heart", "speed": 1.0 } }
  ],
  "edges": [
    { "id": "e1", "source": "n1", "sourceHandle": "n1-audio",
      "target": "n2", "targetHandle": "n2-tts_result" }
  ],
  "viewport": { "x": 0, "y": 0, "zoom": 1 },
  "settings": { "onError": "stop", "retryTimes": 0 }
}
```

On save, serialize ONLY `{id, type, label, position, data}` per node — strip Vue Flow runtime props (Automa does exactly this). Support export/import as a `.json` file download/upload. Ship 2–3 built-in template workflows (e.g. "Full pipeline", "Scenes only", "Re-export") the user can start from.

### 4. Config panel (schema-driven, zero per-node UI code)

Clicking a node opens a right-side panel (or double-click → modal) that renders the form **generically from the registry's `properties` array** — n8n's `ParameterInputList` pattern:

- Widget per property `type`: `string`, `number` (slider+input), `boolean` (toggle), `options` (select, with async `optionsFrom` endpoint support), `textarea`, `json`.
- `displayOptions.show/hide` re-evaluated on every value change for conditional fields.
- Panel header: rename node label, enable/disable node toggle, delete button.
- n8n's killer layout, simplified: show **last input data | parameters | last output data** side by side when run data exists, so the user configures against real data.
- Validate before close; show inline issues (missing required fields) as a badge on the node card too.

### 5. Execution engine (backend, `studio/workflow/engine.py`)

- `POST /api/workflow/run` with the workflow JSON (or id) → returns `job_id` + `project_id`; progress over SSE like the existing pipeline (reuse `_emit` pattern), events per node: `{node_id, status: queued|running|done|error, duration, summary}`.
- Engine: validate the graph (single trigger, no cycles, required inputs connected, type-check edges) → build a `sourceHandle → [targets]` connection map (Automa's O(1) lookup) → execute as a **stack/queue machine** (n8n style), not naive topological sort: pop node, gather inputs from upstream results, dispatch to the wrapped step function, store result in `run_data[node_id]`, push downstream nodes. Multi-input nodes (Assemble, Merge) wait until all connected inputs have arrived.
- Data on edges = the existing JSON artifacts (pass paths + parsed dicts; reuse `_load_prior_results` logic for caching).
- Error handling per node: `onError` = stop | continue | retry (n retries with interval); optional dedicated **error output handle** (fallback path) that routes to an alternative branch when connected.
- **Partial execution / caching**: "Run to this node" and "Run from this node" — reuse persisted upstream outputs when their node config hash is unchanged (this app already persists everything under `output/`, so this is cheap and is n8n's pin-data superpower for free).
- Stop button reuses the existing stop-request mechanism.

### 6. Editor UX (must-haves, all from n8n/Automa)

1. **Palette**: left sidebar, search box, nodes grouped by category with colors, drag onto canvas (`dataTransfer` carries the node type; on drop, project screen→canvas coords and insert with registry defaults). Also: drag a connection from an output handle and release on empty canvas → open the palette filtered to type-compatible nodes, auto-connect the chosen one (n8n's best trick).
2. **Node operations**: drag to move, duplicate (Ctrl+D), delete, disable/enable, rename, copy/paste as JSON (clipboard = workflow fragment, works across workflows), right-click context menu.
3. **Replace node**: context-menu "Replace with…" keeps compatible connections (e.g. swap Asset Grabber provider node).
4. **Undo/redo** via a command stack (add/move/delete/connect/config-change), Ctrl+Z / Ctrl+Shift+Z, dirty-state indicator + unsaved-changes prompt.
5. **Run visualization**: per-node spinner/success/error states, item summary on edges after run (e.g. "10 segments", "28.5s audio"), click a finished node to inspect its actual output JSON.
6. **Autosave** the working graph (localStorage or `work@in@progress` file) + explicit save; keep last N versions for restore.

### 7. Implementation phases (each phase leaves the app working)

1. **Phase 1 — Canvas MVP**: install Vue Flow; WorkflowPage with palette, drag-drop, connect/delete, save/load workflow JSON, registry with the 9 core nodes (no execution yet). Type-checked connections.
2. **Phase 2 — Config panel**: schema-driven property renderer with displayOptions, validation badges, async options.
3. **Phase 3 — Execution**: `studio/workflow/engine.py` wrapping existing step functions, SSE per-node status, canvas run visualization, stop.
4. **Phase 4 — Power UX**: undo/redo, copy/paste, replace node, partial runs with cached upstream outputs, error-output handles, templates, import/export, dagre tidy-up.

Work phase by phase, verify each in the running app (`start-dev.bat`) before moving on. Follow existing code conventions (feature folders, composables, Pinia stores, `safe_json_write` atomic persistence, `security.py` sanitization for workflow ids).

---

## Research notes backing these choices

- **Vue Flow everywhere**: n8n migrated from jsPlumb, Automa from Drawflow — both landed on `@vue-flow/core`. It's Vue-3-native, matches this codebase, and gives handles, zoom/pan, minimap, selection out of the box.
- **Declarative registry** (Automa `src/utils/shared.js` `tasks` object; n8n `INodeTypeDescription`): one object drives palette + node rendering + defaults + edit form + validation. Zero per-node UI code.
- **Schema-driven config with `displayOptions`** (n8n NDV): generic renderer + conditional visibility; any new node is data, not code.
- **Handle-encoded routing + connection map** (Automa `WorkflowEngine.init`): edges → `{sourceHandle: targets}` map, O(1) next-node lookup, `fallback` handle = error path.
- **Stack-machine execution with per-node run data** (n8n `WorkflowExecute`): pop → gather inputs → execute → record `run_data[node]` → push successors; multi-input nodes wait for all inputs; branch = choose output index.
- **Pin/cache upstream outputs for partial runs** (n8n `pinData` + partial-execution graph): this app already persists every step's JSON, so "run from here" is nearly free.
- **Serialize minimal node shape** on save (Automa): `{id, type, label, position, data}` only.
