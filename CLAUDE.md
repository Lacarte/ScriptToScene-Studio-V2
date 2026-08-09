# ScriptToScene Studio V2 — agent guide

Local-first AI video production app: a script or story idea becomes a narrated,
storyboarded, captioned, exported short-form video. Python/Flask backend, Vue 3 +
Vite + Pinia frontend, FFmpeg for media.

## Verification commands (read this first)

**`python` and `pytest` are NOT on PATH on this machine.** Bare `python` resolves to a
non-existent interpreter. Always use the venv:

```bash
venv/Scripts/python.exe -m pytest tests/ -q     # backend, from repo root
cd frontend && npm run test                     # vitest
cd frontend && npm run build                    # production build (writes ../static/dist)
venv/Scripts/python.exe -m studio.workflows.docs --check   # generated-doc drift gate
```

All four must be green before committing. `npm run build` regenerates `static/dist/`,
which is gitignored — it will not dirty the tree.

Run the app with `start-dev.bat` (dev, enables `STS_WORKFLOW_DEV_RELOAD`) or
`start-prod.bat`. Backend boots from `app.py`, binding loopback-only by default and taking the
first free port from 5050 upward — so check the startup line before assuming the port. Health
check is `GET /api/health` (`app.py:158`).

## Layout

```
app.py                     Flask entry; registers ~15 blueprints, inits provider registries (L90-95)
config.py                  env/.env loading (webhook URLs, API keys)
settings/settings.json     canonical provider settings + selected provider per domain
app-config.json            frontend preference blob (separate store — see Known traps)
studio/                    backend packages, one per capability
  workflows/               the visual workflow builder (registry, scheduler, adapters, persistence)
  shared/providers_common/ provider registry, manifests, settings, discovery, health
  tts/ storyboard/ animator/ story/ build_scene_blueprints/ music/ captions/ editor/ pipeline/
frontend/src/
  features/<name>/         feature folders: views/, components/, stores/, composables/, __tests__/
  shared/                  api client, composables, data
tests/                     pytest, one file per subsystem
_dev/loop-engineering/     plan-driven orchestrator (see below)
output/                    generated projects, workflows, executions, artifacts, TRASH
```

## Core architecture

**The backend registry is authoritative.** `studio/workflows/registry.py` holds every node
type — ports, `config_schema`, capabilities, `type_version`, and an `executor` string. The
frontend renders entirely from `GET /api/workflow/node-types`; it hardcodes nothing except
SVG icon paths (`NodeIcon.vue`) and port colors (`constants.js`). Adding a node type means
editing the registry or dropping a JSON file in `studio/workflows/node_definitions/` — never
editing Vue components.

**Adapters are the executor contract.** Every node executor is
`(inputs, config, context) -> outputs`, resolved from a dotted `module:function` string.
Helpers live in `studio/workflows/adapters/common.py`: `AdapterError(code, message, details)`,
`AdapterContext`, `inherited_config()` (explicit config beats inherited project settings),
`artifact_ref()`, and `outputs(**ports)` which prepends the control port.

**Providers are being generalized.** `studio/shared/providers_common/` supplies discovery,
manifests, settings, and health for `tts`, `storyboard`, and `animator` only. Phases 10–16 of
the plan extend this to all seven AI domains. See the traps below before touching it.

**Wrap, don't rewrite.** TTS, alignment, segmentation, scene generation, storyboard, animator,
captions, music, editor, and export logic all work. Put thin adapters around them.

## Conventions

- Atomic JSON writes via `safe_json_write` (`studio/io_utils.py`) — never bare `open().write()`.
- Path joins under `output/` via `safe_join` (`studio/security.py`). Validate IDs strictly;
  never silently accept the altered result of `sanitize_project_id`.
- Workflow API routes are loopback-only (`_require_loopback()`), and errors use one envelope:
  `{"error": {"code", "message", "details?"}}`.
- Never persist credentials — not in workflow JSON, execution records, SSE events, logs,
  errors, archives, notifications, or exported templates.
- Frontend: feature folders, Pinia stores, composables. Tests in `__tests__/` beside the feature.
- Async dropdown options come from a backend allowlist. Adding one means editing **both**
  `ASYNC_OPTION_SOURCES` (`studio/workflows/registry.py`) and `_RESOLVERS`
  (`studio/workflows/options.py`) — a module-level assert and a test enforce parity.
- Generated docs (`docs/workflow-nodes.md`, `docs/workflow-node-author-guide.md`,
  `docs/providers.md`, `docs/provider-author-guide.md`) are produced by
  `studio.workflows.docs` (providers also via `studio.shared.providers_common.docs`).
  Edit the registry/domains/hub, regenerate, never hand-edit; drift tests enforce it.

## Known traps

- **Bare `python` is broken.** Covered above, but it catches everyone.
- **The provider ABC layer is dead code.** `TTSProvider.synthesize`,
  `Storyboard`/`AnimatorProvider.submit`/`poll`, and all seven `get_provider()` factories have
  zero call sites. Execution branches on `if provider_id == …` into legacy modules. Do not
  assume those classes run — they have never executed.
- **Two provider-selection stores.** `settings/settings.json` (`domains.*.selected_provider`)
  and `app-config.json` (`sts-tts-provider`) both exist. `settings_manager.set_selected_provider()`
  is defined but never called; the UI rewrites the whole blob via `PUT /api/settings/v2`.
- **`GET /api/workflow/options/<source>` takes no parameters**, so no dropdown can currently
  depend on the selected provider.
- **Env vars have side effects.** A present `INWORLD_API_KEY` flips the selected TTS provider to
  `inworld` during first-run seeding (`settings_manager.py:67-107`).
- **Legacy provider aliases are still live**: `gemini_ws→gemini`, `wavespeed_webhook→webhook`,
  `wavespeed_direct→direct`, `grok_automa→grok`, `kie_ai→kie-ai`
  (`studio/pipeline/services.py:550` and `:644`).
- **Live providers are partly unavailable**: the WaveSpeed key returns 401, the hosted n8n
  webhook is retired, OpenRouter's balance is negative, and `grok_automa` needs a human driving
  a browser. Tests marked `@pytest.mark.live` are skipped unless `STS_LIVE=1`.

## Working with the plan

`_dev/loop-engineering/` runs the roadmap step by step. The plan markdown is the single source
of truth and is parsed live:

- Phases are `## Phase N — Title`, steps are `### N.M Title`, and every step **must** end with a
  literal `**Done when:**` line. Variants like `**Done when (Phase 3 gate):**` do not parse.
- Progress is detected from commit subjects containing `step N.M`, so commit subjects matter.
- Check state with `_dev/loop-engineering/run.bat --status`.
- Don't run the loop while an interactive session edits the same repo — one writer at a time.

The authoritative spec is `_dev/loop-engineering/phases-plans/proposition-final.md`; frozen
machine contracts are in `contracts.md` beside it. Resolve any conflict between docs and code in
favor of working behavior, and record the adjustment.
