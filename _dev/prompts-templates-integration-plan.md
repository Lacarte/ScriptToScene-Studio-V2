# Prompts + Templates Integration Plan

**Goal:** Make `prompts.py` and `templates.py` work together to produce scenes with stronger visual quality, better style consistency, color coherence, cinematic continuity, and clearer alignment between scene description and selected style template.

---

## Current Architecture

- `prompts.py` defines `SCENE_GENERATOR_PROMPT` — the LLM system prompt (how to generate scenes)
- `templates.py` defines `SCENE_STYLE_TEMPLATES` — style presets with `style_prompt` prose (what visual style to apply)
- Assembly in `routes.py` / `chapters.py`: style_prompt is appended as `## STYLE INSTRUCTIONS\n{style_prompt}`

---

## Design Problems

### 1. Responsibility overlap — both modules define the same things

The system prompt asks the LLM to generate its own `color_palette`, `visual_style`, `environment`, `lighting` in the analysis step. But each template's `style_prompt` ALSO specifies color palette, lighting, composition, and style keywords. The LLM receives two competing authorities and has to reconcile them on its own — sometimes it follows the analysis it generated, sometimes it follows the style template, producing inconsistency.

### 2. Templates give instructions the system prompt doesn't know about

The system prompt defines a strict `image_prompt` format:
```
FORMAT: [shot type], [subject + action], [setting], [lighting], [mood], [2-3 motion cues], [style keywords]
```

But templates inject their own composition rules, shot type preferences, and style references that have no designated slot in this format. Example: `cyberpunk` says "low-angle shots emphasizing scale, tight alleys with depth, Dutch angles" — these contradict the system prompt's rule "No two consecutive scenes may use the same shot type" because the template pushes toward a narrow set of shots.

### 3. Templates are "generate" instructions, not "constraint" data

Every template starts with "Generate..." — written as if it were the entire system prompt. The style instruction competes with the main prompt's authority rather than feeding into its structured analysis step. The LLM treats the style block as a second director shouting different orders.

### 4. The analysis step doesn't reference the template

The LLM produces `color_palette`, `visual_style`, `environment`, etc. in the analysis — but doesn't know whether to use its own judgment or defer to the template's specifications. There's no instruction saying "your analysis should be informed by the STYLE INSTRUCTIONS." The analysis and the style template are two parallel, uncoordinated systems.

### 5. No continuity anchors

Nothing anchors visual continuity across scenes:
- No instruction for a **recurring subject** (main character, environment)
- No rule for **lighting progression** (should it shift with narrative arc, or stay fixed?)
- No mention of a **visual throughline** (a recurring prop, color, texture that ties scenes together)
- Camera language varies randomly rather than following a **cinematographic grammar**

### 6. Templates mix what with how

Each template mixes together:
- **Constraints** (color palette, lighting type) — things the LLM must obey
- **Suggestions** (compositions, environments, motifs) — things to draw from
- **Vibes** (style references like "Mindhunter meets Se7en") — tone guidance

These aren't separated, so the LLM can't distinguish "you must use this palette" from "here are some ideas."

---

## Proposed Architecture

### Clear separation of responsibility

| Concern | Lives in `prompts.py` | Lives in `templates.py` |
|---|---|---|
| Output format / JSON schema | Yes | No |
| Narrative roles (hook, buildup, etc.) | Yes | No |
| Type mix rules (video/image/text) | Yes | No |
| Shot type vocabulary + variation rule | Yes | No |
| Thematic interpretation rules | Yes | No |
| Motion cue categories | Yes | No |
| **How to use style data** | Yes | No |
| Color palette values | No | Yes |
| Lighting vocabulary | No | Yes |
| Texture/material vocabulary | No | Yes |
| Composition tendencies | No | Yes |
| Style reference keywords | No | Yes |
| Mood/atmosphere keywords | No | Yes |
| Environment vocabulary | No | Yes |

### Template restructuring — from prose to structured data

Instead of a paragraph of competing instructions, each template provides **structured style data** that the system prompt knows how to consume:

