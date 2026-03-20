# Niche & Style Architecture — Implementation Plan

## Problem

`templates.py` mixes topical entries (`dark_psychology`, `true_crime`, `documentary`) with visual entries (`stickman_animation`, `cinematic`, `anime`) in one flat list. The UI forces `category = style` via a bidirectional sync. Users can't combine "dark psychology tone" with "stickman visuals" without a separate template for every combo.

## Architecture

```
NICHE PRESET (user picks one card)
  ├── category       → broad topic (psychology, crime, motivation)
  ├── niche          → audience angle (dark_psychology, true_crime)
  ├── visual_style   → scene rendering (stickman_animation, cinematic)
  ├── story_tone     → narration tone (suspenseful, educational)
  ├── editing_style  → pacing/cuts (shorts_retention, slow_cinematic)
  ├── voice          → TTS voice (af_heart, bm_daniel)
  └── speed          → TTS speed (0.5–2.0)
```

**Key principle**: niche = product layer (what users see), dimensions = system layer (what the pipeline uses).

## Current State

### Templates (43 entries in `studio/scenes/templates.py`)

**Pure Visual** (how it looks):
- `cinematic`, `anime`, `surreal`, `noir`, `minimal`, `cyberpunk`, `vintage_retro`, `fantasy_epic`, `sci_fi`, `watercolor`, `comic_book`, `gothic`, `vaporwave`, `3d_render`, `dark_academia`, `tropical`, `urban_street`, `lofi_pixel`, `stickman_animation`

**Topical / Hybrid** (topic + visual baked together):
- `dark_horror`, `reddit_story`, `motivational`, `nature_doc`, `documentary`, `dark_psychology`, `religion_spiritual`, `politics_power`, `true_crime`, `conspiracy`, `stoicism`, `wealth_luxury`, `mythology`, `children_storybook`, `war_military`, `two_choices`

### Schemas

- `PipelineRunRequest.style` — single template ID (e.g. `"cinematic"`)
- `StoryGenerateRequest.preset_style` + `story_category` — already separated but always same value
- `style_compiler.resolve_template_bundle()` — takes one template ID, returns full bundle

### Frontend Sync (PipelinePage.vue)

```javascript
// Lines 28-36: bidirectional sync
function setCategory(id) { story.storyCategory.value = id; style.value = id }
function setStyle(id) { style.value = id; story.storyCategory.value = id }

// Line 121-124: reactive watch
watch(style, (val) => { story.storyCategory.value = val || 'cinematic' }, { immediate: true })
```

---

## Phase 1 — Tag Templates + Add Niche Presets

**Goal**: Classify existing templates and create niche preset data. No pipeline changes, no UI changes. Everything backward-compatible.

### 1.1 Add `type` and `category` fields to templates

**File**: `studio/scenes/templates.py`

Add two fields to each template dict:

```python
"stickman_animation": {
    "type": "visual",          # NEW — visual | topical | hybrid
    "category": None,          # NEW — None for pure visual
    "name": "Stickman Animation",
    # ... rest unchanged
},
"dark_psychology": {
    "type": "topical",         # NEW
    "category": "psychology",  # NEW
    "name": "Dark Psychology",
    # ... rest unchanged
},
"dark_horror": {
    "type": "hybrid",          # NEW — has both visual identity + topic
    "category": "horror",      # NEW
    "name": "Dark / Horror",
    # ... rest unchanged
},
```

**Classification for all 43 templates:**

