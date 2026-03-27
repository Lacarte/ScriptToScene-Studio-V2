# Template & Preset Creation Guide

How to create a new visual style template, register it, and wire it into the pipeline.

---

## Quick Overview

A complete template requires editing **3-5 files**:

| File | Purpose |
|------|---------|
| `studio/build_scene_blueprints/templates.py` | Register the visual style template |
| `studio/niches/presets.py` | Create niche presets that use it |
| `assets/image-models.json` | Map the style to image generation models |
| `studio/build_scene_blueprints/style_compiler.py` | *(optional)* Add negative rules |
| `frontend/src/features/pipeline/constants/colors.js` | *(optional)* Add category color |

---

## Step 1: Define the Visual Style Template

**File:** `studio/build_scene_blueprints/templates.py`

Add an entry to the `SCENE_STYLE_TEMPLATES` list:

```python
{
    "id": "your_style_id",           # Unique ID (snake_case, no spaces)
    "type": "visual",                # "visual" | "hybrid" | "topical"
    "category": "psychology",        # Content category (or None for generic)
    "name": "Your Style Name",       # Display name
    "description": "One sentence describing the look.",
    "color": "#4ECDC4",              # Accent color (hex) for UI
    "style_prompt": """Generate image prompts with these rules:

DO:
- Vast white negative space (80%+ of frame)
- Single bold geometric object as focal point
- Flat/origami aesthetic with clean vector lines
- 9:16 portrait framing, centered composition
- Minimal composition, surgical precision
- Soft even lighting, almost shadowless
- Limited palette: one accent color + white/off-white

DO NOT:
- No busy or cluttered backgrounds
- No realistic textures or photorealism
- No dark/moody backgrounds
- No text, watermarks, or UI overlays
- No multiple subjects competing for attention
- No gradients or complex color palettes
- No drop shadows or 3D effects
- No human faces (use abstract/geometric figures instead)
""",
}
```

### Writing Effective Style Prompts

Every `style_prompt` should have **three sections**:

1. **DO** — What the image MUST have (composition, palette, lighting, framing)
2. **DO NOT** — What to explicitly avoid (common AI pitfalls for this style)
3. **ALWAYS** — Non-negotiable rules (aspect ratio, subject count, mood)

The DO NOT section is critical — without it, image models tend to:
- Add busy backgrounds when you want minimal
- Default to photorealism when you want illustration
- Add text/watermarks
- Over-saturate colors
- Add multiple subjects when you want a single focal point

### Template Fields

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | Unique snake_case identifier |
| `type` | Yes | `visual` (image-only), `hybrid` (image + story), `topical` (story-driven) |
| `category` | No | Links to a content category (`psychology`, `horror`, `motivation`, etc.) |
| `name` | Yes | Human-readable label |
| `description` | Yes | Short description for tooltip/info |
| `color` | Yes | Hex color for UI cards and accents |
| `style_prompt` | Yes | Detailed prompt instructions for the LLM that generates image prompts |

### Available Categories

`psychology` `crime` `horror` `motivation` `philosophy` `religion` `mystery`
`science` `history` `nature` `romance` `comedy` `children` `anecdote`
`politics` `survival` `curiosity` `space`

### Available Types

- **`visual`** — Style defines only the visual look. Story tone comes from the preset.
- **`hybrid`** — Style includes both visual and narrative direction.
- **`topical`** — Style is content-driven (e.g., "science explainer" dictates both visuals and story).

---

## Step 2: Create a Niche Preset

**File:** `studio/niches/presets.py`

Add an entry to the `_DEFAULTS` list:

```python
{
    "id": "your_preset_id",                      # Unique preset ID
    "label": "Your Preset — Category",           # Display name
    "description": "What this preset produces",
    "category": "psychology",                     # Content category
    "niche": "dark_psychology",                   # Niche tag (for grouping)
    "visual_style": "your_style_id",             # Must match template id
    "story_tone": "suspenseful",                 # Story tone
    "voice": "af_heart",                         # Kokoro TTS voice
    "speed": 0.9,                                # TTS speed multiplier
    "duration": 45,                              # Target video duration (seconds)
    "tags": ["trending", "tiktok", "shorts"],    # Discovery tags
},
```

### Available Story Tones

