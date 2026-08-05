# Workflow Builder — Implementation Plan (digestible steps)

> Companion to [proposition-final.md](proposition-final.md) (the authoritative spec).
> This plan breaks the 6 phases into small, independently verifiable steps.
> Each step is a commit-sized unit (roughly half a day to two days), has explicit
> "done when" criteria, and leaves the app working.
>
> Grounded in the actual codebase (verified 2026-08-04):
> - `app.py` imports and registers 14 blueprints at lines 71–84 — `workflows_bp` follows the same startup pattern.
> - `frontend/src/app/router.js` lazy-loads feature pages — `/workflow` follows the pattern.
> - `studio/pipeline/routes.py` is ~2,400 lines with `_step_*` functions embedded (lines 1242–2371)
>   — service extraction (step 3.1) is the highest-risk step in the plan.
> - Backend tests exist (`tests/test_*.py`, pytest). Vitest, Vue Test Utils, jsdom,
>   and an initial frontend smoke test were added during step 0.3.
> - Existing modules to wrap: `studio/{tts, timing, segmenter, build_scene_blueprints,
>   storyboard, animator, captions, music, editor}` + assemble/export steps in pipeline routes.

## Working agreements (apply to every step)

- One step = one commit (or a small stack). Never mix service extraction with behavior change.
- After each **phase**: run `pytest`, run frontend tests, run `npm run build` in `frontend/`, smoke-test in the running app (`start-dev.bat`), and record results before starting the next phase.
- `/pipeline`, module pages, timeline editor, and export library must work after every single step.
- New backend runtime code goes in `studio/workflows/`; new frontend runtime code in `frontend/src/features/workflow/`. Nothing else moves except deliberate integration points and the extraction in 3.1.
- Follow existing conventions: feature folders, composables, Pinia stores, `safe_json_write` (`studio/io_utils.py`), and `safe_join` (`studio/security.py`). Workflow and execution IDs require strict prefix/format validation; do not silently accept the altered result of `sanitize_project_id`.

---

## Phase 0 — Audit, contracts, and test infrastructure

No workflow runtime or UI feature code belongs in this phase. Development-only test
configuration and small deterministic fixture assets are allowed.

### 0.1 Artifact & step audit → node contract table
Read `studio/pipeline/routes.py` step functions (`_step_tts` … `_step_export`, `_load_prior_results`, `_emit`) and each wrapped module. For every planned node, document: stable input/output **port IDs**, port types, required/optional and cardinality rules, exact input artifacts (file + dict shape), output artifacts, config keys actually consumed, cancellation/retry support, determinism, and side effects on `output/{project_id}/`.
Resolve the open question: how Assemble treats storyboard images vs animation assets (audit `_step_assemble` at line 1919 and `_step_assets` at 1813) — encode the answer in the Assemble adapter contract.
**Deliverable:** `_dev/loop-engineering/phases-plans/contracts.md` with the input/output contract table.
**Done when:** every node in the catalog maps to a real function + real artifacts; every edge in every built-in template names real ports; project/source-folder identity propagation is explicit; and discrepancies vs the spec are documented and resolved in favor of working behavior.

### 0.2 Freeze the machine contracts
In the same doc, freeze: workflow JSON schema (with `schema_version`, `type_version`, reserved `variables`), execution record schema, the served node-type shape, exact HTTP request/response envelopes and status codes, the full API route list, SSE event shape (with `sequence` and standard SSE `id`/`Last-Event-ID` replay), port-type compatibility matrix, control-edge readiness semantics, dynamic-port resolution for `stub.input`, `stub.output`, and `workflow.output`, and stable error codes. Include security/threat notes: strict ID validation, `safe_join`, redaction points, import limits, endpoint authorization/loopback policy, approved async option sources, and managed-media rules.

Define the fixture inventory and validation schema in this step. Capture or generate the actual sanitized fixtures before step 2.5, when they are first consumed. Prefer deterministic local media generation and provider-mocked JSON; a Phase 0 gate must not depend on live n8n/provider availability.

**Done when:** the contracts are internally consistent; every persistent and served field has a type, required/optional status, limits, and unknown-field policy; templates validate against named ports; and later phases can code against them without redesign.

### 0.3 Test infrastructure
Establish and record the backend baseline. Add **Vitest + @vue/test-utils + jsdom** to `frontend/` with an `npm run test` script and one trivial smoke test that mounts a component. Add a reproducible development dependency declaration for pytest instead of relying on packages installed only inside one local venv.

**Done when:** `npm run test` and `npm run build` pass; the backend suite is green, or a pre-existing environment-sensitive failure has a tracked resolution (dependency pin, corrected test/code, or explicit quarantine with owner approval). Merely recording a failure is not a green Phase 0 gate. CI/dev docs note exact commands and supported Node/Python versions.

### 0.4 Phase 0 consistency review and gate
Validate `contracts.md` against `proposition-final.md` and the repository one final time. Check every built-in template edge, node port, artifact filename, API route, status enum, and ID/path rule. Record completed, deferred, and blocked items with evidence; do not label draft prose as a frozen machine contract.

**Done when:** there are no unresolved contradictions; fixture capture has an owner and deadline before 2.5; test results are current; and Phase 1 can begin without inventing contract semantics.

### Phase 0 review status — 2026-08-04

- **0.1: complete.** The module/artifact audit, named port contracts, control readiness, source artifacts, and Storyboard/Animator/Assemble discrepancy are documented.
- **0.2: complete for Phase 0.** Field constraints, HTTP envelopes/status codes, strict IDs, SSE `Last-Event-ID` replay, security limits, and fixture validation rules are frozen. The actual deterministic fixture files are an explicit prerequisite of step 2.5, where they are first used.
- **0.3: complete.** `requirements-dev.txt` tracks pytest; backend is 14 passed plus 2 subtests; Vitest is 1 passed; the production frontend build succeeds; supported runtimes are recorded in `contracts.md`.
- **0.4: complete.** The corrected contracts and plan are internally consistent and Phase 1 can begin without inventing graph, persistence, API, or replay semantics.

**Phase 0 is gated complete.** The next implementation step is 1.1. Fixture files remain a
tracked prerequisite of 2.5, not a hidden Phase 0 dependency.

