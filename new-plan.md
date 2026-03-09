# New Plan: Prompt + Asset Quality Improvement

## Scope Reviewed
- Prompt files:
  - `_dev/prompts/scene-writer-n8n-v2.txt`
  - `_dev/prompts/scene-writer-n8n-v1.txt`
  - `_dev/prompts/scene-writer-n8n-v1-copy.txt`
  - `_dev/prompts/scene-planner-v1.txt`
- 4 recent projects:
  - `pm_G23NB0` (comic_book)
  - `pm_MJ32GC` (vaporwave)
  - `pm_QEX061` (watercolor)
  - `pm_WFOCFA` (3d_render)

## Honest Evaluation (Ranked)
1. `pm_QEX061` (watercolor): best story alignment, decent visual continuity, but schema/role errors and style-mix drift.
2. `pm_WFOCFA` (3d_render): best potential for "real-video" look, but weaker semantic consistency in selected outputs.
3. `pm_G23NB0` (comic_book): strong style identity, weaker story fidelity (style dominates narrative).
4. `pm_MJ32GC` (vaporwave): biggest style inconsistency and role-structure drift.

## Core Problems
1. Schema mismatch across planner/writer/validator.
   - Legacy prompts still allow `text` and `text_accent` while stricter validation expects different sets.
2. Style drift within single projects.
   - Conflicting style tokens inside prompts create inconsistent scene-to-scene output.
3. "Video scene" prompts still rely on still-image generation first.
   - Output feels slideshow-like unless motion stage is added.
4. Weak continuity enforcement.
   - Character/motif/palette are not consistently carried across scenes.
5. Variant selection weakness.
   - Selection appears to favor default variants instead of best semantic/style match.

## Prompt File Comparison
- Best current base: `scene-writer-n8n-v2.txt`.
- `scene-writer-n8n-v1.txt`: solid, but less strict anti-drift enforcement.
- `scene-writer-n8n-v1-copy.txt`: outdated contract vs current validation.
- `scene-planner-v1.txt`: good beat timing, but output schema should match writer/validator contract exactly.

## Priority Improvements (Highest Impact First)
1. Unify schema contract (planner + writer + validator)
- Define one canonical enum set for `narrative_role` and `type_of_scene`.
- Remove permissive auto-fix fallbacks where possible.
- Fail fast on schema mismatch.

2. Add strict style-lock fields in scene generation
- Add per-run lock fields:
  - `style_anchor`
  - `forbidden_styles`
  - `style_keywords_lock` (2-3 fixed keywords)
- Enforce these in every scene prompt.

3. Add continuity-lock fields per project
- Inject and enforce:
  - `character_signature`
  - `recurring_motif`
  - `palette_lock`
- Require character in >= 70% scenes (where narratively valid).

4. Replace default variant picking with scored selection
- Score each candidate (0..3) by:
  - script-scene semantic match,
  - style consistency score,
  - continuity with previous selected scene,
  - shot-type diversity target.
- Select highest weighted score, not fixed index.

5. Add motion generation stage for video scenes
- For `type_of_scene=video`, run image-to-video or consistent motion pass.
- Use role-aware motion presets:
  - hook: fast arresting motion,
  - buildup: controlled motion,
  - peak: strongest motion,
  - transition: smooth calming motion,
  - cta: lingering resolve.

## Quality Gates (Definition of Done)
1. No invalid roles/types in generated scene JSON.
2. Same style anchor and locked keywords across all scenes.
3. Character signature consistency score above threshold.
4. No back-to-back low-information static shots unless intentionally tagged.
5. Final sequence judged as continuous story (not disconnected artworks).

## 2-Week Execution Plan
### Week 1
1. Implement schema unification.
2. Patch planner/writer prompts to same contract.
3. Add style-lock and continuity-lock enforcement in generation step.