```python
{
    "id": "cyberpunk",
    "name": "Cyberpunk / Neon",
    "description": "Neon-soaked streets, futuristic tech, rain-slicked chrome",
    "color": "#00FFF7",
    "style": {
        "render": "photorealistic digital art",
        "color_palette": ["deep black", "neon magenta", "electric cyan", "purple haze", "chrome silver"],
        "lighting": ["neon signage", "holographic projections", "LED underlighting", "rain-refracted glow"],
        "textures": ["wet asphalt", "chrome metal", "holographic glass", "exposed wiring", "steam"],
        "environments": ["rain-slicked alleys", "megastructure canyons", "neon market stalls", "rooftop overlooks", "underground data dens"],
        "mood_keywords": ["gritty", "electric", "oppressive", "alive"],
        "composition_tendencies": ["low-angle for scale", "tight depth for claustrophobia", "reflection shots", "leading neon lines"],
        "camera_lenses": ["wide-angle for architecture", "shallow DOF for neon bokeh", "anamorphic flare"],
        "style_references": "Blade Runner 2049, Ghost in the Shell, Akira",
        "motion_vocabulary": ["neon flicker", "rain streaking", "hologram glitch", "steam curling", "crowd flow"],
        "avoid": ["daylight scenes", "natural/organic settings", "warm earth tones"]
    }
}
```

### System prompt restructuring — teach it to consume style data

The system prompt needs a new section that explicitly tells the LLM how to integrate the style data into its analysis and scene writing.

**Analysis step becomes style-aware:**
```
## STEP 1: ANALYZE (style-informed)
Read the full script and the STYLE SPECIFICATION below.
Your analysis must MERGE the script's content with the style's constraints:
- color_palette: start from the style's palette, adjust for the script's mood
- visual_style: combine the style's render type with the script's tone
- environment: select from the style's environment vocabulary, adapted to the script
- lighting: default to the style's lighting vocabulary throughout
```

**New continuity section:**
```
## CONTINUITY RULES
- ANCHOR SUBJECT: Identify one recurring visual subject (person, object, place).
  It must appear in at least 60% of scenes, described consistently.
- LIGHTING ARC: Choose a lighting baseline from the style. It may shift
  slightly with narrative_role (warmer at buildup, harsher at peak) but
  the base temperature and source type stay consistent.
- COLOR DISCIPLINE: Every scene's color description must use 2+ colors
  from the analysis color_palette. Never introduce colors outside the palette
  unless the narrative demands a deliberate contrast moment.
- ENVIRONMENT THREAD: Scenes share the same world. If scene 2 is in a
  rain-slicked alley, scene 5 shouldn't be in a sunny meadow unless the
  script demands a location change.
```

**Explicit camera grammar:**
```
## CAMERA GRAMMAR
Follow a cinematographic shot progression:
- hook: wide or extreme — establish the world
- buildup: medium, over-shoulder, POV — build intimacy
- peak: extreme-close-up or low-angle — maximum intensity
- transition: wide or bird's-eye — breathing room
- text_accent: blurred medium — background for text
- cta: match hook framing — bookend the piece
No two adjacent scenes may share the same shot type.
```

### Assembly point changes

In `routes.py`, the style template would be injected differently:

```python
# Current (competing prose blocks):
system_prompt += f"\n\n## STYLE INSTRUCTIONS\n{style_prompt}"

# Proposed (structured data the prompt knows how to read):
system_prompt += f"\n\n## STYLE SPECIFICATION\n{json.dumps(template['style'], indent=2)}"
```

---

## Files to modify

| File | What changes | Why |
|---|---|---|
| `studio/scenes/templates.py` | Restructure from prose `style_prompt` to structured `style` dict | LLM can consume structured constraints more reliably than competing prose |
| `studio/scenes/prompts.py` | Add style integration instructions, continuity rules, camera grammar | The system prompt must teach the LLM *how* to use style data, not just append it |
| `studio/scenes/routes.py` | Change assembly to inject `style` dict as JSON, not prose | Clean handoff between the two modules |
| `studio/scenes/chapters.py` | Same assembly change as routes.py | Consistency across both generation paths |
| `studio/scenes/templates.py` | Add `avoid` field per template | Prevent the LLM from drifting into off-brand visuals |
| `studio/pipeline/routes.py` | Update style resolution to use new `style` dict | Pipeline must use same assembly logic |

### Backward compatibility

- Keep generating a `style_prompt` string from the structured data for any external code or custom webhook payloads that pass `style_prompt` directly via the API schema
- The frontend `/api/scenes/templates` endpoint continues to return the same shape (id, name, description, color) — the `style` dict is additional data consumed server-side only

---

## Expected quality improvements

1. **Style consistency** — LLM follows one authority (its own analysis, built from structured style data) instead of two competing prose blocks
2. **Color coherence** — explicit palette constraint + discipline rule prevents palette drift across scenes
3. **Cinematic continuity** — anchor subject, environment thread, and lighting arc rules force visual coherence
4. **Camera language** — shot type mapped to narrative role prevents random shot selection
5. **No style fighting** — templates provide data, the prompt provides instructions; no more two-directors problem
6. **Better thematic depth** — existing thematic interpretation rules preserved and reinforced by style-aware analysis