| Template ID | Type | Category |
|---|---|---|
| `cinematic` | visual | — |
| `anime` | visual | — |
| `surreal` | visual | — |
| `noir` | visual | — |
| `minimal` | visual | — |
| `cyberpunk` | visual | — |
| `vintage_retro` | visual | — |
| `fantasy_epic` | visual | — |
| `sci_fi` | visual | — |
| `watercolor` | visual | — |
| `comic_book` | visual | — |
| `gothic` | visual | — |
| `vaporwave` | visual | — |
| `3d_render` | visual | — |
| `dark_academia` | visual | — |
| `tropical` | visual | — |
| `urban_street` | visual | — |
| `lofi_pixel` | visual | — |
| `stickman_animation` | visual | — |
| `dark_horror` | hybrid | horror |
| `reddit_story` | hybrid | anecdote |
| `motivational` | hybrid | motivation |
| `nature_doc` | hybrid | nature |
| `documentary` | hybrid | history |
| `dark_psychology` | topical | psychology |
| `religion_spiritual` | topical | religion |
| `politics_power` | topical | politics |
| `true_crime` | topical | crime |
| `conspiracy` | topical | mystery |
| `stoicism` | topical | philosophy |
| `wealth_luxury` | topical | motivation |
| `mythology` | topical | history |
| `children_storybook` | hybrid | children |
| `war_military` | hybrid | history |
| `two_choices` | hybrid | psychology |

### 1.2 Create niche presets

**File**: `studio/niches/presets.py` (new file)

```python
"""
Niche presets — user-facing combinations of visual style + story tone + defaults.

A niche is a marketable content angle. Selecting a niche auto-fills:
  - category (broad topic)
  - visual_style (template ID for scene rendering)
  - story_tone (narration tone keyword)
  - voice, speed (TTS defaults)
  - editing_style (future: pacing preset)
"""

NICHE_PRESETS = {
    # ── Psychology ──
    "dark_psychology_stickman": {
        "label": "Stickman Dark Psychology",
        "category": "psychology",
        "niche": "dark_psychology",
        "visual_style": "stickman_animation",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.95,
        "tags": ["trending", "tiktok", "shorts"],
    },
    "dark_psychology_cinematic": {
        "label": "Cinematic Dark Psychology",
        "category": "psychology",
        "niche": "dark_psychology",
        "visual_style": "cinematic",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.95,
        "tags": ["youtube", "shorts"],
    },
    "dark_psychology_noir": {
        "label": "Noir Dark Psychology",
        "category": "psychology",
        "niche": "dark_psychology",
        "visual_style": "noir",
        "story_tone": "suspenseful",
        "voice": "bm_daniel",
        "speed": 0.9,
        "tags": ["youtube"],
    },

    # ── Crime ──
    "true_crime_cinematic": {
        "label": "Cinematic True Crime",
        "category": "crime",
        "niche": "true_crime",
        "visual_style": "cinematic",
        "story_tone": "dramatic",
        "voice": "bm_daniel",
        "speed": 0.9,
        "tags": ["youtube"],
    },
    "true_crime_noir": {
        "label": "Noir True Crime",
        "category": "crime",
        "niche": "true_crime",
        "visual_style": "noir",
        "story_tone": "dramatic",
        "voice": "bm_daniel",
        "speed": 0.85,
        "tags": ["youtube"],
    },

    # ── Horror ──
    "horror_cinematic": {
        "label": "Cinematic Horror",
        "category": "horror",
        "niche": "horror",
        "visual_style": "dark_horror",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.9,
        "tags": ["youtube", "shorts"],
    },
    "horror_stickman": {
        "label": "Stickman Horror",
        "category": "horror",
        "niche": "horror",
        "visual_style": "stickman_animation",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.95,
        "tags": ["tiktok", "shorts"],
    },

    # ── Motivation ──
    "stoicism_cinematic": {
        "label": "Cinematic Stoicism",
        "category": "philosophy",
        "niche": "stoicism",
        "visual_style": "cinematic",
        "story_tone": "educational",
        "voice": "bm_daniel",
        "speed": 0.9,
        "tags": ["youtube", "shorts"],
    },
    "motivation_stickman": {
        "label": "Stickman Motivation",
        "category": "motivation",
        "niche": "motivation",
        "visual_style": "stickman_animation",
        "story_tone": "inspirational",
        "voice": "af_heart",
        "speed": 1.0,
        "tags": ["tiktok", "shorts"],
    },

    # ── Religion ──
    "biblical_cinematic": {
        "label": "Cinematic Biblical",
        "category": "religion",
        "niche": "biblical",
        "visual_style": "cinematic",
        "story_tone": "dramatic",
        "voice": "bm_daniel",
        "speed": 0.85,
        "tags": ["youtube"],
    },

    # ── Mystery / Conspiracy ──
    "conspiracy_noir": {
        "label": "Noir Conspiracy",
        "category": "mystery",
        "niche": "conspiracy",
        "visual_style": "noir",
        "story_tone": "suspenseful",
        "voice": "bm_daniel",
        "speed": 0.9,
        "tags": ["youtube"],
    },

    # ── Anime ──
    "anime_horror": {
        "label": "Anime Horror",
        "category": "horror",
        "niche": "horror",
        "visual_style": "anime",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 1.0,
        "tags": ["shorts"],
    },
    "anime_romance": {
        "label": "Anime Romance",
        "category": "romance",
        "niche": "romance",
        "visual_style": "anime",
        "story_tone": "dramatic",
        "voice": "af_heart",
        "speed": 1.0,
        "tags": ["shorts"],
    },

    # ── Children ──
    "children_storybook_wholesome": {
        "label": "Wholesome Storybook",
        "category": "children",
        "niche": "children",
        "visual_style": "children_storybook",
        "story_tone": "wholesome",
        "voice": "af_heart",
        "speed": 0.9,
        "tags": ["youtube"],
    },

    # ── Sci-Fi ──
    "scifi_cyberpunk": {
        "label": "Cyberpunk Sci-Fi",
        "category": "science",
        "niche": "sci_fi",
        "visual_style": "cyberpunk",
        "story_tone": "dramatic",
        "voice": "bm_daniel",
        "speed": 1.0,
        "tags": ["youtube", "shorts"],
    },
}

# Story tone definitions — narration style keywords for the LLM
STORY_TONES = {
    "suspenseful": "Dark, tense, slow-building dread. Use short punchy sentences. Build unease.",
    "dramatic": "Emotional weight, vivid imagery, strong narrative arc. Vary sentence rhythm.",
    "educational": "Clear, authoritative, insightful. Teach through story, not lecture.",
    "inspirational": "Uplifting, empowering, forward-looking. End with a call to action.",
    "comedic": "Witty, unexpected twists, conversational. Subvert expectations.",
    "wholesome": "Warm, gentle, age-appropriate. Simple language, positive resolution.",
}

# All valid categories
CATEGORIES = [
    "psychology", "crime", "horror", "motivation", "philosophy",
    "religion", "mystery", "science", "history", "nature",
    "romance", "comedy", "children", "anecdote", "politics",
    "survival", "curiosity", "space",
]
```

