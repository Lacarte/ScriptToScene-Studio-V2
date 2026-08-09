# Workflow Builder — Machine Contracts (Phase 0 frozen)

> Produced by the Phase 0 audit (steps 0.1 + 0.2 of [implementation-plan.md](implementation-plan.md)).
> Grounded in code as of commit `4aca8cb` (2026-08-04). Line numbers refer to that state.
> Rule inherited from the spec: discrepancies between the spec and the code are resolved
> **in favor of preserving working behavior** — every such resolution is recorded here.

> **Status:** Phase 0.4 review passed on 2026-08-04. Named ports/control semantics, strict
> ID rules, HTTP envelopes, SSE replay, security limits, and the test baseline are frozen.
> Deterministic fixture files are scheduled as the first prerequisite of step 2.5, before
> stubs consume them.

---

## 1. Spec-vs-code discrepancies (resolved)

| # | Spec said | Code reality | Resolution |
|---|---|---|---|
| D1 | `studio/scenes` module | Does not exist. Scene generation is `studio/build_scene_blueprints/` (blueprint name `scenes`, routes `/api/scenes/*`) | Adapters import from `studio.build_scene_blueprints.*` |
| D2 | `studio/assets` module | Does not exist. The "assets" step is `studio/animator/` (`animation_routes.py` grabber + `organizer.py`) | Animator node wraps `studio.animator`; "assets" is UI vocabulary only |
| D3 | Assemble consumes audio+scenes+assets via data edges | `_step_assemble(project_id)` takes **only** `project_id` and reads everything from disk (`routes.py:1919`) | Assemble node keeps typed input ports for **ordering/readiness**, but the adapter contract is: inputs assert artifact presence; payload = `project_id` |
| D4 | Storyboard and/or Animator feed Assemble | **Mutually exclusive.** `_pick_scene_asset` (`editor/routes.py:72`) reads ONLY `output/animator/`. Storyboard images are reference inputs to the animator (base64 side channel, `animation_routes.py:243-256`); no code path puts them on the timeline | Assemble's asset input port type is `animation_assets` only. Storyboard output port connects to Animator (reference) or Workflow Output — never Assemble. Storyboard→timeline is a possible future adapter feature, out of scope v1 |
| D5 | Resume can reload any step | `_load_prior_results` has **no `assets` branch** (`routes.py:793`) — assets are never reloadable in the legacy pipeline | Workflow engine's own `run_data` + fingerprint cache supersedes `_load_prior_results`; adapters must not depend on it |
| D6 | — | `storyboard_provider`, `image_model`, `arguments` are declared in `PipelineRunRequest` but never copied into the job config (`routes.py:283-318`) — silently dead in the legacy pipeline | Workflow node configs bypass the legacy config dict entirely; adapters receive node configuration directly |
| D7 | Project identity can be inferred from every edge payload | Legacy artifacts sometimes use a `source_folder` different from the editor `project_id`; several steps reconstruct paths from one or the other | Every execution has one immutable project context. New runs allocate `pm_XXXXXX`; `project.existing` selects an existing ID before side-effecting nodes start. Artifact outputs carry safe relative refs plus `project_id` and `source_folder` where relevant. Adapters consume those fields instead of guessing paths. Conflicting existing-project inputs or request/project-node mismatches fail validation. |

## 2. Node contract table (core production nodes)

Legend: **cfg** = node configuration keys; **in/out** = typed ports; **artifacts** = files under `output/`;
**service** = the function(s) the adapter calls (✅ = already clean/importable, 🔶 = requires extraction in step 3.1).

### `project.setup` (Project Setup)
- in: — · out: `project_settings`
- cfg: `project_name, channel_name, logo_enabled, logo, logo_position, logo_size, logo_opacity, logo_margin, tone, style, aspect_ratio`
- service: trivial validate+emit (new code). Logo is a managed reference under `output/branding/`.
- artifacts: none. Instant, cacheable, no side effects.

### `script.input` (Script Input)
- in: — · out: `script` (str, 1–10,000 chars)
- cfg: `text` (textarea). Later: Story Generator node (`studio/story`) can feed the same port type.

### `trigger.manual`, `project.existing` (entry nodes)
- `trigger.manual`: no config or artifacts; emits one `control` token when included in the selected execution scope. It is optional because the toolbar/API already initiates runs.
- `project.existing`: cfg `project_id`; validates strict project ID syntax and existence, then resolves WIP before `initial.json` using the same preference as `editor_load_project` (`editor/routes.py:1211`). It emits `project_id` and an `editor_project` artifact reference without copying or rewriting the project.
- Execution validation permits at most one enabled `project.existing` node in a selected side-effecting subgraph. Its ID must agree with any `project_id` supplied to `/api/workflow/run`.

### `tts.generate` (Text to Speech)
- in: `script` (required) · optional `project_settings` · out: `audio_file`, `tts_metadata`
- cfg: `engine` (kokoro|inworld), `voice`, `speed` (0.5–2.0), `provider_options` (dict)
- service: 🔶 extract from `_step_tts` + `_step_tts_kokoro_pipeline` / `_step_tts_inworld_pipeline` (`pipeline/routes.py:1242-1467`). Underlying clean pieces: `studio.tts.normalize.clean_for_tts` ✅, `studio.tts.audio.{pad_audio,run_loudnorm}` ✅, `studio.tts.inworld.synthesize_to_wav` ✅. Kokoro path uses module singletons `kokoro_instance`/`generation_inference_lock` (`tts/routes.py:199-204`) — adapter must reuse the SAME singletons (do not duplicate; see K1 below).
- artifacts: `output/tts/{pid}/voice.wav`, `output/tts/{pid}/tts.json` (+ cache `TMP_DIR/tts/{sha16}.wav`)
- `tts_metadata` payload = the metadata dict of §4.3 of the step audit; minimum downstream needs: `{wav_path, folder, filename, duration_seconds, words}`.
- Known quirks preserved: local voice fallback `af_bella` (schema default is `af_heart`); Inworld ignores `speed`; cache key sha256(text|voice|speed) ignores provider; cache hits get loudnorm twice.

