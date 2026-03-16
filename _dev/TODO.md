# TODO

## Deferred Review Items

### Asset History Thumbnail Work
- Move video thumbnail generation out of `GET /api/assets/history`.
- Precompute thumbnails when assets are written, or enqueue background thumbnail jobs with caching.
- Revisit the preview contract in `studio/assets/routes.py` after that refactor so the history endpoint stays fast under larger libraries.

### Automated Regression Coverage
- Add backend API tests for each Flask blueprint, especially import/export, TTS, timing, captions, scenes, and pipeline.
- Add contract tests for frontend payloads versus backend schema expectations.
- Add end-to-end smoke tests for the main pipeline, ZIP import/export, and export-library flows.
- Replace the current ad hoc `_dev/tools/test_*.py` scripts with repeatable automated checks where possible.


FIX SPECIAL CHARACTER AND FOREIGN THE NAME PRONUNCIACION IN THE TTS

 Thewisestickman - Channel Tiktok Youtube Instagram  Facebook

 Fix cut initial audop voice.

 how to add a little reverb in the tts voice


 explain each part of the video of the sequecial part of the vide and then generate a prompt that can show  the action 

 multiple prompts for taste 

 define editing presets

 batch export multiple projects at once

 auto-detect scene transitions from audio energy peaks

 drag and drop reorder scenes in the timeline

 background music volume ducking during speech

 watermark overlay option for exports

 undo/redo history panel with visual diff

 auto-save editor state every 30s

 keyboard shortcuts cheat sheet overlay (? key)

 split scene at playhead position

 duplicate scene with one click

 theme/color grading presets per project style

 waveform visualization on audio track

 export progress notification via webhook (Discord, Slack)

 caption style templates (subtitle, karaoke, word-by-word)

 multi-language TTS support with voice preview

 project templates (short-form, long-form, ad, tutorial)

 asset library search and filter by tags

 collaborative editing session via shared link

 AI-powered script rewrite suggestions