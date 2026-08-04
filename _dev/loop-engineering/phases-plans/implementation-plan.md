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

### 4.4 Run history + deep inspection UI
Bottom panel full version: execution list (`GET /api/workflow/executions?workflow_id=`), node timeline, per-node resolved inputs/outputs/logs/errors/attempts, cache decisions and stale reasons. Summaries by default, explicit expansion for large values.
**Done when (Phase 4 gate):** a failed run can be diagnosed and retried from the UI without rerunning successful nodes.

---

## Phase 5 — Power UX, utilities, expressions

### 5.1 Undo/redo command stack
Commands: add, move (drag coalesced into one command), delete, connect, disconnect, config change, disable, replace. Ctrl+Z / Ctrl+Shift+Z.
**Done when:** every canvas operation round-trips through undo/redo (Vitest on the command stack).

### 5.2 Clipboard, duplicate, replace, context menus
Copy/paste minimal workflow fragments (works across workflows), Ctrl+D duplicate, right-click context menus, "Replace with…" preserving position/name/compatible config/connections with warning for incompatible ones (undoable). Drop-connection-on-empty-canvas → compatible-filtered palette → auto-connect.
**Done when:** each operation has a test and is undoable.

### 5.3 Notes, recently used, remaining templates
Sticky notes; recently-used section in the library; ship **Narration Only**, **Storyboard Only**, **Re-export Existing Project** templates (valid and typed).
**Done when:** all templates validate and run.

### 5.4 Utility nodes (semantics first)
Merge, Condition, Set Value, Wait — define ports, skip/join behavior, and scheduler semantics in `contracts.md` first, then implement with pytest coverage. Story Generator node wrapping `studio/story`.
**Done when:** a branched workflow (Condition → two paths → Merge) executes correctly, including skip propagation.

### 5.5 Expressions & data mapping (deferred scope, last)
`expressions.py`: deliberately small parser for `{{ nodes.x.outputs.y }}`, `{{ workflow.project_id }}`, `{{ variables.* }}` — no eval, upstream-only references, typed value preservation, sandbox tests (no env/secrets/attribute/filesystem access). Visual upstream-output picker in the inspector; pre-execution expression validation.
**Done when:** expression-driven config runs correctly and the sandbox test suite passes.

### Final gate — Definition of Done
Walk the 14-point Definition of Done checklist in [proposition-final.md](proposition-final.md) in the running app; fix anything that fails; record the results. Only then is the upgrade complete.

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

31 steps total. The critical path is 0.1 → 0.2 → 0.4 → 1.2 → 1.6 → 3.1 → 3.2 → 3.3 → 3.5 → 3.6; everything else hangs off it. The two steps to treat with the most care are **3.1** (extracting step functions from the 2,400-line `routes.py` without behavior change) and **4.2** (cache correctness — wrong reuse silently corrupts projects).