### `timing.align` (Force Alignment)
- in: `audio_file` + `script` (both required) · out: `alignment`
- cfg: — (model fixed: stable-whisper tiny.en)
- service: `studio.timing.routes._run_alignment(wav_path, prompt_text)` ✅ logic (module import pulls blueprint — acceptable; singleton `alignment_model`/`alignment_lock`). Text cleaning: strip `[]*_#`~` + whitespace-collapse (`routes.py:1474-1477`).
- artifacts: `output/alignments/{folder}/alignment.json` (+ wav copy if absent)
- Failure mode: `_run_alignment` returns `None` on ANY exception → adapter raises `NODE_EXECUTION_FAILED` with code `ALIGNMENT_EMPTY`.
- `alignment` payload: `{project_id, source_file, folder, transcript, alignment:[{word,begin,end}], word_count, inference_time, timestamp}`

### `segment.run` (Segmenter)
- in: `alignment` (required) · out: `segments`
- cfg: `segment_config` overrides of `DEFAULT_CONFIG = {target_min:1.5, target_max:4.0, hard_max:5.0, hard_min:0.8, gap_filler:0.3}` (+ `break_weights`, `max_silence`)
- service: `studio.timing.segmenter.run_segmenter(alignment, config, metadata)` ✅ (purest module in repo) + `save_output` ✅
- artifacts: `output/segmenters/{pid}/segmented.json`
- `segments` payload: file content + injected `output_folder`, `output_path`. `stats.segment_count` counts non-filler only.

### `scenes.blueprint` (Scene Blueprint)
- in: `segments` + `script` (required) · optional `project_settings` (tone/style defaults) · out: `scenes`, `image_prompts`
- cfg: `webhook_url` (fallback `N8N_WEBHOOK_URL`), `style` (template id), `style_prompt` (custom notes), `story_tone`
- service: 🔶 extract orchestration from `_step_scenes` (`pipeline/routes.py:1586-1704`). Clean pieces ✅: `resolve_template_bundle`, `build_visual_bible`, `build_scene_blueprints`, `summarize_blueprints`, `build_scene_system_prompt`, `should_use_chapters`, `studio.webhooks.call_webhook`, `_normalize_webhook_response`, `_apply_segmenter_timing`, `ensure_analysis_payload`, `finalize_scene_result`, `resolve_niche`. Chunked path: `generate_with_chapters_chunked` (lives in bsb/routes.py — move in 3.1).
- artifacts: `output/scenes/{pid}/scenes.json`
- Side effects: outbound HTTP to n8n webhook; unseeded `random.shuffle` in `_assign_hook_animations` (non-deterministic `text_hook_animation`) — excluded from fingerprint.
- Progress: accepts `progress_cb(str)` → engine forwards as node progress events.
- No stop check inside (v1: interruptible only at boundaries).

### `storyboard.generate` (Storyboard)
- in: `scenes` (required, uses `scenes[].{index,image_prompt}`) · optional `project_settings` · out: `storyboard_images`
- cfg: `provider` (webhook|direct|gemini; registry ids `wavespeed_webhook|wavespeed_direct|gemini_ws`), `aspect_ratio`, `style`, `image_model`, `prompt_prefix` (gemini only), `auto_type`
- service: 🔶 `_generate_storyboard(project_id, scenes, aspect_ratio, webhook_url, style, image_model)` ✅ (already thread-callable, `storyboard/routes.py:144`) or `gemini_ws.add_job/queue_image_job` ✅ (WebSocket to extension). Status: re-read `output/storyboard/{pid}/storyboard.json` — NOT the HTTP status route.
- artifacts: `output/storyboard/{pid}/storyboard.json`, `{scene}/image.{ext}` (versioned rotation), thumbnails, `scene_prompts.json` (gemini)
- Poll contract: 10s interval, 30min timeout; **errors count toward completion** (`pending = total-ready-errors`).
- `storyboard_images` payload: `{total, ready, errors, scene_statuses}` + artifact refs.

### `animator.generate` (Animator — the "assets" step)
- in: `scenes` (required) · optional `storyboard_images` (reference-image edge; see D4) · optional `project_settings` · out: `animation_assets`
- cfg: `provider` (grok|kie-ai; registry ids `grok_automa|kie_ai`), `aspect_ratio`, `mode` (video|image), `quality`, `duration`, `arguments`, `auto_type`
- service: 🔶 biggest extraction: `grabber_start` logic (`animation_routes.py:188-`) is `@validate_json`-route-coupled. Clean pieces ✅: `organizer.organize_grabber_assets`, `save_base64_assets`, `reconcile_project`, `kie_ai.generate_image`, `routes.add_job/queue_grabber_start`.
- artifacts: `output/animator/{pid}/{scene}/*` (media + `*_thumb.jpg`), `metadata.json`, `grabber_job.json`
- Poll contract: 10s interval, **120min** timeout. In-memory `grabber_jobs` JobStore — status lost on process restart (adapter must tolerate + fall back to disk reconcile).
- `animation_assets` payload: `{total, ready, errors, provider}` + artifact refs.
- `mode=video` filters non-video URLs to `status="error"` at ingest — the only lever forcing video assets.

### `assemble.project` (Assemble Project)
- in: `animation_assets` + `tts_metadata` + `scenes` (readiness edges; see D3) · optional `captions`, `music_track`, `project_settings` · out: `editor_project`
- cfg: — (v1; force-rebuild is implicit)
- service: 🔶 **extract `assemble(project_id, *, force=True) -> dict` from `assemble_project_for_editor` (`editor/routes.py:1451`, ~300 lines)** — the single biggest extraction. Uses clean helpers `_pick_scene_asset`, `_load_asset_metadata`, `_resolve_audio_url`, `select_music/select_sfx` ✅, `_group_words_into_captions` ✅.
- artifacts: `output/projects/{pid}/initial.json` (overwritten on force; WIP untouched), `output/captions/{pid}/captions.json` (auto-gen branch)
- Asset resolution (frozen contract): per scene, tier 1 = animator `metadata.json` `local_files` (any video beats any image; last list entry wins); tier 2 = dir scan of `output/animator/{pid}/{scene_key}` (videos preferred; newest mtime wins); global de-dup via `used_asset_urls` (one file backs one scene); losers get `mediaUrl:""` + `status:"pending"`.
- **Not interruptible; no stop check. Music/SFX selection is random (bounded by 10-entry history) → non-deterministic; excluded from fingerprint, and pinning the output is the determinism lever.**
- `editor_project` payload: `{scene_count, total_duration, has_audio, has_captions, assembled_data}`.

### `captions.generate` (Caption Generator)
- in: `alignment` (required) · out: `captions`
- cfg: `preset_id` (approved preset id), `words_per_group` (1–10, default 3), `enabled` (default true)
- service: `studio.captions.routes._group_words_into_captions(alignment, words_per_group)` ✅ and preset lookup via `CAPTION_PRESETS` / `_get_default_caption_preset_id` ✅. Extraction to a service module in 3.1 avoids importing a route module from the adapter.
- artifacts: `output/captions/{source_folder}/captions.json`, written atomically. Payload matches existing editor support: `{project_id, source_folder, preset, captions:[{text,start,end,words}]}`.
- deterministic and synchronously cancellable at the node boundary; no retry needed. Invalid word timings fail validation instead of being silently reordered.

### `music.select` (Background Music)
- in: optional `project_settings`, optional `project_id` · out: `music_track`
- cfg: `mode` (`tone|random|specific`), `story_tone`, managed `track_ref`, `volume` (0–1), `fade_in`, `fade_out`, `loop`, `ducking_enabled`, `ducking_level`
- service: `studio.music.selector.{select_music,select_random_music,recall_last_music}` ✅ plus existing history helpers. The adapter converts approved absolute library selections into managed `/assets/sounds/music/...` references before emitting output; arbitrary browser paths are rejected.
- artifacts: no standalone node artifact in v1; selection/history is persisted in the execution record and later editor project. If a project ID is present, history mutation is deferred until Assemble succeeds so a failed exploratory run does not consume a random pick.
- selection is non-deterministic unless `specific` or pinned. Its fingerprint includes the resolved managed track reference; cache lookup happens before a fresh random choice.

### `timeline.project`, `workflow.output` (output helpers)
- `timeline.project`: takes `editor_project`, verifies its managed artifact, and atomically writes/updates the editor project through the extracted editor save service. It emits the same `editor_project` reference plus `project_id`. It must not overwrite `work@in@progress.json` unless the workflow explicitly targets the existing project and the run request authorizes replacement.
- `workflow.output`: cfg `port_type`, `label`; accepts one dynamically typed value, records a redacted summary and safe artifact refs in the execution result, and has no filesystem side effect of its own.
- `stub.input` and `stub.output` remain testing nodes described below; they never allocate a project or convert sample-derived artifacts into a normal project without an explicit non-sample rebuild.

### `export.video` (Video Export)
- in: `editor_project` (required) · optional `project_settings` (logo block, aspect ratio) · out: `video_file`
- cfg: `profile` (yt_shorts|tiktok|reels|yt_landscape|square), `captions` (bool), `grain` (bool) — v1 sourced from node config, NOT app-config (deliberate divergence: node config beats `app-config.json`; recorded as workflow behavior)
- service: 🔶 extract job creation from `start_export` (`editor/routes.py:2192`); `VideoProcessor` ✅ (`video_processor.py:201`, clean class) + `_process_video` ✅ (already thread-run). Logo overlay pass added here (Phase 3.2).
- artifacts: `output/exports/{pid}_{job8}.mp4` + sidecar json; mutates `initial.json`/WIP via audio-persist helpers
- Known defects preserved-but-documented (fix candidates AFTER parity, tracked in §8): export status route omits `output_filename` (⇒ legacy auto-sync dead); only the FIRST sfx track reaches the renderer (per-scene SFX dropped); `_persist_auto_selected_export_audio` strips per-scene SFX from saved projects; audio fallback can promote music to narration channel when no voice track exists.
- Cancellation: cooperative via export job cancel — the ONLY step with true cancel support.

### Utility/testing nodes
- `stub.input`: out = dynamic `port_type`; cfg `{port_type, payload}`; executes instantly; file-backed types reference `studio/workflows/fixtures/` only.
- `stub.output`: in = dynamic; captures + displays; Phase 4 pinning = winning cache entry.
- `workflow.output`, `trigger.manual`, `project.existing`: declarative, no side effects.

### Phase 5.4 utility nodes (frozen v1 semantics)

- `story.generate` (Story Generator): in `trigger:control?`, `settings:project_settings?`; out
  `control:control`, `script:script`. Configuration is `preset_style`, `story_category`,
  `duration` (15-180 seconds), `language`, optional `language_level`, optional `story_tone`,
  optional `idea`, and optional `webhook_url`. Explicit node configuration wins over incoming
  `settings.style`/`settings.tone`. It calls the importable `studio.story` prompt, webhook,
  parser, persistence, and history services directly (never its Flask route), writes
  `output/stories/{execution_project_id}/story.json`, and emits the parsed `story_text` on the
  existing `script` port. It is provider-dependent, retryable, and non-deterministic.
- `utility.set_value` (Set Value): in `trigger:control?`, `value:generic_json?`; out
  `control:control`, `value:generic_json`. Configuration `value` is any bounded JSON value.
  The configured value always replaces the optional input; the input exists only to sequence
  and branch the node. The node is instant, deterministic, and side-effect free.
- `utility.condition` (Condition): in `trigger:control?`, `value:generic_json`; out
  `true:generic_json?`, `false:generic_json?`. Configuration `operator` is one of
  `truthy|falsy|equals|not_equals|contains`; `compare_to` is used by the last three operators.
  Exactly one output port is present at runtime and carries the input value unchanged. The
  other output is deliberately inactive, not `null`, not an error, and not a success token.
  `contains` means membership for arrays/object keys and substring containment for strings;
  other input types evaluate false. Equality uses normal JSON structural equality. The node
  is instant, deterministic, and side-effect free.
- `utility.wait` (Wait): in `trigger:control?`, `value:generic_json?`; out `control:control`,
  `value:generic_json`. Configuration `delay_ms` is an integer from 0 through 300000. It emits
  its input unchanged (or JSON `null` when absent) after the delay, checks cancellation in
  intervals no longer than 50 ms, and creates no artifacts. It is deterministic but is never
  cache-reused because the delay itself is its intended side effect.
- `utility.merge` (Merge): in `values:generic_json` with `multiple:true`; out
  `control:control`, `value:generic_json`. It is the only skip-tolerant join in v1. The
  scheduler waits until every connected predecessor is terminal, then discards inactive
  edges caused by Condition/skip propagation and runs Merge when at least one value edge is
  active. Zero active inputs skips Merge. Active values retain saved edge order. Configuration
  `mode=array` emits the ordered list, `mode=first` emits its first item, and `mode=object`
  shallow-merges objects from left to right (later keys win) and fails if an active value is
  not an object. Merge is instant, deterministic, and side-effect free.

Scheduler rule for conditional branches: a succeeded node activates only output ports actually
present in its output mapping. A node with any inactive normal predecessor is skipped, and that
skip propagates through ordinary descendants. This is a normal successful-run state. Merge is
the explicit convergence boundary: inactive/skipped predecessors count as resolved rather than
as required active inputs. Failures and cancellations are not converted to inactive branches;
the existing error policy remains authoritative.

## 3. Port types & compatibility matrix

Types (v1): `control, text, script, project_id, project_settings, audio_file, tts_metadata, alignment, segments, scenes, image_prompts, storyboard_images, animation_assets, captions, music_track, editor_project, export_profile, video_file, generic_json`.

Compatibility rule: **exact type match only.** No wildcard: `generic_json` connects only to `generic_json`. `stub.input`/`stub.output` resolve their dynamic type from configuration at validation time and then obey exact-match. Additional rules: no in→in / out→out; single-value inputs reject a second edge; DAG only (cycle rejection); control edges distinct from data edges. Every payload that references files carries `{artifact_refs: [relpaths]}` alongside inline JSON; integrity check = existence + nonzero size.

### 3.1 Stable port IDs and control readiness

Type names alone are not port IDs. Registry entries and persisted edges use the following
stable IDs; renaming a display label never changes them.

| node type | inputs (`id:type`, `?` optional) | outputs (`id:type`) |
|---|---|---|
| `trigger.manual` | — | `control:control` |
| `project.setup` | `trigger:control?` | `control:control`, `settings:project_settings` |
| `script.input` | `trigger:control?` | `control:control`, `script:script` |
| `project.existing` | `trigger:control?` | `control:control`, `project_id:project_id`, `project:editor_project` |
| `tts.generate` | `trigger:control?`, `script:script`, `settings:project_settings?` | `control:control`, `audio:audio_file`, `metadata:tts_metadata` |
| `timing.align` | `trigger:control?`, `audio:audio_file`, `script:script` | `control:control`, `alignment:alignment` |
| `segment.run` | `trigger:control?`, `alignment:alignment` | `control:control`, `segments:segments` |
| `scenes.blueprint` | `trigger:control?`, `segments:segments`, `script:script`, `settings:project_settings?` | `control:control`, `scenes:scenes`, `image_prompts:image_prompts` |
| `storyboard.generate` | `trigger:control?`, `scenes:scenes`, `settings:project_settings?` | `control:control`, `images:storyboard_images` |
| `animator.generate` | `trigger:control?`, `scenes:scenes`, `storyboard:storyboard_images?`, `settings:project_settings?` | `control:control`, `assets:animation_assets` |
| `captions.generate` | `trigger:control?`, `alignment:alignment` | `control:control`, `captions:captions` |
| `music.select` | `trigger:control?`, `settings:project_settings?`, `project_id:project_id?` | `control:control`, `track:music_track` |
| `assemble.project` | `trigger:control?`, `assets:animation_assets`, `metadata:tts_metadata`, `scenes:scenes`, `captions:captions?`, `music:music_track?`, `settings:project_settings?` | `control:control`, `project:editor_project` |
| `timeline.project` | `trigger:control?`, `project:editor_project` | `control:control`, `project:editor_project`, `project_id:project_id` |
| `export.video` | `trigger:control?`, `project:editor_project`, `settings:project_settings?` | `control:control`, `video:video_file` |
| `workflow.output` | `trigger:control?`, `value:<dynamic>` | — |
| `stub.input` | — | `value:<dynamic>` |
| `stub.output` | `value:<dynamic>` | `value:<dynamic>` |

Required data inputs are shown without `?`; registry fields still encode this as
`required` and `multiple`. All inputs above are single-value in v1. Outputs may fan out.
`workflow.output` and both stubs resolve `<dynamic>` from validated `configuration.port_type`.

Data edges establish both a dependency and a typed value. Control edges establish only a
dependency and never satisfy a required data input. A node with a connected `trigger` waits
for that control predecessor as well as all required data. An unconnected optional `trigger`
does not block a node. A node emits `control` only after successful completion; skipped,
failed, and cancelled propagation is handled explicitly by scheduler policy rather than by
fabricating a success token. These rules make Manual Trigger useful without making it
mandatory for partial or isolated execution.

## 4. Workflow JSON schema (frozen)

As specified in [proposition-final.md](proposition-final.md) §Persistence — `schema_version: 1`, nodes `{id, type, type_version, name, position, configuration, disabled}`, edges `{id, source_node, source_port, target_node, target_port, edge_type}`, `variables`, `viewport`, `settings: {on_error}`, ISO timestamps. Persisted under `output/workflows/{workflow_id}.json` via `safe_json_write`; soft-delete to `output/TRASH/workflows/`. `output/workflows/` and `output/branding/` must be added to clear-all handling.

`sanitize_project_id` is a normalizer, not sufficient request validation: it silently removes
invalid characters and can alias two user inputs. API IDs must first match the entire strict
pattern `^wf_[A-Z0-9]{6}$` or `^ex_[A-Z0-9]{6}$` as applicable, then be resolved with
`safe_join`. Imported node/edge IDs use a documented bounded safe pattern and must also be
unique within the document. Reject altered, empty, overlong, wrong-prefix, and duplicate IDs;
never normalize them into acceptance.

### 4.1 Field-level validation policy

The implementation may use Pydantic or equivalent explicit validators, but these constraints
are transport-independent:

| field | rule |
|---|---|
| document | JSON object, UTF-8, maximum 2 MiB after encoding, maximum nesting depth 20 |
| `schema_version` | required integer, exactly `1` |
| `workflow_id` | server-generated on create; otherwise required `^wf_[A-Z0-9]{6}$` |
| `name` | required trimmed string, 1–120 characters |
| `description` | string, 0–2,000 characters |
| `nodes` | required array, 0–200 unique nodes |
| `edges` | required array, 0–500 unique edges |
| node `id` | `^[A-Za-z][A-Za-z0-9_-]{0,63}$`, unique |
| node `type` | required registry key, maximum 80 characters |
| node `type_version` | required positive integer supported by the registry |
| node `name` | trimmed string, 1–120 characters |
| node `position.x/y` | finite number in `[-1000000, 1000000]` |
| node `configuration` | JSON object, maximum 256 KiB per node, schema-validated |
| node `disabled` | required boolean |
| edge `id` | `^[A-Za-z][A-Za-z0-9_-]{0,63}$`, unique |
| edge endpoints/ports | existing node IDs and registry port IDs; maximum 64 characters each |
| edge `edge_type` | `data` or `control`, and must match the source/target port types |
| `variables` | finite JSON object, maximum 64 KiB; expression path segments match `[A-Za-z_][A-Za-z0-9_]{0,63}` |
| `viewport` | finite `x/y`; `zoom` in `[0.1, 1.5]` |
| `settings.on_error` | `stop` in v1; later values enabled only with Phase 4 capability support |
| timestamps | RFC 3339 strings written by the server; clients cannot override them on update |

V1 rejects unknown fields at the document, node, and edge levels. Forward-compatible metadata
must live under a bounded `extensions` object (reserved now, optional, ignored by execution,
round-tripped). This avoids silently trusting misspelled contract fields while leaving an
explicit extension path. JSON numbers must be finite; `NaN` and infinities are rejected.

### Expressions and data mapping (Phase 5.5)

An expression is a string containing exactly one whole-value reference (surrounding whitespace
is ignored): `{{ nodes.<node_id>.outputs.<port_id> }}`, `{{ workflow.project_id }}`, or
`{{ variables.<name>[.<nested_name>...] }}`. Interpolation, operators, calls, indexing, and
all other roots are invalid. Whole-value replacement preserves the referenced JSON type.
Expressions may appear recursively in configuration JSON, but structural configuration such as
dynamic `port_type` must still resolve to a valid registry value.

Node-output references must name an existing non-control output on a strict graph ancestor and
that ancestor must be included in the selected execution scope. Static expression validation is
part of workflow validation and scheduler construction. Immediately before a node is fingerprinted
and invoked, expressions resolve from already-produced outputs, immutable execution `project_id`,
and the workflow snapshot's finite JSON `variables`; the resolved configuration is schema-validated.
A skipped, absent, or stale output fails with `EXPRESSION_VALUE_UNAVAILABLE`. The parser does not
evaluate code and exposes no environment, secret store, object attributes, or filesystem API.

## 5. Execution record schema (frozen)

```jsonc
{
  "schema_version": 1,
  "execution_id": "ex_XXXXXX",           // generate_project_id-style, sanitized
  "workflow_id": "wf_XXXXXX",
  "workflow_snapshot": { /* full workflow JSON at run time */ },
  "project_id": "pm_XXXXXX",
  "run_mode": "full|node_with_deps|node_isolated|selected|from_node|retry_failed|retry_failed_desc",
  "scope_node_ids": ["n_tts"],
  "status": "running|succeeded|failed|cancelled|partial",
  "started_at": "ISO", "finished_at": "ISO|null",
  "nodes": {
    "n_tts": {
      "status": "idle|invalid|queued|running|waiting|succeeded|failed|cancelled|skipped|stale",
      "attempts": 1, "duration_ms": 5230,
      "fingerprint": "sha256…", "cache": {"hit": false, "reason": "config_changed"},
      "from_sample_data": false,
      "resolved_inputs_summary": {"script": {"chars": 812}},
      "outputs_summary": {"audio_file": {"artifact": "tts/pm_X/voice.wav", "duration_s": 28.5}},
      "artifact_refs": ["tts/pm_X/voice.wav", "tts/pm_X/tts.json"],
      "logs": [{"ts": "ISO", "level": "info", "message": "…"}],
      "error": null   // or structured error, §7
    }
  }
}
```
Persisted per run at `output/workflows/executions/{execution_id}.json` (atomic, redacted). Large payloads stay as artifact refs — never inlined.

Execution records are server-owned and never accepted back as workflow definitions. Node map
keys must equal node IDs in the stored snapshot. `attempts` is a non-negative integer;
`duration_ms` is null until terminal and otherwise non-negative; `artifact_refs` are normalized
relative paths beneath approved output roots; logs are capped by count and bytes; and all
free-text/log/error fields pass through redaction before persistence and SSE emission. Overall
and node status transitions are monotonic according to the scheduler state machine; terminal
states cannot transition back to running.

## 6. API surface & SSE event shape (frozen)

Routes exactly as the spec lists (`/api/workflows` CRUD+import/export; `/api/workflow/node-types|validate|run|executions/*`). New blueprint `workflows_bp`, name `"workflows"`, **no url_prefix** (matches all 14 existing blueprints), imported and registered with the other blueprints in `app.py`. Provider-backed option resolution occurs at request time after startup initialization; blueprint registration itself must not assume populated provider registries.

All endpoints are local-app endpoints and enforce `is_loopback_remote`; mutation endpoints also
require JSON content types where applicable. Success payloads are JSON objects rather than bare
arrays. Errors use one envelope everywhere:

```json
{
  "error": {
    "code": "WORKFLOW_INVALID",
    "message": "Workflow has validation errors",
    "details": { "problems": [] }
  }
}
```

`details` is optional and redacted. Expected endpoint contracts:

| endpoint | request | success |
|---|---|---|
| `GET /api/workflows` | optional `limit` 1–200 (default 100) | `200 {workflows:[summary], total:n}` sorted by `updated_at` descending then ID; no pagination until the 200-item cap is insufficient |
| `POST /api/workflows` | `{workflow:<definition without server id/timestamps>}` | `201 {workflow}` + `Location`; server allocates ID/timestamps |
| `GET /api/workflows/<id>` | — | `200 {workflow}`; `404` if absent |
| `PUT /api/workflows/<id>` | `{workflow, expected_updated_at}` | `200 {workflow}`; `409 WORKFLOW_CONFLICT` on stale update |
| `DELETE /api/workflows/<id>` | `{expected_updated_at?}` | `200 {deleted:true, workflow_id}` after atomic move to trash; `409` on stale update |
| `POST /api/workflows/import` | `{workflow, on_conflict:"reject"|"new_id"}` | `201 {workflow, imported_from_id?}`; default `new_id` |
| `GET /api/workflows/<id>/export` | — | `200 application/json` definition with attachment filename; no execution data/secrets |
| `GET /api/workflow/node-types` | — | `200 {registry_version, node_types, port_types}` with no executor/callable internals |
| `GET /api/workflow/templates` | — | `200 {templates:[{template_id, workflow}]}`; every bundled graph passes server validation |
| `POST /api/workflow/validate` | `{workflow}` | `200 {valid, problems, warnings}` for a well-formed request, even when graph-invalid; malformed transport is `400` |
| `POST /api/workflow/run` | `{workflow_id xor workflow, run_mode, target_node_ids:[], force:false, project_id?}` | `202 {execution_id, project_id, status:"queued"}` |
| `POST /api/workflow/executions/<id>/stop` | `{}` | `202 {execution_id, status:"cancelling"}`; `409` if already terminal |
| `GET /api/workflow/executions/<id>` | — | `200 {execution}`; `404` if absent |
| `GET /api/workflow/executions/<id>/events` | standard `Last-Event-ID` on reconnect | `200 text/event-stream`; `404` if absent |
| `GET /api/workflow/executions` | required `workflow_id`, optional `limit` 1–200 | `200 {executions:[summary], total:n}` sorted newest first |
| `GET /api/workflows/<id>/webhook` | — | `200 {webhook, token, path}` with `Cache-Control: no-store`; creates the separately persisted token when absent |
| `POST /api/workflows/<id>/webhook/regenerate` | `{}` | `200 {token, path}` with `Cache-Control: no-store`; immediately invalidates the prior URL |
| `POST /api/workflow/hooks/<id>/<token>` | mapped JSON object, max 64 KiB | `202 {execution_id, project_id, status:"queued"}` with queue source `webhook`; available only to loopback clients while the server itself is loopback-bound |

Create/import/save return `422 WORKFLOW_INVALID` when the JSON transport is valid but violates
workflow rules. Use `400` for malformed JSON/request shape, `403` for non-loopback access,
`404` for missing resources, `409` for conflicts/locks/terminal stop, `413` for size limits,
and `500` only for unexpected redacted server failures. Add `WORKFLOW_CONFLICT` to the stable
error-code set.

SSE (own emitter in `studio/workflows/events.py` — do NOT reuse pipeline `_emit`, which is private and closes over `_jobs`; see blocker B6):

```jsonc
{ "sequence": 12, "execution_id": "ex_123", "node_id": "n_tts",
  "status": "running", "attempt": 1, "timestamp": "ISO",
  "duration_ms": 0, "summary": "Generating narration",
  "progress": {"ready": 3, "total": 10},      // optional, poll-driven nodes
  "from_sample_data": false }                  // present when stub-fed
```
Monotonic `sequence` per execution; each SSE frame includes `id: <sequence>` and a JSON `data:` payload. The stream ends on terminal event `{node_id: null, status: "succeeded|failed|cancelled"}`. On automatic reconnect, browser `EventSource` sends the standard `Last-Event-ID` header; the server replays events with greater sequence values from a bounded ring (1000 events). If the requested ID predates the retained buffer, emit a snapshot/reset event before live events. The client also deduplicates by `sequence`.

## 7. Error codes (stable)

`WORKFLOW_INVALID, WORKFLOW_CONFLICT, UNKNOWN_NODE_TYPE, UNSUPPORTED_NODE_VERSION, PORT_TYPE_MISMATCH, MISSING_REQUIRED_INPUT, CYCLE_DETECTED, PROJECT_LOCKED, NODE_EXECUTION_FAILED, ALIGNMENT_EMPTY, WEBHOOK_FAILED, WEBHOOK_NOT_FOUND, WEBHOOK_PAYLOAD_INVALID, PROVIDER_UNAVAILABLE, EXTENSION_NOT_CONNECTED, POLL_TIMEOUT, EXPORT_FAILED, CANCELLED, ARTIFACT_MISSING, CACHE_INTEGRITY, STUB_PAYLOAD_INVALID, SAMPLE_FIXTURE_MISSING`.
Failure payload: `{code, node_id, node_name, message, details_redacted, attempt, timestamp, recovery_suggestion}`.

## 8. Extraction blockers & known defects (input to step 3.1)

Blockers (must fix in 3.1):
- **B1** HTTP-to-self calls in storyboard/assets/assemble/auto-sync steps (`127.0.0.1:{STS_PORT}`) — replace with direct service calls.
- **B2** `STS_PORT` env var set inside a request handler (`pipeline/routes.py:280`) — never rely on it in workflow code.
- **B3** `grabber_start` `@validate_json` route-coupling — extract `start_grabber(request_model) -> job` service.
- **B4** `assemble_project_for_editor` — extract `assemble(project_id, *, force=False) -> dict`.
- **B5** Duplicate Kokoro/misaki singletons in `tts/routes.py` AND `tts/providers/kokoro/provider.py` (two model caches possible) — collapse to one owner (K1).
- **B6** No shared SSE emitter — build `studio/workflows/events.py`; later optionally lift pipeline `_emit` onto it.
- **B7** `ProviderRegistry.VALID_DOMAINS` is closed `{tts,storyboard,animator}` — workflow engine goes through existing domains only; no new domain in v1.
- **B8** Provider modules load under synthetic names — always `registry.get(id)`, never `import`.
- Dual provider vocabulary: **registry ids are canonical** in node configs (`kokoro, inworld, wavespeed_webhook, wavespeed_direct, gemini_ws, grok_automa, kie_ai`); legacy strings accepted on import with mapping.

Known defects (preserve during extraction; fix only as explicit follow-ups): export status omits `output_filename`; per-scene SFX dropped at export & stripped by persist helper; audio fallback promotes non-voice track to narration; double loudnorm on TTS cache hit; TTS cache key ignores provider; `_step_scenes`/kokoro paths have no stop checks; storyboard poll counts errors as done; `midjourney`/`meta_ai` are URL strings, not providers.

## 9. Mandatory shared helpers

- `studio.io_utils`: `safe_json_write` / `safe_json_read` for every JSON touch; `JobStore` instead of new dict+Lock pairs; `now_iso`.
- `studio.security`: `sanitize_project_id` (workflow/execution ids), `safe_join` (all path building), `is_safe_webhook_url`, `is_loopback_remote`. Do not copy the hand-rolled sanitizers in editor/story.
- `config.py`: all dir constants; `generate_project_id(prefix)` — workflow projects use existing prefixes (`pm_`) plus `wf_`/`ex_` for workflow/execution ids.
- Frontend: setup-style `defineStore` (both existing stores are composition style); `@` alias inherited by Vitest through `vite.config.js`.

## 10. Sample fixtures map (step 0.2 → consumed by 2.5/3.5)

`studio/workflows/fixtures/` — one per port type, frozen from a real tiny-script pipeline run:

| port type | fixture | notes |
|---|---|---|
| `script` | `script.json` | ~40-word script text |
| `audio_file` + `tts_metadata` | `voice.wav` + `tts.json` | few seconds, kokoro |
| `alignment` | `alignment.json` | matching the fixture audio |
| `segments` | `segmented.json` | 3 segments |
| `scenes` / `image_prompts` | `scenes.json` | 3 scenes with prompts |
| `storyboard_images` | `storyboard.json` + 1 small image | |
| `animation_assets` | `metadata.json` + 1 tiny mp4 + 1 jpg | |
| `editor_project` | `initial.json` | references fixture assets |
| `project_settings` | `project_settings.json` | defaults + sample logo png |
| `captions` / `music_track` | `captions.json` / ref to a resources track | |

Fixture validation is type-specific, not just "JSON parses": script is non-empty and bounded;
audio is a decodable WAV with positive duration; alignment words have finite ordered times;
segments are ordered, non-overlapping, and reference the canonical script; scenes have stable
indices and prompts; all media references are relative and contained beneath the fixture root;
storyboard/animator counts match their listed statuses; editor-project URLs resolve only to
fixture assets; and caption/music timings fit the canonical audio duration. A manifest records
SHA-256, byte size, media metadata, port types, and fixture schema version for every file.

Generation procedure: use a tiny canonical script; derive JSON shapes from audited real
artifacts; strip timestamps, secrets, provider payloads, and absolute paths; generate tiny
WAV/image/video media deterministically with local tools; validate all cross-references; and
commit the result. Live n8n/provider access must not be required to reproduce the fixture set.

**Current status: captured and frozen (step 2.5, 2026-08-04).** The fixture set lives in
`studio/workflows/fixtures/` (~188 KiB total) with `manifest.json` recording SHA-256, byte
size, media metadata, port types, and `fixture_schema_version: 1` for every file. Media is
generated locally (stdlib `wave`, Pillow, ffmpeg in bitexact mode) by
`studio/workflows/fixtures/generate.py`, which is byte-for-byte reproducible and requires no
provider access. `studio/workflows/sample_data.py` enforces the type-specific validation rules
above (`validate_fixtures()`, exercised by `tests/test_workflow_fixtures.py`) and serves the
per-port-type sample payloads consumed by stub nodes. One deliberate divergence from the
inventory table: the `music_track` fixture references a bundled `media/music.wav` instead of a
resources-library track so the set stays self-contained under the fixture root.

## 11. Security / threat notes

Redaction points: node configuration echoes (provider options may hold keys), execution records, SSE payloads, logs, clipboard fragments, exported workflow JSON — all through `studio/workflows/redaction.py`. Import validation limits: max 2 MB workflow JSON, ≤ 200 nodes, ≤ 500 edges, ids sanitized, unknown types/versions block execution. Async option sources: allowlist identifiers only (`tts_voices, story_tones, style_templates, storyboard_providers, animator_providers, export_profiles, caption_presets`). Media uploads (`media_asset`): extension+MIME+size (≤ 5 MB) validation into `output/branding/`, never raw paths. All new endpoints respect `MAX_CONTENT_LENGTH`, CORS config, and loopback guards for destructive ops.

Request hardening (step 6.3): JSON body limits are enforced by a bounded stream read (≤ 2 MiB + 1 byte), so chunked transfer encoding with no `Content-Length` cannot bypass them; non-empty bodies still require a JSON content type (forces a CORS preflight for cross-origin callers). Submitted values for `options_source` config fields are validated server-side against the allowlisted resolver's current values (`allowed_option_values`, process-lifetime cached); an unavailable resolver fails open — bad values are rejected, missing providers never block saving. Branding uploads cap the whole multipart request at 6 MiB via per-request `max_content_length` (Werkzeug enforces it while reading, chunked included; `413 REQUEST_TOO_LARGE` envelope via blueprint error handler) and cap the library at 50 stored logos (`409 LIMIT_EXCEEDED`).

## 12. Phase 0 verification record (2026-08-04)

- Backend: `venv` was broken (base interpreter from another project, missing). Rebuilt on Python 3.10.0; requirements + pytest installed. Initial run exposed a real false positive in the watermark confidence gate: the clean radial-glow regression had brightness difference 8.82, while the weakest real watermark fixture was about 17. Raising `_BRIGHTNESS_DIFF_MIN` from 8 to 10 preserves the real fixtures and fixes the false positive. Current `pytest tests/ -q`: **14 passed, 2 subtests passed**.
- Frontend: Vitest + @vue/test-utils + jsdom added (`npm run test`): **1 passed**. `test` block lives in `vite.config.js` (alias inherited).
- No `conftest.py`/pytest config exists; tests are `unittest`-style and run from repo root. Development dependencies are declared in `requirements-dev.txt` so pytest installation is reproducible without adding it to runtime requirements.
- Verified toolchain: Python 3.10.0; Node 24.14.0; npm 11.11.0. Vite 8 requires Node `^20.19.0 || >=22.12.0`, which is the frontend minimum. The Python source uses 3.10 union syntax, so Python 3.10+ is the backend minimum.
- Leftover empty `tests/test_*_<hash>/` dirs from an old run: ignorable noise.

### Tracked follow-through after the Phase 0 gate

1. Capture/generate and validate the fixture inventory before step 2.5.
2. Convert the field-level contracts into executable validators/tests as their owning modules
   land in Phases 1–3; until then, this document is the normative source.

---

# Provider Platform — Migration Audit (Phase 10.1)

> Produced by step 10.1 of [implementation-plan.md](implementation-plan.md).
> Grounded in code at commit `36734f6` (2026-08-08). Every line number below was read
> directly at that commit, not inferred.
> Vocabulary reconciled with `_dev/docs/plans/modular-providers-plan-v4.md` (the design doc
> the existing `studio/shared/providers_common/` was built from). Where v4 and this plan
> disagree, this document wins and the divergence is recorded in §17.6.
>
> **Scope.** Five domains migrate: `script`, `scene_blueprint`, `tts`, `storyboard`,
> `animator`. Music and Captions are excluded by owner decision; they are audited in §17.7
> only to confirm they keep working untouched.

## 13. Domain migration matrix

Legend — **State**: `platform` = has a provider package + registry today; `ad-hoc` = no
provider abstraction at all.

### 13.1 `script` (Story Generator) — state: **ad-hoc**

| aspect | evidence |
|---|---|
| entry points | `POST /api/story/generate` (`studio/story/routes.py:197`); workflow node `story.generate` → `studio.workflows.adapters.story:generate` (`registry.py:159`, adapter `adapters/story.py:10`) |
| shared service | `studio.story.service.generate_story(config, project_id=…)` — called by the adapter (`adapters/story.py:18`). The legacy route does **not** call it; it re-implements the same flow inline (`routes.py:197-351`) |
| other routes | `GET /api/story/webhook-url` (`routes.py:185`), `GET /api/story/categories` (`routes.py:191`), `GET /api/story/history` (`routes.py:353`), `GET /api/story/<project_id>` (`routes.py:382`), `POST /api/story/classify-style` (`routes.py:404`) |
| inputs | `preset_style, story_category, duration (15–180), language (english\|french\|spanish), language_level, story_tone, idea, webhook_url, project_name_id, niche_preset` (`studio/story/schemas.py:21-53`) |
| outputs | `{success, project_id, story_text, sections{hook,build,climax,cta}, metadata{…}}` |
| artifacts | `output/stories/{project_id}/story.json`; history `output/story_history/{preset}__{category}__{language}.json` (cap 10 entries) |
| side effects | outbound HTTP to n8n (120 s timeout); anti-repeat history mutation; non-deterministic concept-family pick |
| provider IDs | **none.** `"provider": "gemini"` is a hardcoded literal in the response metadata (`studio/story/service.py:102`, and again at `routes.py:287`) — a label, not a selector |
| aliases | none |
| settings/env | `N8N_STORY_WEBHOOK_URL` (`config.py:74-76`), `N8N_CLASSIFY_WEBHOOK_URL` (`config.py:80-82`), `STS_ALLOW_PRIVATE_WEBHOOKS`. **No `settings.json` participation** |
| hardcoded branches | none (single path) |
| callers | frontend `features/pipeline/composables/useStory.js`; `PipelinePage.vue` (classify); workflow scheduler through the adapter |
| owner | 13.1 (random_template provider), 13.2 (AI provider wrap), 13.3 (generic dispatch + defect fix) |

**Frontend random-story templates are not a provider and never were.**
`frontend/src/shared/data/stories.js:6` exports a static `RANDOM_STORIES` array of
`{text, type, styles}` objects; `useRandomStory.js:14` picks one at random while avoiding an
immediate repeat (`lastIdx`, lines 4 and 19). Consumers: `usePipeline.js:5`, `useTts.js:13`,
`PipelinePage.vue:17`, `TtsPage.vue:5`. It never calls an API and has no backend counterpart —
it is a "fill the textarea with sample text" affordance. 13.1 moves this catalog and its
anti-repeat rule behind a backend `random_template` script provider; until then it is
**public compatibility surface** (users rely on the button) with **zero** migration coupling.

### 13.2 `scene_blueprint` (Scene Blueprint) — state: **ad-hoc**

| aspect | evidence |
|---|---|
| entry points | `POST /api/scenes/generate` (`studio/build_scene_blueprints/routes.py:263`); workflow node `scenes.blueprint` → `adapters/scenes.py:7`; legacy pipeline `_step_scenes` (`studio/pipeline/services.py:403`, wrapper `pipeline/routes.py:1265`) |
| other routes | `GET /api/scenes/templates` (`routes.py:251`), `/api/scenes/webhook-url` (`:257`), `/api/scenes/history` (`:533`), `/api/scenes/<project_id>` (`:565`), `/api/scenes/audio/<source_folder>` (`:579`) |
| inputs | `segments[] (required), script, style, style_prompt, custom_style_notes, full_segments, webhook_url, project_id, parent_id, source_folder, aspect_ratio` (`schemas.py`, `extra="allow"`) |
| outputs | `{scenes[], analysis, style_spec, style_prompt, scene_blueprints, coherence_score, coherence_warnings, coherence_metrics, sfx_report, total_duration, …}` |
| artifacts | `output/scenes/{project_id}/scenes.json` (`routes.py:360`, `services.py:517`) |
| side effects | outbound HTTP to n8n; chapter mode splits into chunks with per-chunk retry; unseeded `random.shuffle` in `_assign_hook_animations` (`pipeline/services.py:384-396`, invoked at `:508`) |
| provider IDs | **none.** A grep for `provider` across `studio/build_scene_blueprints/` returns nothing |
| aliases | none |
| settings/env | `N8N_WEBHOOK_URL` (`config.py:68-70`), `STS_ALLOW_PRIVATE_WEBHOOKS`. **No `settings.json` participation** |
| dispatch branch | the only branch is `should_use_chapters(segments)` → `speech_count > 20` (`chapters.py:31-34`) — a payload-size decision, not a provider decision |
| transport | `studio.webhooks.call_webhook(url, payload, timeout=180, label=…)`; 3 attempts, 2/4/8 s backoff; chapter mode raises the timeout to 300 s |
| owner | 13.4 |

### 13.3 `tts` — state: **platform** (registry present, dispatch still by string)

| aspect | evidence |
|---|---|
| entry points | `POST /api/tts/generate` (`studio/tts/routes.py:625`), `/api/tts/stream` (`:896`), `/api/tts/voices` (`:515`), model download/status, `/api/tts/cache/*`; workflow node `tts.generate` → `adapters/tts.py:7`; legacy `_step_tts` (`services.py:59`) |
| provider IDs | `kokoro`, `inworld` |
| aliases | **none** for TTS; the legacy and canonical IDs are both `kokoro` / `inworld` |
| dispatch | `services.py:77-82` resolves `tts_provider_override → tts_provider → settings.json domains.tts.selected_provider → "kokoro"`, then **branches on the string** at `services.py:103` (`if provider_id == "inworld"`). `tts_registry.get()` at `:84` is only an existence gate plus `.version`/`.kind` reads (`:106`, `:112`) |
| route dispatch | `tts/routes.py:629`, `:517`, `:902` each branch `if provider == "inworld"` |
| registry bypass | **`studio/tts/routes.py` never imports or touches the registry** — a grep for `registry` and `providers import` in that file returns **no matches** |
| settings | `settings.json domains.tts.{selected_provider, per_provider.{kokoro,inworld}}`; legacy `app-config.json` key `sts-tts-provider`; kokoro schema = `voice, speed, lang, blend, blendA, blendB, blendRatio, blendMethod`; inworld = `api_key, voice, model, speed` |
| env | `INWORLD_API_KEY` (side effect — §14.3), `INWORLD_TTS_MODEL`, `INWORLD_TTS_BASE_URL` |
| artifacts | `output/tts/{basename}/{basename}.wav` + `.json`; pipeline `…/voice.wav` + `tts.json`; cache `TMP_DIR/tts/{sha16}.wav` |
| cache key | `sha256(f"{text}|{voice}|{speed:.2f}")[:16]` (`tts/routes.py:854-862`) — **provider is not in the key** (known defect, §8) |
| node config | `engine` is a **static hardcoded list** `["kokoro","inworld"]` (`registry.py:186`); there is no `tts_providers` option source (§15.1) |
| callers | frontend `useTts.js` and `TtsPage.vue`; pipeline `usePipelineForm.js`, `usePipeline.js`, `PipelinePage.vue`, and `VoicePicker.vue`; workflow scheduler through `adapters/tts.py` |
| owner | 15.1, 15.2, 15.3 |

### 13.4 `storyboard` — state: **platform** (registry present, dispatch still by string)

| aspect | evidence |
|---|---|
| entry points | `POST /api/storyboard/generate` (`studio/storyboard/routes.py:283`), `/api/storyboard/grab` (`:490`), status/images/image-models/webhook-url/remove-watermarks; workflow node `storyboard.generate` → `adapters/storyboard.py:54`; legacy `_step_storyboard` (`services.py:530-627`) |
| provider IDs | `gemini_ws`, `wavespeed_webhook`, `wavespeed_direct` |
| aliases | canonical→legacy: `gemini_ws→gemini`, `wavespeed_webhook→webhook`, `wavespeed_direct→direct` (`services.py:550`). The legacy page and single-image route use `gemini` / `webhook`; there is no general reverse-normalization layer |
| dispatch | bulk `routes.py:311-324` uses `provider_override → settings.json selection → gemini_ws`, then branches on `gemini_ws`; single-image `routes.py:603-605` branches on legacy `provider == "gemini"`. **The bulk route ignores its legacy extra field `provider`**, so the pipeline's canonical→legacy value at `services.py:563` does not select the provider; without `provider_override`, the settings selection wins. Adapter branches at `adapters/storyboard.py:21` |
| async transport | WebSocket `/ws/storyboard-gemini-image-grabber`, registered by `gemini_ws.register_runtime(app, sock)` through `call_provider_runtime` when `manifest.kind == "extension"` (`storyboard/providers/__init__.py:36-52`) |
| artifacts | `output/storyboard/{pid}/storyboard.json`, `{scene}/image.{ext}` (versioned), `scene_prompts.json`, thumbnails |
| poll contract | 10 s interval / 30 min timeout; errors count toward completion (`pending = total-ready-errors`) |
| settings | `per_provider.wavespeed_webhook.{webhook_url,image_model}`, `wavespeed_direct.{api_key,image_model}`, `gemini_ws.{auto_type}`; legacy frontend key `sts-storyboard-provider` (default `gemini`) |
| env | `WAVESPEED_API_KEY` seeds `wavespeed_direct.api_key` (`settings_manager.py:94-96`) |
| callers | frontend `StoryboardPage.vue`; pipeline `usePipeline.js`, `useProviderTabs.js`, and `PipelinePage.vue`; workflow scheduler through `adapters/storyboard.py` |
| owner | 14.1, 14.2, 14.4, 14.5 |

### 13.5 `animator` — state: **platform** (registry present, dispatch still by string)

| aspect | evidence |
|---|---|
| entry points | `POST /api/animator/grabber/start` (`animation_routes.py:186`) plus pending/results/upload/status/redownload/history/reconcile/project/thumbnails; WS `/ws/animator-grok-video-grabber` (`animator/routes.py:199`); workflow node `animator.generate` → `adapters/animator.py:64`; legacy `_step_assets` (`services.py:630`) |
| provider IDs | `grok_automa`, `kie_ai` |
| aliases | canonical→legacy in the pipeline: `grok_automa→grok`, `kie_ai→kie-ai` (`services.py:644`). Reverse normalization is local to `GrabberStartRequest.provider_id`: `midjourney→grok_automa`, `grok→grok_automa`, `kie-ai→kie_ai`, and every unknown legacy value→`grok_automa` (`schemas.py:30-36`) |
| dispatch | `animation_routes.py:194` uses `GrabberStartRequest.provider_id` (override or legacy-map result), falls back to `grok_automa` only if that ID is absent from the registry, then branches at `:266`, `:297`, `:314`, `:333`. Despite the comment at `:190`, it **does not read `domains.animator.selected_provider` for selection**. Adapter branches at `adapters/animator.py:28` and `:37` |
| registry bypass | **`animation_routes.py:21`**: `from .providers.kie_ai import generate_image as kie_ai_generate` — direct module import; the registry is never consulted for this call |
| artifacts | `output/animator/{pid}/{scene}/*` (+ `*_thumb.jpg`), `metadata.json`, `grabber_job.json`, legacy `animator.json` |
| poll contract | 10 s interval / **120 min** timeout; `grabber_jobs` JobStore is in-memory, rehydrated from disk on import |
| settings | `per_provider.kie_ai.{api_key,model,resolution}`, `grok_automa.{mode,quality,duration}`; legacy frontend key `sts-asset-provider` (default `grok`). The backend selected value is currently catalog/display state, not route or adapter dispatch input |
| env | `KIE_AI_API_KEY`, `KIE_AI_MODEL` seed `kie_ai` settings (`settings_manager.py:98-104`) |
| dead config | `arguments if provider == "midjourney"` (`animation_routes.py:260`) — `midjourney` is not a registered provider; the branch is unreachable |
| callers | frontend `AssetsPage.vue`, `useAssets.js`, `GrabberControls.vue`, and `AssetCard.vue`; pipeline `usePipeline.js`, `useProviderTabs.js`, and `PipelinePage.vue`; workflow scheduler through `adapters/animator.py` |
| owner | 14.1, 14.3, 14.4, 14.5 |

## 14. The seven mandated items, answered

### 14.1 Dead-interface inventory

Method: exhaustive repo-wide grep for `.synthesize(`, `.submit(`, `.poll(`, and `get_provider`.

| symbol | call sites found | verdict |
|---|---|---|
| `TTSProvider.synthesize` (+ both implementations) | **0** | never executed |
| `StoryboardProvider.submit` / `.poll` (3 implementations) | **0** — the only `.submit(` in the repo is `pool.submit(` (`scheduler.py:535`); the only `.poll(` calls are `subprocess.poll()` (`storyboard/lama_client.py:77,114,152`) | never executed |
| `AnimatorProvider.submit` / `.poll` (2 implementations) | **0** (same evidence) | never executed |
| `get_provider()` — domain factories (`tts/providers/__init__.py:26`, `storyboard/…:26`, `animator/…:26`) | **0 call sites**; only the `def` plus an `__all__` entry at `:57` of each | never executed |
| `get_provider()` — provider factories (`storyboard/providers/gemini_ws/provider.py:89`, `wavespeed_webhook/provider.py:108`, `wavespeed_direct/provider.py:98`, `animator/providers/grok_automa/provider.py:106`, `kie_ai/provider.py:246`) | **0**; `kie_ai/__init__.py:11` merely re-exports it | never executed |

Beware the false positive: `settings_manager.get_provider_settings()` is a **different, live**
function with many call sites. It is not a factory.

What *is* live on provider objects: `.version` / `.kind` metadata (`services.py:106,112`),
`.validate_settings()` (`editor/routes.py:282`, `pipeline/routes.py:129,142,155`),
`.health_check()` (`editor/routes.py:327`), `.settings_schema()` (`editor/routes.py:361`),
`.to_dict()` (`editor/routes.py:368`), and `registry.to_dict()` (`editor/routes.py:247-249`).

**Consequence, frozen:** every `provider.py` body listed above is *unverified code under
first-time test*, not a preserved baseline. The behavior to preserve is the observable output
of the string-branch legacy paths. Owner: 11.4 (contract tests that actually invoke each
previously-unexecuted method), then 14.2 / 14.3 / 15.1 for the domain rewiring.

### 14.2 Selection-store conflict

Two independent stores exist and neither writes to the other. The conflict affects all three
existing provider domains, not only TTS:

| domain | nested selection | legacy frontend selection | actual dispatch readers |
|---|---|---|---|
| TTS | `domains.tts.selected_provider` | `sts-tts-provider` (currently persisted as `inworld`) | nested: pipeline fallback at `services.py:80`; legacy: `useTts.js:142`, `usePipelineForm.js:93`, `SettingsPage.vue:452` and pipeline request construction |
| Storyboard | `domains.storyboard.selected_provider` | `sts-storyboard-provider` (frontend default `gemini`; absent from the current blob) | nested: bulk route fallback at `storyboard/routes.py:315-316`; legacy: `StoryboardPage.vue:28-30`, `usePipeline.js`, `useProviderTabs.js` |
| Animator | `domains.animator.selected_provider` | `sts-asset-provider` (frontend default `grok`; absent from the current blob) | nested: **no generation dispatch reader** (catalog response only at `editor/routes.py:249`); legacy: `usePipeline.js`, `useProviderTabs.js`, Assets UI |

The nested selections are written by `PUT /api/settings/v2` whole-blob replacement
(`editor/routes.py:215-227`). The legacy keys are written independently by `PATCH /api/settings`
through `useSettings.update()` (`useSettings.js:41-49`). Workflow nodes use their saved
`engine` / `provider` configuration and do not inherit any of these default selections.

`settings_manager.set_selected_provider()` (`settings_manager.py:189-198`) exists and has
**zero call sites** — only `__all__` re-exports at `shared/__init__.py:12` and
`providers_common/__init__.py:20,59`.

The frontend selection path is `useProviders.js:66-100`: `GET /api/settings/v2` →
spread-merge a new `selected_provider` → `PUT /api/settings/v2` with the **entire** blob.
`put_settings_v2` calls `save_settings(data)`, a full replace with no `expected_updated_at`
and no field-level merge — a genuine lost-update window between any two concurrent writers.

The current values/defaults happen to agree semantically (`inworld`, `gemini↔gemini_ws`, and
`grok↔grok_automa`), so there is no persisted divergence to repair today. They can silently
diverge on the next write. Animator is worse than a two-store disagreement: selecting it in the
provider modal changes catalog state but does not change legacy route, pipeline, or workflow
dispatch at all.

**Recommendation carried into 10.2 — accepted and frozen in §24:** make
`settings/settings.json` `domains.*.selected_provider` authoritative — it is the intended
backend store, it is already per-domain, and it is the v4 design's stated source of truth.
First wire the missing animator dispatch read. Migrate all three legacy keys by having the legacy
pages read selections from the provider catalog API, keeping read-through fallbacks for one
release, then deleting the keys.
Replace the whole-blob write with a targeted selection endpoint routed through the existing
`set_selected_provider()`. Owners: 10.2 freezes it, 11.5 builds the endpoint, 12.4 moves the
legacy page, 16.1 deletes the loser key.

### 14.3 Env-var side effects

All in `_seed_from_env()` (`settings_manager.py:67-107`), which runs **only when
`settings/settings.json` is absent** (first run):

| env var | effect | line |
|---|---|---|
| `INWORLD_API_KEY` | seeds `per_provider.inworld.api_key` **and flips `domains.tts.selected_provider` to `"inworld"`** | `:85-88` |
| `INWORLD_TTS_MODEL` | seeds `per_provider.inworld.model` | `:90-92` |
| `WAVESPEED_API_KEY` | seeds `per_provider.wavespeed_direct.api_key` | `:94-96` |
| `KIE_AI_API_KEY` | seeds `per_provider.kie_ai.api_key` | `:98-100` |
| `KIE_AI_MODEL` | seeds `per_provider.kie_ai.model` | `:102-104` |
| `STS_SYNC_FOLDER`, `STS_AUTO_SYNC` | seed `general.*` | `:79-83` |

`INWORLD_API_KEY` is the **only** implicit *selection* change; the other four seed values
only. Defaults without env: `kokoro` / `gemini_ws` / `grok_automa`
(`settings_manager.py:148,152,156`).

Separately, a present-but-empty `api_key` is persisted for `kie_ai`, `wavespeed_direct`, and
`inworld` in the live `settings.json`, so "key configured" cannot be inferred from key
presence. Owner: 11.3 (env fallback without returning values), 10.2 (availability states).

### 14.4 Legacy alias tables

Verified verbatim:

- `studio/pipeline/services.py:550` — `id_to_legacy = {"gemini_ws": "gemini", "wavespeed_webhook": "webhook", "wavespeed_direct": "direct"}`, applied at `:551`; consumed at `:552` (`prompt_prefix` only when `sb_provider == "gemini"`) and sent as `payload["provider"]` at `:563` over an **HTTP-to-self** call to `/api/storyboard/generate` (`:566`, blocker B1).
- That storyboard wire value is currently **ignored for dispatch**: `StoryboardGenerateRequest`
  has no model field named `provider` (it is accepted only because `extra="allow"`), its property
  always derives from `provider_override`, and `routes.py:311-316` reads only
  `provider_override` or nested settings. Thus a legacy `provider="webhook"` request can run the
  selected `gemini_ws` provider. Preserve the field as wire compatibility, but owner 14.2 must
  normalize it before dispatch rather than preserving the bug.
- `studio/pipeline/services.py:644` — `id_to_legacy = {"grok_automa": "grok", "kie_ai": "kie-ai"}`, applied at `:645`; consumed at `:664` (`if anim_override == "grok_automa" or provider == "grok"` → grok-specific payload keys).
- `studio/animator/schemas.py:30-36` is the reverse/legacy normalization point:
  `midjourney|grok→grok_automa`, `kie-ai→kie_ai`, and unknown values→`grok_automa`.
- `app.py:248-286` `POST /api/pipeline/preflight` — defaults `storyboard_provider="gemini"` (`:253`) and `asset_provider="grok"` (`:254`), branching at `:266` and `:276` to probe extension connectivity.
- `app.py:198-200` `focus-studio` — `if target == "gemini" … elif target == "grok"`.

Direction matters: the two pipeline tables map **canonical → legacy**; Animator alone also has
the reverse map above. The legacy strings are the wire format of the internal HTTP hop and the
preflight API; the canonical IDs are what the registry and `settings.json` use. Owner: 10.4
(freeze the mapping in both directions),
16.1 (delete once the internal HTTP hop is gone).

### 14.5 Registry bypasses

1. `studio/animator/animation_routes.py:21` — `from .providers.kie_ai import generate_image as kie_ai_generate`, invoked inside `_kie_ai_generate_all`. Violates §8 blocker B8 ("always `registry.get(id)`, never `import`"). Owner: 14.3.
2. `studio/tts/routes.py` — **no registry reference at all**. Every TTS HTTP route dispatches on a raw request string. Owner: 15.2.
3. `studio/workflows/adapters/animator.py:33` reads `settings_manager.get_provider_settings("animator", "kie_ai")` with a **literal provider ID**, hardcoding the adapter to one provider's settings. Owner: 14.3.
4. `studio/storyboard/routes.py` and `animation_routes.py` do call `registry.get()`, but only to validate existence and read settings — dispatch remains the string branch. Owner: 14.2 / 14.3.

### 14.6 Duplicated contracts

`JobHandle` and `JobStatus` are **field-for-field identical** in both files; `SceneResult`
differs only in two field names:

| dataclass | storyboard | animator | identical? |
|---|---|---|---|
| `JobHandle` | `base.py:13-17` — `job_id, status, created_at` | `base.py:12-17` — same | yes |
| `JobStatus` | `base.py:20-28` — `job_id, status, progress, message, result, error` | `base.py:20-28` — same | yes |
| `SceneResult` | `base.py:31-38` — `scene_index, image_url, image_path, thumbnail_url, metadata` | `base.py:31-38` — `scene_index, `**`video_url, video_path`**`, thumbnail_url, metadata` | no — media field renamed |

Related duplication: `studio/<domain>/providers/__init__.py` exists in **three** copies (tts,
storyboard, animator), each exactly 57 lines, structurally identical but **not** byte-identical
(distinct MD5s `2506fb31…`, `941ed83d…`, `64fe87a3…`) because each embeds its domain name and
`init_<domain>_registry` function name.

**Correction to the plan:** step 11.1 says "the four copies of the identical 57-line
`studio/<domain>/providers/__init__.py`". There are **three**, and they are not byte-identical.
The consolidation remains correct; only the count in 11.1 is wrong.

Owner: 11.4 unifies the job dataclasses (one `SceneResult` with a neutral media field plus
domain aliases); 11.1 replaces the three `__init__.py` copies with one shared binding.

### 14.7 Known latent defect — `story` output port

`adapters/story.py:24-27` returns `outputs(script=…, story=with_artifacts(result, path))`.
`registry.py:139` declares only `outputs: [_CONTROL_OUT, _out("script", "script")]`.

**The plan's stated mechanism is wrong and is corrected here.** `_validate_outputs`
(`scheduler.py:958-967`) iterates the **declared** ports and raises `NODE_OUTPUT_MISSING` when
one is absent. It never inspects undeclared keys, so it does **not** drop `story`.
What actually happens:

- `story` survives into `node_outputs[node_id]` (`scheduler.py:729`).
- `_artifact_refs` (`scheduler.py:217-228`) recurses over *all* values, so
  `output/stories/{pid}/story.json` **does** reach `node_record.artifact_refs`
  (`scheduler.py:731`) and the execution record. The plan's "its artifact refs never reach a
  port" is inaccurate for the record; it is accurate that they reach no *port*.
- The payload is nonetheless **unreachable by any consumer**: no edge may target it (edge ports
  must be registry port IDs, §4.1), and static expression validation rejects it —
  `expressions.py:131-134` looks the port up in `get_node_type(...)["outputs"]` and emits
  `EXPRESSION_OUTPUT_MISSING`. Runtime `resolve_configuration` (`expressions.py:160`) would
  return it happily, but validation never lets execution get that far.

Net effect: dead weight in the output dict plus a misleading artifact ref attributed to a port
that does not exist. Severity is low; the remedy in 13.3 (declare the port **or** fold the
artifacts into `script`) is unaffected. Owner: **13.3**, which must also drop the
"`_validate_outputs` drops it" wording and replace the hardcoded `"provider": "gemini"` at
`studio/story/service.py:102`.

## 15. Hard-coded provider decision register

Backend and frontend production decisions on provider/engine literals. Tests excluded. A row may
group several branches in one component; each has an owner.

| # | location | branch | owner |
|---|---|---|---|
| P1 | `app.py:198` | `target == "gemini"` (focus-studio) | 16.1 |
| P2 | `app.py:200` | `target == "grok"` | 16.1 |
| P3 | `app.py:266` | `storyboard_provider == "gemini"` (preflight) | 14.4 |
| P4 | `app.py:276` | `asset_provider == "grok"` (preflight) | 14.4 |
| P5 | `pipeline/services.py:91` | `provider_id == "inworld"` (voice-key selection) | 15.2 |
| P6 | `pipeline/services.py:103` | `provider_id == "inworld"` (dispatch) | 15.2 |
| P7 | `pipeline/services.py:550-552` | storyboard alias table + `sb_provider == "gemini"` | 14.2 |
| P8 | `pipeline/services.py:644-645`, `:664` | animator alias table + `provider == "grok"` | 14.3 |
| P9 | `pipeline/routes.py:325` | `tts_provider == "inworld"` (voice default) | 15.2 |
| P10 | `pipeline/routes.py:630` | `provider == "grok"` | 14.3 |
| P11 | `pipeline/routes.py:1051` | `storyboard_provider == "gemini"` | 14.2 |
| P12 | `animator/animation_routes.py:260` | `provider == "midjourney"` — **unreachable**, no such provider | 14.3 (delete) |
| P13 | `animator/animation_routes.py:266` | `provider_id == "grok_automa"` | 14.3 |
| P14 | `animator/animation_routes.py:297` | `provider_id == "kie_ai"` | 14.3 |
| P15 | `animator/animation_routes.py:314` | `provider_id == "grok_automa"` | 14.3 |
| P16 | `animator/animation_routes.py:333` | `provider_id == "kie_ai"` | 14.3 |
| P17 | `workflows/adapters/storyboard.py:21` | `provider == "gemini_ws"` | 14.2 |
| P18 | `workflows/adapters/animator.py:28` | `provider == "kie_ai"` | 14.3 |
| P19 | `workflows/adapters/animator.py:37` | `provider == "kie_ai"` | 14.3 |
| P20 | `workflows/adapters/animator.py:33` | literal `"kie_ai"` settings lookup | 14.3 |
| P21 | `tts/routes.py:517` | `provider == "inworld"` (voice list) | 15.2 |
| P22 | `tts/routes.py:629` | `provider == "inworld"` (generate) | 15.2 |
| P23 | `tts/routes.py:902` | `provider == "inworld"` (stream reject) | 15.2 |
| P24 | `storyboard/routes.py:324` | `provider_id == "gemini_ws"` | 14.2 |
| P25 | `storyboard/routes.py:605` | `provider == "gemini"` (grab-one, legacy string) | 14.2 |
| P26 | `workflows/registry.py:186` | `engine` static list `["kokoro","inworld"]` — the only domain whose node has no `options_source` | 12.3 / 15.2 |
| P27 | `workflows/registry.py` storyboard + animator config | `display_options.show.provider: ["gemini_ws"]` / `["grok_automa"]` provider-specific field gating | 12.3 |
| P28 | `editor/routes.py:236-238, 260-262, 305-307, 342-344, 397-399` | five handlers each re-importing the three registries and building a literal `{tts,storyboard,animator}` dict | 11.5 |
| P29 | `providers_common/registry.py:177` | `VALID_DOMAINS = {'tts','storyboard','animator'}` | 11.1 |
| P30 | `providers_common/settings_manager.py:270` | duplicate `valid_domains = {"tts","storyboard","animator"}` | 11.1 |
| P31 | `providers_common/settings_manager.py:137-160` | `_default_settings()` hardcodes the same three domains and their default provider IDs | 11.1 / 11.3 |
| P32 | `workflows/options.py:38-50` | `_provider_options(domain)` handles only `storyboard` / `animator` | 12.2 |
| P33 | `story/service.py:102`, `story/routes.py:287` | literal `"provider": "gemini"` in result metadata | 13.3 |
| P34 | `animator/schemas.py:20, 30-36` | legacy default plus `midjourney/grok/kie-ai` normalization and unknown→Grok fallback | 14.3 / 14.4 |
| P35 | `frontend/src/features/settings/composables/useSettings.js:12-14` | legacy defaults for all three domains | 12.4 / 16.1 |
| P36 | `frontend/src/features/tts/composables/useTts.js:142,390,661` | legacy TTS selection and Inworld generation branch | 12.4 / 15.2 |
| P37 | `frontend/src/features/pipeline/composables/usePipelineForm.js:93-107,155` | legacy TTS selection, voice routing, and Inworld voice loading | 12.4 / 15.2 |
| P38 | `frontend/src/features/pipeline/views/PipelinePage.vue:117-125,412,541-545` | TTS preview and niche/preset behavior branch on Inworld | 12.4 / 15.2 |
| P39 | `frontend/src/features/pipeline/components/VoicePicker.vue:18` | Inworld-specific picker UI | 12.4 / 15.2 |
| P40 | `frontend/src/features/storyboard/views/StoryboardPage.vue:28-30,350-411,535,572` | legacy `gemini` / `webhook` selection, payload, and UI branches | 12.4 / 14.2 |
| P41 | `frontend/src/features/pipeline/composables/useProviderTabs.js:15,29,50-55` | legacy Gemini/Grok tab focus and extension reachability | 14.4 / 16.1 |
| P42 | `frontend/src/features/pipeline/composables/usePipeline.js:190-202,236-245,292-301` | reads and sends all three legacy provider selections/defaults | 12.4 / 14.2 / 14.3 / 15.2 |
| P43 | `frontend/src/features/assets/composables/useAssets.js:19,115,314` | legacy Grok default and request field | 12.4 / 14.3 |
| P44 | `frontend/src/features/assets/views/AssetsPage.vue:413-434` | Grok-specific submit/retry behavior | 12.4 / 14.3 |
| P45 | `frontend/src/features/assets/components/GrabberControls.vue:7,39-41,183` | Midjourney/Grok/Kie-specific controls and label | 12.4 / 14.3 |
| P46 | `frontend/src/features/assets/components/AssetCard.vue:11` | legacy Grok provider default | 12.4 / 14.3 |
| P47 | `frontend/src/features/settings/views/SettingsPage.vue:452` | Inworld-vs-Kokoro implementation label | 12.4 / 15.2 |

### 15.1 Parameterized option sources — the blocker for 15.2

`GET /api/workflow/options/<source>` resolves `resolve_options(source)`
(`studio/workflows/options.py:108`), which takes **exactly one argument** and passes no
context. `_RESOLVERS` (`options.py:64-72`) has seven entries and must stay in lockstep with
`ASYNC_OPTION_SOURCES` (`registry.py:30-34`) — enforced by the module-level assert at
`options.py:75-77`.

Consequence today: `_tts_voices()` (`options.py:19-21`) returns `studio.tts.routes.VOICES`, a
static Kokoro list, regardless of the selected engine, so an Inworld node still offers Kokoro
voice IDs. There is no `tts_providers` source at all. `allowed_option_values`
(`options.py:85-105`) caches per source for the process lifetime and fails open. Owner: 10.2
froze the extended envelope in **§23**, 12.2 implements it, 15.2 consumes it.

## 16. Never-executed provider code paths — owner assignment

| path | files | owner |
|---|---|---|
| `TTSProvider.synthesize` + `list_voices` + `shutdown` | `tts/providers/base.py`, `kokoro/provider.py`, `inworld/provider.py` | 11.4 (first test), 15.1 (bring onto Contract v2) |
| `StoryboardProvider.submit`/`poll`/`generate_one` | `storyboard/providers/base.py` + 3 providers | 11.4, 14.2 |
| `AnimatorProvider.submit`/`poll`/`open_url` | `animator/providers/base.py` + 2 providers | 11.4, 14.3 |
| 3 domain `get_provider()` factories | `<domain>/providers/__init__.py:26` | 11.1 (replace with hub resolution) |
| 5 provider `get_provider()` factories | the five `provider.py` files in §14.1 | 11.2 (factory instantiation) |
| duplicate Kokoro singletons `kokoro_instance` / `kokoro_lock` / `generation_inference_lock` (never populated; the live ones are in `tts/routes.py`) | `tts/providers/kokoro/provider.py` | 15.1 (blocker B5 / K1 — collapse to one owner) |

## 17. Compatibility surface vs internal debt

### 17.1 Public compatibility surface (must keep working)

HTTP: `/api/story/*`, `/api/scenes/*`, `/api/tts/*`, `/api/storyboard/*`, `/api/animator/*`,
`/api/providers*`, `/api/settings/v2`, `/api/pipeline/*`, `/api/workflow/*`.
Wire formats: the five request schemas; the legacy alias strings on the internal HTTP hop and
preflight; `sts-tts-provider`, `sts-storyboard-provider`, and `sts-asset-provider` in
`app-config.json` until migrated. The Storyboard bulk route's ignored legacy `provider` field is
accepted compatibility input, but its failure to affect dispatch is debt (§14.4), not behavior to
preserve.
Files: `output/stories/*/story.json`, `output/scenes/*/scenes.json`, `output/tts/*`,
`output/storyboard/*/storyboard.json`, `output/animator/*/{grabber_job,metadata}.json`,
`settings/settings.json` v1 shape.
Workflow: node type IDs, `type_version: 1`, port IDs, and saved node `configuration` keys
(`engine`, `provider`, `webhook_url`, `style`, …) — old workflows must run unedited.
UI: the random-story button, the provider gear modal, the per-domain selectors.
Transports: the two WebSocket URLs (`/ws/storyboard-gemini-image-grabber`,
`/ws/animator-grok-video-grabber`). Browser extensions are versioned independently and cannot
be migrated in lockstep, so these paths and their message types are frozen.

### 17.2 Internal debt (free to change)

The ABC layer and all eight `get_provider()` factories; the three duplicated
`providers/__init__.py`; the duplicated job dataclasses; the string-branch dispatch (P1–P25);
the two hardcoded domain sets (P29, P30); the provider API living in the editor blueprint
(P28); the whole-blob settings write; the internal HTTP-to-self hop (B1); the unreachable
`midjourney` branch (P12); the duplicate Kokoro singletons; the undeclared `story` port; and the
ignored Storyboard legacy selection. The legacy selection keys themselves remain public until
migration even though the duplicate storage design is debt.

### 17.3 Pre-existing defects reconfirmed (not introduced by this migration)

TTS cache key omits provider (`tts/routes.py:854-862`); double loudnorm on cache hit;
storyboard poll counts errors as completion; `_step_scenes` has no stop check;
`midjourney` / `meta_ai` are URL strings, not providers. These stay on the §8 list.

### 17.4 Live-provider availability (gates fixture work)

The WaveSpeed key returns 401; the hosted n8n webhook is retired; OpenRouter's balance is
negative; `grok_automa` requires a human driving a browser; `kie_ai` is the only pinned working
cloud animator. Only Kokoro TTS runs offline end-to-end. Tests marked `@pytest.mark.live` skip
unless `STS_LIVE=1`. Every Phase 11–15 contract test must therefore be fixture-backed.
Owner: 10.4.

### 17.5 Test coverage baseline for the migrated surface

`tests/test_workflow_adapters.py` covers the TTS adapter port mapping and both async adapters'
typed outputs and failure codes with mocked services. `tests/test_scene_generation_v2.py`
covers blueprint planning and annotation. `tests/test_story_routes.py` covers only
classify-webhook derivation — **story generation itself has no test**.
`tests/test_live_providers.py` is live-gated. No test invokes any ABC method. Frontend tests do
not freeze the provider-specific branches P35-P47 or the legacy-selection mappings.
Owner: 11.4 (contract tests), 13.2 (story fixtures).

### 17.6 Divergences from `modular-providers-plan-v4.md`

| v4 said | this plan | resolution |
|---|---|---|
| three domains (`tts`, `storyboard`, `animator`) | five (`+script`, `+scene_blueprint`) | five; the domain catalog becomes data (11.1) |
| "temporary flat↔nested settings adapter, deleted in Phase 9" | no such adapter exists in the tree | dropped; `settings_adapter.py` is absent from `providers_common/` |
| "Discovery: on restart only. No hot reload." | dev hot-reload required (11.2) | 11.2 wins, guarded by `STS_WORKFLOW_DEV_RELOAD` |
| "Pipeline stops knowing provider names" | it still knows them (P5–P11) | unmet goal, now owned by 14.x / 15.x |
| `docs/provider-template/` scaffolds | absent; `providers_common/scaffold.py` (341 lines) exists instead | keep `scaffold.py`; 16.2 owns the kit |
| idle-shutdown deferred to Phase 9 | not in this plan | out of scope |

v4's vocabulary is otherwise adopted unchanged: *manifest*, *capabilities*, *runtime hook*,
*broken-provider isolation*, and *rich job snapshots* (already implemented as `job_meta` in
`services.py`), plus *per-domain provider folders*.

### 17.7 Out of scope — Music and Captions (confirmed working, not migrated)

Neither has a `providers/` package, a provider ID, or any dispatch branch. Music is
`studio/music/selector.py` (`select_music`, `select_random_music`, `recall_last_music`) with a
10-entry history; Captions is `studio/captions/routes.py` (`_group_words_into_captions`,
`CAPTION_PRESETS`). Both are consumed by the `music.select` / `captions.generate` nodes and by
Assemble. They touch the provider platform at exactly two points, both of which must keep
resolving: the `caption_presets` and `story_tones` option sources (`options.py:53-61` and
`:24-26` — the latter reads `studio.music.selector.TONE_MUSIC_MAP`). No migration work;
regression-only.

## 18. Coverage assertion

Every path that reaches a model or provider was enumerated: five domains × {legacy HTTP route,
legacy pipeline step, workflow adapter}, plus the WebSocket transports, the internal
HTTP-to-self hop, the preflight probe, the provider settings/health API, and the legacy frontend
pages/settings consumers. The four
never-provider-driven surfaces (frontend story templates, scene blueprint, music, captions) are
explicitly accounted for. The unexecuted provider path groups (§16) and forty-seven hardcoded
provider-decision entries (§15) each carry an owner step. No item in §13–§17 is left without
an owner.

Open decisions deliberately deferred: the authoritative selection store (recommendation in
§14.2 → **now frozen in §24**), the parameterized option-source envelope (§15.1 → **now frozen
in §23**), the unified job/result/error contract (§14.6 → 10.3), and fixture ownership
(§17.4 → 10.4).

---

# Provider Contract v2 (Phase 10.2 frozen)

> Produced by step 10.2 of [implementation-plan.md](implementation-plan.md).
> Grounded in code at commit `e79ac1c` (2026-08-08); §13–§18 above is the audit this
> contract is built on. Every `file:line` reference was read at that commit.
>
> **Reuse rule.** This contract *extends* the shipped
> `studio/shared/providers_common/` (registry, manifest, settings manager, discovery,
> migrations, runtime hooks, broken-provider isolation). Nothing here authorizes a parallel
> framework. Where v2 differs from today's code the delta is stated with an owner step, so
> Phase 11 is a set of edits to existing modules, never a rewrite.
>
> **What 10.2 does not freeze.** Invocation context, request/result envelopes, job handles,
> and `ProviderError` belong to 10.3. Legacy field/alias mapping tables and fixtures belong
> to 10.4. This section stops at *what a provider is, how it is found, how it is configured,
> and what the browser may see*.

## 19. Domains, packages, identity

### 19.1 Domain catalog — data, not code

Exactly **five** domains are supported. Music and Captions are excluded by owner decision
(§17.7) and have no `DomainSpec`.

| domain id | label | provider package | discovery base | default provider | legacy selection key |
|---|---|---|---|---|---|
| `script` | Script / Story | `studio.story.providers` | `studio/story/providers` | `random_template` | *(none)* |
| `scene_blueprint` | Scene Blueprint | `studio.build_scene_blueprints.providers` | `studio/build_scene_blueprints/providers` | `n8n_webhook` | *(none)* |
| `tts` | Text to Speech | `studio.tts.providers` | `studio/tts/providers` | `kokoro` | `sts-tts-provider` |
| `storyboard` | Storyboard | `studio.storyboard.providers` | `studio/storyboard/providers` | `gemini_ws` | `sts-storyboard-provider` |
| `animator` | Animator | `studio.animator.providers` | `studio/animator/providers` | `grok_automa` | `sts-asset-provider` |

The catalog lives in **one** new module, `studio/shared/providers_common/domains.py`,
exporting `DOMAINS: dict[str, DomainSpec]` in the declaration order above.

```python
@dataclass(frozen=True)
class DomainSpec:
    id: str                      # catalog key; also settings.json domains.<id>
    label: str                   # human label for the provider modal
    package: str                 # dotted import path of the provider package
    providers_base: str          # absolute path, built with os.path.join(ROOT_DIR, ...)
    default_provider: str        # last-resort selection; must exist after discovery
    capability_vocabulary: frozenset[str]   # §20.4
    legacy_selection_key: str | None        # app-config.json key being retired (§24)
    request_model: str | None = None        # dotted path — filled by 10.3
    result_model: str | None = None         # dotted path — filled by 10.3
```

Adding a sixth domain is one `DomainSpec` entry plus a provider folder. It must not require
editing the registry class, the settings manager, a route, or a Vue component.

**This catalog replaces both hardcoded three-domain sets.** `ProviderRegistry.VALID_DOMAINS`
(`registry.py:177`, P29) becomes `frozenset(DOMAINS)`; the duplicate `valid_domains`
in `settings_manager.validate_settings` (`settings_manager.py:270`, P30) reads the same
constant; `_default_settings()` (`settings_manager.py:137-160`, P31) is generated by
iterating `DOMAINS` instead of listing three literals. Owner: **11.1**, in one step, so the
two can never drift again. A test must assert all three derive from `DOMAINS` and that
`settings.json` accepts every catalog domain.

### 19.2 Package layout (frozen)

```
studio/<module>/providers/
  __init__.py            one shared binding (§27) — not a per-domain copy
  <provider_id>/
    manifest.py          REQUIRED — def manifest() -> ProviderManifest
    provider.py          optional — factory + validate_settings + health_check + impl
    settings_schema.py   optional — def settings_schema() -> dict
    __init__.py          optional; MUST NOT be required for discovery
```

Discovery keys on `manifest.py` only (`registry.py:246-249`); folders starting with `_` or
`.` are skipped (`registry.py:243`). Modules are loaded from file paths under synthetic names
`_sts_provider_{domain}_{id}_{manifest|provider|schema}` (`registry.py:273`), which is why
blocker **B8** stands: consumers resolve providers with `registry.get(id)` and never `import`
a provider module. `kie_ai/__init__.py` re-exporting `get_provider` (§14.1) is the one
existing violation and is deleted by 14.3.

Provider folders stay owned by their module. One hub (§27) exposes all domain registries;
it does not move the folders.

### 19.3 Provider identity and versions (frozen)

| field | rule |
|---|---|
| `id` | `^[a-z][a-z0-9_]{1,31}$`; **must equal the folder name** (already enforced, `registry.py:320-323`); unique within its domain. The registry key is the pair `(domain, id)` — the same id may exist in two domains. |
| `aliases` | **new, optional** `list[str]`, same charset as `id`. Legacy wire strings (`gemini`, `webhook`, `direct`, `grok`, `kie-ai`, `midjourney`) move here, retiring the hand-written tables at `pipeline/services.py:550`/`:644` and `animator/schemas.py:30-36` (P7, P8, P34). Resolution order: exact `id` first, then alias. An alias that collides with a real id **loses**, and the collision is logged WARN and recorded in `excluded()` metadata. Aliases are never written to settings and never returned as `selected`. The concrete mapping table is 10.4's deliverable; 10.2 freezes only the mechanism. |
| `version` | semver `MAJOR.MINOR.PATCH`, the *implementation* version. Informational: it is never used to gate compatibility, and it is carried into result provenance (10.3). |
| `contract_version` | **new, optional** `int`, default `2`. `1` = the legacy ABC shape (all seven providers today; never executed, §14.1/§16). The registry loads both; only `2` may be invoked through the 10.3 invocation contract. A value above the build's maximum excludes the provider with reason `MANIFEST_UNSUPPORTED_CONTRACT`. |
| `domain` | must equal the owning registry's domain or registration is refused (`registry.py:196-199`). |

Provider IDs in node configurations and `settings.json` are **canonical ids only**; legacy
strings are accepted on input and normalized through the alias table (§8, "registry ids are
canonical").

## 20. Manifest contract

### 20.1 Fields

`ProviderManifest` (`registry.py:17-27`) is the frozen carrier. Required and optional fields:

| field | required | type | default | notes |
|---|---|---|---|---|
| `id` | yes | str | — | §19.3 |
| `label` | yes | str | — | shown in the provider modal and every dropdown |
| `domain` | yes | str | — | must be a `DOMAINS` key |
| `kind` | yes | enum | — | `local` \| `cloud` \| `extension` \| `webhook` (§20.2) |
| `version` | yes | str | — | semver |
| `capabilities` | yes | `dict[str,bool]` | — | **must be non-empty**: `registry.py:314-318` treats a falsy value as missing, so `capabilities={}` silently excludes the provider. This trap is frozen as-is and documented in the author guide (owner 16.2). |
| `requires` | no | `list[str]` | `[]` | settings **key names** that must be non-empty for the provider to be usable (§21.5). Never values. |
| `open_url` | no | `str \| None` | `None` | URL the UI may offer to open for `extension` providers |
| `aliases` | no | `list[str]` | `[]` | new (§19.3); owner 11.2 |
| `contract_version` | no | `int` | `2` | new (§19.3); owner 11.2 |
| `description` | no | `str \| None` | `None` | new; one sentence, browser-safe |
| `docs_url` | no | `str \| None` | `None` | new; must be `http(s)` |

### 20.2 `kind` semantics (frozen)

- `local` — runs in-process, no network (today: `kokoro`). May own heavy singletons; must
  implement `shutdown()`.
- `cloud` — outbound HTTPS to a third-party API with credentials in settings (today:
  `inworld`, `wavespeed_direct`, `kie_ai`).
- `webhook` — outbound HTTP to a user-supplied URL, validated by `is_safe_webhook_url`
  (today `wavespeed_webhook` is declared `cloud`; 14.2 reclassifies it).
- `extension` — needs a browser extension and a WebSocket runtime; the **only** kind whose
  `register_runtime(app, sock)` is called at boot (`<domain>/providers/__init__.py:47-52`)
  (today: `gemini_ws`, `grok_automa`). The two WS URLs are frozen public surface (§17.1).

### 20.3 Validation and unknown-field policy (frozen)

Manifest validation runs at discovery, in this order — each failure excludes only that
provider (§21.4):

1. `manifest.py` imports without raising.
2. A module-level `manifest` attribute exists and is callable.
3. `manifest()` returns a `ProviderManifest` **or** a dict coercible to one.
4. All required fields of §20.1 are present and truthy.
5. `manifest.id == folder name`.
6. `manifest.domain` is a `DOMAINS` key and matches the owning registry.
7. `kind` is in the §20.2 enum; `version` parses as semver; `capabilities` values are `bool`.
8. `contract_version` ≤ the build's maximum.

**Unknown fields — the one behavioral change here.** Today `ProviderManifest(**dict)` raises
`TypeError` on any unrecognized key and the provider is excluded (`registry.py:304-309`), so a
provider folder written against a newer build cannot load on an older one. Frozen v2 policy:
unknown top-level manifest keys are **ignored, logged WARN once, and surfaced** in the
provider's browser payload as `warnings: ["unknown manifest field: <name>"]`. Unknown
*capability* keys and unknown *`kind`* values follow the same ignore-and-warn rule, except
that an unknown `kind` falls back to `cloud` for scheduling purposes and never to `extension`
(so an unrecognized provider can never claim a WebSocket route). Steps 7 and 8 above remain
hard failures because they are identity, not vocabulary. Owner: **11.2**.

### 20.4 Capability vocabulary (frozen)

Capabilities are declarative booleans the platform and UI may branch on **generically** — they
are the replacement for branching on a provider id. Values must be `bool`; a missing key means
`False`. Each domain's `DomainSpec.capability_vocabulary` is the closed set for that domain;
unknown keys are ignored and warned (§20.3).

Shared by all five domains:

| capability | meaning | in use today |
|---|---|---|
| `test_connection` | `health_check` performs a real probe worth exposing as a button | all seven |
| `single_scene` | can produce one unit in isolation (one scene, one take) | all seven |
| `batch` | can accept a multi-unit request | all seven |
| `async_job` | returns a job handle and is polled rather than returning inline | storyboard + animator providers (implicit today) |
| `push_callbacks` | pushes progress over an existing transport instead of being polled | `gemini_ws` |
| `cancel` | honors the cancellation token | none yet (10.3 defines the token) |
| `progress` | reports fractional progress, not just terminal states | none yet |

Domain-specific additions:

| domain | capabilities |
|---|---|
| `script` | `structured_sections` (returns hook/build/climax/cta), `language_select`, `offline` (no network — the `random_template` provider from 13.1) |
| `scene_blueprint` | `chaptering` (can split oversized inputs, cf. `chapters.py:31-34`), `coherence_scoring`, `sfx_report` |
| `tts` | `streaming`, `voice_list`, `voice_blend`, `speed_control`, `model_download` |
| `storyboard` | `image_edit`, `watermark_removal`, `prompt_prefix` |
| `animator` | `image_to_video`, `duration_control`, `resolution_select` |

`streaming`, `voice_list`, and `model_download` are already declared by the shipped TTS
manifests; the rest are frozen names for capabilities that exist in the legacy code as
provider-id branches (P5–P25) and become declarative during Phases 14–15.

## 21. Lifecycle, discovery, and isolation

### 21.1 Lifecycle hooks (frozen)

| phase | hook | when | failure policy |
|---|---|---|---|
| discover | *(none — filesystem scan)* | once per process, or on dev reload under `STS_WORKFLOW_DEV_RELOAD` | per-provider exclusion |
| describe | `manifest()` | discovery | exclusion |
| describe | `settings_schema()` | lazy, first request, memoized (`registry.py:107-117`) | returns `None`, WARN; provider still listed with `has_settings: false` |
| configure | `validate_settings(settings) -> list[dict]` | on save, on select, on demand | exception → single root `error` issue (`registry.py:133-135`) |
| probe | `health_check(settings) -> dict \| str \| HealthResult` | explicit user action or TTL cache (§21.5) | exception → `HealthResult(status="fail", message=str(e))` (`registry.py:154-156`) |
| construct | **`create(context) -> Provider`** (new v2 factory) | lazily, at first invocation | exception → `ProviderError` at the registry boundary (10.3); provider marked `degraded` |
| serve | domain-specific invocation | per request | 10.3 |
| bind | `register_runtime(app, sock)` | once at boot, `kind == "extension"` only | caught and logged (`runtime.py:63-65`); boot continues |
| release | `shutdown()` | registry teardown, dev reload, process exit | best-effort; exceptions logged, never raised; **must be idempotent** |

The v2 factory replaces the eight zero-argument `get_provider()` functions, none of which has
ever executed (§14.1, §16). Frozen rules: `create()` is called **at most once per
`(domain, provider_id)` per process**, memoized under the registry lock, never at import time,
and never during discovery — so importing a provider package can never start a model load, a
thread, or a socket. `context` is the invocation context frozen by 10.3. Owner: **11.2**.

`shutdown()` today exists on `Runtime` (`runtime.py:45-47`) and on `TTSProvider` with **zero
callers**. v2 requires the registry to call it for every constructed provider on teardown, in
reverse construction order. Owner: **11.2**.

### 21.2 Registration and discovery order (frozen)

1. Domains initialize in `DOMAINS` declaration order: `script`, `scene_blueprint`, `tts`,
   `storyboard`, `animator` — replacing the fixed three-call sequence at `app.py:90-95`.
2. Within a domain, providers are loaded in **`sorted()` order of folder name**. Today
   `os.listdir` order is used unsorted (`registry.py:239`); sorting is required so discovery
   logs, catalog responses, and "first wins" duplicate resolution are deterministic.
   Owner: **11.1**.
3. Discovery is idempotent — a second `discover()` on a registry that already scanned is a
   no-op (`<domain>/providers/__init__.py:20-23`). Dev reload explicitly resets the flag after
   calling `shutdown()` on constructed providers.
4. Extension runtimes bind after **all** domains have been discovered, never interleaved with
   discovery, so a runtime can rely on the full catalog being present.
5. Registration never touches `app.py` or `studio/workflows/registry.py`.

### 21.3 Duplicate IDs (frozen)

Within a domain, **first registration wins**; the later one is skipped with a WARN
(`registry.py:202-205`, already correct) and recorded as an exclusion with reason
`DUPLICATE_ID`. Cross-domain duplicates are legal (the key is `(domain, id)`). An alias that
duplicates any real id in the same domain is dropped, not the provider. Duplicate registration
must never raise, must never replace the incumbent, and must never abort discovery.

### 21.4 Broken-plugin isolation (frozen)

Every exclusion is *local*: it logs a WARN and continues. A broken provider must never
(a) abort discovery, (b) abort application startup, (c) hide or unregister a healthy provider,
or (d) leak a stack trace or filesystem path into an API response.

Frozen exclusion reason codes, all currently implemented as bare log lines
(`registry.py:278-323`):

| code | condition | current line |
|---|---|---|
| `MANIFEST_LOAD_FAILED` | spec/loader is `None`, `SyntaxError`, `ImportError`, or any other exception importing `manifest.py` | `:278`, `:284`, `:287`, `:290` |
| `MANIFEST_MISSING` | no `manifest` attribute | `:294` |
| `MANIFEST_RAISED` | `manifest()` raised | `:300` |
| `MANIFEST_INVALID_TYPE` | not a `ProviderManifest` and not a coercible dict | `:308`, `:311` |
| `MANIFEST_FIELDS_MISSING` | a required field is absent or falsy | `:317` |
| `MANIFEST_ID_MISMATCH` | `manifest.id != folder` | `:321` |
| `MANIFEST_DOMAIN_MISMATCH` | wrong domain | `:197` |
| `MANIFEST_UNSUPPORTED_CONTRACT` | `contract_version` too new | new (§19.3) |
| `DUPLICATE_ID` | id already registered | `:203` |

**Exclusions become data, not just logs.** `ProviderRegistry.excluded() -> [{id, reason_code,
message}]` is new and is surfaced in `to_dict()` so the provider modal can show "3 providers
loaded, 1 excluded" instead of the current silent disappearance. `message` is truncated to
200 characters, stripped to a basename if it contains a path, and passed through
`redact_settings` semantics. Owner: **11.2**.

**Partial degradation.** When `manifest.py` loads but `provider.py` does not, the provider is
still registered and its callables fall back across modules (`_resolve`, `registry.py:73-81`,
warned at `:335`). Frozen: this state is `availability: "degraded"` (§21.5) with a warning
string, not a silent success. A degraded provider may be listed and configured but must not be
constructed or invoked.

### 21.5 Availability vs health (frozen)

Two orthogonal axes. Conflating them is the current bug source: `useProviders.selectProvider`
runs a *validation* call to decide whether a provider "needs configuration"
(`useProviders.js:71`), while the catalog exposes no state at all.

**Availability** — cheap, synchronous, no network, safe to compute on every catalog request:

| state | meaning |
|---|---|
| `available` | registered, `provider.py` loaded, every `requires` key non-empty after env fallback |
| `needs_configuration` | registered and loadable, but a `requires` key is empty |
| `degraded` | registered, but `provider.py` or `settings_schema.py` failed to load, or `create()` previously raised |
| `unavailable` | discovered but excluded (§21.4); present only in the `excluded[]` list |

**Health** — may perform I/O; runs on explicit user action (`POST /api/providers/<d>/<p>/test`)
or from a TTL cache. Frozen states are exactly today's values: `ok`, `warn`, `fail`, `unknown`
— the first three are what the seven shipped `health_check` bodies return
(`kokoro/provider.py:295-300`, `inworld/provider.py:195-210`, `gemini_ws/provider.py:80`,
`wavespeed_webhook/provider.py:91-102`, `wavespeed_direct/provider.py:90-92`,
`grok_automa/provider.py:97`, `kie_ai/provider.py:227-240`), and `unknown` is the registry's
coercion default (`registry.py:146`). `HealthResult` fields stay
`status, latency_ms, message, details` (`registry.py:30-36`); `details` is passed through
redaction before it leaves the process.

Two frozen corrections: a provider with **no** `health_check` returns `unknown`, not the
current `ok` (`registry.py:157`) — no live provider hits that branch today, since all seven
define the hook, so this is safe. And health **never blocks** selection or execution: a `fail`
provider may still be selected, with the failure surfaced as a warning. Owner: **11.3**.

"Configured" is computed from `requires` after env fallback, never from key presence: the
live `settings.json` stores present-but-empty `api_key` values for `kie_ai`,
`wavespeed_direct`, and `inworld` (§14.3).

## 22. Settings contract

### 22.1 Schema shape

`settings_schema()` returns a JSON-Schema subset object — `{"type": "object", "properties":
{...}, "required": [...]}` — exactly the shape shipped today
(`tts/providers/inworld/settings_schema.py`). Per-property keys: `type`
(`string|number|integer|boolean`), `label`, `description`, `default`, `minimum`, `maximum`,
`multipleOf`, `enum`, and `ui`.

### 22.2 Widget vocabulary (frozen)

| `ui.type` | rendered today | source |
|---|---|---|
| *(absent)* | text input (or number input when `type` is numeric) | fallback |
| `password` | masked input, marked required | `ProviderSettingsForm.vue:30,138` |
| `dropdown` / `select` | select from `ui.options` (strings or `{value,label}`) | `:33-36,46-55` |
| `slider` | range using `minimum`/`maximum`/`multipleOf` | `:38-40,57-67` |
| `toggle` | checkbox | `:42-44` |
| `textarea` | **new** — multi-line text | owner 12.4 |

An unrecognized `ui.type` falls back to a text input and adds a warning; it is never an error.
This is the settings-form counterpart of §20.3.

### 22.3 Conditional fields (frozen)

`ui.show_if: {field_name: [allowed_values]}` — identical semantics to the workflow node
`display_options.show` already in the registry (`registry.py:263,288`): **AND** across keys,
**OR** within a list. Frozen behavior for a hidden field: its stored value is **preserved**,
it is **not** validated as required, and it is **not** sent in the invocation config. The
renderer is new work (owner **12.4**); the shape is frozen now because 15.2 needs it for
provider-specific TTS fields.

### 22.4 Dynamic options in provider settings (frozen)

`ui.options_source: {"source": "<allowlisted id>", "context": {...}}` resolves through the
same envelope as workflow node fields (§23). This is the mechanism that lets the Inworld voice
list appear in the provider modal without a Vue edit. `ui.options` and `ui.options_source` are
mutually exclusive; if both are present, `options_source` wins and a warning is recorded.

### 22.5 Validation, severities, and unknown keys (frozen)

`validate_settings(settings) -> list[dict]`, each `{field, severity, message}` with
`severity ∈ {error, warning, info}`; a raising implementation yields one
`{field: "root", severity: "error", message: str(e)}` (`registry.py:133-135`). `error` blocks
saving (`editor/routes.py:410-412`); `warning` and `info` never do.

Unknown keys in *saved* provider settings are **preserved and reported as a `warning`**, never
dropped. Today `put_provider_settings` merges anything with no check
(`editor/routes.py:400-401`); dropping would silently destroy configuration when a user rolls
back to an older provider version. Required-but-empty is an `error`; a hidden field (§22.3) is
exempt.

### 22.6 Secrets and environment (frozen)

A field is a secret if `ui.type == "password"` **or** its key matches `SENSITIVE_KEYS_RE`
(`api_key|token|secret|password|auth|bearer|credential`, `settings_manager.py:214-217`).

- Secrets are stored in `settings/settings.json` in plaintext (unchanged; the file is
  local-only). The contract governs **egress**, not at-rest encryption.
- Secrets must never appear in an API response, log line, error message, execution record, SSE
  frame, exported template, or archive. Every settings payload leaving the process passes
  through `redact_settings` / `redacted_provider_settings`.
- **Live defect recorded here, not fixed by 10.2:** `GET /api/settings/v2`
  (`editor/routes.py:211-212`) and `GET /api/providers/<domain>/<provider_id>/settings`
  (`editor/routes.py:360-366`) return **unredacted** provider settings, including `api_key`.
  `redacted_provider_settings` exists (`settings_manager.py:247-249`) with **zero call sites**
  outside `__all__`. Owner: **11.5**, which must also decide how the modal round-trips a
  redacted value without overwriting the real one (rule: a field whose submitted value is
  exactly the redaction sentinel `"***"` is ignored on save).
- **Env vars are a read-time fallback, never a seed for secrets.** A provider resolves a
  credential as `settings[key] or os.environ[ENV_NAME]`, and the resolved value is never
  written back to `settings.json` and never returned. This replaces copying values in
  `_seed_from_env` (`settings_manager.py:85-104`). Owner: **11.3**.
- **The `INWORLD_API_KEY` selection side effect is frozen as removed.** First-run seeding may
  populate values but must never write `selected_provider` (`settings_manager.py:88`, §14.3).
  Migration: existing installs keep whatever selection is already persisted — no rewrite, no
  reset. Owner: **11.3**.

## 23. Parameterized option sources (frozen)

Freezes §15.1. `GET /api/workflow/options/<source>` currently calls `resolve_options(source)`
with no context (`options.py:108`, `routes.py:196`), which is why `_tts_voices()` returns the
static Kokoro list regardless of engine (`options.py:19-21`) and why no `tts_providers` source
exists at all. 12.2 implements this; 15.2 depends on it.

### 23.1 Request

```
GET /api/workflow/options/<source>?domain=<d>&provider=<p>&node_type=<t>&project_id=<id>
```

The source stays **allowlisted** — `<source>` must be a key of `ASYNC_OPTION_SOURCES`; a
schema-supplied URL is still never fetched (§11). `ASYNC_OPTION_SOURCES`
(`registry.py:30-34`) changes from a list to a dict of specs. Every existing consumer uses
`set(...)` or `in` (`options.py:75`, `tests/test_workflow_options.py:60`,
`tests/test_workflow_registry.py:81`), so the parity assert and its test survive unchanged.

```python
ASYNC_OPTION_SOURCES = {
    "tts_voices": OptionSourceSpec(context=("domain", "provider"), cache="settings"),
    "tts_providers": OptionSourceSpec(context=(), cache="discovery"),      # new (P26)
    "storyboard_providers": OptionSourceSpec(context=(), cache="discovery"),
    "animator_providers": OptionSourceSpec(context=(), cache="discovery"),
    "script_providers": OptionSourceSpec(context=(), cache="discovery"),          # new
    "scene_blueprint_providers": OptionSourceSpec(context=(), cache="discovery"), # new
    "story_tones": OptionSourceSpec(context=(), cache="static"),
    "style_templates": OptionSourceSpec(context=(), cache="static"),
    "export_profiles": OptionSourceSpec(context=(), cache="static"),
    "caption_presets": OptionSourceSpec(context=(), cache="static"),
}
```

**Context validation is an allowlist too.** Only the parameter names in that source's
`context` tuple are accepted; any other query parameter is ignored. `domain` must be a
`DOMAINS` key; `provider` must resolve in that domain's registry (id or alias, normalized to
the canonical id before it reaches the resolver); `node_type` must be a registry node type;
`project_id` must survive `sanitize_project_id` unchanged. A declared parameter may be
omitted — the resolver then falls back to the domain's selected provider (§24), which is what
makes existing single-argument callers keep working.

The five per-domain `*_providers` sources make P26 and P32 disappear: the TTS node's `engine`
field stops being a static `["kokoro","inworld"]` list (`registry.py:186`) and
`_provider_options` stops hardcoding two domains (`options.py:38-50`).

### 23.2 Response

```json
{
  "source": "tts_voices",
  "context": {"domain": "tts", "provider": "inworld"},
  "options": [{"value": "Ashley", "label": "Ashley", "group": null, "disabled": false}],
  "generated_at": "2026-08-08T00:00:00Z"
}
```

`context` echoes the **validated, normalized** context so the client can key its cache on the
server's interpretation rather than on its own query string. `group` and `disabled` are
optional and default to `null`/`false`; `{value, label}` remains the minimum, so today's
`_opt()` helper (`options.py:15-16`) is unchanged and the existing client
(`useOptionSources.js:14`, reads `data.options`) keeps working without edits.

### 23.3 Failure semantics (frozen)

| condition | HTTP | code |
|---|---|---|
| unknown `<source>` | 404 | `NOT_FOUND` (unchanged, `routes.py:200`) |
| context parameter invalid, unknown domain/provider, or fails sanitization | 400 | `OPTION_CONTEXT_INVALID` |
| resolver raised — provider unreachable, model missing, extension offline | 503 | `PROVIDER_UNAVAILABLE` (unchanged, `routes.py:198`) |

`OPTION_CONTEXT_INVALID` is the only addition to the stable error-code list in §7; it is
additive and no existing code changes meaning. The 503 body carries a redacted message and
never the provider's raw exception.

**Save-time validation still fails open.** `allowed_option_values` (`options.py:85-105`)
becomes context-aware but keeps its contract from step 6.3: a bad value is rejected, an
unavailable resolver returns `None` and never blocks saving an otherwise-valid workflow. For
a context-sensitive source the legal set is the **union** over the currently registered
providers of that domain, so switching provider can never retroactively invalidate a saved
workflow.

### 23.4 Caching and invalidation (frozen)

The current process-lifetime cache keyed by source alone (`_VALUE_CACHE`, `options.py:82`) is
wrong once options depend on settings. Frozen replacement:

- Cache key: `(source, tuple(sorted(normalized_context.items())))`.
- `cache="static"` — process lifetime, as today.
- `cache="discovery"` — invalidated on discovery and on dev reload.
- `cache="settings"` — TTL 300 s **and** explicitly invalidated on
  `PUT /api/providers/<domain>/<provider_id>/settings` and on a selection change (§24.2), for
  that domain only. Changing an API key must make the voice list refetch.
- Bounded: at most 64 entries per source, LRU eviction, so context parameters cannot grow the
  cache without limit.
- The browser cache in `useOptionSources.js` keys on the full request URL rather than the bare
  source string; `clearOptionSourceCache()` stays the test hook.

## 24. Authoritative selection store (frozen)

Freezes §14.2. `settings/settings.json` → `domains.<domain>.selected_provider` is the
**single authority** for every domain. The `app-config.json` keys `sts-tts-provider`,
`sts-storyboard-provider`, and `sts-asset-provider` (`useSettings.js:12-14`) are the losers and
are retired.

### 24.1 Precedence chain (frozen, all five domains)

1. An explicit provider field on the request (`provider_override`, `provider_id`, `engine`).
2. For workflow execution: the node's **saved** `configuration` value.
3. `settings.json` `domains.<domain>.selected_provider`.
4. `DomainSpec.default_provider`.

Environment variables never appear in this chain (§22.6). Rule 2 is load-bearing: switching
the global selection must **not** change how an existing saved workflow runs (§17.1, "old
workflows must run unedited"). Rule 3 is what `animation_routes.py:194` fails to do today —
its comment claims it reads the animator selection and it does not, so selecting an animator
in the modal changes nothing. Wiring that read is a precondition for calling this store
authoritative. Owner: **14.3**.

### 24.2 Write path (frozen)

The whole-blob read-modify-write in `useProviders.js:73-84` (`GET /api/settings/v2` → spread →
`PUT` the entire document, a genuine lost-update window since `put_settings_v2` calls
`save_settings` with no concurrency check, `editor/routes.py:215-227`) is replaced by:

```
PUT /api/providers/<domain>/selection      body: {"provider_id": "inworld"}
→ 200 {"domain", "selected", "availability", "issues": [...]}
```

The handler validates the domain against `DOMAINS`, resolves `provider_id` through id-then-
alias, refuses an id that is not registered (404) or is `unavailable` (409), and calls
`settings_manager.set_selected_provider()` (`settings_manager.py:189-198`) — which finally
gains its first call site (§14.2). It then invalidates the `cache="settings"` option entries
for that domain (§23.4). A `needs_configuration` or `fail`-health provider **may** be selected;
the response carries the issues so the modal can prompt (matching today's non-blocking
behavior at `useProviders.js:71-95`).

`PUT /api/settings/v2` remains for import/reset of the whole document and must no longer be
used to change a selection. `PATCH /api/settings/v2` is added for field-level deep merge of
everything else. Owner: **11.5**.

### 24.3 Migration of the three legacy keys (frozen)

One-time, on first load after upgrade, per domain, for each of the three keys:

1. If `settings.json` has no explicit `selected_provider` for the domain **and**
   `app-config.json` holds the legacy key, adopt the legacy value, normalized through the
   alias table (`gemini→gemini_ws`, `grok→grok_automa`, `kie-ai→kie_ai`), and write it once.
2. Otherwise `settings.json` wins; the legacy key is ignored from that moment on.
3. Legacy pages read the selection from `GET /api/providers` instead of `useSettings`, keeping
   a read-through fallback to the legacy key for one release (owner **12.4**).
4. The three keys are deleted from `app-config.json` and from `useSettings.DEFAULTS` (owner
   **16.1**).

Today's values agree semantically (`inworld`, `gemini↔gemini_ws`, `grok↔grok_automa`), so this
migration is a no-op on the current machine — but it must still run, because the two stores can
diverge on the next write.

## 25. Frontend-safe serialization (frozen)

Exactly these fields may cross to the browser.

`ProviderInstance.to_dict()` v2 — extends the eight fields at `registry.py:159-171`:

```json
{
  "id": "inworld", "label": "Inworld", "domain": "tts", "kind": "cloud",
  "version": "1.0.0", "contract_version": 2, "aliases": [],
  "requires": ["api_key"], "capabilities": {"streaming": false},
  "open_url": null, "docs_url": null, "description": null,
  "has_settings": true, "availability": "needs_configuration", "warnings": []
}
```

`ProviderRegistry.to_dict()` v2 — extends `registry.py:350-357`:

```json
{"domain": "tts", "providers": [...], "selected": "kokoro", "count": 2,
 "excluded": [{"id": "broken", "reason_code": "MANIFEST_RAISED", "message": "..."}]}
```

`requires` carries settings **key names only** — never values, which is what makes it safe to
ship while the values themselves are secrets.

**Never serialized to the browser, under any route:** settings values for secret fields
(§22.6), absolute or relative filesystem paths, module objects or synthetic module names
(`_sts_provider_*`), stack traces, raw provider exception text, environment variable values,
raw third-party API responses, and the `provider_module` / `schema_module` handles. Exclusion
`message` strings are truncated to 200 characters and path-stripped to a basename before they
enter `excluded[]`.

## 26. Zero-touch assertion

Adding a provider to an existing domain must require creating exactly one folder —
`studio/<module>/providers/<id>/` with `manifest.py` and optionally `provider.py` and
`settings_schema.py` — and editing **nothing** else. Specifically it must not require an edit
to:

| surface | why it is satisfied | owner of the remaining gap |
|---|---|---|
| `app.py` | domains initialize from `DOMAINS` through the hub (§27) | 11.1 |
| `studio/workflows/registry.py` | provider dropdowns use `options_source: "<domain>_providers"` (§23.1); the static `engine` list is replaced | 12.3 / 15.2 |
| `studio/workflows/options.py` | `_provider_options(domain)` becomes catalog-driven instead of a two-branch `if` (P32) | 12.2 |
| any route dispatcher | dispatch is `registry.get(id)` + the 10.3 invocation contract, not `if provider_id == …` (P5–P25) | 14.2 / 14.3 / 15.2 |
| any Vue component | the provider modal renders from `settings_schema()` (§22.2) and the node inspector from `config_schema` | 12.4 |
| `settings_manager._default_settings` | generated from `DOMAINS` (P31) | 11.1 |

**The one genuine obstacle, frozen.** Provider-specific *node* fields gated by
`display_options.show.provider: ["gemini_ws"]` / `["grok_automa"]` (`registry.py:263,288-294`,
P27) mean a new storyboard or animator provider today needs a workflow-registry edit to expose
its own options. Frozen resolution: a node's `config_schema` keeps only **provider-agnostic**
fields; every provider-specific field moves into that provider's `settings_schema()` and is
rendered by the inspector as a per-provider sub-form resolved from the node's selected
provider. The existing gated fields keep their current config keys so saved workflows load
unchanged. Owner: **12.3**.

## 27. Registry hub (shape only — 11.1 owns the implementation)

One process-wide hub resolves `(domain, provider_id)` across all five domains and replaces the
five handlers in `editor/routes.py` that each re-import three registries and build a literal
`{tts, storyboard, animator}` dict (`:236-238, 260-262, 305-307, 342-344, 397-399`, P28).
Frozen surface: `hub.domains()`, `hub.registry(domain)`, `hub.get(domain, provider_id)`
(id-then-alias), `hub.list(domain)`, `hub.catalog()`, `hub.shutdown()`. The existing per-module
`registry`, `get_provider`, and `list_providers` imports remain as compatibility facades
(§17.1). The three 57-line `studio/<domain>/providers/__init__.py` copies (§14.6 — three, not
four) collapse into one shared binding parameterized by `DomainSpec`.

## 28. Deltas this contract requires of shipped code

Nothing in §19–§27 is implemented yet. Every delta, with its owner:

| # | delta | current state | owner |
|---|---|---|---|
| D1 | `domains.py` catalog; `VALID_DOMAINS`, `validate_settings`, `_default_settings` derive from it | three hardcoded sets (P29, P30, P31) | 11.1 |
| D2 | sorted discovery order | `os.listdir` order (`registry.py:239`) | 11.1 |
| D3 | one shared `providers/__init__.py` binding | three near-identical copies (§14.6) | 11.1 |
| D4 | registry hub replacing the five literal domain dicts | P28 | 11.1 / 11.5 |
| D5 | `aliases` + `contract_version` in the manifest | hand-written alias tables (P7, P8, P34) | 11.2 |
| D6 | unknown manifest/capability fields ignored + warned | `TypeError` → exclusion (`registry.py:304-309`) | 11.2 |
| D7 | `excluded()` recorded and serialized | WARN log only | 11.2 |
| D8 | v2 `create(context)` factory, memoized, plus real `shutdown()` calls | eight never-executed `get_provider()` factories; `shutdown` never called | 11.2 |
| D9 | `availability` computed and serialized | not present | 11.3 |
| D10 | missing `health_check` → `unknown` | returns `ok` (`registry.py:157`) | 11.3 |
| D11 | env as read-time fallback; no secret seeding; no selection flip | `_seed_from_env` copies values and flips TTS selection (`settings_manager.py:85-88`) | 11.3 |
| D12 | redaction on `GET /api/settings/v2` and `GET /api/providers/*/settings`; `"***"` sentinel ignored on save | both return raw `api_key`; `redacted_provider_settings` has zero call sites | 11.5 |
| D13 | `PUT /api/providers/<domain>/selection`; `PATCH /api/settings/v2` | whole-blob `PUT` from `useProviders.js:73-84` | 11.5 |
| D14 | legacy-key migration + read-through fallback + deletion | two independent stores (§14.2) | 12.4 / 16.1 |
| D15 | animator route reads `domains.animator.selected_provider` | never read (`animation_routes.py:194`) | 14.3 |
| D16 | `OptionSourceSpec` map, context validation, new `*_providers` sources, keyed cache | single-argument `resolve_options`; source-only cache | 12.2 |
| D17 | `OPTION_CONTEXT_INVALID` added to §7 | not present | 12.2 |
| D18 | `ui.show_if`, `ui.options_source`, `textarea` in the settings form | none supported | 12.4 |
| D19 | provider-specific node fields move to provider settings schemas | `display_options.show.provider` gating (P27) | 12.3 |

## 29. Phase 10.2 coverage assertion

Frozen by this section: the five-domain catalog and its data shape; package layout; provider
id, alias, and version rules; every required and optional manifest field with its type and
default; the `kind` and capability vocabularies; manifest validation order and the
unknown-field policy; the full lifecycle from discovery through `create()` to `shutdown()`;
registration and discovery order; duplicate-ID resolution; the nine broken-plugin exclusion
reason codes and the isolation guarantees; settings-schema widgets, conditional fields, and
dynamic options; validation severities and the unknown-key policy; secret classification, the
redaction obligation, and env-fallback rules; the availability and health state machines; the
exact browser-safe serialization allowlist and its prohibitions; the parameterized
option-source envelope with its context allowlist, response shape, three failure codes, and
cache invalidation rules; and the authoritative selection store with its precedence chain,
replacement write path, and three-key migration.

Both hardcoded three-domain sets (P29, P30) are replaced by the catalog, and §26 shows that
adding a provider to an existing domain touches no workflow node, route dispatcher, or Vue
component — with the one real obstacle (P27) resolved rather than waved through. Deferred by
design: invocation context, request/result envelopes, job handles, and `ProviderError`
(10.3); alias mapping tables, legacy field compatibility, and fixtures (10.4).