Phase 0 verification commands:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
Set-Location frontend
npm ci
npm test
npm run build
```

---

## Phase 1 — Canvas & persistence MVP (no execution)

### 1.1 Dependencies + route shell
Install `@vue-flow/core`, `@vue-flow/background`, `@vue-flow/minimap`, `@vue-flow/controls`, `@dagrejs/dagre`. Add `/workflow` route in `router.js` → new `features/workflow/views/WorkflowPage.vue` with the five empty layout regions (library / canvas / inspector / bottom panel / toolbar) and nav entry.
**Done when:** page renders with an empty Vue Flow canvas; `/pipeline` untouched; `npm run build` passes.

### 1.2 Backend registry + node-types endpoint
Create `studio/workflows/{__init__.py, registry.py, routes.py}`; register `workflows_bp` in `app.py`. `registry.py` holds the authoritative core catalog (all core + testing nodes from the spec table, including `project.setup` with its branding/logo schema, with `type`, `type_version`, ports, `config_schema`, defaults, capabilities). `GET /api/workflow/node-types` serves the presentation-safe form (no executor internals).
**Done when:** endpoint returns the full catalog; pytest covers serialization, version fields, and that no callable/internal fields leak.

### 1.3 Workflow store + node library panel
Pinia store (`features/workflow/stores/workflow.js`) holding nodes/edges/viewport/dirty state; fetch node-types on mount. Left panel: search, category groups with colors, name+icon+description, drag source (`dataTransfer` carries node type).
**Done when:** all catalog nodes appear grouped and searchable; drag starts (drop handled next step).

### 1.4 Canvas + generic NodeCard
Drop → project screen→canvas coords → insert with registry defaults. One generic `NodeCard.vue`: category strip, icon, label, typed handles, placeholder status/validation badges. Move, multi-select, group move, Delete key, 20px snap grid, minimap colored by category, controls, fit-to-view, dagre tidy-up button.
**Done when:** a user can drag out and arrange the full pipeline visually; Vitest covers add/move/delete store mutations.

### 1.5 Typed connection validation (client)
`onConnect` rules from the spec: type compatibility (explicit matrix from 0.2 — no implicit `generic_json` wildcard), single-input cardinality, no in→in / out→out, cycle rejection, duplicate rejection. Handle colors by port type; highlight compatible targets while dragging; plain-language rejection toasts.
**Done when:** every rule has a Vitest case; invalid connections are impossible on canvas.

### 1.6 Workflow persistence (backend + save/load)
`studio/workflows/{models.py, validation.py, persistence.py}`: full CRUD at `/api/workflows` (list/create/get/update/soft-delete→TRASH), strict `wf_` ID validation plus `safe_join`, atomic writes, minimal serialized shape (strip Vue Flow runtime props). Server-side re-validation of types/ports/cycles on save. Toolbar: New, Open, Save, Save As, Duplicate.
**Done when:** save → reload → reopen round-trips losslessly; pytest covers round-trip, path-traversal rejection, soft delete, unknown-type/version rejection with useful errors.

### 1.7 Import/export + fixed-pipeline template
`POST /api/workflows/import` (validate size/schema/ids/counts before saving), `GET /api/workflows/<id>/export`, and `GET /api/workflow/templates`. Ship the **Full Video** template representing the current pipeline; template picker in the workflow toolbar/library surface.
**Done when:** exported file re-imports cleanly; template opens as a correctly connected, valid graph. **Phase 1 gate:** full test + build + manual smoke pass.

### Phase 1 review status — 2026-08-04

- **1.1–1.5: reviewed and strengthened.** Vue Flow route/canvas, backend-owned registry, generic cards, store, and typed client validation are present. Dynamic ports now reject unsupported types, and capability flags no longer advertise cancellation paths the existing providers do not expose.
- **1.6: complete.** Workflow CRUD uses strict IDs, `safe_join`, atomic JSON writes/backups, optimistic timestamps, server-side schema/port/cardinality/cycle validation, bounded requests and extension data, finite-number and maximum-depth enforcement, RFC 3339 identity timestamps, soft deletion, and persisted-shape-only frontend serialization.
- **1.7: complete.** Import/export and the server-validated Full Video template are wired into the toolbar with New, Open, Save, Save As, Duplicate, Import, Export, template selection, dirty-state prompts, and viewport restoration.
- Automated gate: 40 backend tests plus 2 subtests and 21 frontend tests pass; the production build and a live Flask create/load/update/delete and template API round trip pass.
- Manual visual gate: pending because the in-app browser surface was unavailable during this review. Verify drag/drop, toolbar overflow at the target window size, minimap, connection feedback, save/reopen, and template fit-to-view once in the running app before beginning Phase 2.

**Phase 1 is implementation-complete but awaits the documented manual visual smoke check.**

---

## Phase 2 — Configuration & validation

### 2.1 Schema-driven inspector renderer
Right panel renders forms generically from `config_schema`: string, textarea, number (constraints), boolean, options, JSON editor with validation. Defaults, descriptions, rename/disable/duplicate/delete actions.
**Done when:** every core node is configurable with zero per-node UI code; Vitest covers widget rendering per schema type.

#### Step 2.1 review status — 2026-08-04

- **Complete and strengthened.** The generic inspector covers every Phase 2.1 widget and node action without per-node UI code. Selection is document-scoped and cleared on removal; save/save-as preserve valid selection; duplication retains extension metadata while respecting persisted name and coordinate bounds.
- Automated gate: inspector/store coverage is included in the frontend suite and the production build passes. Manual visual verification remains part of the Phase 2 gate.

### 2.2 Conditional fields + validation badges + server validate
`display_options.show/hide` re-evaluated on every change (e.g. TTS `blend` only for kokoro). Missing-required and invalid-config badges on node cards and in the inspector. `POST /api/workflow/validate` returns structured problems; Validate toolbar button surfaces them.
**Done when:** client and server agree on validity for seeded good/bad workflows (pytest + Vitest).

#### Step 2.2 review status — 2026-08-04

- **Complete and strengthened.** Conditional visibility and required-field semantics now match on both sides. Client badges cover unsupported versions, malformed or unknown configuration fields, type/range/pattern/option/JSON/media violations, and required inputs; malformed validation envelopes correctly return HTTP 400 while graph-invalid drafts remain structured HTTP 200 results.
- Automated gate: backend and frontend validation regressions pass with the full suites and production build. Manual badge and conditional-field verification remains part of the Phase 2 visual gate.

### 2.3 Approved async option sources + media_asset widget
`options_source` identifiers resolved through a backend allowlist (e.g. `tts_voices` → existing voices endpoint; `story_tones`, `style_templates`; provider lists via existing provider registries). No schema-provided URLs are ever fetched. Add the `media_asset` inspector widget for Project Setup's logo: upload endpoint into `output/branding/` with type/size validation, thumbnail preview, and an upload-new / pick-existing chooser; never accept raw filesystem paths from the browser.
**Done when:** TTS voice, tone, style, and provider dropdowns populate live; a logo uploads, previews, persists in workflow JSON as a managed reference, and survives save/reload; a test proves unknown identifiers and disallowed file types are rejected.

### 2.4 Dirty state, draft autosave, leave protection
Debounced draft autosave (separate from explicit save), unsaved-change indicator, navigation warning, draft recovery on reopen.
**Done when:** killing the tab mid-edit loses nothing; explicit save clears dirty state.

### 2.5 Sample-data stubs — node types + auto-attach UX (no execution yet)
Capture/generate and validate the fixture inventory defined in 0.2 before building the UI; fixtures must be deterministic, sanitized, small, and independent of live providers. Add `stub.input` (Sample Input) and `stub.output` (Result Viewer) to the registry with dynamic `port_type` resolution in the compatibility matrix. Frontend: dropping a node with no connections auto-spawns one pre-connected Sample Input stub per required input and one Result Viewer on the principal output; half-height dashed rendering with "sample" badge; connecting a real edge to a stubbed input removes that stub (undoably); auto-attach toggle in workflow settings; manual attach via library "Testing" category and node context menu. Stub payloads editable in the inspector with per-port-type validation; file-backed types reference bundled fixtures only (never browser-supplied paths).
**Done when:** dropping a lone Segmenter shows editable stubs wired up; Vitest covers auto-attach, auto-detach-on-real-edge, undo, and payload validation; server-side validation accepts stub graphs. **Phase 2 gate.**

---

## Phase 3 — Core execution & observability

### 3.1 Service extraction (highest-risk step — pure moves only)
Extract the `_step_*` bodies from `studio/pipeline/routes.py` into importable service functions (e.g. `studio/pipeline/services.py` or per-module services), leaving routes as thin callers. **No behavior change**: same artifacts, same SSE events, same error paths.
**Done when:** existing pytest suite passes; a full run through the classic `/pipeline` UI produces identical artifacts (compare `pipeline.json` + outputs before/after).

### 3.2 Node adapters
`studio/workflows/adapters/` wrapping the extracted services (tts, timing, segmenter, scenes, storyboard, animator, captions, music, assemble via editor, export) plus the trivial `project.setup` adapter (validate + emit settings). Adapters translate node inputs/config → service args, and service results → typed outputs + artifact refs; consumers of `project_settings` apply the explicit-beats-inherited rule (own config overrides incoming defaults). Extend the FFmpeg export engine with the **logo-overlay pass** (position/size/opacity/margin from settings, correct across all export profiles — same pattern as the grain overlay). Never call Flask routes over HTTP in-process.
**Done when:** each adapter has a pytest exercising it against a fixture project (mock providers where needed); an export with logo enabled renders the watermark at the right position in 9:16, 16:9, and 1:1.

### 3.3 Deterministic scheduler + project locking
`studio/workflows/scheduler.py`: validated-DAG ready queue, reverse-dependency maps, multi-input wait, stable tie-breakers (saved order, then id), sequential v1 execution, disabled-node skip, per-project execution lock with atomic artifact promotion.
**Done when:** pytest covers ordering determinism, multi-input readiness (Assemble waits for all inputs), diamond graphs, disabled skip, and lock contention.

### 3.4 Execution records + redaction
`models.py` execution dataclasses; persist records (snapshot, per-node status/durations/attempts, resolved input summaries, artifact refs, structured logs/errors) via `persistence.py`; `redaction.py` scrubs secrets from everything persisted or emitted.
**Done when:** a run produces a complete record; a redaction test seeds a fake API key through config/logs/errors and proves it never appears in any persisted or emitted byte.

### 3.5 Run + stop endpoints, sequenced SSE
`POST /api/workflow/run` (id or validated snapshot; full-workflow, node+deps, and **node-in-isolation** modes first), `POST /api/workflow/executions/<id>/stop` (cooperative, reuses existing stop mechanisms), `GET .../events` streaming monotonically sequenced events via the `_emit` pattern. Each SSE message uses `id: <sequence>`; reconnect reads the standard `Last-Event-ID` header and replays later buffered events. Isolated mode: `stub.input` executes instantly returning its payload as a typed output; every downstream result produced from stub data is flagged `from_sample_data` in events and the persisted execution record.
**Done when:** pytest covers run→events→terminal-state, stop mid-run (a cancelled run never later reports success), isolated stub-fed execution, ordered replay after `Last-Event-ID`, and reset behavior when the requested event is older than the retained buffer; the client deduplicates by `sequence`.

### 3.6 Live canvas states + minimal bottom panel
Wire SSE to the store: status colors (idle/queued/running/waiting/succeeded/failed/cancelled/skipped/stale), animated running edges, post-run edge summaries, "from sample data" markers on stub-fed results, Stop button. Result Viewer stubs display their captured output summary (read-only at this phase). Bottom panel v1: current run's node list with status/duration/error; click a finished node → its output JSON. "Open in Timeline Editor" when an `editor_project` exists.
**Done when (Phase 3 gate):** the Full Video template runs end-to-end from the canvas, produces a project that opens in the timeline editor, and exports video through the existing FFmpeg engine.

---

## Phase 4 — Partial runs & resilience

### 4.1 Remaining run modes
Selected-nodes+deps, from-node-through-descendants, retry-failed, retry-failed+descendants. Scope calculation in `validation.py`/`scheduler.py`; toolbar + context-menu entries.
**Done when:** pytest covers subgraph scope for each mode on branch/diamond graphs; UI can run any mode.

### 4.2 Fingerprints, cache reuse, stale propagation
`cache.py`: canonical fingerprint (type+version, relevant config, upstream artifact fingerprints, adapter schema version). Reuse only on fingerprint match + artifacts exist + integrity check + prior success + no forced regen. Edge/config/upstream changes mark descendants stale (orange). Persist cache-hit/miss reasons.
**Done when:** re-running an unchanged workflow re-executes zero nodes; changing one upstream config re-executes exactly the affected subgraph (pytest-proven).
Also in this step: **Result Viewer pinning** — an edited viewer payload becomes a winning cache entry (validated against the port type) that feeds downstream nodes until unpinned, and editing it marks descendants stale; pinned state is visible on the stub card.

#### Step 4.2 review status — 2026-08-04

- **Complete.** Canonical node fingerprints include resolved defaults, typed inputs, topology-qualified upstream output/artifact fingerprints, type version, and adapter cache schema version. Persistent cache entries are workflow/project/node scoped, atomic, and contain only component hashes plus reusable outputs.
- Reuse fails closed for forced regeneration, prior failure/absence, configuration/input/upstream/schema changes, malformed entries, missing/empty/modified artifacts, non-JSON outputs, and sensitive outputs. Every decision is persisted on the node execution record, and cache misses caused by a prior result surface a transient stale state before execution.
- Frontend graph/config edits mark the affected node and descendants stale without treating cosmetic rename/move changes as computation changes. Result Viewers support typed, validated pinned payloads; the pin wins independently of upstream changes, feeds downstream nodes, persists in workflow JSON, and is visible on the card.
- Automated verification: 115 backend tests plus 38 subtests and 80 frontend tests pass; the production frontend build succeeds.

### 4.3 Retry policies + explicit error outputs
Per-node `on_error`: stop / bounded retry with delay/backoff / continue via explicit error output (control path) / skip-optional — only where capability flags permit. Structured failure payloads (stable code, user message, redacted details, attempt, recovery suggestion).
**Done when:** pytest covers each policy including backoff timing and error-branch routing.

#### Step 4.3 review status — 2026-08-04

- **Complete.** Nodes persist a capability-gated `on_error` policy for stop, bounded retry, explicit error-control routing, or optional skipping. Retry attempts use bounded exponential backoff, retain per-attempt diagnostics, and emit retry events without publishing staged artifacts from failed attempts.
- Failure records and events include node identity, stable code, user message, redacted details, attempt, timestamp, and recovery suggestion. Handled failures finish as `partial`; ordinary success paths never activate error branches.
- The generic inspector exposes only supported policies and retry bounds. Automated verification: 121 backend tests plus 38 subtests and 81 frontend tests pass; the production frontend build succeeds.

### 4.4 Run history + deep inspection UI
Bottom panel full version: execution list (`GET /api/workflow/executions?workflow_id=`), node timeline, per-node resolved inputs/outputs/logs/errors/attempts, cache decisions and stale reasons. Summaries by default, explicit expansion for large values.
**Done when (Phase 4 gate):** a failed run can be diagnosed and retried from the UI without rerunning successful nodes.

#### Step 4.4 review status — 2026-08-04

- **Complete.** The bottom panel loads newest-first persisted history for the active workflow, opens full execution records, and presents a duration-scaled node timeline with status, attempts, sample-data state, and per-node selection.
- Deep inspection shows bounded input/output/artifact summaries with explicit JSON expansion, structured current and per-attempt errors, recovery suggestions, logs, cache hit/miss decisions, and cache/stale reasons. Failed nodes expose retry-failed and retry-failed-plus-descendants actions; these use partial-run scope and preserve unaffected successful work.
- Automated verification: 121 backend tests plus 38 subtests and 84 frontend tests pass; the production frontend build succeeds. The in-app browser surface was unavailable, so the final interactive layout smoke check remains to be performed when that surface is available.

---

## Phase 5 — Power UX, utilities, expressions

### 5.1 Undo/redo command stack
Commands: add, move (drag coalesced into one command), delete, connect, disconnect, config change, disable, replace. Ctrl+Z / Ctrl+Shift+Z.
**Done when:** every canvas operation round-trips through undo/redo (Vitest on the command stack).

#### Step 5.1 review status â€” 2026-08-04

- **Complete.** The workflow store now has a bounded runtime-only command history for add, atomic multi-node move, delete, connect, disconnect, configuration, disable, and replace. Compound add-with-stubs and real-edge stub replacement operations undo and redo as single commands; new edits invalidate redo, and document loads clear history.
- The canvas exposes Undo/Redo controls and handles Ctrl+Z / Ctrl+Shift+Z outside editable fields. Tidy-up and group dragging each produce one move command.
- Automated verification: all 92 frontend tests pass, including dedicated round-trip command-stack coverage, and the production frontend build succeeds.

### 5.2 Clipboard, duplicate, replace, context menus
Copy/paste minimal workflow fragments (works across workflows), Ctrl+D duplicate, right-click context menus, "Replace with…" preserving position/name/compatible config/connections with warning for incompatible ones (undoable). Drop-connection-on-empty-canvas → compatible-filtered palette → auto-connect.
**Done when:** each operation has a test and is undoable.

#### Step 5.2 review status — 2026-08-04

- **Complete.** Selected nodes copy as versioned, document-independent workflow fragments with only internal edges; paste remaps node/edge IDs and supports positioning on another workflow. Ctrl+D duplicates a selected node or subgraph, including internal connections.
- Node, edge, and pane context menus expose copy, paste, duplicate, enable/disable, delete/disconnect, existing run/sample actions, and replacement. Replacement retains identity, name, position, shared configuration, and type-compatible connections, and confirms before removing incompatible connections.
- Dropping an unfinished connection on empty canvas opens a palette filtered to compatible ports and inserts plus connects the chosen node atomically. Clipboard, duplication, replacement (compatible and incompatible cases), and insert-and-connect all round-trip through undo/redo.
- Automated verification: all 98 frontend tests pass, including 6 focused step 5.2 domain/UI tests, and the production frontend build succeeds.

### 5.3 Notes, recently used, remaining templates
Sticky notes; recently-used section in the library; ship **Narration Only**, **Storyboard Only**, **Re-export Existing Project** templates (valid and typed).
**Done when:** all templates validate and run.

#### Step 5.3 review status — 2026-08-04

- **Complete.** Sticky notes are editable, colorable, draggable, persisted in workflow extensions, and covered by undo/redo without entering the execution DAG. The node library keeps a bounded local recently-used section based on actual palette/insert usage.
- Narration Only, Storyboard Only, and Re-export Existing Project are versioned, typed built-ins. All four built-in templates pass authoritative validation and execute successfully through the deterministic scheduler with adapter boundaries mocked.
- Automated verification: 121 backend tests plus 38 subtests and 101 frontend tests pass; the production frontend build succeeds.

### 5.4 Utility nodes (semantics first)
Merge, Condition, Set Value, Wait — define ports, skip/join behavior, and scheduler semantics in `contracts.md` first, then implement with pytest coverage. Story Generator node wrapping `studio/story`.
**Done when:** a branched workflow (Condition → two paths → Merge) executes correctly, including skip propagation.

#### Step 5.4 review status — 2026-08-04

- **Complete.** Utility ports and runtime semantics are frozen in `contracts.md`. Condition
  emits exactly one value branch, ordinary inactive descendants propagate `skipped`, and Merge
  is the explicit skip-tolerant join that consumes active inputs in saved-edge order after all
  predecessors resolve. Set Value, cooperative/cancellable Wait, and array/first/object Merge
  modes are registered and executable through the generic workflow UI.
- Story Generator wraps an importable `studio.story` service, reusing its prompts, webhook,
  parser, artifact persistence, and diversity history while emitting the existing `script` type.
- Automated verification: 129 backend tests plus 38 subtests and 102 frontend tests pass; the
  production frontend build succeeds. Focused tests execute both Condition outcomes through two
  paths into Merge and verify skip propagation, utility edge cases, integer timing validation,
  cancellation, and the Story Generator adapter boundary.

### 5.5 Expressions & data mapping (deferred scope, last)
`expressions.py`: deliberately small parser for `{{ nodes.x.outputs.y }}`, `{{ workflow.project_id }}`, `{{ variables.* }}` — no eval, upstream-only references, typed value preservation, sandbox tests (no env/secrets/attribute/filesystem access). Visual upstream-output picker in the inspector; pre-execution expression validation.
**Done when:** expression-driven config runs correctly and the sandbox test suite passes.

#### Step 5.5 review status — 2026-08-04

- **Complete.** Whole-value expressions support typed upstream outputs, the immutable execution
  project ID, and nested workflow variables through a fixed non-evaluating grammar. Static
  validation enforces real non-control output ports, strict graph ancestry, and selected-run scope;
  resolved values are schema-validated before fingerprinting and adapter execution.
- The inspector provides workflow-variable JSON editing and a visual picker containing only data
  outputs from graph ancestors. Expression mode works for every schema widget without coercing
  referenced arrays, objects, numbers, or booleans to strings.
- Sandbox coverage rejects interpolation, operators, calls, environment/secret roots, arbitrary
  attributes, and filesystem access. Automated verification: 140 backend tests plus 38 subtests
  and 105 frontend tests pass; the production frontend build succeeds. The in-app browser surface
  was unavailable, so the Phase 5 interactive expression-picker smoke check remains outstanding.

### Final gate — Definition of Done
Walk the 14-point Definition of Done checklist in [proposition-final.md](proposition-final.md) in the running app; fix anything that fails; record the results. Only then is the upgrade complete.

---

## Phase 6 — Hardening & production readiness

The feature is built; this phase makes it safe under real conditions. Sources: the outstanding
findings from the 2026-08-04 adversarial review that Phases 3–5 did not absorb, plus the two
surfaces no automation has ever touched (live providers, legacy-UI relationship).

### 6.1 Live-provider verification
Every suite runs on fixtures; run the full pipeline template through the workflow runner against
the real providers (TTS, alignment, storyboard, animator, export). Fix what breaks. Capture
provider quirks as tests marked `@pytest.mark.live`, skipped unless `STS_LIVE=1` is set, so the
orchestrator's fixture-based validation stays green and deterministic.
**Done when:** one full live run from script to playable export succeeds through the workflow runner, and the live-marked tests document each provider's verified behavior.

#### Step 6.1 review status — 2026-08-05

- **Complete (one provider externally blocked).** A full live run — script → Kokoro TTS →
  stable-whisper alignment → segmenter → scene blueprint (n8n + OpenRouter LLM) → Kie AI
  assets → captions → music → assemble → timeline → FFmpeg export — succeeded through
  `ExecutionManager`/`WorkflowScheduler` and produced a playable 1080×1920 mp4 with video and
  audio streams (ffprobe-verified). `tests/test_live_providers.py` (marker `live`, registered
  in the new `pytest.ini`, gated on `STS_LIVE=1`) documents each provider's verified behavior:
  9 passed, 1 documented skip.
- Live infrastructure findings: the hosted Railway n8n no longer serves the scene-blueprint
  webhook (workflow inactive, API key revoked) and the OpenRouter balance is negative, which
  rejects paid models with HTTP 402 while free models still complete. Live verification now
  self-hosts n8n from the repo's own workflow export with a pinned free model
  (`_dev/loop-engineering/live-verification/setup_local_n8n.py`; procedure in that folder's
  README). The WaveSpeed key is rejected upstream on every model (HTTP 401 "Invalid API key"),
  so the storyboard branch is removed from the live document and its test skips with the
  reason recorded until a valid key is configured (`STS_LIVE_STORYBOARD=1` restores it);
  grok_automa remains non-automatable by design (human-driven browser).
- Product fixes from live breakage, each with a fixture regression in
  `tests/test_workflow_adapters.py`: empty node-config values no longer mask inherited
  project settings (`inherited_config` — the template's Project Setup tone was silently
  discarded by the music/scenes empty schema defaults, failing runs with `MUSIC_NOT_FOUND`);
  storyboard and animator adapters now fail with `STORYBOARD_FAILED`/`ANIMATOR_FAILED` when
  every scene errors instead of reporting success with zero assets.
- Automated verification: 143 backend tests plus 38 subtests pass with the live suite
  correctly skipped when `STS_LIVE` is unset; no frontend code changed in this step.

### 6.2 Persistence hardening
`persistence.py`: atomic trash move with no `.bak` resurrection path, single-writer file locking
around read-modify-write cycles, monotonic `updated_at` so optimistic concurrency cannot alias
within the same millisecond, and a delete path that works on a stored workflow that no longer
parses or validates.
**Done when:** a concurrency test with two interleaved writers corrupts nothing and loses neither write's conflict signal, and a hand-corrupted workflow file can be trashed via the API.

#### Step 6.2 review status — 2026-08-05

- **Complete.** `persistence.py` now serializes every read-modify-write cycle (update, delete)
  behind a per-workflow single-writer lock: an in-process per-path `threading.Lock` for app
  threads plus a blocking exclusive OS lock (`msvcrt.locking`/`fcntl.flock`) on a `.json.lock`
  sidecar for cross-process safety. An instrumented two-writer test proves the critical section
  never overlaps, exactly one writer wins, the loser receives `WorkflowConflict`, and the stored
  document still parses and validates.
- `updated_at` is strictly monotonic: when the clock has not advanced past the stored value, the
  new stamp is the previous timestamp plus one microsecond, so optimistic-concurrency tokens can
  never alias within the same instant (frozen-clock test covers two same-instant updates).
- The trash move is resurrection-proof: the `.bak` rotates into trash **before** the primary
  (an interruption leaves the primary intact instead of a resurrecting backup), moves use
  atomic `os.replace` with a cross-volume fallback, destination names are collision-guarded,
  and no `{id}.json*` remnant stays in `output/workflows/` after deletion.
- Delete no longer routes through `load_workflow`: the conflict check reads `updated_at`
  directly from the primary file without the `.bak` restore side effect and is skipped when the
  file no longer parses, so a hand-corrupted workflow (and its backup) can be trashed via
  `DELETE /api/workflows/<id>` — verified end-to-end through the Flask test client, including
  the post-delete 404 that proves no backup resurrection.
- Automated verification: 148 backend tests plus 38 subtests pass (10 gated live tests skipped);
  no frontend code changed in this step.

### 6.3 Request hardening
Enforce body-size limits that chunked transfer encoding cannot bypass; validate submitted
`options_source` values server-side against the allowlisted resolvers; cap branding upload size
and count. All rejections use the standard error envelope.
**Done when:** pytest proves an oversized chunked request, an invalid option value, and an oversized upload are each rejected with the envelope and correct status code.

#### Step 6.3 review status — 2026-08-05

- **Complete.** JSON endpoints now read the body through a bounded stream read
  (2 MiB + 1 byte) instead of trusting the `Content-Length` header, so a chunked request
  (terminated stream, no declared length) is rejected `413 REQUEST_TOO_LARGE` with the standard
  envelope; non-empty bodies still require a JSON content type, preserving the CORS-preflight
  requirement for cross-origin callers. The DELETE route was moved onto the same bounded reader.
- Submitted values for `options_source` config fields are validated server-side against the
  allowlisted resolver's current values (`allowed_option_values` in `options.py`, process-lifetime
  cached). A bad value fails a save with the `422 WORKFLOW_INVALID` envelope naming the exact
  config path; an unavailable resolver fails open so a missing provider never blocks saving,
  and non-string values are rejected rather than crashing set membership.
- Branding uploads cap the whole multipart request at 6 MiB via per-request
  `max_content_length` — Werkzeug enforces it while reading the stream, chunked included, and a
  blueprint `RequestEntityTooLarge` handler converts the failure to the `413` envelope with no
  file written. The library itself is capped at 50 stored logos (`409 LIMIT_EXCEEDED`), counted
  by allowed extension before any multipart parsing.
- Automated verification: `tests/test_workflow_request_hardening.py` proves the oversized
  chunked JSON request, oversized chunked and declared multipart uploads, invalid/valid/
  non-string option values, fail-open resolver behavior, and the count cap — each rejection
  asserting the envelope and status code. Full backend run: 160 passed, 38 subtests,
  10 gated live tests skipped; no frontend code changed in this step.

### 6.4 Client error-truth
Parse the `{error:{code,message}}` envelope on every remaining API call in the workflow store
(save/load/list/import paths), block Save with a visible reason while any JSON widget holds
invalid text, and fix the number-widget DOM desync so the displayed value always matches state.
**Done when:** Vitest covers envelope surfacing for each store API path, and Save is disabled with a visible reason while any field is invalid.

#### Step 6.4 review status — 2026-08-05

- **Complete.** The shared API client now parses the standard `{error:{code,message}}`
  envelope on every non-OK response, throwing errors that carry the backend's message,
  stable code, HTTP status, and optional details instead of a raw
  `METHOD path → status: body` string. Every workflow-store API path — node-types, open,
  save (create and update), save-as, import, workflow list, templates, run, stop,
  execution refresh, and run history — surfaces that envelope through its store error ref
  as `message [CODE]`, including the two list paths that previously threw with no
  handling at all.
- Save is truthfully blocked while any JSON widget holds unparseable text: JSON config
  fields and the workflow-variables editor register with a store-level invalid-field
  registry (`saveBlockedReason`), the toolbar disables Save/Save As/Duplicate with the
  reason visible as a red toolbar alert naming the node and field, and
  `saveWorkflow`/`saveAs` themselves refuse (without an API call) so the block holds even
  outside the button. Blocks release when the text is fixed, the field is hidden or
  unmounted, the node is deselected, or a new document loads — matching where invalid
  text can actually live.
- The number widget's DOM can no longer desync from state: clamped input that lands on
  the unchanged stored value, cleared input, and unparseable input all force the input
  element back to the value actually kept, and updates are emitted only when the value
  really changes.
- Automated verification: 26 new Vitest cases (client envelope parsing, all 12 store
  surfacing paths, save gating at store/widget/inspector/page level, number-widget sync)
  bring the frontend suite to 131 passed across 16 files; the production build succeeds.
  No backend code changed in this step.

### 6.5 Legacy UI bridge
The canvas becomes the default landing surface. Legacy step pages stay reachable behind explicit
navigation, with cross-links both ways for the same project; routes that no surface links to
anymore are removed. No behavior changes inside the legacy pages themselves.
**Done when:** opening the app lands on the workflow builder, each surface links to the other, and no dead routes remain.

#### Step 6.5 review status — 2026-08-05

- **Complete.** The root route now redirects to `/workflow`, so opening the app lands on the
  workflow canvas; the sidebar lists the Workflow Builder as the primary surface with the
  legacy pipeline dashboard explicitly below it ("Legacy Pipeline Dashboard").
- Cross-links run both ways: the workflow toolbar gains a "Legacy → Pipeline" link to the
  step-by-step dashboard, and the legacy pipeline header (now badged "Legacy") gains an
  "Open Workflow Builder" link. Project-scoped bridging already existed and is preserved —
  the execution panel's "Open in Timeline Editor" carries `?project=` into the legacy editor,
  and legacy pages keep their own `?project=` hand-offs. No behavior inside legacy pages
  changed; both additions are pure hash-history navigation links.
- Dead-route removal: the `/timing` → `/alignment` alias redirect, which no surface linked to,
  is deleted; a route test asserts every remaining route is either the root redirect or a
  surface-linked page.
- Automated verification: 4 new Vitest cases (default-landing redirect, legacy pipeline
  reachability, no-dead-routes allowlist, workflow-toolbar legacy link) bring the frontend
  suite to 135 passed across 18 files; the production build succeeds. No backend code changed
  in this step.

### 6.6 Docs and onboarding
A user guide for building, validating, and running workflows (including sample-data stubs, run
modes, and draft recovery), plus a node reference generated from the backend registry so it
cannot drift from the code.
**Done when:** a newcomer can build and run the pipeline template using only the docs, and the node reference is generated, not hand-written.

#### Step 6.6 review status — 2026-08-05

- **Complete.** `docs/workflow-guide.md` provides a newcomer path from setup through the
  built-in Full Video template, node configuration, server validation, saving, full and
  partial run modes, sample-data stubs, cache/staleness diagnostics, retries, import/export,
  and browser draft recovery. The root README links directly to both workflow documents and
  its Windows quick start now names the existing `start-prod.bat` launcher.
- `studio.workflows.docs` generates `docs/workflow-nodes.md` from the presentation-safe
  backend registry and validated built-in templates. The reference covers every registry
  port type, category, node type/version, capability, input/output port, configuration field,
  constraint, default, and template; its generated-file header documents the regeneration
  command and source of truth.
- Automated drift protection compares the committed reference byte-for-byte with fresh
  generator output, exercises `--check`, checks registry coverage and internal-field
  redaction, verifies the required guide topics, and keeps the README entry point covered.
  Verification: 9 documentation tests passed (23 subtests); the full project suite passed
  with 169 tests and 61 subtests (10 live-provider tests skipped).

---

## Phase 7 — Triggers & automation

Until now every run is a human clicking Run. This phase makes workflows fire themselves:
scheduled, file-driven, and webhook-driven runs, serialized through a queue, with notifications.

### 7.1 Run queue
Queue model persisted next to executions: pending/running/done/failed/cancelled, source
(manual/schedule/watch/webhook), requested run mode. Triggered runs enqueue; the existing
project lock drains the queue one run per project at a time. Queue panel in the bottom UI
with cancel-pending.
**Done when:** two runs triggered for the same project serialize (pytest-proven) while runs for different projects do not block each other, and pending runs can be cancelled from the UI.

#### Step 7.1 review status — 2026-08-05

- **Complete.** Every accepted run now creates an atomic queue record under
  `output/workflows/queue/`, keyed by its execution ID, with the requested mode, target nodes,
  project, source (`manual`, `schedule`, `watch`, or `webhook`), timestamps, and the persisted
  `pending` → `running` → `done|failed|cancelled` lifecycle. Execution records and SSE streams
  retain their existing IDs and envelopes.
- Dispatch uses one FIFO worker per project. Runs for the same project therefore enter the
  existing project lock one at a time, while different projects have independent workers and can
  execute concurrently. Pending cancellation atomically updates both queue and execution records,
  emits a terminal SSE event, and guarantees the cancelled request is skipped by its worker.
- `GET /api/workflow/queue` serves the persisted queue for a workflow and
  `POST /api/workflow/queue/<execution_id>/cancel` rejects anything except a pending run. The
  bottom Runs & diagnostics UI now includes a queue strip with source/mode/status and a Cancel
  action for pending items; the Pinia store refreshes it on load, manual refresh, enqueue, and
  terminal events.
- Automated verification: the full backend suite passes with 173 tests and 61 subtests
  (10 live-provider tests skipped); the full frontend suite passes with 137 tests across 18 files;
  the production frontend build succeeds. Dedicated queue tests prove same-project serialization,
  cross-project overlap, persistence, source/mode capture, endpoint behavior, and pending
  cancellation that never executes.

### 7.2 Scheduled runs
Per-workflow cron-style schedules (persisted in workflow `settings`), a scheduler tick service
started with the app, enable/disable per schedule, next-fire display in the UI. Missed fires
while the app was closed run at most once on startup (catch-up policy: latest only).
**Done when:** an accelerated-clock pytest proves a schedule enqueues exactly one run at the right time, catch-up fires at most once, and disabled schedules never fire.

#### Step 7.2 review status â€” 2026-08-05

- **Complete.** Workflows persist up to 16 independently enabled five-field UTC cron schedules
  in `settings.schedules`; server validation rejects malformed expressions, duplicate/invalid
  schedule IDs, unknown fields, and invalid enable flags.
- The app starts a daemon tick service alongside the Flask server. Runtime cursors live under
  `output/workflows/schedule-state/`, separate from workflow definitions, so ticks do not disturb
  optimistic edit tokens. Each cursor advances before queue dispatch, scheduled executions use
  the Phase 7.1 queue with `source: schedule`, and startup catch-up selects only the latest missed
  fire. Disabled intervals advance the cursor without firing and are never replayed on re-enable.
- The workflow toolbar now opens Scheduled runs settings with add/remove and per-schedule enable
  controls, UTC cron editing, catch-up policy guidance, and a server-computed next-fire display.
  Unsaved schedule edits explicitly ask the user to save before recalculating.
- Automated verification: the full backend suite passes with 176 tests and 61 subtests
  (10 live-provider tests skipped); the frontend suite and production build pass. Dedicated
  accelerated-clock tests prove exact-time enqueueing, tick idempotence, latest-only catch-up,
  disabled behavior, cron validation, and next-fire metadata.

### 7.3 Watch-folder trigger
A workflow can watch a configured folder for files matching a pattern; a stable-size debounce
avoids half-written files; the file feeds the script input (or a configured port) of the run.
Processed files move to a `processed/` subfolder to prevent re-triggering.
**Done when:** dropping a file into a watched tmp folder triggers exactly one queued run carrying the file's content, half-written files do not trigger, and processed files never re-trigger (pytest with tmp dirs).

#### Step 7.3 review status — 2026-08-05

- **Complete.** Each workflow can persist one enabled watch folder with an absolute path,
  filename glob, and optional text/script input-port destination. With no explicit port, file
  content replaces the enabled Script Input value in the execution snapshot without changing the
  saved workflow.
- A daemon polling service starts with the app. It requires an unchanged size and modification
  timestamp for at least one second, accepts bounded UTF-8 text, atomically claims stable matches,
  queues them with `source: watch`, and moves successful claims into `processed/`. Failed enqueue
  attempts restore the source file for a later retry; processed files are outside the scan root.
- The workflow toolbar now opens Watch folder settings for enablement, absolute folder path,
  filename pattern, and compatible port selection. Server validation rejects malformed settings,
  missing targets, and non-text destinations.
- Automated verification: the backend suite passes with 179 tests and 61 subtests (10 live-provider
  tests skipped); the frontend suite passes with 139 tests across 20 files; the production build
  succeeds. Dedicated tmp-directory tests prove stable-write debounce, exactly-once queueing,
  content injection, pattern/disable behavior, and processed-file isolation.

### 7.4 Webhook trigger
Loopback-only `POST /api/workflow/hooks/<workflow_id>/<token>` starts a queued run; per-workflow
random token, regenerable in the UI; JSON payload validated and mapped to declared typed inputs.
Invalid token or payload rejected with the standard error envelope.
**Done when:** a valid POST enqueues a run with the mapped payload, invalid token/payload/oversize are rejected with the envelope, and the endpoint refuses non-loopback binds.

#### Step 7.4 review status — 2026-08-05

- **Complete.** Saved workflows can enable a webhook and declare up to 32 required/optional dotted
  JSON payload paths mapped to unique, enabled data-input ports. Payload values are validated by
  their resolved static or dynamic port type before they become scheduler input overrides, and
  accepted requests enter the Phase 7.1 queue with `source: webhook`.
- Each workflow gets a cryptographically random URL-safe token under separate private runtime state
  (`output/workflows/hook-tokens/`), keeping credentials out of workflow exports and execution
  snapshots. The settings dialog reveals and copies the loopback URL and regenerates its token with
  immediate invalidation of the previous URL; token responses are marked `Cache-Control: no-store`.
- The hook accepts JSON objects up to 64 KiB, compares tokens in constant time, uses the standard
  error envelope for missing/disabled hooks and invalid typed payloads, rejects non-loopback clients,
  and refuses all requests whenever `STS_BIND_HOST` is not loopback-only.
- Automated verification: the backend suite passes with 184 tests and 61 subtests (10 live-provider
  tests skipped); the frontend suite passes with 141 tests across 21 files; the production build
  succeeds. Dedicated tests cover valid typed mapping and queue source, required/invalid payloads,
  oversize rejection, token rotation, workflow validation, remote clients, and exposed server binds.

### 7.5 Run notifications
Per-workflow notification settings: on completion/failure, emit a Windows toast and append to a
persisted notification log surfaced in the UI (badge + list). Outbound webhook notification as
an optional channel.
**Done when:** failed and successful runs each produce the configured notification record (pytest), and the UI shows unseen-notification state.

#### Step 7.5 review status — 2026-08-05

- **Complete.** Per-workflow settings independently enable completion and failure records, Windows
  toast delivery, and an optional outbound HTTP(S) webhook. Terminal dispatch is idempotent per
  execution and channel failures remain delivery metadata instead of changing workflow results.
- Records persist under `output/workflows/notifications/`; local-only list and acknowledge APIs
  expose total and unseen counts. The workflow toolbar now shows an unseen badge, and its notification
  center combines channel settings with the persisted success/failure history.
- Automated verification: the backend suite passes with 188 tests and 61 subtests (10 live-provider
  tests skipped); the frontend suite passes with 142 tests across 22 files; the production build
  succeeds. Dedicated tests cover success/failure records, idempotent channel delivery, bounded
  webhook payloads, unseen acknowledgement, settings validation, and notification-center behavior.

---

## Phase 8 — Node developer kit

Turns the builder from a feature into a platform: creating a node becomes one command plus a guide.

### 8.1 Node scaffolder
`python -m studio.workflows.scaffold <node_key>` generates a registry entry, adapter skeleton,
config schema stub, and a passing test file, wired into the palette on next start. Refuses
existing keys and invalid port types.
**Done when:** running the scaffolder for a demo node yields a palette-visible, configurable, executable node whose generated tests pass unmodified.

#### Step 8.1 review status — 2026-08-05

- **Complete.** `python -m studio.workflows.scaffold <node_key>` creates a source-controlled JSON
  registry entry, editable adapter skeleton, JSON config-field stub, and node-specific smoke tests.
  Repeatable `--input ID:TYPE` and `--output ID:TYPE` options use the registry's frozen port
  vocabulary; invalid port types, reserved/duplicate port IDs, existing node keys, and existing
  target files are refused without overwriting them.
- Generated definitions are discovered when the workflow registry imports, so the existing
  node-types endpoint exposes them to the palette on the next application start and the scheduler
  resolves their generated adapter normally. Built-in registry contract tests now require the core
  catalog as a subset so developer nodes can extend it without weakening per-node validation.
- End-to-end verification scaffolded `scaffold_check.echo` through the real CLI: the node was
  registry-visible, configurable, executable, and both generated tests passed unchanged. The
  temporary demo files were then removed. The focused suite passes with 17 tests; the complete
  workflow backend suite passes with 172 tests and 59 subtests.

### 8.2 Dev hot-reload
Behind a dev-mode flag: registry and adapter modules reload on file change without restarting
Flask; the frontend refetches node-types on a reload signal. Never active in normal runs.
**Done when:** with the flag on, editing a node definition updates the palette without a server restart; with the flag off, nothing watches or reloads (tests cover the guard).

### 8.3 type_version migrations
Nodes declare config migrations between `type_version`s; documents upgrade on load with a
recorded migration trail; unknown future versions load read-only with a warning instead of
crashing.
**Done when:** a stored workflow with an old node version opens upgraded and re-saves at the new version (pytest covers a two-hop migration chain), and a future-version document is view-only with a visible warning.

### 8.4 Node-author guide
A written guide (docs/ or in-app) walking scaffold → schema → adapter → test → ship, generated
partly from `contracts.md` and the registry so port types and rules cannot drift. Validated by
building one real node following only the guide.
**Done when:** the demo node from 8.1 is rebuilt following only the guide, and the guide's port/type tables are generated from the registry.

---

## Phase 9 — Scale & asset lifecycle

New node types and automated triggers will multiply workflows, runs, and artifacts; this phase
keeps execution fast and disk usage bounded.

### 9.1 Parallel branch execution
The scheduler runs independent DAG branches concurrently under a bounded worker pool while
keeping SSE event ordering deterministic per node and the run-level record consistent.
Per-node concurrency opt-out for adapters that are not thread-safe (Kokoro singleton et al.).
**Done when:** a diamond workflow executes both branches concurrently (measured overlap in pytest), results and event streams are deterministic, and opted-out adapters never overlap.

### 9.2 Concurrent runs across projects
Multiple runs for different projects execute simultaneously; the same project still serializes
through the Phase 7 queue. Run history and SSE streams stay correctly scoped per execution.
**Done when:** pytest proves two projects run at the same time without cross-talk in events, records, or artifacts, and same-project runs still serialize.

### 9.3 Asset garbage collection
An orphan scan lists artifacts under `output/` referenced by no execution record or pinned
payload; a GC command (UI + CLI) deletes only listed orphans, with a dry-run default and a
protected-paths allowlist.
**Done when:** GC removes seeded orphans and provably never touches referenced or pinned artifacts (pytest builds both cases), and dry-run reports without deleting.

### 9.4 Project archive & restore
Export a project (workflow, executions, referenced artifacts, branding) as one archive file;
restore recreates it under a new or original ID with references rewritten. Used for backup and
machine moves.
**Done when:** archive → delete → restore round-trips a fixture project with byte-identical referenced artifacts and a workflow that validates and runs.

### 9.5 Large-canvas performance
Profile and fix canvas behavior at 150+ nodes: memoized node cards, viewport-culled rendering
if needed, debounced persistence, and a generated large-workflow fixture for regression use.
**Done when:** the 150-node fixture loads, pans, and drags without dropped-frame stalls (documented measurement), and interaction tests on the fixture pass.

---

## Phase 10 — Distribution & assistant

The app stops depending on a terminal and a memory of `python main.py`; a copilot drafts
workflows from prompts.

### 10.1 Desktop launcher
A single entry point that starts the backend, waits for health, opens the app window (browser
or lightweight shell), adds a tray icon with open/restart/quit, and handles port-in-use
gracefully.
**Done when:** double-clicking the launcher on a clean boot yields the running app with no console window, and quit from the tray stops the backend cleanly.

### 10.2 Versioned release build
A build script that produces a versioned, reproducible release folder/installer: frontend
production build, pinned dependencies, version stamp surfaced in the UI, and a changelog entry
gate.
**Done when:** one command emits a versioned artifact from a clean checkout, and the running app displays that version.

### 10.3 Backup & restore of all state
One command/UI action exports all workflows, settings, schedules, and (optionally) projects to
a single backup file; restore brings a fresh install to the same state. Builds on 9.4.
**Done when:** backup → fresh install → restore round-trips the full app state and every workflow validates afterward.

### 10.4 Workflow copilot
Prompt → draft workflow: an assistant panel that sends the registry (declarative node/port
contracts) plus the user's goal to a configured LLM, receives a workflow document, runs
authoritative validation, and only offers valid results for insertion — never silent apply.
**Done when:** a natural-language prompt yields a workflow that passes server validation and appears on the canvas only after explicit user acceptance; invalid generations surface their validation errors instead of applying.

---

## Step count & sequencing summary

| Phase | Steps | Parallelizable? |
|---|---|---|
| 0 — Audit & contracts | 0.1–0.4 (4) | 0.3 can run alongside 0.1/0.2 |
| 1 — Canvas & persistence MVP | 1.1–1.7 (7) | 1.2 alongside 1.1/1.3 |
| 2 — Config & validation | 2.1–2.5 (5) | sequential; 2.5 after 2.1 |
| 3 — Execution | 3.1–3.6 (6) | 3.1 must land alone; 3.3/3.4 parallel after 3.2 |
| 4 — Partial runs & resilience | 4.1–4.4 (4) | 4.3 parallel with 4.2 |
| 5 — Power UX & expressions | 5.1–5.5 (5) | 5.1–5.3 parallelizable |
| 6 — Hardening & production readiness | 6.1–6.6 (6) | 6.2/6.3/6.4 parallelizable; 6.1 first (may reveal new work); 6.5/6.6 last |
| 7 — Triggers & automation | 7.1–7.5 (5) | 7.1 (queue) must land first; 7.2/7.3/7.4 parallel after it |
| 8 — Node developer kit | 8.1–8.4 (4) | 8.2/8.3 parallel after 8.1; 8.4 last |
| 9 — Scale & asset lifecycle | 9.1–9.5 (5) | 9.1 must land alone (scheduler change); 9.3/9.4/9.5 parallelizable |
| 10 — Distribution & assistant | 10.1–10.4 (4) | 10.1/10.2 first; 10.3 builds on 9.4; 10.4 independent |

55 steps total (31 original + 6 hardening + 18 roadmap). Phases 7–10 ordering logic: automation
(7) multiplies the value of existing workflows; the developer kit (8) creates the node variety
that surfaces the scale problems (9) fixes; distribution (10) wants a stable feature set last. The critical path is 0.1 → 0.2 → 0.4 → 1.2 → 1.6 → 3.1 → 3.2 → 3.3 → 3.5 → 3.6; everything else hangs off it. The two steps to treat with the most care are **3.1** (extracting step functions from the 2,400-line `routes.py` without behavior change) and **4.2** (cache correctness — wrong reuse silently corrupts projects).