| Tone | Description |
|------|-------------|
| `suspenseful` | Dark, tense, slow-building dread |
| `dramatic` | Emotional weight, vivid imagery |
| `educational` | Clear, authoritative, insightful |
| `inspirational` | Uplifting, empowering |
| `comedic` | Witty, unexpected twists |
| `wholesome` | Warm, gentle, age-appropriate |

### Available Voices (Kokoro TTS)

| Voice | Character |
|-------|-----------|
| `af_heart` | Female, warm |
| `af_bella` | Female, clear |
| `am_adam` | Male, deep |
| `am_michael` | Male, authoritative |
| `bf_emma` | British female |
| `bm_george` | British male |

---

## Step 3: Map Image Generation Models

**File:** `assets/image-models.json`

Add a key matching your template `id`:

```json
{
  "your_style_id": [
    {
      "model": "GPT Image 1.5",
      "provider": "openai",
      "priority": 1
    },
    {
      "model": "Reve",
      "provider": "reve",
      "priority": 2
    }
  ]
}
```

If your style works well with the default model (Flux Dev LoRA), you can skip this — styles without an entry use the default pipeline.

### Model Priority

Models are tried in priority order. If model 1 fails, model 2 is used as fallback.

### When to Use Custom Models

| Style Type | Recommended Models |
|-----------|-------------------|
| Photorealistic | GPT Image 1 Mini, Minimax 01 |
| Illustration/Cartoon | GPT Image 1.5, Reve |
| Anime | GPT Image 1.5, Reve |
| Abstract/Artistic | Reve, GPT Image 1.5 |
| Simple/Minimal | Any (default Flux works fine) |

---

## Common DO NOT Rules by Style Type

Use these as starting points when writing the DO NOT section of your `style_prompt`:

| Style Type | Common DO NOT Rules |
|-----------|-------------------|
| **Minimal/Clean** | No clutter, no busy backgrounds, no gradients, no text, no multiple subjects |
| **Dark/Horror** | No cheerful colors, no bright daylight, no smiling faces, no cartoon aesthetic |
| **Anime/Cartoon** | No photorealism, no muted colors, no realistic proportions, no film grain |
| **Cinematic** | No flat lighting, no cartoon aesthetic, no centered composition, no clean edges |
| **Illustration** | No photorealism, no 3D effects, no film grain, no lens flare |
| **Noir** | No saturated colors, no daylight, no warm tones, no cheerful mood |
| **Stickman** | No realistic anatomy, no detailed faces, no complex backgrounds, no color fills |
| **Children's** | No violence, no dark themes, no complex imagery, no small text |
| **Abstract** | No recognizable objects, no text, no borders, no symmetry (unless intentional) |

These rules prevent the most common AI image generation failures for each style.

---

## Step 4 (Optional): Add Negative Rules

**File:** `studio/build_scene_blueprints/style_compiler.py`

Add negative rules in the `_NEGATIVE_RULES` dict to prevent unwanted image attributes:

```python
_NEGATIVE_RULES = {
    # ...existing rules...
    "your_style_id": [
        "avoid cheerful bright colors",
        "avoid cluttered compositions",
        "no text overlays",
    ],
}
```

---

## Step 5 (Optional): Add Category Color

**File:** `frontend/src/features/pipeline/constants/colors.js`

If you added a new `category`, register its color:

```js
export const CATEGORY_COLORS = {
  // ...existing...
  your_category: '#hexcolor',
}
```

---

## Creating Templates From Reference Material

### From Images

