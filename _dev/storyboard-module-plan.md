# Storyboard Module — Implementation Plan

## Context

The pipeline currently generates videos with inconsistent visual styles because each scene hits Grok independently with only a text prompt (text-to-video). By inserting a **Storyboard** step between Scene Blueprint and Asset Generator, we generate one reference image per scene first, establishing a visual anchor. Later (handled separately by the user), the Animator will use these images for image-to-video generation.

**New pipeline:**
```
TTS → Alignment → Segment → Scenes → Storyboard → Animator → Build → Export
                                        (NEW)       (renamed)
```

**Key decisions:**
- Call WaveSpeed via **n8n webhook** (wrap existing sub-workflow), send scenes one-by-one
- **Defer Grok Automa img2video changes** — user handles separately
- Add `auto_storyboard` toggle to make the step optional

---

## Phase 1: Config Foundation

**Goal:** Add directory constants, env vars, and register the new output directory.

### Files to modify

**`config.py`**
- Add `STORYBOARD_DIR = os.path.join(OUTPUT_DIR, "storyboard")` after `ASSETS_DIR` (line 30)
- Add `STORYBOARD_DIR` to the `os.makedirs` loop (line 50-52)
- Add `STORYBOARD_DIR` to `_collect_existing_project_ids()` `dir_only_roots` tuple (line 89-96)
- `N8N_ASSET_WEBHOOK_URL` already exists at line 61 (`http://localhost:5678/webhook/image-generator`) — reuse it for storyboard

**`app.py`**
- Add `STORYBOARD_DIR` to imports from `config` (line 16-22)
- Add to `_CLEAR_MODULES` (line 177-189): `{"page": "Storyboard", "module": "Storyboard Images", "dir": STORYBOARD_DIR}`
- Add `STORYBOARD_DIR` to `_PROJECT_DIRS` (line 190-193)

**Verify:** Server starts, `output/storyboard/` auto-created, health check passes.

---

## Phase 2: n8n Webhook Workflow

**Goal:** Create a webhook-triggered n8n workflow that wraps the existing `create-images.json` sub-workflow.

### New file: `_dev/automation/n8n/storyboard-webhook.json`

**Workflow chain:**
```
Webhook (POST /webhook/storyboard-generator)
  → Execute Sub-Workflow (create-images)
  → Respond to Webhook (return image_url)
```

- **Webhook node**: Receives `{image_prompt, aspect_ratio}` per scene
- **Execute Sub-Workflow**: Calls existing `create-images` (FaPKbPV3in6ctCGx) with `{image_prompt, image_reference: null, aspect_ration: aspect_ratio}`
- **Respond to Webhook**: Returns `{image_url}` from sub-workflow output
- Response mode: "All Incoming Items" (same pattern as scene-generator)

**Verify:** Deploy to n8n, test with HTTP request: `POST /webhook/storyboard-generator` with `{image_prompt: "test", aspect_ratio: "9:16"}` → returns `{image_url: "https://..."}`.

---

## Phase 3: Storyboard Backend Module

**Goal:** Create `studio/storyboard/` module with routes for generating and managing storyboard images via n8n webhook.

### New files

**`studio/storyboard/__init__.py`**
- Export `storyboard_bp`

**`studio/storyboard/schemas.py`**
```python
class StoryboardScene(BaseModel):
    scene: int
    prompt: str = Field(min_length=1)

class StoryboardGenerateRequest(BaseModel):
    project_id: str
    scenes: list[StoryboardScene] = Field(min_length=1)
    aspect_ratio: str = "9:16"
    webhook_url: Optional[str] = None  # override N8N_ASSET_WEBHOOK_URL
```

**`studio/storyboard/routes.py`**

Routes:
- `POST /api/storyboard/generate` — Start generation (background thread, returns job status)
- `GET /api/storyboard/status/<project_id>` — Poll per-scene status
- `GET /api/storyboard/images/<project_id>` — List generated images with metadata
- `GET /api/storyboard/images/<project_id>/<scene_num>` — Serve individual image file

**Background generation logic:**
- In-memory job tracking (`_storyboard_jobs` dict + lock, same pattern as asset grabber)
- Iterate scenes sequentially (one-by-one as user requested)
- For each scene: call n8n webhook via `call_webhook()` from `studio/webhooks.py`
  - Payload: `{image_prompt: scene.prompt, aspect_ratio: req.aspect_ratio}`
  - Response: `{image_url: "https://..."}`
- Download returned `image_url` to `output/storyboard/{project_id}/{scene_num}.jpg`
- Track per-scene status: `pending → generating → downloading → ready | error`
- Write `storyboard.json` metadata on completion

**Output structure:**
```
output/storyboard/{project_id}/
  0.jpg, 1.jpg, 2.jpg, ...
  storyboard.json  →  {project_id, scenes: [{scene, status, image_url, local_path}], ...}
```

**Key patterns to reuse:**
- `call_webhook()` from `studio/webhooks.py` — retry + n8n unwrapping
- `organize_grabber_assets()` download pattern from `studio/assets/organizer.py`
- Job tracking pattern from `studio/assets/routes.py` grabber system

**Register in `app.py`:**
```python
from studio.storyboard import storyboard_bp
app.register_blueprint(storyboard_bp)
```

**Verify:** POST to `/api/storyboard/generate` with test data, poll `/api/storyboard/status/{id}`, verify images saved to disk.

---

## Phase 4: Pipeline Integration (Backend)

**Goal:** Insert `storyboard` as step 5/8 in the pipeline runner with full resume/stop support.

### File: `studio/pipeline/schemas.py`

