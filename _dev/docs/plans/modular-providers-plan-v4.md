# Modular Providers Plan v4 — Final

Status: **Locked**, ready to execute. Awaiting "start Phase 1" to begin.

---

## Goal

Adding a new provider means:
1. Create a folder under `studio/{domain}/providers/<new_id>/`.
2. Implement the provider contract + manifest + settings schema.
3. Restart the app.
4. The provider appears in the domain dropdown automatically.
5. Click the gear icon to configure its defaults.
6. Save — values land in `settings/settings.json`.
7. Select as default and run the pipeline without touching core logic.

---

## Locked decisions

- **Settings source of truth**: `settings/settings.json` on backend. Nested, versioned.
- **Frontend compatibility**: temporary adapter translates between current flat `/api/settings` shape and the new nested shape. Adapter has a hard expiration — deleted in Phase 9.
- **Discovery**: on restart only. No hot reload.
- **Per-domain providers folders**: `studio/tts/providers/`, `studio/storyboard/providers/`, `studio/animator/providers/`.
- **Shared helpers location**: `studio/shared/providers_common/` (renamed to avoid `providers/` name collision).
- **Provider contract**: common base (5 methods) + domain-specific interfaces. No fake unified interface.
- **Capabilities manifest**: required on every provider. Prevents `if provider_id == "..."` regressions.
- **Runtime hook**: `register_runtime(app, sock)` for extension providers. They own their WS routes.
- **Idle-shutdown**: deferred to Phase 9 (optional). Stability first.
- **Pipeline**: stops knowing provider names. Uses `provider_options` bag. Snapshots resolved settings per job.
- **"No page-specific provider code" rule**: enforced, with documented escape hatch (new shared widget types need approval, not one-off components).
- **Broken provider isolation**: precisely defined (see Phase 2).
- **Auto-open gear modal on invalid switch**: if a user selects a provider with missing/invalid settings, the gear modal opens immediately.
- **Rich job snapshots**: every job records `provider_id`, `provider_version`, `provider_kind`, `resolved_settings_redacted`, `provider_options`, `resolved_at`, `settings_version`.

---

## Final structure

```text
settings/
└── settings.json                      # canonical nested settings

studio/
├── shared/
│   └── providers_common/              # shared helpers
│       ├── http_client.py             # retry/backoff wrapper
│       ├── file_download.py           # normalized download → output dir
│       ├── progress.py                # status.json writer
│       ├── settings_adapter.py        # flat ↔ nested translator (temporary)
│       ├── settings_manager.py        # read/write/validate settings.json + redaction
│       ├── settings_migrations.py     # version-to-version migrations
│       ├── runtime.py                 # base Runtime class for extension providers
│       ├── registry.py                # shared registry base used by each domain
│       └── scaffold.py                # CLI for creating new providers from templates
│
├── tts/
│   ├── routes.py                      # thin dispatch; no provider-specific branches
│   └── providers/
│       ├── __init__.py                # domain registry instance
│       ├── base.py                    # TTSProvider contract
│       ├── kokoro/
│       │   ├── manifest.py
│       │   ├── settings_schema.py
│       │   ├── provider.py
│       │   └── runtime.py             # optional
│       └── inworld/
│
├── storyboard/
│   ├── routes.py
│   └── providers/
│       ├── __init__.py
│       ├── base.py                    # StoryboardProvider contract
│       ├── gemini_ws/                 # owns its WS runtime
│       ├── wavespeed_webhook/
│       └── wavespeed_direct/
│
└── animator/
    ├── routes.py
    └── providers/
        ├── __init__.py
        ├── base.py                    # AnimatorProvider contract
        ├── grok_automa/               # owns its WS runtime
        └── kie_ai/

docs/
└── provider-template/                 # single source for provider scaffolds
    ├── tts.template.py
    ├── storyboard.template.py
    └── animator.template.py
```

---

## Settings model

```json
{
  "version": 1,
  "general": {
    "default_style": "cinematic",
    "sync_folder": "D:/@Sync/PHONE-S24-PC",
    "auto_sync": true
  },
  "domains": {
    "tts": {
      "selected_provider": "inworld",
      "per_provider": {
        "inworld": { "api_key": "...", "voice": "Ashley", "model": "tts-1-hd" },
        "kokoro":  { "voice": "af_bella", "speed": 1.0 }
      }
    },
    "storyboard": {
      "selected_provider": "gemini_ws",
      "per_provider": {
        "gemini_ws":          { "auto_type": true },
        "wavespeed_webhook":  { "webhook_url": "...", "image_model": "" }
      }
    },
    "animator": {
      "selected_provider": "grok_automa",
      "per_provider": {
        "grok_automa": { "mode": "video", "quality": "480p", "duration": "6s" },
        "kie_ai":      { "model": "google/nano-banana", "resolution": "1" }
      }
    }
  }
}
```