### 1.3 Add resolve function

**File**: `studio/niches/presets.py` (same file, bottom)

```python
def resolve_niche(config: dict) -> dict:
    """Resolve a niche preset into pipeline dimensions.

    Accepts a config dict with any combination of:
      - niche_preset: preset ID (auto-fills everything)
      - style: legacy template ID (backward compat)
      - visual_style: override visual template
      - story_tone: override narration tone
      - voice, speed: override TTS defaults

    Returns dict with resolved: visual_style, story_tone, category, voice, speed
    """
    preset_id = config.get("niche_preset")
    preset = NICHE_PRESETS.get(preset_id) if preset_id else None

    # Legacy fallback: treat "style" as both visual_style and potential niche
    legacy_style = config.get("style", "cinematic")

    return {
        "visual_style": config.get("visual_style") or (preset["visual_style"] if preset else legacy_style),
        "story_tone": config.get("story_tone") or (preset["story_tone"] if preset else None),
        "category": config.get("category") or (preset["category"] if preset else None),
        "niche": preset["niche"] if preset else None,
        "voice": config.get("voice") or (preset.get("voice", "af_heart") if preset else "af_heart"),
        "speed": config.get("speed") or (preset.get("speed", 1.0) if preset else 1.0),
    }
```

### 1.4 Add API endpoint to serve presets

**File**: `studio/niches/routes.py` (new file)

```python
from flask import Blueprint, jsonify
from studio.niches.presets import NICHE_PRESETS, STORY_TONES, CATEGORIES

niches_bp = Blueprint("niches", __name__)

@niches_bp.route("/api/niches", methods=["GET"])
def list_niches():
    """Return all niche presets for the frontend picker."""
    return jsonify({
        "presets": NICHE_PRESETS,
        "story_tones": STORY_TONES,
        "categories": CATEGORIES,
    })
```

