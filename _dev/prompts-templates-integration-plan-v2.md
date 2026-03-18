# Prompts + Templates Integration Plan V2

## Why a V2

The original plan correctly identifies the biggest current problem: `prompts.py` and `templates.py` both try to direct the model, so style and scene logic compete instead of cooperating.

That said, scene coherence in ScriptToScene Studio is not only a prompt-format problem. In this app, coherence is affected by:

- style template design
- the system prompt
- chapter/chunk generation behavior
- how much structure is decided before the LLM call
- what continuity state is carried between calls
- whether the response is validated after generation

If we only convert `style_prompt` prose into structured data, scene quality will improve, but we will still have drift across scenes, especially in chapter mode and long scripts.

This V2 proposes a fuller architecture that matches how the app actually works today:

- single-call and chapter-based scene generation both exist
- `analysis` is persisted to `scenes.json`
- the pipeline and `/api/scenes/generate` both assemble prompts
- `style_prompt` is still part of the public request schema

The goal is not just better prompts. The goal is a more reliable scene planner.

---

## What the Current Plan Gets Right

The original plan is directionally strong in four important ways:

1. It correctly separates responsibilities:
   - `prompts.py` should define generation rules and output contract
   - `templates.py` should define style information

2. It correctly calls out style/template overlap:
   - color
   - lighting
   - composition
   - tone

3. It correctly pushes templates toward structured data instead of prose blobs.

4. It correctly identifies missing continuity concepts:
   - recurring subject
   - lighting consistency
   - environmental throughline
   - camera grammar

Those are the right foundations.

---

## What the Current Plan Still Misses

### 1. It treats coherence as an LLM-only problem

Right now the LLM decides too many things at once:

- analysis
- narrative roles
- scene types
- shot progression
- style interpretation
- continuity

That makes the output harder to stabilize. The app already has strong upstream structure from segmentation and timing. We should use more of that structure before the prompt is sent.

### 2. It does not solve chapter/chunk continuity

This is the biggest missing piece.

In `chapters.py`, later chapter/chunk calls reuse the original `analysis`, but they do not receive enough continuity state from previously generated scenes. That means the system cannot reliably preserve:

- shot alternation across chunk boundaries
- type-mix balance across the whole video
- recurring anchor presence
- environment continuity
- escalation of intensity from buildup to peak

For long scripts, this is where coherence breaks most often.

### 3. It does not separate canonical style data from derived story-specific style decisions

There are really three layers, not two:

1. Template spec:
   the reusable style preset, such as `cinematic` or `dark_psychology`

2. Visual bible:
   the story-specific interpretation of that template for this script

3. Scene blueprint:
   per-scene instructions and continuity constraints

The current plan jumps from template data straight into scene writing. That skips the project-specific middle layer that actually creates coherence.

### 4. It leaves narrative roles and scene types too loose

The prompt currently asks the model to manage percentages like:

- 60-75% video
- 20-30% image
- 5-10% text

That is hard to enforce, especially across chapter chunks. A better design is:

- the server preplans role/type targets
- the model executes creatively within those targets

### 5. It does not include validation or repair

Today the code validates scene indexes well, but not visual coherence. If we want reliability, we should score the generated scenes after the webhook returns and optionally:

- accept
- warn
- retry once
- repair only the failed scenes

### 6. It under-specifies backward compatibility

The app currently supports optional raw `style_prompt` in request schemas and uses it in both direct scene generation and pipeline mode. V2 needs a clear policy for:

- legacy `style_prompt`
- template-based style selection
- future custom style presets

---

## V2 Design Principles

1. One source of truth per layer.
2. Deterministic planning before generative writing where possible.
3. Chapter-safe continuity.
4. Structured constraints over freeform prose.
5. Validation is part of generation, not an afterthought.
6. Backward compatibility stays intact during migration.

---

## Proposed Architecture

### Layer 1: Template Spec

`templates.py` should define reusable visual constraints and vocabularies, not full generation prose.

Each template should contain clearly separated buckets:

- `identity`
  - render mode
  - overall aesthetic
  - reference keywords

- `hard_constraints`
  - allowed palette families
  - forbidden colors or environments
  - lighting baseline
  - texture/material expectations

- `soft_preferences`
  - composition tendencies
  - camera tendencies
  - recurring motifs
  - emotional texture

- `motion_profile`
  - motion vocabulary for video scenes
  - pace and energy cues

- `negative_rules`
  - what to avoid

Example:

