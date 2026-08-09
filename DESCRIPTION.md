Below is a paste-ready project description you can give ChatGPT or another coding agent.

---

# ScriptToScene Studio V2 — Project Context

## Project goal

ScriptToScene Studio V2 is a local-first AI video production application that turns a written script or story idea into a finished short-form video.

Its main goal is to automate the complete production process:

1. Generate or accept a script.
2. Convert the script into narration.
3. Align every spoken word with timestamps.
4. Divide the narration into visual scenes.
5. Generate scene descriptions and image prompts.
6. Create storyboard images and animated assets.
7. Assemble everything into an editable timeline.
8. Add captions, music, branding, and effects.
9. Export a finished video using FFmpeg.

The application targets content such as YouTube Shorts, TikTok videos, Instagram Reels, narrated stories, educational clips, motivational content, and cinematic short-form videos.

## Technology stack

### Backend

- Python
- Flask
- Flask-CORS
- Flask-Sock for WebSocket support
- Pydantic for schemas and validation
- Loguru for logging
- FFmpeg and FFprobe for media processing
- Kokoro ONNX and Inworld for text-to-speech
- Whisper/stable-ts for word-level alignment
- Pillow for image processing
- External AI providers and n8n webhooks

The Flask development server normally runs on port `5050`.

### Frontend

- Vue 3
- Vite
- Pinia
- Vue Router
- Vue Flow
- Dagre graph layout
- Vitest
- Vue Test Utils
- jsdom

The Vite development server normally runs on port `5174`.

## Main user interfaces

The application has two complementary interfaces.

### Workflow Builder

The Workflow Builder is the primary modern interface. It allows users to visually construct video-production pipelines by connecting typed nodes on a canvas.

It includes:

- Drag-and-drop node creation
- Typed input and output ports
- Schema-driven node configuration
- Workflow validation
- Undo and redo
- Copy, paste, duplicate, and multi-selection
- Sticky notes
- Automatic graph arrangement
- Minimap and zoom controls
- Automatic sample-data stubs
- Workflow templates
- Draft autosave and recovery
- Import and export as JSON
- Execution history and diagnostics
- Live node status updates
- Selective and partial execution
- Result caching and stale-node detection
- Scheduled, folder, and webhook triggers

### Legacy production pages

The original step-by-step pages remain available for direct control of:

- Pipeline execution
- TTS
- Timing and alignment
- Segmentation
- Scene generation
- Storyboards
- Asset generation
- Timeline editing
- Export library
- Settings

Both interfaces operate on the same projects and generated artifacts.

## Backend modules

### `app.py`

The main Flask entry point.

Responsibilities:

- Creates the Flask application
- Configures CORS and request-size limits
- Registers all backend blueprints
- Initializes provider registries
- Configures WebSockets
- Serves the built Vue application
- Exposes health, configuration, output, and project-management routes
- Configures application logging

### `config.py`

Central configuration module.

It defines:

- Output directories
- Temporary directories
- Model locations
- Static frontend paths
- API and webhook configuration
- Environment-variable settings
- FFmpeg-related paths
- Project storage locations

### `studio/pipeline`

The legacy end-to-end pipeline orchestrator.

It coordinates the traditional production sequence:

```text
TTS
→ alignment
→ segmentation
→ scene blueprints
→ asset generation
→ project assembly
→ export
```

It also handles:

- Background jobs
- Step progress
- Per-step timing
- Stop-after controls
- Pipeline history
- Server-Sent Events for live progress

### `studio/story`

Generates narration scripts from ideas, niches, tones, languages, and duration targets.

It contains:

- Prompt construction
- Story-generation services
- Story history
- Schemas
- API routes
- Anti-repetition behavior

### `studio/niches`

Contains predefined content niches and story-generation presets.

Examples may include motivational, psychological, horror, educational, or story-driven content categories.

### `studio/tts`

Text-to-speech subsystem.

Features:

- Kokoro local neural TTS
- Inworld TTS integration
- Multiple voices and languages
- Voice blending
- Text normalization
- Pronunciation handling
- Breathing and pause processing
- Audio concatenation
- Loudness normalization
- Provider-specific settings and validation

Providers currently include:

- Kokoro
- Inworld

### `studio/timing`

Creates word-level timestamps for narration using Whisper/stable-ts.

It takes narration audio and the original script and produces an alignment document containing each word’s beginning and ending time.

### `studio/segmenter`

Divides aligned narration into scene-sized segments.

Segmentation considers:

- Punctuation
- Silence gaps
- Target duration
- Word count
- Mood changes
- Transition keywords
- Visual nouns
- Action verbs

### `studio/build_scene_blueprints`

Transforms script segments into structured scene plans.

It contains:

- AI prompt construction
- Chapter processing for long scripts
- Scene planning
- Style compilation
- Visual continuity rules
- Sound-effect validation
- Output validation
- Style templates
- Scene schemas

Generated scene information can include:

- Narrative role
- Scene type
- Visual description
- Image prompt
- Overlay text
- Camera direction
- Mood and continuity information

### `studio/storyboard`

Generates or processes storyboard images.

