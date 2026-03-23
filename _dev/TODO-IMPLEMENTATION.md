# _dev/ Directory Map & Improvements

```
_dev/
├── automation/
│   ├── automa/
│   │   ├── grok/                # Grok Assets Synchronizer — browser automation for AI asset generation
│   │   └── midjourney/          # Midjourney Assets Synchronizer — browser automation workflow
│   └── n8n/                     # n8n workflow exports (scene-generator, story-generator, classify-style)
├── docs/                        # Internal documentation
│   ├── plans/                   # Architecture plans and roadmaps
│   ├── tts-pronunciation-guide.md
│   ├── prompt-rules.md
│   └── security-audit.md
├── fixtures/                    # Sample data for testing (alignments, scene outputs)
├── http/                        # HTTP request files for local API testing
├── prompts/                     # LLM prompt iterations and templates
├── tools/                       # Dev scripts (FFmpeg tests, overlay gen, n8n validators)
└── TODO-IMPLEMENTATION.md       # This file
```

---

## automation/automa/grok/

Grok Assets Synchronizer — injects JS into Grok to auto-type prompts, bypass CSP, and sync generated assets back to the studio pipeline.

**Improvements:**

- FIX SPECIAL CHARACTER AND FOREIGN THE NAME PRONUNCIACION IN THE TTS
-
-

---

## automation/automa/midjourney/

Midjourney Assets Synchronizer — browser automation workflow for Midjourney image generation and download.

**Improvements:**

-
-
-

---

## automation/n8n/

n8n workflow exports: scene-generator, story-generator, classify-style.

**Improvements:**

-
-
-

---

## docs/

Internal documentation — architecture plans, roadmaps, TTS pronunciation guide, prompt rules, security audit.

**Improvements:**

-
-
-

---

## fixtures/

Sample data for testing — alignment JSON, scene output snapshots, request samples.

**Improvements:**

- Replace ad hoc `_dev/tools/test_*.py` scripts with repeatable automated checks
- Add contract tests for frontend payloads vs backend schema expectations
-

---

## http/

HTTP request files (`.http`) for local API testing against Flask endpoints.

**Improvements:**

-
-
-

---

## prompts/

LLM prompt iterations and templates — scene planner, scene writer, cheat-code prompts.

**Improvements:**

- multiple prompts for taste
- explain each part of the video sequentially then generate a prompt that shows the action
-

---

## tools/

Dev scripts — FFmpeg tests, overlay generation, n8n validators, sync tools.

**Improvements:**

-
-
-

---

## Studio Pipeline

**Improvements:**

- Thewisestickman — Channel TikTok YouTube Instagram Facebook
- Fix cut initial audio voice
- How to add a little reverb in the TTS voice
- Define editing presets
- Batch export multiple projects at once
- Auto-detect scene transitions from audio energy peaks
- Drag and drop reorder scenes in the timeline
- Background music volume ducking during speech
- Watermark overlay option for exports
- Undo/redo history panel with visual diff
- Auto-save editor state every 30s
- Keyboard shortcuts cheat sheet overlay (? key)
- Split scene at playhead position
- Duplicate scene with one click
- Theme/color grading presets per project style
- Waveform visualization on audio track
- Export progress notification via webhook (Discord, Slack)
- Caption style templates (subtitle, karaoke, word-by-word)
- Multi-language TTS support with voice preview
- Project templates (short-form, long-form, ad, tutorial)
- Asset library search and filter by tags
- Collaborative editing session via shared link
- AI-powered script rewrite suggestions

---

## Deferred Review Items

### Asset History Thumbnail Work
- Move video thumbnail generation out of `GET /api/assets/history`.
- Precompute thumbnails when assets are written, or enqueue background thumbnail jobs with caching.
- Revisit the preview contract in `studio/assets/routes.py` after that refactor so the history endpoint stays fast under larger libraries.

### Automated Regression Coverage
- Add backend API tests for each Flask blueprint, especially import/export, TTS, timing, captions, scenes, and pipeline.
- Add contract tests for frontend payloads versus backend schema expectations.
- Add end-to-end smoke tests for the main pipeline, ZIP import/export, and export-library flows.