```python
{
    "id": "dark_psychology",
    "name": "Dark Psychology",
    "description": "Manipulation, mind games, shadowy figures, psychological tension",
    "color": "#6D28D9",
    "style_spec": {
        "identity": {
            "render_mode": "cinematic photorealistic thriller",
            "style_keywords": [
                "psychological thriller",
                "claustrophobic framing",
                "distorted reflections",
                "split-face duality",
            ],
            "references": ["Mindhunter", "Se7en", "Gone Girl"],
        },
        "hard_constraints": {
            "palette": ["deep violet", "charcoal black", "cold steel grey", "blood-red accent"],
            "lighting_baseline": [
                "harsh overhead practicals",
                "faces half in shadow",
                "hard rim light in dark rooms",
            ],
            "environments": [
                "dim interrogation rooms",
                "narrow corridors",
                "empty paired-chair spaces",
                "mirror-lined interiors",
            ],
        },
        "soft_preferences": {
            "motifs": ["masks", "chess pieces", "puppet strings", "cracked mirrors"],
            "composition": ["tight framing", "power imbalance over-shoulders", "negative space behind subjects"],
        },
        "motion_profile": {
            "energy": "restrained but tense",
            "video_motion": ["slow push-in", "flickering light", "subtle head turn", "curtain drift"],
        },
        "negative_rules": [
            "avoid bright daylight",
            "avoid playful color palettes",
            "avoid cozy or inviting spaces",
        ],
    },
}
```

Important: `style_prompt` can still exist as a compiled legacy field during migration, but it should no longer be the canonical source of truth.

---

### Layer 2: Visual Bible

For each project, generate a story-specific `visual_bible` once from:

- full script
- chosen template spec
- segment list summary

This is the missing middle layer. It should live inside `analysis` or alongside it in the saved result.

Suggested shape:

```json
{
  "core_theme": "manipulation thrives when people mistake control for care",
  "tone_arc": "intrigue -> discomfort -> revelation",
  "world_anchor": "a dim institutional interior with reflective surfaces",
  "anchor_subject": "a composed figure whose face is never fully visible",
  "anchor_motifs": ["cracked reflection", "chess pattern", "empty second chair"],
  "palette_guardrails": ["deep violet", "charcoal", "cold steel", "red accent only at peaks"],
  "lighting_baseline": "hard overhead practical lighting with partial facial shadow",
  "camera_grammar": {
    "hook": "wide or low-angle",
    "buildup": "medium or over-shoulder",
    "peak": "extreme-close-up or oppressive high-angle",
    "transition": "wide or centered-symmetrical",
    "text_accent": "soft medium with abstract blur",
    "cta": "echo hook framing with reduced certainty"
  },
  "environment_rules": [
    "stay inside one related architectural world unless script clearly changes location",
    "mirror surfaces should recur but vary in form"
  ],
  "negative_guardrails": [
    "no bright outdoor daylight",
    "no clean corporate optimism",
    "no warm domestic coziness"
  ]
}
```

This should be the continuity contract for the full video.

---

### Layer 3: Scene Blueprint

The server should precompute a lightweight blueprint for each segment before asking the LLM to write final scenes.

This is the highest leverage improvement beyond the original plan.

Why:

- the segmenter already gives stable order, duration, and break metadata
- the app already knows first/last segment positions
- some scene logic should be deterministic, not re-decided by the LLM every time

The blueprint can assign or strongly suggest:

- `narrative_role`
- `preferred_scene_type`
- `text_scene_allowed`
- `target_shot_family`
- `intensity_level`
- `continuity_priority`
- `anchor_required`

Example:

```json
{
  "index": 4,
  "segment_words": "By the time you notice it, they've already framed the choice.",
  "narrative_role": "peak",
  "preferred_scene_type": "video",
  "target_shot_family": "extreme-close-up",
  "intensity_level": 0.92,
  "anchor_required": true,
  "continuity_priority": "high",
  "text_scene_allowed": false
}
```

This changes the LLM's job from "invent the whole scene system" to "creatively render a constrained scene plan."

That should improve:

- consistency
- chapter reliability
- type-mix accuracy
- shot progression
- ending quality

---

## Prompt Strategy in V2

The prompt should no longer act as one giant instruction block.

It should explicitly consume three inputs:

1. `style_spec`
2. `visual_bible`
3. `scene_blueprints`

### Prompt responsibilities

`prompts.py` should define:

- output schema
- thematic interpretation rules
- how to apply style constraints
- how to apply visual bible continuity
- how to respect scene blueprint targets
- type-specific prompt formatting rules