**Settings version migration plumbing** — `settings_migrations.py` ships with a v1→v1 identity migration from day one:

```python
MIGRATIONS = {
  1: lambda data: data,    # identity, reserves the slot
  # 2: migrate_v1_to_v2,   # added later when needed
}
```

On load: `settings_manager` reads `version`, applies migrations sequentially, writes back if anything changed.

**Compatibility adapter** — `settings_adapter.py` translates between old flat `app-config.json['user']` keys and new nested `domains.{domain}.per_provider.{id}` paths. Marked deprecated in Phase 1, **deleted in Phase 9**.

---

## Provider contract

**Common base (all providers):**
- `manifest() -> ProviderManifest`
- `settings_schema() -> SchemaSpec`
- `validate_settings(settings) -> list[ValidationIssue]` (cheap, sync, no network)
- `health_check(settings) -> HealthResult` (network-aware, ok/warn/fail + latency)
- `shutdown() -> None`

**Optional runtime hook** (extension providers):
- `register_runtime(app, sock) -> None` — called once at boot; provider registers its own WS routes and owns its client pool, handshake, queueing, reconnect logic.

**TTS contract:**
- `synthesize(request, settings, on_progress=None) -> TTSResult`
- `list_voices(settings) -> list[Voice]`
- `list_models(settings)` *optional*
- `download_model(model_id, settings)` *optional*
- `stream(request, settings)` *optional*

**Storyboard contract:**
- `submit(job, settings, on_progress=None) -> JobHandle`
- `poll(job_id, settings) -> JobStatus` *or* push callbacks via runtime
- `generate_one(scene, settings)` *optional*

**Animator contract:**
- `submit(job, settings, on_progress=None) -> JobHandle`
- `poll(job_id, settings) -> JobStatus` *or* push callbacks via runtime
- `open_url(settings)` *optional*

**The separation rule (load-bearing):**
> Providers own external-service logic only. They do not own the app's core file layout, pipeline metadata format, or generic job persistence. Domain services still own output folders, normalized metadata, status files, thumbnails, and scene status structure.

---

## Provider manifest — required fields

```python
ProviderManifest(
    id="inworld",
    label="Inworld",
    domain="tts",
    kind="cloud",                 # local | cloud | extension
    version="1.0.0",
    requires=["api_key"],
    capabilities={
        "test_connection": True,
        "streaming": False,
        "model_download": False,
        "single_scene": True,
        "batch": True,
        "voice_list": True,
    },
    open_url=None,
)
```

Every UI/pipeline decision that used to be `if provider_id == "..."` now reads a capability flag.

---

## Broken provider isolation — concrete definition

**Excluded from registry at startup** (WARN log, no crash) if:
- `manifest.py` cannot be imported (SyntaxError, ImportError, missing file)
- `manifest()` call raises
- Manifest missing required fields (`id`, `label`, `domain`, `kind`, `version`, `capabilities`)
- `id` collides with an already-registered provider in the same domain

**Registered but unhealthy** (red badge, clean error on use) if:
- `validate_settings()` returns issues
- `health_check()` returns `fail` or `warn`
- Required env vars / API keys missing
- Network errors during health check

**Rule**: structural problems exclude; configuration/network problems report. No silent `except Exception: pass`.

---

## Pipeline normalization

Current pipeline hardcodes provider branches at `studio/pipeline/schemas.py:17` and `studio/pipeline/routes.py:1203`. Target:

```python
{
  "tts":        { "provider_override": null, "provider_options": {} },
  "storyboard": { "provider_override": "wavespeed_direct", "provider_options": {"aspect_ratio": "16:9"} },
  "animator":   { "provider_override": null, "provider_options": {} }
}
```

Resolution order per step:
1. `provider_override` if set, else `settings.json → domains.{step}.selected_provider`
2. Merge `settings.json → per_provider.{id}` with request `provider_options` (request wins for this run only)
3. `validate_settings()` — fail fast if config is broken
4. Snapshot into job metadata (see below)

---

## Job metadata snapshot

Written to `output/{step}/{project_id}/job_meta.json`:

```python
{
    "provider_id": "inworld",
    "provider_version": "1.0.0",
    "provider_kind": "cloud",
    "resolved_settings_redacted": {
        "api_key": "***",
        "model": "tts-1-hd",
        "voice": "Ashley"
    },
    "provider_options": { "speed": 1.2 },
    "resolved_at": "2026-04-10T14:32:11Z",
    "settings_version": 1
}
```

**Redaction rule**: fields with `settings_schema` type `password` or keys matching `*_key`, `*_token`, `*_secret` → replaced with `***`. Redaction logic lives in `shared/providers_common/settings_manager.py`.

