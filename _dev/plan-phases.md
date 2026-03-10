# ScriptToScene Studio — Phased Improvement Plan

> Synthesized from project quality analysis of 6 projects, prompt file comparison, and session log (2026-03-09).

---

## Priority Matrix

| Priority | Problem | Impact | Effort |
|----------|---------|--------|--------|
| P0 — Critical | Schema mismatch across planner/writer/validator | Breaks output validity | Medium |
| P0 — Critical | Null `text_content` in all scenes | Missing captions/overlays | Low |
| P1 — High | Style drift within projects | Inconsistent visual output | Medium |
| P1 — High | No character consistency across scenes | Breaks narrative coherence | Medium |
| P2 — Medium | Weak variant selection (default index) | Sub-optimal scene picks | Medium |
| P2 — Medium | Lazy final scenes ("blurred background") | Low-quality endings | Low |
| P2 — Medium | No motion/camera direction in prompts | Static slideshow feel | Medium |
| P3 — Low | Duplicate scene indices in output | Minor data integrity | Low |
| P3 — Low | Style mixing in sub-style tokens | Subtle visual noise | Low |

---

## Phase 1 — Schema & Data Integrity (Foundation)

**Goal:** Every generated scene is structurally valid. No invalid roles, no null required fields, no duplicate indices.

### Tasks

1. **Define canonical schema contract**
   - Single source of truth for `narrative_role` enum: `hook`, `buildup`, `peak`, `transition`, `cta`
   - Single source of truth for `type_of_scene` enum
   - Enforce in planner prompt, writer prompt, and validator
   - Remove permissive auto-fix fallbacks — fail fast on mismatch

2. **Fix null `text_content`**
   - Update writer prompt to require non-null `text_content` for every scene
   - Add fallback generation: derive from `visual_prompt` if AI returns null
   - Validate in schema check

3. **Fix duplicate scene indices**
   - Add unique index validation in writer output parsing
   - Auto-reindex if duplicates detected

4. **Patch all prompt files to unified contract**
   - Update `scene-writer-n8n-v2.txt` (primary base)
   - Update `scene-planner-v1.txt` to match writer/validator schema exactly
   - Deprecate `scene-writer-n8n-v1.txt` and `v1-copy.txt`

### Quality Gate
- Zero schema validation errors across 4 test runs with different styles

---

## Phase 2 — Visual Consistency (Style & Character Lock)

**Goal:** Every scene in a project looks like it belongs to the same visual world.

### Tasks

1. **Add style-lock fields to scene generation**
   - `style_anchor`: primary style identifier (locked per run)
   - `forbidden_styles`: explicit exclusion list (e.g., watercolor project forbids `digital_paint`, `ink_wash`)
   - `style_keywords_lock`: 2–3 fixed keywords injected into every scene prompt
   - Enforce in prompt template injection, not just instructions

2. **Add continuity-lock fields per project**
   - `character_signature`: fixed appearance description (clothing, features, colors)
   - `recurring_motif`: visual element that ties scenes together
   - `palette_lock`: 3–5 hex colors enforced across all scenes
   - Require character presence in >= 70% of scenes (where narratively valid)

3. **Fix lazy final scenes**
   - Add explicit rule in writer prompt: closing scenes must have full visual detail
   - Ban patterns: "blurred background", "simple gradient", "out of focus"
   - CTA/closing scene must maintain same visual richness as peak scenes

### Quality Gate
- Style anchor and locked keywords present in 100% of scene prompts
- Character signature consistency score > 0.7 across project scenes
- No "blurred background" or equivalent lazy patterns in output

---

## Phase 3 — Smart Selection (Variant Scoring)

**Goal:** Best scene variant is selected automatically, not by default index.

### Tasks

1. **Implement multi-criteria variant scoring**
   - Score each variant candidate (0–3) on:
     - Script-scene semantic match (does it depict what the script says?)
     - Style consistency (does it match the style anchor?)
     - Continuity with previous selected scene (visual flow)
     - Shot-type diversity (avoid 3 identical compositions in a row)
   - Select highest weighted score, not fixed index

2. **Add shot-type diversity enforcement**
   - Track shot types across scenes: `wide`, `medium`, `close-up`, `extreme_close`, `aerial`
   - Penalize back-to-back identical shot types in scoring
   - No back-to-back low-information static shots unless intentionally tagged

3. **Build A/B evaluation harness**
   - Run same script + style through old pipeline vs new pipeline
   - Compare 4 test runs per configuration
   - Output comparison report with per-scene scores

### Quality Gate
- Variant selection picks semantically best match in >= 80% of cases (manual review)
- No 3+ consecutive same-shot-type scenes
- A/B comparison shows measurable improvement

---

## Phase 4 — Motion & Video (Dynamic Output)

**Goal:** Video scenes feel like video, not a slideshow of still images.

### Tasks

1. **Add motion generation stage**
   - For `type_of_scene=video`, run image-to-video or consistent motion pass after image generation
   - Integrate motion generation API/model into pipeline

2. **Implement role-aware motion presets**
   - `hook`: fast, arresting motion (zoom, whip pan)
   - `buildup`: controlled, steady motion (slow dolly, gentle pan)
   - `peak`: strongest, most dramatic motion (dynamic camera, parallax)
   - `transition`: smooth, calming motion (crossfade drift, slow zoom out)
   - `cta`: lingering, resolving motion (subtle hold, gentle float)

3. **Add camera direction fields to scene prompts**
   - `camera_movement`: pan, tilt, dolly, zoom, static
   - `movement_intensity`: 1–5 scale
   - `movement_direction`: left-to-right, in, out, up, etc.
   - Writer prompt generates these per scene based on narrative role

### Quality Gate
- Video scenes contain actual motion, not static frames
- Motion intensity correlates with narrative role (peak > buildup > transition)
- Final sequence feels like continuous story, not disconnected artworks

---

## Phase 5 — Workflow Polish & DX

**Goal:** Smooth developer and user experience across the full pipeline.

### Tasks

1. **Prompt file cleanup**
   - Archive deprecated prompts (`v1`, `v1-copy`) to `_dev/prompts/archive/`
   - Single active prompt per role: planner, writer
   - Version prompt files with changelog header

2. **Pipeline observability**
   - Add per-stage timing and status logging
   - Surface quality scores in pipeline history UI
   - Show style-lock and continuity-lock status in scene results

3. **Template management improvements**
   - Template validation on load (warn if style conflicts detected)
   - Template preview: show sample output thumbnails per style
   - Allow custom forbidden_styles per template

4. **Error handling hardening**
   - Race condition prevention audit (expand `loadTemplates().then()` pattern)
   - Graceful degradation when n8n webhook is unreachable
   - Retry with backoff for transient API failures

### Quality Gate
- No race conditions in UI module initialization
- All pipeline stages have timing data visible in history
- Deprecated prompt files archived, not active

---

## Execution Summary

| Phase | Focus | Dependencies | Est. Scope |
|-------|-------|-------------|------------|
| Phase 1 | Schema & Data Integrity | None | Prompt files, validator, schemas |
| Phase 2 | Visual Consistency | Phase 1 (valid schema) | Prompt templates, generation step |
| Phase 3 | Smart Selection | Phase 2 (consistent output) | Variant picker, scoring logic |
| Phase 4 | Motion & Video | Phase 1 (valid schema) | Pipeline, motion API integration |
| Phase 5 | Workflow Polish | Phases 1–3 | UI, DX, observability |

> **Start with Phase 1.** It removes invalid outputs and stabilizes everything downstream.