### New rule hierarchy inside the prompt

1. Segment contract
2. Visual bible continuity
3. Scene blueprint compliance
4. Style constraints
5. Creative enrichment

This order matters. Right now style and creativity are too high in the stack.

### Important instruction change

Instead of:

> Here is a style instruction block

Use:

> You must obey the template constraints, keep all scenes inside the visual bible, and treat the scene blueprint as the target shot plan for each segment.

---

## Long-Script / Chapter Continuity

This is where V2 should be materially stronger than the original plan.

### Current issue

Later chunks only inherit the high-level `analysis`. They do not inherit enough local continuity state from previous generated scenes.

### Proposed fix

Every chunk after the first should receive:

- the shared `visual_bible`
- a compact `global_plan_summary`
- the last 1-2 generated scenes from the prior chunk
- quota state:
  - text scenes already used
  - type counts so far
  - recent shot types
- continuity state:
  - current anchor usage rate
  - active environment thread
  - last visual motif used

Example chunk context:

```json
{
  "progress_state": {
    "generated_scene_count": 12,
    "type_counts": { "video": 9, "image": 2, "text": 1 },
    "recent_shot_types": ["medium", "over-shoulder"],
    "anchor_coverage": 0.67,
    "active_environment": "reflective interrogation corridor",
    "last_motif": "cracked mirror"
  }
}
```

This lets the model continue a sequence instead of restarting one every chunk.

### Chapter-safe rules

The prompt for continuation chunks should explicitly say:

- preserve continuity with the previous generated scenes, not just the original script
- avoid repeating the immediately previous shot type from prior chunk context
- keep anchor subject presence above target coverage
- continue type distribution toward the global quota rather than recalculating from scratch

---

## Validation and Repair Layer

V2 should add a response-quality check after webhook generation.

This should be implemented in Python, not left to prompt hope.

### Validate at minimum

- scene index coverage
- no adjacent shot-type repetition
- first/last scene not text
- text scene count within policy
- anchor coverage above threshold
- palette adherence above threshold
- environment drift warnings
- role progression sanity

### Suggested scoring

Give each result a `coherence_score` and per-rule warnings:

```json
{
  "coherence_score": 0.84,
  "coherence_warnings": [
    "anchor subject appears in only 42% of scenes",
    "shot type repeats across chapter boundary between scenes 7 and 8",
    "scene 11 introduces a sunny exterior that conflicts with world anchor"
  ]
}
```

### Repair strategy

If the response fails only a few rules:

- retry only failed scenes
- pass previous and next scene context
- preserve indexes and timing

If the response fails badly:

- retry the whole chunk once

This is much cheaper and safer than full regeneration every time.

---

## Backward Compatibility Strategy

V2 should not break current API consumers.

### Keep during migration

- `style` request field
- optional raw `style_prompt`
- `/api/scenes/templates` frontend shape: `id`, `name`, `description`, `color`

Important:

`/api/scenes/templates` currently returns the raw template objects. Once `style_spec` is added, that route should return a filtered public payload instead of dumping the full internal structure. Otherwise the internal planning schema becomes an accidental API contract.

### Add internally

- `style_spec`
- `visual_bible`
- `scene_blueprints`
- `coherence_score`
- `coherence_warnings`

### Policy for raw `style_prompt`

If a request provides `style_prompt`, treat it as one of:

1. legacy override
2. custom style notes

Recommended approach:

- keep using it short-term
- map it into `custom_style_notes`
- append it as a secondary override, not as the main style authority

This avoids breaking existing workflows while moving the system toward structured style control.

---

## Recommended File-Level Changes

### Keep and modify

| File | Change |
|---|---|
| `studio/scenes/templates.py` | Convert canonical template data from prose `style_prompt` to structured `style_spec`; optionally compile `style_prompt` for legacy use |
| `studio/scenes/prompts.py` | Replace monolithic prompt constant with prompt builders that consume `style_spec`, `visual_bible`, `scene_blueprints`, and continuation state |
| `studio/scenes/routes.py` | Resolve template data, build visual bible, build blueprints, call validator, persist coherence metadata, and return filtered public template payloads |
| `studio/scenes/chapters.py` | Carry forward continuity state across chunks and chapters, not just analysis |
| `studio/pipeline/routes.py` | Reuse the same scene planning stack so pipeline mode and direct mode stay identical |
| `studio/scenes/schemas.py` | Preserve `style_prompt`, but prepare fields for structured style/custom overrides |
| `studio/pipeline/schemas.py` | Preserve `style_prompt`, but prepare pipeline requests for structured style/custom overrides |