Register blueprint in app factory.

### 1.5 Create `studio/niches/__init__.py`

Empty file, makes it a package.

**Phase 1 touches:**
- `studio/scenes/templates.py` — add `type` + `category` fields (edit)
- `studio/niches/presets.py` — new file
- `studio/niches/routes.py` — new file
- `studio/niches/__init__.py` — new file
- App factory — register `niches_bp`

**Phase 1 does NOT touch:**
- Pipeline schemas
- Frontend
- Style compiler
- Story prompts
- Any existing behavior

---

## Phase 2 — Backend Integration (backward-compatible)

**Goal**: Pipeline accepts new fields, resolves niche → dimensions, passes them separately to story gen and scene gen. Old `style` field still works.

### 2.1 Extend pipeline schema

**File**: `studio/pipeline/schemas.py`

Add optional fields:

```python
class PipelineRunRequest(BaseModel):
    # ... existing fields unchanged ...
    style: str = "cinematic"                    # KEEP — backward compat

    # New niche fields (all optional)
    niche_preset: Optional[str] = None          # Preset ID from NICHE_PRESETS
    visual_style: Optional[str] = None          # Override visual template
    story_tone: Optional[str] = None            # Override narration tone
    category: Optional[str] = None              # Override broad topic
```

### 2.2 Extend story schema

**File**: `studio/story/schemas.py`

```python
class StoryGenerateRequest(BaseModel):
    # ... existing fields unchanged ...
    preset_style: str = "cinematic"             # KEEP
    story_category: str = "motivation"          # KEEP

    # New fields
    story_tone: Optional[str] = None            # Narration tone keyword
```

### 2.3 Wire resolve_niche into pipeline

**File**: `studio/pipeline/routes.py`

At the top of the pipeline run handler, after parsing config:

```python
from studio.niches.presets import resolve_niche

# Resolve niche dimensions
resolved = resolve_niche(config)

# Use resolved values downstream
visual_style = resolved["visual_style"]      # → scene generation
story_tone = resolved["story_tone"]          # → story generation
category = resolved["category"]             # → story generation
```

Pass `visual_style` to `resolve_template_bundle()` instead of raw `style`.
Pass `story_tone` + `category` to story prompt builder.

### 2.4 Update story prompt builder

**File**: `studio/story/prompts.py`

```python
def build_story_system_prompt(
    preset_style: str,
    story_category: str,
    duration: int,
    language: str,
    story_tone: str = None,       # NEW — optional tone override
) -> str:
    # If story_tone provided, inject tone description
    tone_desc = ""
    if story_tone:
        from studio.niches.presets import STORY_TONES
        tone_desc = STORY_TONES.get(story_tone, "")

    # ... existing logic, but add tone_desc to prompt ...
```

**Phase 2 touches:**
- `studio/pipeline/schemas.py` — add optional fields
- `studio/story/schemas.py` — add `story_tone`
- `studio/pipeline/routes.py` — call `resolve_niche()`, pass dimensions
- `studio/story/prompts.py` — accept `story_tone` param

**Phase 2 does NOT touch:**
- Frontend
- templates.py structure
- Style compiler internals

---

## Phase 3 — Frontend: Niche Picker + Decoupled Dropdowns

**Goal**: Replace single style dropdown with niche gallery + advanced overrides. Remove category=style sync.

### 3.1 Remove bidirectional sync

**File**: `frontend/src/features/pipeline/views/PipelinePage.vue`

Delete:
```javascript
// DELETE these
function setCategory(id) { story.storyCategory.value = id; style.value = id }
function setStyle(id) { style.value = id; story.storyCategory.value = id }
watch(style, (val) => { story.storyCategory.value = val || 'cinematic' }, { immediate: true })
```