Providers include:

- Gemini WebSocket
- WaveSpeed direct API
- WaveSpeed webhook

It also contains:

- Watermark removal
- Image processing
- LaMa-based inpainting through an isolated Python environment
- Provider schemas and health checks

### `studio/animator`

Turns scene prompts or storyboard images into final scene assets.

Providers include:

- Grok through Automa browser automation
- Kie AI

Responsibilities include:

- Starting media-generation jobs
- Tracking provider progress
- Organizing generated images and videos
- Associating assets with scene indexes
- Provider-specific settings
- Asset download and validation

### `studio/captions`

Creates caption data and exposes caption-related APIs.

Caption features include:

- Word-level timing
- Multiple presets
- Font and color customization
- Stroke, shadow, and background styling
- Position controls
- Pop, fade, highlight, and hard-cut animations
- Karaoke-style highlighting
- Single-line short-form captions

### `studio/music`

Manages background music.

Features:

- Music library
- Track selection
- Volume controls
- Narration ducking
- Looping
- Fade-in and fade-out
- Support for MP3, WAV, OGG, M4A, and FLAC

### `studio/editor`

Timeline-project and video-export backend.

Responsibilities:

- Assemble generated artifacts into an editor project
- Save work-in-progress timeline state
- Process scene media
- Manage narration, music, and sound-effect tracks
- Apply captions and branding
- Render final video through FFmpeg

### `studio/thumbnails`

Generates thumbnails for:

- Scene assets
- Timeline projects
- Exported videos

It supports both individual-project and batch thumbnail generation.

### `studio/shared/providers_common`

Shared provider infrastructure used by TTS, storyboard, and animator providers.

It includes:

- Dynamic provider discovery
- Provider manifests
- Settings schemas
- Settings migration
- Health checks
- Provider validation
- HTTP helpers
- File downloading
- Progress reporting
- Runtime management
- Broken-provider isolation

Each provider is intended to be modular and independently configurable.

### `studio/workflows`

The backend for the visual Workflow Builder.

Important parts include:

- `registry.py` — authoritative node catalog and port definitions
- `models.py` — workflow and execution models
- `validation.py` — graph, schema, connection, and configuration validation
- `execution.py` — workflow execution engine
- `scheduler.py` — run queue and dependency scheduling
- `cache.py` — node-result caching and fingerprinting
- `events.py` — execution event streaming and replay
- `persistence.py` — workflow storage
- `migrations.py` — workflow-version migration
- `expressions.py` — safe upstream-output and variable expressions
- `templates.py` — built-in workflow templates
- `options.py` — server-controlled option lists
- `notifications.py` — completed and failed run notifications
- `scheduled_runs.py` — cron-based triggers
- `watch_folders.py` — folder-based workflow triggers
- `webhook_triggers.py` — private loopback webhook triggers
- `project_archive.py` — portable project archives and restoration
- `asset_gc.py` — orphaned-asset detection and cleanup
- `redaction.py` — secret and sensitive-value redaction
- `scaffold.py` — creation of new workflow nodes
- `docs.py` — generated node documentation
- `adapters/` — connects workflow nodes to the existing application modules

## Workflow node catalog

The Workflow Builder currently includes these major nodes:

### Input nodes

- Manual Trigger
- Project Setup
- Script Input
- Existing Project

### Audio nodes

- Text to Speech
- Background Music

### Timing nodes

- Force Alignment
- Segmenter

### AI nodes

- Story Generator
- Scene Blueprint

### Asset nodes

- Storyboard
- Animator

### Video nodes

- Caption Generator
- Assemble Project

### Output nodes

- Timeline Project
- Video Export

### Utility nodes

- Set Value
- Condition
- Merge
- Wait
- Workflow Output

### Testing nodes

- Sample Input
- Result Viewer
- Scaffold Check Echo

Connections are strongly typed. Port types include scripts, project settings, audio files, TTS metadata, alignments, segments, scenes, storyboard images, animation assets, captions, music tracks, editor projects, export profiles, video files, control signals, and generic JSON.

## Built-in workflow templates

The application provides several starting templates:

- Full Video — complete script-to-video production
- Narration Only — script to TTS audio
- Storyboard Only — script to storyboard images
- Re-export Existing Project — create a new export from an existing timeline project

## Workflow execution features

A workflow can be run in several modes:

- Full workflow
- Selected node with dependencies
- Selected nodes with dependencies
- Node in isolation
- From a selected node downstream
- Retry one failed node
- Retry a failed node and its descendants

The execution engine supports:

- Dependency-aware scheduling
- Parallel execution where safe
- Per-project queue serialization
- Cooperative cancellation
- Retry policies and backoff
- Continue, skip, or error-output policies
- Persisted execution records
- Live SSE progress
- Event replay after reconnecting
- Structured node errors
- Resolved input and output inspection
- Cache hit and miss explanations

Successful results are cached using the node type, configuration, and upstream artifacts. When a node changes, only that node and its descendants become stale.

## Frontend modules

### `frontend/src/app`

Application shell containing:

- Vue Router
- Main layout
- Sidebar navigation
- Root application component