**Line 19** — Add `"storyboard"` to valid steps:
```python
_VALID_STEPS = ("tts", "timing", "alignment", "segment", "scenes", "storyboard", "assets", "assemble", "export")
```

**Add field** to `PipelineRunRequest`:
```python
auto_storyboard: bool = True
```

### File: `studio/pipeline/routes.py`

**Line 41** — Update step list:
```python
ALL_PIPELINE_STEPS = ["tts", "timing", "segment", "scenes", "storyboard", "assets", "assemble", "export"]
```

**Add `STORYBOARD_DIR`** to imports from config (line 27).

**Config dict** (line 144-167) — Add `"auto_storyboard": data.auto_storyboard`.

**Resume chain** (lines 706-713) — Add storyboard dependencies:
```python
required_chain = {
    "timing": ["tts"],
    "segment": ["tts", "timing"],
    "scenes": ["tts", "timing", "segment"],
    "storyboard": ["tts", "timing", "segment", "scenes"],
    "assets": ["tts", "timing", "segment", "scenes"],  # storyboard NOT required (optional)
    "assemble": ["tts", "timing", "segment", "scenes"],
    "export": ["tts", "timing", "segment", "scenes", "assemble"],
}
```

**`_load_prior_results()`** (line 626-679) — Add storyboard loading:
```python
elif step == "storyboard":
    sb_path = os.path.join(STORYBOARD_DIR, project_id, "storyboard.json")
    if os.path.isfile(sb_path):
        loaded["storyboard"] = safe_json_read(sb_path)
```

**Update all step numbering** from `X/7` to `X/8`:
- Lines 757, 764 → "Step 1/8"
- Lines 785, 792 → "Step 2/8"
- Lines 812, 820 → "Step 3/8"
- Lines 840, 848, 856 → "Step 4/8"
- Lines 880, 890 → "Step 6/8" (was 5/7)
- Lines 910, 917 → "Step 7/8" (was 6/7)
- Lines 936, 943 → "Step 8/8" (was 7/7)

**Insert new step block** between scenes (line ~868) and assets (line ~870):
```python
# -- Step 5: Storyboard --
_raise_if_stop_requested(job_id, step_name="storyboard")
if _should_skip("storyboard"):
    storyboard_result = results.get("storyboard", {})
elif config.get("auto_storyboard", True):
    # generate reference images
    _step_storyboard(...)
else:
    # skipped — emit skipped status
    ...
if stop_after == "storyboard":
    # early exit
    ...
```

**New function `_step_storyboard()`:**
- Extract `image_prompt` from each scene in `scenes_result`
- Call storyboard module via internal HTTP (same pattern as `_step_assets` calling grabber)
- Poll `/api/storyboard/status/{project_id}` until all scenes ready
- Emit progress events during polling
- Return `{total, ready, errors}`

**`_emit_done()` summary** (line 564-577) — Add `"storyboard": results.get("storyboard")`.

**Verify:** Run pipeline with `stop_after: "storyboard"`, with `auto_storyboard: false` (should skip), resume from storyboard, full pipeline run showing 8 steps.

---

## Phase 5: Frontend Updates

**Goal:** Add storyboard step to pipeline UI, rename Assets → Animator, add toggle.

### File: `frontend/src/features/pipeline/composables/usePipeline.js`

**`ALL_STEPS` (lines 73-81):**
```javascript
const ALL_STEPS = [
  { id: 'tts', label: 'TTS', icon: '🎤' },
  { id: 'timing', label: 'Alignment', icon: '⏱' },
  { id: 'segment', label: 'Segment', icon: '✂' },
  { id: 'scenes', label: 'Scenes', icon: '🎬' },
  { id: 'storyboard', label: 'Storyboard', icon: '🖼' },
  { id: 'assets', label: 'Animator', icon: '🎥' },
  { id: 'assemble', label: 'Build', icon: '🔧' },
  { id: 'export', label: 'Export', icon: '📤' },
]
```

**`maybeOpenProviderLoadingTab()` (lines 172-178):** Logic uses `stepIds.indexOf('assets')` which auto-adjusts, but verify it still works with 8 steps.

### File: `frontend/src/features/pipeline/views/PipelinePage.vue`

**`destinations` (lines 532-540):** Add storyboard route:
```javascript
storyboard: '/scenes',  // reuse scenes page (storyboard images visible there)
assets: '/assets',
```

**Stop-after dropdown (lines 990-998):** Add storyboard option, rename assets:
```html
<option value="storyboard">→ Storyboard</option>
<option value="assets">→ Animator</option>
```

**Add `auto_storyboard` toggle** near the existing `auto_scenes` toggle — checkbox/switch that controls `autoStoryboard` ref, sent in pipeline run payload.

**Add `autoStoryboard`** to the `usePipeline` composable — ref with localStorage persistence, included in the run request body.

**Verify:** 8-step progress bar renders correctly, stop-after dropdown shows all options, toggle works, labels correct.

---

## Phase Summary

| Phase | Scope | Dependencies | Key Files |
|-------|-------|-------------|-----------|
| 1 | Config constants | None | `config.py`, `app.py` |
| 2 | n8n webhook workflow | Phase 1 | `_dev/automation/n8n/storyboard-webhook.json` |
| 3 | Storyboard backend module | Phase 1 | `studio/storyboard/{__init__,routes,schemas}.py` |
| 4 | Pipeline integration | Phase 1, 3 | `studio/pipeline/{routes,schemas}.py` |
| 5 | Frontend updates | Phase 4 | `usePipeline.js`, `PipelinePage.vue` |

**Not in scope (user handles separately):** Grok Automa modification for image-to-video mode.
