# ScriptToScene Studio

Turn a script into a fully produced short-form video — TTS narration, AI scene generation, asset grabbing, timeline editing, captions, and one-click export.

---

## Workflow Builder

The workflow builder is the default interface for assembling and running
production pipelines. Start with the [Workflow Builder user guide](docs/workflow-guide.md)
to create, validate, save, and run the built-in Full Video template. For every
available node, port, setting, and built-in template, see the generated
[Workflow Node Reference](docs/workflow-nodes.md). Developers can add a node
from scaffold through release with the generated
[Workflow Node Author Guide](docs/workflow-node-author-guide.md).

## Provider platform

Script, Scene Blueprint, TTS, Storyboard, and Animator dispatch through
registered providers. The live catalog and domain contracts are generated as the
[Provider Reference](docs/providers.md). Developers can add a provider from
scaffold through release with the
[Provider Author Guide](docs/provider-author-guide.md)
(including the [troubleshooting](docs/provider-author-guide.md#troubleshooting)
path). Quick scaffold notes also live in
[docs/provider-template/README.md](docs/provider-template/README.md).

Regenerate workflow and provider docs together:

```powershell
venv\Scripts\python.exe -m studio.workflows.docs
venv\Scripts\python.exe -m studio.workflows.docs --check
```

---

## How It Works — A Real Scenario

Imagine you have a 200-word script about a psychological phenomenon. Here's what happens when you paste it into ScriptToScene Studio and hit **Run Pipeline**:

```
 YOUR SCRIPT
 "There is a psychological phenomenon called the Baader-Meinhof effect.
  Once you learn about something new, you suddenly start seeing it everywhere..."
      │
      ▼
 ┌─────────────────────────────────────────────────────────────┐
 │  STEP 1 — TTS                                              │
 │  Kokoro neural TTS reads your script aloud using the        │
 │  "af_heart" voice at 1.0× speed.                           │
 │  Output: voice.wav (16 kHz mono) + voice.json metadata     │
 └────────────────────────┬────────────────────────────────────┘
                          ▼
 ┌─────────────────────────────────────────────────────────────┐
 │  STEP 2 — FORCE ALIGNMENT                                  │
 │  Whisper aligns every spoken word to its exact timestamp    │
 │  in the audio file (word-level precision).                  │
 │  Output: alignment.json — [{word, begin, end}, ...]        │
 └────────────────────────┬────────────────────────────────────┘
                          ▼
 ┌─────────────────────────────────────────────────────────────┐
 │  STEP 3 — SEGMENTATION                                     │
 │  The alignment is split into natural scene-sized chunks     │
 │  (1.5–3 s each) based on punctuation, pauses, and mood     │
 │  shift keywords like "but", "however", "suddenly".          │
 │  Output: segmented.json — 8-12 segments for a 200-word     │
 │  script, each with start/end times and text.                │
 └────────────────────────┬────────────────────────────────────┘
                          ▼
 ┌─────────────────────────────────────────────────────────────┐
 │  STEP 4 — SCENE GENERATION (AI)                            │
 │  Segments are sent to Gemini 2.5 Flash (via n8n webhook).  │
 │  The AI analyzes mood, theme, and tone, then writes a      │
 │  detailed image_prompt for each segment — respecting the   │
 │  chosen style template (e.g. "cinematic", "pixel art").    │
 │  Output: scenes.json — image prompts, narrative roles,     │
 │  scene types (video/image/text), overlay text.             │
 └────────────────────────┬────────────────────────────────────┘
                          ▼
 ┌─────────────────────────────────────────────────────────────┐
 │  STEP 5 — ASSET GRABBING                                   │
 │  Each scene's image_prompt is sent to an AI media provider  │
 │  (Grok, Midjourney, Meta AI, or Kie AI).                   │
 │  The grabber polls until all assets are ready.              │
 │  Output: one video or image file per scene in               │
 │  output/animator/{project_id}/{scene_index}/                │
 └────────────────────────┬────────────────────────────────────┘
                          ▼
 ┌─────────────────────────────────────────────────────────────┐
 │  STEP 6 — ASSEMBLY                                         │
 │  Scenes + assets + audio are merged into a project JSON     │
 │  and loaded into the visual timeline editor.                │
 │  Output: initial.json + work@in@progress.json               │
 └────────────────────────┬────────────────────────────────────┘
                          ▼
 ┌─────────────────────────────────────────────────────────────┐
 │  STEP 7 — EXPORT                                           │
 │  FFmpeg renders the final video: scene media stitched       │
 │  together, narration layered on top, background music       │
 │  ducked under speech, captions baked in, grain overlay      │
 │  applied. Exported as H.264 MP4.                            │
 │  Output: output/exports/{project_id}/video.mp4              │
 └─────────────────────────────────────────────────────────────┘
```

You can halt the pipeline at any step with `stop_after` (e.g. `stop_after=scenes`) and resume or branch off manually from the UI.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Browser (Vue 3 + Vite)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐ │
│  │ Pipeline  │ │ TTS      │ │ Scenes   │ │ Timeline │ │ Export    │ │
│  │ Control   │ │ Panel    │ │ Viewer   │ │ Editor   │ │ Library   │ │
│  └─────┬────┘ └─────┬────┘ └─────┬────┘ └─────┬────┘ └─────┬─────┘ │
└────────┼────────────┼────────────┼────────────┼────────────┼────────┘
         │            │            │            │            │
         ▼            ▼            ▼            ▼            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     Flask API (localhost:5050)                        │
│                                                                      │
│  studio/                                                             │
│  ├── pipeline/     Orchestrator — runs all 7 steps, SSE progress     │
│  ├── tts/          Kokoro TTS — voices, blending, normalization      │
│  ├── timing/       Whisper alignment — word-level timestamps         │
│  ├── segmenter/    Break scoring — split aligned text into scenes    │
│  ├── scenes/       AI prompts — n8n webhook → Gemini 2.5 Flash      │
│  ├── assets/       Multi-provider grabber — Grok, MJ, Meta, Kie     │
│  ├── editor/       Timeline assembly + FFmpeg export engine          │
│  ├── captions/     Word-level captions — presets + custom styles     │
│  ├── music/        Background tracks — volume, ducking, loops        │
│  └── thumbnails/   Preview generation — per-scene + per-export       │
│                                                                      │
│  Shared:  config.py · io_utils.py · security.py · ffmpeg_utils.py   │
└──────────────────────────────────────────────────────────────────────┘
         │                    │                     │
         ▼                    ▼                     ▼
┌──────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ Kokoro ONNX  │   │ n8n Webhook      │   │ Asset Providers  │
│ + Whisper    │   │ → Gemini 2.5     │   │ Grok / MJ / Meta │
│ (local)      │   │   Flash          │   │ / Kie AI         │
└──────────────┘   └──────────────────┘   └──────────────────┘
```

---

## Data Schemas (with examples)

Every pipeline step writes its output to `output/` as JSON. Below is what each file looks like.

### TTS Metadata — `output/tts/{project_id}/voice.json`

```jsonc
{
  "project_id": "pp_8T1UU3",
  "voice": "af_heart",
  "speed": 1.0,
  "prompt": "There is a psychological phenomenon called the Baader-Meinhof effect...",
  "duration": 28.5,
  "sample_rate": 24000,
  "created_at": "2026-03-18T14:30:00"
}
```

### Alignment — `output/alignments/{project_id}/alignment.json`

Word-level timestamps produced by Whisper force-alignment:

```jsonc
{
  "alignment": [
    { "word": "There",         "begin": 0.24, "end": 0.44 },
    { "word": "is",            "begin": 0.44, "end": 0.56 },
    { "word": "a",             "begin": 0.56, "end": 0.64 },
    { "word": "psychological", "begin": 0.64, "end": 1.32 },
    { "word": "phenomenon",    "begin": 1.32, "end": 2.04 }
    // ... every word in the script
  ],
  "transcript": "There is a psychological phenomenon...",
  "word_count": 106,
  "inference_time": 14.488
}
```

### Segmentation — `output/segmenters/{project_id}/segmented.json`

The alignment is split into natural scene-sized chunks. The segmenter scores potential break points using punctuation, silence gaps, mood-shift keywords (`but`, `yet`, `however`), visual nouns (`sky`, `tree`, `water`), and action verbs.

```jsonc
{
  "segments": [
    {
      "index": 0,
      "words": "There is a psychological phenomenon called the Baader-Meinhof effect.",
      "start": 0.24,
      "end": 3.14,
      "duration": 2.9,
      "is_filler": false,         // true = silence gap (no speech)
      "break_reason": "strong_break"
    },
    {
      "index": 1,
      "words": "Once you learn about something new,",
      "start": 3.14,
      "end": 5.28,
      "duration": 2.14,
      "is_filler": false,
      "break_reason": "punctuation"
    }
    // ...one segment per future scene
  ],
  "config": {
    "target_min": 1.5,   // minimum scene duration (seconds)
    "target_max": 3.0,   // target scene duration
    "hard_max": 4.0,     // absolute maximum
    "hard_min": 0.8,     // absolute minimum
    "gap_filler": 0.3    // silence threshold
  },
  "stats": {
    "total_segments": 10,
    "total_duration": 28.5,
    "avg_duration": 2.85
  }
}
```

### Scenes — `output/scenes/{project_id}/scenes.json`

AI-generated scene descriptions and metadata. The `analysis` block drives visual consistency across all scenes:

```jsonc
{
  "analysis": {
    "core_theme": "Our brains are pattern-seeking machines that create meaning from coincidence",
    "mood": "observational wonder",
    "environment": "everyday urban settings",
    "color_palette": ["steel blue", "warm amber", "muted grey", "soft white", "burnt orange"],
    "tone": "informative",
    "visual_style": "cinematic photorealistic with warm editorial tones"
  },
  "scenes": [
    {
      "index": 0,
      "title": "The Hidden Pattern",
      "narrative_role": "hook",         // hook | buildup | peak | transition | text_accent | cta
      "type_of_scene": "video",         // video | image | text
      "image_prompt": "Wide shot, a person walking through a busy crosswalk, surrounded by blurred pedestrians, golden hour side-lighting casting long shadows, steel blue tones in the background buildings, subtle lens flare, shallow depth of field isolating the subject, slow crowd drift, gentle light shift, ambient city motion",
      "text_content": null,             // only for type_of_scene: "text"
      "timestamp": 0.0,
      "timeline_start": 0.0,
      "timeline_end": 3.14,
      "duration": 3.14,
      "segment_words": "There is a psychological phenomenon called the Baader-Meinhof effect."
    },
    {
      "index": 1,
      "title": "Sudden Recognition",
      "narrative_role": "buildup",
      "type_of_scene": "video",
      "image_prompt": "Medium close-up, a person's eyes widening in recognition at a coffee shop counter, warm amber lamplight overhead, shallow focus on the face with bokeh background, steam rising from a cup, subtle head turn, eye dart, background customer movement",
      "text_content": null,
      "timestamp": 3.14,
      "timeline_start": 3.14,
      "timeline_end": 5.28,
      "duration": 2.14,
      "segment_words": "Once you learn about something new,"
    }
    // ...one scene per segment
  ],
  "pipeline_timing": {
    "tts": 5.23,
    "timing": 14.49,
    "segment": 0.15,
    "scenes": 28.3,
    "assets": 120.5
  }
}
```

### Project (Editor State) — `output/projects/{project_id}/work@in@progress.json`

The timeline editor saves the full project state including scene order, music, captions, and export settings:

```jsonc
{
  "project_id": "pp_8T1UU3",
  "scenes": [
    {
      "index": 0,
      "title": "The Hidden Pattern",
      "duration": 3.14,
      "asset_path": "output/animator/pp_8T1UU3/0/video.mp4",
      "text_overlay": null,
      "visible": true
    }
    // ...
  ],
  "audio": {
    "narration": "output/tts/pp_8T1UU3/voice.wav",
    "music": {
      "file": "output/musics/ambient-lo-fi.mp3",
      "volume": 0.3,
      "loop": true,
      "duck_under_voice": true,
      "fade_in": 2.0,
      "fade_out": 3.0
    }
  },
  "captions": {
    "preset": "bold_popup",
    "enabled": true
  },
  "export_settings": {
    "profile": "9:16",
    "grain_overlay": true,
    "grain_opacity": 0.15
  }
}
```

---

## Narrative Roles

Every scene is assigned a **narrative role** that determines its visual function in the video:

| Role | Purpose | Typical camera | Example |
|---|---|---|---|
| `hook` | Grab attention in the first 1–2 seconds | Wide or extreme wide — establish the world | A lone figure in a vast cityscape |
| `buildup` | Develop tension or context | Medium, over-shoulder, POV — build intimacy | Eyes scanning a crowded room |
| `peak` | Maximum emotional intensity | Extreme close-up or low-angle — impact | A hand slamming a table in slow motion |
| `transition` | Breathing room between beats | Wide or bird's-eye — reset | An empty hallway, door closing |
| `text_accent` | Overlay text on blurred background | Blurred medium — frame for text | Soft bokeh behind bold text: "THE TRUTH" |
| `cta` | Call to action / closing shot | Match hook framing — bookend | Same cityscape, now at sunset |

---

## Style Templates

Choose a visual style when running the pipeline. Each template instructs the AI scene generator on color palette, lighting, composition, and mood:

| Template | Aesthetic | Think... |
|---|---|---|
| `cinematic` | Photorealistic, dramatic lighting, film grain | Hollywood cinematography |
| `dark_horror` | Eerie shadows, desaturated tones, fog | Atmospheric horror |
| `reddit_story` | Everyday realism, relatable settings | Candid photography |
| `motivational` | Bright, warm, epic scale | Sunrise over a mountain peak |
| `nature_doc` | BBC Earth, macro detail, sweeping landscapes | Planet Earth |
| `anime` | Vivid cel-shading, expressive characters | Makoto Shinkai skies |
| `surreal` | Impossible geometry, floating objects | Dali meets digital art |
| `noir` | High-contrast B&W, venetian blind shadows | Classic detective film |
| `minimal` | Negative space, single focal subject | Modern design photography |
| `cyberpunk` | Neon-soaked streets, rain-slicked chrome | Blade Runner 2049 |
| `vintage_retro` | 70s–80s faded film, warm amber tones | Kodachrome nostalgia |
| `fantasy_epic` | Dragons, castles, enchanted forests | Tolkien concept art |
| `sci_fi` | Spaceships, alien worlds, cosmic scale | Interstellar, The Expanse |
| `watercolor` | Soft washes, visible brushstrokes | Children's book illustration |
| `comic_book` | Bold outlines, halftone, flat colors | Marvel meets Lichtenstein |
| `gothic` | Ornate architecture, candlelit elegance | Tim Burton grandeur |
| `vaporwave` | Pastel grids, glitch art, VHS distortion | A E S T H E T I C |
| `documentary` | Raw, photojournalistic, available light | Magnum Photos |
| `3d_render` | Clean CGI, soft studio lighting | Pixar / Octane render |
| `dark_academia` | Old libraries, lamplight, autumn tones | Oxford meets Donna Tartt |
| `tropical` | Lush jungles, turquoise waters, golden sun | Travel magazine cover |
| `urban_street` | City grit, graffiti, street photography | Vivian Maier |
| `dark_psychology` | Manipulation, shadows, duality | Mindhunter, Se7en |
| `religion_spiritual` | Sacred imagery, divine light, temples | Renaissance painting |
| `politics_power` | Podiums, crowds, propaganda | House of Cards |
| `true_crime` | Evidence boards, forensic detail | Making a Murderer |
| `conspiracy` | Secret societies, hidden symbols | Eyes Wide Shut |
| `stoicism` | Marble busts, contemplation, ruins | Marcus Aurelius energy |
| `wealth_luxury` | Opulence, supercars, gold accents | Luxury brand advertising |
| `mythology` | Gods, heroes, mythical beasts | God of War concept art |
| `children_storybook` | Whimsical, soft pastels, magical | Beatrix Potter meets Ghibli |
| `war_military` | Battlefields, soldiers, sacrifice | Saving Private Ryan |
| `stickman_animation` | Stick figures, whiteboard doodles | XKCD meets explainer videos |
| `two_choices` | Split-screen fates, branching choices | Bandersnatch |
| `lofi_pixel` | Cozy pixel art, retro game aesthetics | Stardew Valley vibes |

---

## Caption Presets

Captions are generated from word-level alignment data and baked into the export. Built-in presets:

| Preset | Style | Best for |
|---|---|---|
| `bold_popup` | Big, bold, uppercase — pops in | YouTube Shorts, high energy |
| `subtitle_bar` | Clean dark background bar | Informational, documentary |
| `karaoke` | Words light up as spoken | Music, poetry, lyric videos |
| `minimal` | Small, unobtrusive | Accessibility, subtle overlay |
| `single_line` | Viral short-form style | TikTok, Reels |

Each preset is fully customizable:

```jsonc
{
  "font_family": "Montserrat",
  "font_size": 64,
  "font_weight": "800",
  "color": "#FFFFFF",
  "stroke_color": "none",
  "background": "none",
  "position_y": 75,                   // % from top
  "animation": "pop",                 // pop | fade | highlight | hard_cut
  "text_transform": "uppercase",      // none | uppercase | lowercase
  "shadow_color": "#000000",
  "shadow_blur": 8
}
```

---

## Features

### Pipeline (end-to-end automation)
- **7-step pipeline** — TTS → Force Alignment → Segmentation → Scene Generation → Asset Grabbing → Assembly → Export
- **Per-step timing** — each pipeline step is timed and persisted to `scenes.json`, visible in the export library
- **Stop-after control** — halt the pipeline at any step (`stop_after=tts`, `scenes`, `assets`, etc.)
- **Chapter-based generation** — long scripts are automatically chunked into chapters for scene generation

**Job History note:** `Process again` reruns the pipeline with the exact saved story text for that job. To get a completely new story concept for the same niche, start a new job so story generation runs again and anti-repeat logic can apply.

### TTS (Text-to-Speech)
- **Kokoro TTS** — high-quality neural TTS with 50+ voices (American, British, Japanese, Chinese, Spanish, French, Hindi, Italian, Portuguese)
- **Voice blending** — SLERP interpolation between voices for custom styles
- **Pronunciation overrides** — `[word](/IPA/)` syntax for precise control
- **Breathing blocks** — natural pauses inserted for realistic narration
- **Loudness normalization** — consistent audio levels at -23 LUFS

### Alignment & Segmentation
- **Force alignment** — word-level timestamps via Whisper
- **Break scoring** — punctuation, silence gaps, mood-shift keywords, visual nouns, action verbs
- **Configurable** — adjust segment duration (target min/max), word count, gap thresholds

### Scene Generation
- **AI-powered** — Gemini 2.5 Flash via n8n webhook generates image prompts and scene metadata
- **Thematic interpretation** — scenes visualize the *meaning* of the script, never literal dictionary illustrations
- **34 style templates** — cinematic, watercolor, pixel art, cyberpunk, dark horror, and more
- **6 narrative roles** — hook, buildup, peak, transition, text accent, CTA

### Asset Grabber
- **Multi-provider** — Grok (video/image), Midjourney, Meta AI, Kie AI
- **Video-first** — generates video assets by default (configurable quality: 360p/480p/720p, duration: 6s)
- **Auto-polling** — pipeline waits for all assets to be ready before proceeding
- **Smart resolution** — asset picker always prefers video files over thumbnail JPGs

### Timeline Editor
- **Visual editor** — drag-and-drop scene reordering, duration editing, text overlays
- **Audio tracks** — multi-track audio with volume, ducking, fade in/out
- **Captions** — auto-generated word-level captions with preset styles
- **Grain overlay** — optional film grain effect with configurable opacity

### Export
- **Profile-based** — YT Shorts (9:16), TikTok, Reels, Landscape (16:9), Square (1:1)
- **Captions baked in** — optional styled captions rendered into the export
- **Pipeline timing breakdown** — expandable step-by-step timing in the export library UI
- **ZIP download** — download project assets as a bundled archive

### Thumbnails
- **Per-project thumbnails** — organized in `output/thumbnails/{project_id}/` with module subfolders
  - `assets/` — one thumbnail per scene asset (from video or image)
  - `exports/` — one thumbnail per exported video
  - `editor/` — cover thumbnail from first editor scene
- **Batch generation** — generate thumbnails for a single project or all projects at once

### Music
- **Background music** — attach music tracks (mp3, wav, ogg, m4a, flac)
- **Ducking** — auto-lower music volume when narration is active
- **Looping** — loop short tracks to fill the full video duration
- **Fades** — configurable fade in/out durations

---

## Prerequisites

| Dependency | Version | Purpose |
|---|---|---|
| **Python** | 3.10+ | Backend runtime |
| **Node.js** | 18+ | Frontend build tooling (Vite + Vue 3) |
| **npm** | 9+ | Frontend dependency management |
| **FFmpeg** | 6+ | Video/audio processing, thumbnail extraction |
| **n8n** | (optional) | AI scene generation webhook |

### FFmpeg

FFmpeg must be available either on your system PATH or placed in the `bin/` directory at the project root:

```
bin/
├── ffmpeg.exe
└── ffprobe.exe
```

The app checks `bin/` first, then falls back to the system PATH.

### n8n (optional)

Scene generation uses an n8n webhook. Configure the URL in `.env`:

```env
N8N_WEBHOOK_URL=http://localhost:5678/webhook/scene-generator
```

---

## Installation

### Quick start (Windows)

```bat
:: 1. Clone the repo
git clone https://github.com/Lacarte/ScriptToScene-Studio.git
cd ScriptToScene-Studio

:: 2. Run setup (creates venv, installs Python deps)
setup.bat

:: 3. Install frontend dependencies
cd frontend
npm install
cd ..

:: 4. Copy environment config
copy .env.example .env
:: Edit .env with your API keys

:: 5. Start the app
start-prod.bat
```

### Manual setup

```bash
# 1. Create and activate virtual environment
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install frontend dependencies
cd frontend
npm install
cd ..

# 4. Environment config
cp .env.example .env
# Edit .env with your webhook URLs and API keys

# 5. Run the server
python app.py
```

The server starts on `http://localhost:5050` and opens your browser automatically.

### Development mode

```bat
start-dev.bat
```

This starts both the Flask backend (port 5050, minimized) and the Vite dev server (port 5174) with hot reload.

---

## Project Structure

```
ScriptToScene-Studio/
├── app.py                  # Flask entry point
├── config.py               # Centralized config (dirs, env vars)
├── requirements.txt        # Python dependencies
├── studio/                 # Backend modules
│   ├── pipeline/           # End-to-end pipeline orchestrator
│   ├── tts/                # Text-to-speech (Kokoro)
│   │   ├── routes.py       #   API endpoints
│   │   ├── normalize.py    #   Text preprocessing (contractions, foreign words, breathing)
│   │   └── audio.py        #   Concatenation, loudness normalization
│   ├── timing/             # Force alignment (Whisper) + segmentation engine
│   ├── segmenter/          # Segmentation API layer
│   ├── scenes/             # AI scene generation
│   │   ├── prompts.py      #   LLM system prompt (output format, thematic rules)
│   │   ├── templates.py    #   34 style presets (color, lighting, composition)
│   │   └── chapters.py     #   Long-text chunking for chapter-based generation
│   ├── assets/             # Asset grabber (Grok, Midjourney, Meta AI, Kie AI)
│   ├── editor/             # Timeline editor API + FFmpeg export engine
│   ├── captions/           # Caption generation + presets
│   ├── thumbnails/         # Per-project thumbnail generation
│   ├── music/              # Background music management
│   ├── io_utils.py         # JSON I/O with atomic writes and .bak recovery
│   ├── security.py         # Path traversal prevention, ID sanitization
│   └── ffmpeg_utils.py     # FFmpeg/FFprobe binary resolution
├── frontend/               # Vue 3 + Vite frontend
│   └── src/
│       ├── features/       # Feature-based modules (pipeline, editor, export library, etc.)
│       └── shared/         # Shared utilities
├── static/                 # Built SPA (HTML/JS/CSS)
├── assets/                 # App assets (fonts, sounds, caption presets)
├── bin/                    # FFmpeg binaries (not in repo)
├── models/                 # TTS model cache (auto-downloaded)
├── tmp/                    # Temporary files (preview cache, gitignored)
├── _dev/                   # Development tools, automation, and docs (see _dev/TODO.md)
└── output/                 # All generated data (gitignored)
    ├── tts/                # {id}/voice.wav + voice.json
    ├── alignments/         # {id}/alignment.json
    ├── segmenters/         # {id}/segmented.json
    ├── scenes/             # {id}/scenes.json (source of truth)
    ├── assets/             # {id}/{scene_index}/video.mp4 or image.jpg
    ├── projects/           # {id}/initial.json + work@in@progress.json
    ├── exports/            # {id}/video.mp4
    ├── captions/           # {id}/captions.json
    ├── musics/             # User-uploaded music files
    ├── thumbnails/         # {id}/{module}/{file}.jpg
    └── TRASH/              # Soft-deleted files
```

---

## Project IDs

Every project gets a unique ID with a two-character prefix:

| Prefix | Meaning | Created by |
|---|---|---|
| `pp_` | Pipeline project | Running the full pipeline |
| `pm_` | Manual project | Using individual steps (editor, timing, etc.) |

Example: `pp_8T1UU3`, `pm_SLLGTM`. IDs are 6-character alphanumeric with collision detection across all output directories.

---

## API Overview

### Pipeline

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/pipeline/run` | Start full pipeline (returns `job_id` + `project_id`) |
| `GET` | `/api/pipeline/progress/:job_id` | SSE progress stream (real-time step updates) |
| `GET` | `/api/pipeline/jobs` | List recent pipeline executions |

**Pipeline request body:**

```jsonc
{
  "text": "Your script text...",       // 1–10,000 characters
  "voice": "af_heart",                 // Kokoro voice ID
  "speed": 1.0,                        // 0.5–2.0
  "style": "cinematic",                // template ID from style templates
  "stop_after": null,                  // null | "tts" | "timing" | "segment" | "scenes" | "assets" | "assemble"
  "provider": "grok",                  // grok | midjourney | meta_ai | kie_ai
  "aspect_ratio": "9:16",             // export aspect ratio
  "grok_mode": "video",               // video | image
  "grok_quality": "480p",             // 360p | 480p | 720p
  "grok_duration": "6s"               // asset video duration
}
```

### Individual Steps

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/tts/generate` | Generate TTS audio |
| `POST` | `/api/tts/multivoice` | Multi-voice blending |
| `GET` | `/api/tts/voices` | List available voices |
| `POST` | `/api/alignment/run` | Force-align audio with text |
| `POST` | `/api/segmenter/run` | Split alignment into segments |
| `POST` | `/api/scenes/generate` | Generate scene descriptions via AI |
| `POST` | `/api/assets/grabber/start` | Start asset generation/download |
| `GET` | `/api/assets/status/:id` | Check grabber job status |
| `POST` | `/api/projects/:id/assemble` | Assemble project for editor |

### Editor & Export

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/editor/save` | Save editor state |
| `POST` | `/api/export` | Start video export |
| `GET` | `/api/export/library` | List all exported videos |
| `GET` | `/api/captions/presets` | List caption style presets |
| `GET` | `/api/music/library` | List available background tracks |

### Project Management

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/projects` | List all projects |
| `GET` | `/api/health` | System health (alignment, FFmpeg, TTS model) |
| `POST` | `/api/thumbnails/:id/generate` | Generate project thumbnails |
| `GET` | `/api/thumbnails/:id` | List project thumbnails |

---

## Example Workflows

### 1. Full Automation — Script to Export in One Call

```bash
curl -X POST http://localhost:5050/api/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{
    "text": "There is a psychological phenomenon called the Baader-Meinhof effect...",
    "voice": "af_heart",
    "speed": 1.0,
    "style": "cinematic",
    "provider": "grok",
    "grok_mode": "video"
  }'

# Response: { "job_id": "abc123", "project_id": "pp_8T1UU3" }

# Stream real-time progress via SSE:
curl -N http://localhost:5050/api/pipeline/progress/abc123
# Events: { "step": "tts", "status": "running" }
#         { "step": "tts", "status": "done", "duration": 5.23 }
#         { "step": "timing", "status": "running" }
#         ...
#         { "step": "done", "project_id": "pp_8T1UU3" }
```

### 2. Stop Early — Generate Scenes Only, Then Edit Manually

```bash
# Run pipeline but stop after scene generation
curl -X POST http://localhost:5050/api/pipeline/run \
  -d '{ "text": "...", "style": "dark_psychology", "stop_after": "scenes" }'

# Review scenes in the UI, tweak prompts, then grab assets manually
curl -X POST http://localhost:5050/api/assets/grabber/start \
  -d '{ "project_id": "pp_8T1UU3", "provider": "grok", "grok_mode": "video" }'

# Assemble into editor when ready
curl -X POST http://localhost:5050/api/projects/pp_8T1UU3/assemble

# Edit in the timeline editor UI, then export
curl -X POST http://localhost:5050/api/export \
  -d '{ "project_id": "pp_8T1UU3", "profile": "9:16", "captions": true }'
```

### 3. TTS Only — Generate Narration for an External Editor

```bash
curl -X POST http://localhost:5050/api/tts/generate \
  -d '{ "prompt": "Your script here...", "voice": "bf_emma", "speed": 1.2 }'

# Response includes the path to the .wav file
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `N8N_WEBHOOK_URL` | `http://localhost:5678/webhook/scene-generator` | n8n scene generation webhook |
| `N8N_ASSET_WEBHOOK_URL` | `http://localhost:5678/webhook/image-generator` | n8n asset generation webhook |
| `KIE_AI_API_KEY` | — | Kie AI image generation API key |
| `STS_BIND_HOST` | `127.0.0.1` | Server bind address |
| `STS_NO_BROWSER` | — | Set to skip auto-opening browser |
| `STS_CORS_ORIGINS` | — | CORS whitelist for cross-origin requests |

---

## Security

- **Path traversal prevention** — all file operations use `safe_join()` to ensure paths stay within the project root
- **Project ID sanitization** — IDs are stripped to alphanumeric, underscore, hyphen only
- **Webhook URL validation** — requires http/https, blocks invalid hosts
- **Loopback-only endpoints** — sensitive operations (folder open, data wipe) restricted to 127.0.0.1
- **Atomic JSON writes** — `safe_json_write()` uses fsync + `.bak` backups to prevent corruption
- **Soft deletion** — projects are moved to `TRASH/`, not permanently deleted

---

## Browser Automation — Grok Assets Synchronizer

**Location:** `_dev/automation/automa/grok/Grok Assets Synchronizer.automa.json`

The Grok Assets Synchronizer is an [Automa](https://www.automa.site/) browser extension workflow that bridges ScriptToScene Studio with Grok's AI image/video generation on the web. It runs as an injected script on the Grok website and provides:

- **Scene prompt typing** — automatically types each scene's `image_prompt` into Grok's input field, one scene at a time, simulating human keystrokes to bypass paste restrictions
- **Asset polling** — polls the Studio backend (`/api/assets/grabber/pending`) for scenes that still need assets, then queues them for generation
- **Auto-sync** — continuously syncs generated assets back to the Studio backend, matching Grok's output to the correct scene index
- **CSP bypass** — uses Automa's `automaFetch()` to reach `localhost:5050` from Grok's page, which blocks standard `fetch()` via Content Security Policy
- **Floating control panel** — injects a draggable UI overlay on the Grok page with start/stop, batch settings, typing queue status, and connection indicator
- **Configurable** — aspect ratio (`9:16`, `16:9`, `1:1`), quality (`360p`–`720p`), duration (`6s`), and typing speed are adjustable from the overlay panel

### How it fits in the pipeline

During **Step 5 (Asset Grabbing)**, when the provider is set to `grok`, the pipeline writes pending scene prompts to the grabber queue. The Automa workflow running in the browser picks up those prompts, types them into Grok, waits for generation, and syncs the resulting media files back to `output/animator/{project_id}/`.

---

## License

MIT
