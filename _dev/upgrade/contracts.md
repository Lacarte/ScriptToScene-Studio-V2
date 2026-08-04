# Workflow Builder — Machine Contracts (Phase 0 deliverable)

> Produced by the Phase 0 audit (steps 0.1 + 0.2 of [implementation-plan.md](implementation-plan.md)).
> Grounded in code as of commit `4aca8cb` (2026-08-04). Line numbers refer to that state.
> Rule inherited from the spec: discrepancies between the spec and the code are resolved
> **in favor of preserving working behavior** — every such resolution is recorded here.

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

## 3. Port types & compatibility matrix

Types (v1): `control, text, script, project_id, project_settings, audio_file, tts_metadata, alignment, segments, scenes, image_prompts, storyboard_images, animation_assets, captions, music_track, editor_project, export_profile, video_file, generic_json`.

Compatibility rule: **exact type match only.** No wildcard: `generic_json` connects only to `generic_json`. `stub.input`/`stub.output` resolve their dynamic type from configuration at validation time and then obey exact-match. Additional rules: no in→in / out→out; single-value inputs reject a second edge; DAG only (cycle rejection); control edges distinct from data edges. Every payload that references files carries `{artifact_refs: [relpaths]}` alongside inline JSON; integrity check = existence + nonzero size.

## 4. Workflow JSON schema (frozen)

As specified in [proposition-final.md](proposition-final.md) §Persistence — `schema_version: 1`, nodes `{id, type, type_version, name, position, configuration, disabled}`, edges `{id, source_node, source_port, target_node, target_port, edge_type}`, reserved `variables: {}`, `viewport`, `settings: {on_error}`, ISO timestamps. Persisted under `output/workflows/{workflow_id}.json` via `safe_json_write`; ids through `sanitize_project_id`; soft-delete to `output/TRASH`. `output/workflows/` and `output/branding/` must be added to `app.py` `_PROJECT_DIRS`/clear-all handling.

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

## 6. API surface & SSE event shape (frozen)

Routes exactly as the spec lists (`/api/workflows` CRUD+import/export; `/api/workflow/node-types|validate|run|executions/*`). New blueprint `workflows_bp`, name `"workflows"`, **no url_prefix** (matches all 14 existing blueprints), registered in `app.py` after the provider registries.

SSE (own emitter in `studio/workflows/events.py` — do NOT reuse pipeline `_emit`, which is private and closes over `_jobs`; see blocker B6):

```jsonc
{ "sequence": 12, "execution_id": "ex_123", "node_id": "n_tts",
  "status": "running", "attempt": 1, "timestamp": "ISO",
  "duration_ms": 0, "summary": "Generating narration",
  "progress": {"ready": 3, "total": 10},      // optional, poll-driven nodes
  "from_sample_data": false }                  // present when stub-fed
```
Monotonic `sequence` per execution; stream ends on terminal event `{node_id: null, status: "succeeded|failed|cancelled"}`. Reconnect: client sends `Last-Sequence` — server replays from buffer (bounded ring, 1000 events).

## 7. Error codes (stable)

`WORKFLOW_INVALID, UNKNOWN_NODE_TYPE, UNSUPPORTED_NODE_VERSION, PORT_TYPE_MISMATCH, MISSING_REQUIRED_INPUT, CYCLE_DETECTED, PROJECT_LOCKED, NODE_EXECUTION_FAILED, ALIGNMENT_EMPTY, WEBHOOK_FAILED, PROVIDER_UNAVAILABLE, EXTENSION_NOT_CONNECTED, POLL_TIMEOUT, EXPORT_FAILED, CANCELLED, ARTIFACT_MISSING, CACHE_INTEGRITY, STUB_PAYLOAD_INVALID, SAMPLE_FIXTURE_MISSING`.
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

Generation procedure: run the fixed pipeline once on the tiny script with the cheapest providers, copy artifacts in, strip timestamps/absolute paths, commit. (Fixtures not yet captured — first task of Phase 1 once a full run is possible in this environment; requires n8n webhook + a media provider.)

## 11. Security / threat notes

Redaction points: node configuration echoes (provider options may hold keys), execution records, SSE payloads, logs, clipboard fragments, exported workflow JSON — all through `studio/workflows/redaction.py`. Import validation limits: max 2 MB workflow JSON, ≤ 200 nodes, ≤ 500 edges, ids sanitized, unknown types/versions block execution. Async option sources: allowlist identifiers only (`tts_voices, story_tones, style_templates, storyboard_providers, animator_providers, export_profiles`). Media uploads (`media_asset`): extension+MIME+size (≤ 5 MB) validation into `output/branding/`, never raw paths. All new endpoints respect `MAX_CONTENT_LENGTH`, CORS config, and loopback guards for destructive ops.

## 12. Phase 0 verification record (2026-08-04)

- Backend: `venv` was broken (base interpreter from another project, missing). Rebuilt on Python 3.10.0; requirements + pytest installed. `pytest tests/ -q`: **13 passed, 1 failed** — `test_remove_watermark_skips_clean_glow_without_rewriting` (detector scored 0.769 on a clean synthetic image; env-sensitive external `py-gemini-watermark-remover`/opencv versions; unrelated to workflow feature). Recorded as the known baseline exception.
- Frontend: Vitest + @vue/test-utils + jsdom added (`npm run test`): **1 passed**. `test` block lives in `vite.config.js` (alias inherited).
- No `conftest.py`/pytest config exists; tests are `unittest`-style, run from repo root. pytest added to the venv (not requirements.txt — decide in Phase 1 whether to add `requirements-dev.txt`).
- Leftover empty `tests/test_*_<hash>/` dirs from an old run: ignorable noise.