### `features/workflow`

The Workflow Builder interface.

Contains:

- Vue Flow canvas
- Node library
- Node cards and icons
- Schema-driven inspector
- Media-asset picker
- Execution and diagnostics panel
- Notification center
- Workflow store
- Graph validation
- Expressions
- Draft autosave
- Command stack for undo and redo
- Scheduling settings
- Watch-folder settings
- Webhook settings
- Project archive manager
- Asset garbage collection

### `features/pipeline`

Legacy pipeline dashboard.

Contains:

- Pipeline form
- Progress stepper
- Live logs
- Job history
- Story controls
- Voice and niche selection
- Provider tabs
- Scene notifications

### `features/tts`

Dedicated narration interface with:

- Voice selection
- Playback
- TTS generation history
- Provider selection
- Voice configuration

### `features/timing`

Word-alignment viewer with:

- Alignment timeline
- Word chips
- Karaoke preview

### `features/segmenter`

Scene-segmentation editor with:

- Alignment selection
- Segment cards
- Segment timeline

### `features/scenes`

Scene review and editing interface with:

- Scene cards
- Scene timeline
- Style selection
- Scene prompt editing

### `features/storyboard`

Storyboard-generation and review interface.

### `features/assets`

Generated-asset management with:

- Asset cards
- Lightbox preview
- Grabber controls
- Asset status tracking

### `features/editor`

Timeline video editor with:

- Scene arrangement
- Asset picker
- TTS picker
- Music picker
- Export controls
- Export progress
- Project sharing
- Timeline state management

### `features/export-library`

Export management interface with:

- Video cards
- Search
- Analytics
- Deletion
- Download access

### `features/providers`

Shared provider UI for:

- Selecting providers
- Editing provider settings
- Displaying provider-specific schemas
- Health and configuration feedback

### `features/settings`

Application configuration and project-cleanup interface.

### `frontend/src/shared`

Shared frontend infrastructure:

- API client
- Pinia application stores
- Audio playback and registry
- Project synchronization
- Toast notifications
- Activity feed
- Startup behavior
- Welcome overlay
- Formatting utilities
- Shared story and style data

## Project storage

Generated data is stored under `output/`.

Important locations include:

- `output/tts/` — narration audio and metadata
- `output/alignments/` — word-level alignment data
- `output/segmenters/` — segmented narration
- `output/scenes/` — scene-blueprint data
- `output/storyboard/` — storyboard images
- `output/animator/` — generated scene images and videos
- `output/projects/` — initial and work-in-progress timeline projects
- `output/captions/` — caption data
- `output/musics/` — music files
- `output/thumbnails/` — generated thumbnails
- `output/exports/` — final videos
- `output/workflows/` — saved workflows and execution records
- `output/branding/` — managed logos and branding media
- `output/TRASH/` — soft-deleted content

Pipeline projects use IDs beginning with `pp_`. Manually created projects use IDs beginning with `pm_`.

## Reliability and security

The application includes:

- Strict project and workflow ID validation
- Path-traversal prevention
- Safe path joining
- Atomic JSON writes
- Backup recovery
- Soft deletion
- Request-body size limits
- File-extension and MIME validation
- Managed branding uploads
- Secret redaction
- Loopback restrictions for sensitive endpoints
- Webhook URL validation
- Private webhook tokens
- CORS configuration
- Workflow import limits
- Graph-size limits
- Provider failure isolation
- Persisted execution history

## Testing

The backend uses Pytest and includes tests for:

- Workflow validation
- Execution scheduling
- Persistence
- Caching
- Expressions
- Webhooks
- Scheduled runs
- Watch folders
- Project archives
- Asset cleanup
- Request hardening
- Provider adapters
- Scene generation
- TTS and media behavior
- Reliability regressions

The frontend uses Vitest and Vue Test Utils. It tests:

- Workflow store behavior
- Validation
- Inspector forms
- Execution events
- Diagnostics
- Autosave
- Undo and redo
- Expressions
- Notifications
- Large-canvas performance
- Trigger settings
- Legacy-page integration
- Power-user canvas interactions

## Development automation

The `_dev/loop-engineering` directory contains an automated engineering loop that reads the implementation plan and processes work phase by phase.

Its default agent arrangement is:

- Claude for coding and repairs
- AGY as the coding fallback when Claude reaches a credit or usage limit
- Codex as the default adversarial reviewer

The loop independently runs:

- Backend tests
- Frontend tests
- Production frontend builds
- Review and repair passes
- Git progress tracking

## Important development principles

When modifying this project:

- Preserve compatibility between the Workflow Builder and legacy pages.
- Treat backend node definitions as the source of truth.
- Keep workflow ports and artifact types strongly typed.
- Reuse existing services through workflow adapters instead of duplicating business logic.
- Never trust browser-supplied filesystem paths.
- Keep provider-specific behavior inside provider modules.
- Preserve generated artifacts and existing user projects.
- Validate both backend and frontend changes.
- Do not claim a feature works without running the relevant tests.
- Keep the application usable as a local Windows-first desktop production tool.