### Week 2
1. Implement variant scoring + auto-selection.
2. Add motion stage for video scenes.
3. Run A/B evaluation on same script/style across 4 test runs.
4. Keep best pipeline as new default.

## Immediate Next Step
- Start with schema unification first. It removes invalid outputs and stabilizes everything else.

---

## Session Log: Full Feature Build + Analysis (2026-03-09)

### Features Implemented

#### Style Template Display (All Modules)
- Colored dot + bold style name shown consistently across:
  - Scene results stats line
  - Scenes history list items
  - Pipeline history items
  - Assets picker modal items
  - Assets source bar
  - Video Editor header
  - Video Editor import modal

#### Scene Generator
- Clear generated scenes on style template change and on regenerate click
- Fixed template load race condition: `scenesLoadTemplates().then(() => loadScenesHistory())`
- "New project per style" checkbox checked by default
- Removed Copy JSON button from toolbar
- Changed nav icon to clapperboard SVG
- Style sync: loading a project selects its style in the template grid

#### Pipeline
- Auto-scenes toggle checkbox (skip scene generation when unchecked, emits `skipped` status)
- Dynamic style dropdown populated from `/api/scenes/templates` (22 templates instead of hardcoded 9)
- Webhook URL synced from localStorage (scenes settings)
- Style synced to scene generator on pipeline completion
- Style name with colored dot in pipeline history
- Backend resolves `style_prompt` from templates when not provided directly

#### Video Editor
- Style display in editor header with colored dot
- Style field in import-from-assets modal
- Web Audio API `GainNode` for volume boost up to 300%
- Persist audio tracks, volume, and mute state on every add/remove/change via `saveProjectEdits()`

#### Clear All Projects
- Full STATE reset: alignFile, alignResult, alignHistory, segmenterResult, segmenterAlignment, scenesSegData, scenesResult, assetsSceneData, assetStatuses, captionData, captionAlignment
- Clears localStorage editor scenes, all module badges, refreshes history lists, hides results panels

### Files Modified
- `static/js/scenes.js` — style helpers, clear on regen/style change, race fix, style sync
- `static/js/pipeline.js` — auto-scenes, dynamic styles, webhook sync, style in history
- `static/js/assets.js` — style in source bar and picker, style in staged timeline
- `static/js/app.js` — full STATE reset on clear all
- `static/index.html` — auto-scenes checkbox, clapperboard icon, dynamic dropdown, remove copy JSON
- `studio/pipeline/routes.py` — auto_scenes conditional, style_prompt resolution, skipped status
- `studio/pipeline/schemas.py` — `auto_scenes: bool = True`
- `studio/assets/routes.py` — style reading from scenes.json
- `timeline-editor/frontend/js/video-editor.js` — style display, Web Audio gain, track persistence
- `timeline-editor/frontend/js/app.js` — style in project creation and import modal

### Bugs Fixed
- Pipeline using wrong webhook URL (localhost instead of production)
- Style showing as raw prompt text for old projects (fallback to empty string)
- Race condition: history rendering before templates loaded (scenes + pipeline)
- Style not appearing in video editor (missing style field in staged timeline)
- `_scnTemplates` not populated when pipeline init runs before scenes.js
- `_escHtml` not found in video-editor.js (used inline escape)

### Project Quality Analysis (6 Projects)
Key findings across all scene projects:
1. **Schema errors**: 4/6 projects have duplicate indices or invalid `narrative_role` values
2. **Null text_content**: All projects have `null` for every scene's text_content
3. **Lazy final scenes**: "blurred background" prompts on closing scenes
4. **Weak motion**: No camera movement or animation direction in prompts
5. **No character consistency**: Characters described differently scene-to-scene
6. **Style mixing**: Watercolor project mixes incompatible sub-styles (ink wash + digital)

### Pending
- Update `studio/scenes/prompts.py` / n8n system prompt with quality improvements from analysis
- Schema unification across planner/writer/validator (see Priority Improvements above)