Domain services own `job_meta.json` (per the separation rule).

---

## Frontend — gear icon UX

```
┌─ TTS ───────────────────────────────────┐
│  Provider: [Inworld ▼]  [⚙]  [● healthy]│
└─────────────────────────────────────────┘
```

- **Dropdown** → changes `domains.{domain}.selected_provider`
- **Gear icon** → opens `<ProviderSettingsModal>` for the currently selected provider
- **Health badge** → green/yellow/red from last `health_check()`
- **Warning dot on gear** → `validate_settings()` reported issues

**Auto-open on invalid switch**:
- User changes dropdown → frontend calls `validate_settings()` on target provider with current `per_provider` values
- If validation fails or required fields empty → **gear modal opens automatically** with invalid fields highlighted and banner: *"This provider needs configuration before it can be used."*
- Save button disabled until validation passes
- Cancel reverts dropdown to previously selected provider

Modal contains: title `Configure {provider.label}`, form rendered by `<ProviderSettingsForm>`, buttons: **Save**, **Test connection**, **Reset to defaults**, **Cancel**. Save writes to `settings/settings.json → domains.{domain}.per_provider.{id}`.

**Shared widget registry**: `text`, `password`, `dropdown`, `slider`, `file_picker`, `multi_select`, `toggle`, `path_picker`.

**Rule with escape hatch**: providers should not ship custom Vue components. If a provider needs a widget type that doesn't exist, add it to the shared widget registry (with approval), not ship a one-off in the provider folder.

**New endpoint**: `POST /api/providers/{domain}/{id}/validate` — validates without saving (for live dropdown feedback).

---

## Phases

### Phase 1 — Settings foundation + compatibility adapter (~1.0 day)
- Create `settings/settings.json` with schema v1.
- Implement `settings_manager.py` (load, save, validate, atomic writes, redaction).
- Implement `settings_migrations.py` with v1→v1 identity migration.
- Implement `settings_adapter.py` — mark deprecated with removal target "Phase 9".
- Update `studio/editor/routes.py:165` to read through adapter, so existing frontend keeps working.
- Add endpoints: `GET /api/providers` (stub), `GET/PUT /api/settings/v2` (nested shape).
- **Acceptance**: app boots, legacy frontend settings work unchanged, new endpoints respond with stub data.

### Phase 2 — Provider catalog + discovery (~0.5 day)
- Implement `shared/providers_common/registry.py` — base registry with domain scoping.
- Implement discovery: scan `studio/{domain}/providers/<id>/`, load `manifest.py`, apply broken-provider isolation rules.
- Wire empty per-domain registries in `studio/{tts,storyboard,animator}/providers/__init__.py`.
- Wire `GET /api/providers` to return real registry contents.
- Log startup table: `[providers] tts: 0 registered, storyboard: 0, animator: 0`.
- **Acceptance**: app boots; startup table shown; broken test `manifest.py` logs WARN and doesn't crash.

### Phase 3 — Base contracts + runtime hooks + shared helpers (~0.5 day)
- Write `base.py` for each domain (TTS, Storyboard, Animator).
- Write `runtime.py` base class for extension providers.
- Implement `http_client.py`, `file_download.py`, `progress.py`.
- Wire `register_runtime(app, sock)` hook into app boot in `app.py` — iterates registered providers, calls hook if present.
- **Acceptance**: contracts importable; runtime hook called at boot (no-op, no providers exist yet).

### Phase 4 — TTS migration (~1.0 day)
- Port Kokoro from `studio/tts/routes.py` → `studio/tts/providers/kokoro/`.
- Port `studio/tts/inworld.py` → `studio/tts/providers/inworld/`.
- Write manifests + settings schemas.
- Rewrite `_step_tts()` at `studio/pipeline/routes.py:1186` to use registry — delete `_step_tts_kokoro`/`_step_tts_inworld` branches.
- Seed `settings.json` from existing env vars on first run (one-shot migration).
- **Acceptance**: full pipeline runs with Kokoro; switch to Inworld via `settings.json`; both work. Startup log shows `tts: 2 registered`.

### Phase 5 — Provider settings UI + gear modal (~1.5 days)
- Build `<ProviderSettingsForm>` generic renderer with shared widget registry.
- Build `<ProviderSettingsModal>` wrapper with Save/Test/Reset/Cancel.
- Add TTS section to settings page: dropdown + gear + health badge.
- Wire to `GET /api/providers`, `GET/PUT /api/settings/v2`, `POST /api/providers/tts/<id>/test`, `POST /api/providers/tts/<id>/validate`.
- Implement auto-open-on-invalid-switch behavior.
- **Acceptance**: change TTS provider from UI → save → green badge → run pipeline → uses new provider. Switching to unconfigured provider auto-opens modal.