Replace with independent state:
```javascript
const nichePreset = ref(localStorage.getItem('sts-niche-preset') || '')
const visualStyle = ref(localStorage.getItem('sts-visual-style') || 'cinematic')
const storyTone = ref(localStorage.getItem('sts-story-tone') || '')

function selectNiche(preset) {
  nichePreset.value = preset.id
  visualStyle.value = preset.visual_style
  storyTone.value = preset.story_tone
  story.storyCategory.value = preset.category
  voice.value = preset.voice || voice.value
  speed.value = preset.speed || speed.value
  // Persist
  localStorage.setItem('sts-niche-preset', preset.id)
  localStorage.setItem('sts-visual-style', preset.visual_style)
  localStorage.setItem('sts-story-tone', preset.story_tone)
}
```

### 3.2 Create NichePicker component

**File**: `frontend/src/features/pipeline/components/NichePicker.vue`

Grid of niche preset cards:
- Thumbnail (or colored placeholder)
- Label
- Tags (tiktok, youtube, shorts)
- Click → emits `select` with preset data

### 3.3 Add advanced panel

Below the niche picker, collapsible "Advanced" section:
- Visual Style dropdown (filtered to `type: visual` templates)
- Story Tone dropdown (from `STORY_TONES`)
- Category dropdown (from `CATEGORIES`)
- Voice + Speed (existing controls, moved here)

### 3.4 Update pipeline config transmission

**File**: `frontend/src/features/pipeline/composables/usePipeline.js`

```javascript
const config = {
  text: t,
  voice: voice.value,
  speed: speed.value,
  style: visualStyle.value,              // backward compat
  niche_preset: nichePreset.value,       // NEW
  visual_style: visualStyle.value,       // NEW
  story_tone: storyTone.value,           // NEW
  // ... rest unchanged
}
```

### 3.5 Fetch presets from API

**File**: `frontend/src/features/pipeline/composables/useNiches.js` (new)

```javascript
import { ref } from 'vue'
import { api } from '@/shared/api/client.js'

const presets = ref({})
const storyTones = ref({})
const categories = ref([])
const loaded = ref(false)

async function loadNiches() {
  if (loaded.value) return
  const data = await api.get('/api/niches')
  presets.value = data.presets
  storyTones.value = data.story_tones
  categories.value = data.categories
  loaded.value = true
}

export function useNiches() {
  return { presets, storyTones, categories, loadNiches }
}
```

**Phase 3 touches:**
- `PipelinePage.vue` — remove sync, add niche picker, add advanced panel
- `usePipeline.js` — send new fields in config
- New: `NichePicker.vue` component
- New: `useNiches.js` composable

---

## Phase 4 — Polish (optional, after stable)

### 4.1 Save as Niche
- User configures custom combo → clicks "Save as Niche"
- Stored in `_data/custom_niches.json` or user config
- Appears in niche gallery alongside built-in presets

### 4.2 Editing style integration
- Add `EDITING_STYLES` dict (pacing, transitions, caption style)
- Wire into video editor step
- Add to niche presets and advanced panel

### 4.3 Clean file split (only if templates.py gets too large)
- `studio/scenes/visual_styles.py` — pure visual templates
- `studio/story/tones.py` — story tone definitions (already in presets.py)
- `studio/editor/editing_styles.py` — editing presets

### 4.4 Analytics hooks
- Log which niche/visual/tone combos are used
- Track completion rates by niche
- Surface "trending" tags based on usage

---

## File Change Summary

| Phase | New Files | Modified Files |
|-------|-----------|---------------|
| **1** | `studio/niches/__init__.py`, `studio/niches/presets.py`, `studio/niches/routes.py` | `studio/scenes/templates.py`, app factory |
| **2** | — | `studio/pipeline/schemas.py`, `studio/story/schemas.py`, `studio/pipeline/routes.py`, `studio/story/prompts.py` |
| **3** | `frontend/.../NichePicker.vue`, `frontend/.../useNiches.js` | `PipelinePage.vue`, `usePipeline.js` |
| **4** | `_data/custom_niches.json`, `studio/editor/editing_styles.py` | Various |

## Rules

1. Each phase is independently shippable
2. Old `style` field works as fallback in all phases
3. No destructive changes to templates.py until Phase 4
4. story_tone lives in niches/presets.py, not scene templates
5. Frontend sends both old (`style`) and new (`visual_style`, `niche_preset`) fields for backward compat
