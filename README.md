# ScriptToScene Studio

Turn a script into a fully produced short-form video — TTS narration, AI scene generation, asset grabbing, timeline editing, captions, and one-click export.

## Features

### Pipeline (end-to-end automation)
- **7-step pipeline** — TTS → Force Alignment → Segmentation → Scene Generation → Asset Grabbing → Assembly → Export
- **Per-step timing** — each pipeline step is timed and persisted to `scenes.json`, visible in the export library
- **Stop-after control** — halt the pipeline at any step (`stop_after=tts`, `scenes`, `assets`, etc.)
- **Chapter-based generation** — long scripts are automatically chunked into chapters for scene generation

### TTS (Text-to-Speech)
- **Kokoro TTS** — high-quality neural TTS with multiple voices
- **Voice styles** — recommended style suggestions per story type
- **Breathing blocks** — natural pauses inserted for realistic narration
- **Loudness normalization** — consistent audio levels across exports

### Alignment & Segmentation
- **Force alignment** — word-level timestamps via Whisper
- **Smart segmentation** — splits aligned text into scenes based on natural speech boundaries
- **Configurable** — adjust segment duration, word count, and other parameters

### Scene Generation
- **AI-powered** — Gemini 2.5 Flash via n8n webhook generates image prompts and scene metadata
- **Style templates** — cinematic, watercolor, pixel art, lo-fi cozy, and more
- **Narrative roles** — hook, buildup, peak, transition, text accent, CTA

### Asset Grabber
- **Multi-provider** — Grok (video/image), Midjourney, Meta AI
- **Video-first** — generates video assets by default (configurable quality and duration)
- **Auto-polling** — pipeline waits for all assets to be ready before proceeding
- **Smart resolution** — asset picker always prefers video files over thumbnail JPGs

### Timeline Editor
- **Visual editor** — drag-and-drop scene reordering, duration editing, text overlays
- **Audio tracks** — multi-track audio with volume, ducking, fade in/out
- **Captions** — auto-generated word-level captions with preset styles (bold popup, single line, etc.)
- **Grain overlay** — optional film grain effect with configurable opacity and timing

### Thumbnails
- **Per-project thumbnails** — organized in `output/thumbnails/{project_id}/` with module subfolders
  - `assets/` — one thumbnail per scene asset (from video or image)
  - `exports/` — one thumbnail per exported video
  - `editor/` — cover thumbnail from first editor scene
- **Batch generation** — generate thumbnails for a single project or all projects at once
- **Smart sourcing** — extracts frames from videos, resizes images, prefers video over image sources

### Export
- **Profile-based** — YT Shorts (9:16), TikTok, Reels, Landscape (16:9), Square (1:1)
- **Captions baked in** — optional styled captions rendered into the export
- **Pipeline timing breakdown** — expandable step-by-step timing in the export library UI

### Export Library
- **Browse exports** — card-based UI with video preview, metadata chips, and download actions
- **Pipeline timing panel** — collapsible breakdown showing duration of each pipeline step
- **ZIP download** — download project assets as a ZIP bundle

### Music
- **Background music** — attach music tracks with volume, looping, and fade controls
- **Ducking** — auto-lower music volume when narration is active

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
runner.bat
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
dev.bat
```

This starts both the Flask backend (port 5050, minimized) and the Vite dev server (port 5174) with hot reload.

## Project Structure

```
ScriptToScene-Studio/
├── app.py                  # Flask entry point
├── config.py               # Centralized config (dirs, env vars)
├── requirements.txt        # Python dependencies
├── studio/                 # Backend modules
│   ├── tts/                # Text-to-speech (Kokoro)
│   ├── timing/             # Force alignment + segmentation
│   ├── scenes/             # AI scene generation (n8n webhook)
│   ├── assets/             # Asset grabber (Grok, Midjourney, Meta AI)
│   ├── editor/             # Timeline editor API + export
│   ├── pipeline/           # End-to-end pipeline orchestrator
│   ├── captions/           # Caption generation + presets
│   ├── thumbnails/         # Per-project thumbnail generation
│   ├── music/              # Background music management
│   └── segmenter/          # Text segmentation engine
├── frontend/               # Vue 3 + Vite frontend
│   └── src/features/       # Feature-based modules (export library, etc.)
├── static/                 # Main SPA (HTML/JS/CSS)
├── assets/                 # App assets (fonts, sounds)
├── bin/                    # FFmpeg binaries (not in repo)
├── models/                 # TTS model cache (auto-downloaded)
└── output/                 # All generated data (gitignored)
    ├── tts/                # TTS audio + metadata
    ├── alignments/         # Word-level timing data
    ├── segmenters/         # Segmentation output
    ├── scenes/             # Scene definitions (source of truth)
    ├── assets/             # Grabbed media (video/image per scene)
    ├── projects/           # Editor saves (WIP + initial JSON)
    ├── thumbnails/         # Per-project thumbnails by module
    ├── captions/           # Caption data
    ├── exports/            # Final exported videos
    ├── musics/             # Music files
    └── TRASH/              # Soft-deleted files
```

## API Overview

| Module | Endpoint | Description |
|---|---|---|
| Pipeline | `POST /api/pipeline/run` | Start full pipeline |
| Pipeline | `GET /api/pipeline/progress/:id` | SSE progress stream |
| TTS | `POST /api/tts/generate` | Generate TTS audio |
| Scenes | `POST /api/scenes/generate` | Generate scene scripts |
| Assets | `POST /api/assets/grabber/start` | Start asset grabber |
| Editor | `POST /api/projects/:id/assemble` | Assemble project for editor |
| Editor | `POST /api/editor/save` | Save editor state |
| Export | `POST /api/export` | Start video export |
| Export | `GET /api/export/library` | List exported videos |
| Thumbnails | `POST /api/thumbnails/:id/generate` | Generate project thumbnails |
| Thumbnails | `POST /api/thumbnails/generate-all` | Generate all thumbnails |
| Thumbnails | `GET /api/thumbnails/:id` | List project thumbnails |
| Thumbnails | `GET /api/thumbnails/:id/:module/:file` | Serve thumbnail |
| Projects | `GET /api/projects` | List all projects |
| Captions | `POST /api/captions/generate` | Generate captions |
| Music | `GET /api/music/library` | List available music |

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `N8N_WEBHOOK_URL` | `http://localhost:5678/webhook/scene-generator` | n8n scene generation webhook |
| `N8N_ASSET_WEBHOOK_URL` | `http://localhost:5678/webhook/image-generator` | n8n asset generation webhook |
| `KIE_AI_API_KEY` | — | Kie AI image generation API key |
| `STS_BIND_HOST` | `127.0.0.1` | Server bind address |
| `STS_NO_BROWSER` | — | Set to skip auto-opening browser |

## License

MIT