### Phase 6 — Storyboard migration + Gemini WS lift (~2.0 days, **risk phase #1**)
- Port `wavespeed_webhook`, `wavespeed_direct` → `studio/storyboard/providers/`.
- **Lift** `studio/storyboard/gemini_ws.py` → `studio/storyboard/providers/gemini_ws/` — full WebSocket pool, client management, message handlers. Expose `register_runtime(app, sock)`.
- Collapse branch at `studio/storyboard/routes.py:307` into registry dispatch.
- Add Storyboard section to settings UI.
- **Critical test**: end-to-end Gemini WS with real extension + real job, multiple times, after provider switches, after app restarts.
- **Acceptance**: all three storyboard providers selectable from UI; Gemini WS path stable.

### Phase 7 — Animator migration + Grok WS lift (~2.0 days, **risk phase #2**)
- **Lift** Grok WS bridge from `studio/animator/routes.py` → `studio/animator/providers/grok_automa/`. Same pattern as Gemini.
- Port `studio/animator/providers/kie_ai.py` → `studio/animator/providers/kie_ai/` (close to standalone).
- Rewrite `_step_assets()` at `studio/pipeline/routes.py:1700` to use registry dispatch. **Kie AI becomes reachable from the pipeline.**
- Add Animator section to settings UI.
- **Critical test**: Grok extension handshake, multiple jobs back-to-back, switch to Kie AI mid-session, switch back.
- **Acceptance**: both animator providers selectable and runnable; extension bridge stable.

### Phase 8 — Pipeline normalization (~1.0 day)
- Replace provider-specific fields in `studio/pipeline/schemas.py` with generic `{step}_provider_override` + `{step}_provider_options`.
- Delete `grok_mode`, `grok_quality`, `tts_provider`, etc. from schema.
- Implement full job metadata snapshot (`provider_id`, `provider_version`, `provider_kind`, `resolved_settings_redacted`, `provider_options`, `resolved_at`, `settings_version`).
- Move pipeline preflight to call `validate_settings()` and `health_check()` on resolved provider for each step.
- **Acceptance**: schema clean; `grep` for old flat field names = 0 hits; misconfigured provider fails preflight with clear error before work starts.

### Phase 9 — Cleanup, templates, docs, optional lifecycle (~0.5 day + optional)
- **Delete `settings_adapter.py`.** Verify with grep.
- **Delete old flat setting keys from `/api/settings`.** Migrate any remaining frontend consumers.
- Ship `docs/provider-template/` with per-domain skeletons.
- Ship `scaffold.py` CLI: `python -m studio.shared.providers_common.scaffold tts my_new_provider`.
- Update CLAUDE.md with new architecture notes.
- **Optional**: add lazy-open / idle-shutdown to `runtime.py` — only after Phases 6–7 stable for several real runs.

**Definition of Done:**
- ✅ New provider folder appears automatically after restart.
- ✅ Shows in domain dropdown.
- ✅ Gear icon opens settings UI rendered from `settings_schema`.
- ✅ Settings save to `settings/settings.json`.
- ✅ `validate_settings()` and `health_check()` both run.
- ✅ Selecting as default changes app behavior without editing core routes/frontend pages.
- ✅ Pipeline runs using new provider.
- ✅ `settings_adapter.py` is deleted.
- ✅ No file contains `if provider_id == "..."` outside provider folders.
- ✅ `grep` for old flat setting keys = 0 hits.
- ✅ Switching to unconfigured provider auto-opens gear modal.
- ✅ Every completed job has `job_meta.json` with full redacted snapshot.
- ✅ Redaction covers all `password`-type schema fields and `*_key`/`*_token`/`*_secret` patterns.

---

## Effort & risk

| Phase | Days | Risk |
|---|---|---|
| 1. Settings foundation + adapter | 1.0 | low |
| 2. Provider catalog + discovery | 0.5 | low |
| 3. Base contracts + runtime hooks | 0.5 | low |
| 4. TTS migration | 1.0 | low |
| 5. Settings UI + gear modal | 1.5 | medium |
| 6. Storyboard + Gemini WS lift | 2.0 | **high** |
| 7. Animator + Grok WS lift | 2.0 | **high** |
| 8. Pipeline normalization | 1.0 | medium |
| 9. Cleanup + templates | 0.5 | low |
| **Total** | **~10 days** | |

Phases 6 and 7 touch live extension bridges — mandatory checkpoint review after each.

---

## Execution mode

Phase-by-phase with checkpoint approval:
- Phases 1–4: batch freely, review after Phase 4 when TTS runs through new system.
- Phase 5: review before moving on — UI contract solidifies here.
- Phases 6 and 7: **mandatory checkpoint after each.**
- Phases 8–9: batch freely, review at end.