1. Analyze the visual characteristics:
   - Color palette (monochrome? limited palette? bold?)
   - Composition (minimal? busy? centered?)
   - Style (photorealistic? illustration? abstract?)
   - Lighting (even? dramatic? soft?)
   - Framing (wide? close-up? bird's-eye?)

2. Write the `style_prompt` describing these characteristics as generation rules.

3. Place any reference images in `assets/templates/references/your_style_id/`.

### From Video

1. Take key frame screenshots that represent the look.
2. Analyze the visual style across frames (is it consistent?).
3. Note the motion style too — this goes in `motion_profile` if using style_spec.
4. Write the `style_prompt` from the static visual analysis.

### From Text/Script

1. Identify the tone and mood (dark? uplifting? mysterious?).
2. Choose or create a matching `story_tone`.
3. Pick a visual style that complements the text mood.
4. Create a preset combining the tone + style.

### From an Existing Script

1. Run the script through the pipeline with different visual styles.
2. Compare outputs to find the best visual match.
3. Create a preset locking in that combination.

---

## File Reference

### Backend

| File | What to Edit |
|------|-------------|
| `studio/build_scene_blueprints/templates.py` | `SCENE_STYLE_TEMPLATES` list |
| `studio/build_scene_blueprints/style_compiler.py` | `_NEGATIVE_RULES` dict |
| `studio/niches/presets.py` | `_DEFAULTS` list |
| `studio/niches/routes.py` | API endpoints (usually no changes needed) |
| `studio/niches/schemas.py` | Validation schemas (usually no changes needed) |
| `assets/image-models.json` | Model mapping |

### Frontend

| File | What to Edit |
|------|-------------|
| `frontend/src/features/pipeline/constants/colors.js` | `CATEGORY_COLORS` |
| `frontend/src/features/pipeline/constants/steps.js` | Pipeline steps (rarely) |
| `frontend/src/features/pipeline/composables/useNiches.js` | Niche logic (rarely) |

### Runtime Data

| File | Purpose |
|------|---------|
| `_data/niche_presets.json` | User-created custom presets (auto-managed) |

---

## How the Pipeline Uses Templates

```
User selects preset
    │
    ▼
resolve_niche(config)          ← presets.py
    │ fills: visual_style, story_tone, category, voice, speed
    ▼
build_story_system_prompt()    ← story/prompts.py
    │ uses: template name, description, story_tone
    ▼
LLM generates story text
    │
    ▼
resolve_template_bundle()      ← style_compiler.py
    │ returns: template + style_spec + style_prompt
    ▼
build_visual_bible()           ← planner.py
    │ creates: visual guide from style_spec
    ▼
build_scene_blueprints()       ← planner.py
    │ creates: per-scene image prompts
    ▼
get_models_for_style()         ← wavespeed.py
    │ selects: image generation model
    ▼
Image generation (WaveSpeed / Gemini / Grok)
    │
    ▼
Assembly → Export
```

---

## Example: Creating "Minimalist Illustration" From Scratch

### 1. Template (`templates.py`)

```python
{
    "id": "minimal_illustration",
    "type": "visual",
    "category": None,
    "name": "Minimalist Illustration",
    "description": "Bold single object on vast white space, origami aesthetic",
    "color": "#FF6B6B",
    "style_prompt": """Generate image prompts following these rules:

DO:
- Vast white/light negative space (80%+ of frame)
- Single bold focal object, geometric or origami-style
- Flat illustration with clean vector lines
- Limited palette: one strong accent color + white/off-white
- Portrait 9:16 framing, subject centered or slightly off-center
- Soft even lighting, almost shadowless

DO NOT:
- No busy backgrounds or environmental detail
- No realistic textures, gradients, or photorealism
- No dark or moody color schemes
- No text, watermarks, logos, or UI elements
- No multiple competing subjects
- No drop shadows or 3D perspective effects
- No human faces (use abstract/geometric representations)

ALWAYS:
- Maintain vast empty space as the dominant visual element
- Keep the single object bold, simple, and immediately recognizable
- Use clean geometric shapes over organic forms
""",
}
```

### 2. Preset (`presets.py`)

```python
{
    "id": "minimal_illustration_psychology",
    "label": "Minimal Illustration — Psychology",
    "description": "Bold single objects on vast white space, origami aesthetic",
    "category": "psychology",
    "niche": "dark_psychology",
    "visual_style": "minimal_illustration",
    "story_tone": "suspenseful",
    "voice": "af_heart",
    "speed": 0.9,
    "duration": 45,
    "tags": ["trending", "tiktok", "shorts"],
},
```

### 3. Image Models (`image-models.json`)

```json
{
  "minimal_illustration": [
    {"model": "GPT Image 1.5", "provider": "openai", "priority": 1}
  ]
}
```

### 4. Negative Rules (`style_compiler.py`)

```python
"minimal_illustration": [
    "avoid cluttered compositions",
    "avoid realistic textures",
    "avoid dark backgrounds",
    "no text overlays",
],
```

That's it. Restart Flask, and the new preset appears in the pipeline UI.