### Strongly recommended new modules

| File | Responsibility |
|---|---|
| `studio/scenes/planner.py` | Build visual bible and per-scene blueprint from script, segments, style spec |
| `studio/scenes/continuity.py` | Build and update chunk continuity state across long scripts |
| `studio/scenes/validators.py` | Score coherence, detect drift, generate warnings, decide repair path |
| `studio/scenes/style_compiler.py` | Optional helper that converts structured style spec into legacy text for compatibility/debugging |

The original plan keeps everything inside current files. V2 recommends adding modules because planning, prompting, and validation are now separate concerns.

---

## Suggested Runtime Flow

1. Resolve template from `style`.
2. Convert template to canonical `style_spec`.
3. Build `visual_bible` once for the full script.
4. Build all `scene_blueprints` from segments before any webhook calls.
5. For single-call generation:
   - send all blueprints plus visual bible once.
6. For chapter/chunk generation:
   - send only local blueprint slice plus global continuity state.
7. Normalize webhook response.
8. Run coherence validation.
9. Retry or repair if below threshold.
10. Save:
    - analysis
    - visual_bible
    - scenes
    - coherence metadata

---

## Data Contract Proposal

The saved `scenes.json` can remain backwards friendly while becoming more useful:

```json
{
  "project_id": "pp_123456",
  "style": "dark_psychology",
  "analysis": {
    "core_theme": "...",
    "mood": "...",
    "environment": "...",
    "color_palette": ["..."],
    "tone": "...",
    "visual_style": "...",
    "visual_bible": { "...": "..." }
  },
  "coherence_score": 0.87,
  "coherence_warnings": [],
  "scenes": [
    {
      "index": 0,
      "title": "The First Move",
      "narrative_role": "hook",
      "type_of_scene": "video",
      "image_prompt": "...",
      "text_content": null,
      "shot_type": "low-angle",
      "anchor_used": true,
      "motif_used": "chess pattern"
    }
  ]
}
```

Extra fields should be additive only.

---

## Migration Plan

### Phase 1: Structured templates without behavior change

- add `style_spec` to each template
- keep `style_prompt`
- add helper functions for template lookup and legacy compilation

Result:
- no external breakage
- groundwork for prompt changes

### Phase 2: Introduce visual bible generation

- add planner module
- build and persist `visual_bible`
- continue using mostly existing prompt shape

Result:
- immediate improvement in consistency
- low-risk rollout

### Phase 3: Add scene blueprint planning

- preassign role/type/shot targets
- reduce LLM freedom in structural choices

Result:
- better pacing and less randomness

### Phase 4: Fix chapter continuity

- pass continuity state between chunks
- enforce global quotas and shot continuity across boundaries

Result:
- long scripts stop feeling like separate mini-videos

### Phase 5: Add validation and repair

- coherence scoring
- selective retries
- warnings in saved output

Result:
- quality becomes measurable and supportable

### Phase 6: Retire canonical dependence on `style_prompt`

- keep only as compatibility/debug representation
- move all internal logic to structured specs

---

## Acceptance Criteria

V2 should be considered successful when the system consistently achieves the following:

- anchor subject appears in at least 60% of scenes unless intentionally disabled by template/story
- no adjacent shot repetition, including across chunk boundaries
- text scene count respects policy across the full project, not per chunk
- palette drift warnings remain rare
- chapter-generated projects feel like one continuous visual world
- the same script + style combination produces more stable outputs across reruns
- `pipeline` and `/api/scenes/generate` use the same planning logic

---

## Recommended Priority Order

If implementation time is limited, build in this order:

1. structured `style_spec`
2. `visual_bible`
3. chapter continuity state
4. server-side scene blueprint
5. validator and repair loop

If only one extra idea from this V2 is adopted beyond the original plan, it should be:

> Add a project-level visual bible plus chunk continuity state.

That is the shortest path to visibly better coherence in long-form scene generation.

---

## Final Recommendation

The original plan is a good first refactor, but it is best understood as Phase 1 of a broader scene-planning redesign.

For this app, the strongest results will come from moving from:

- prose templates + one big prompt

to:

- structured templates
- a project-level visual bible
- deterministic scene blueprints
- continuity state across chapters
- validation after generation

That turns scene generation from a single LLM guess into a controlled pipeline step that matches the rest of ScriptToScene Studio's architecture.
