# Per-Scene SFX System

End-to-end documentation of the vocabulary-driven, LLM-tagged, per-moment SFX placement system.

## What this is

The scene planner LLM now tags individual scenes with optional `sfx_hint` values from a curated vocabulary of 28 abstract sound concepts. The renderer reads those hints during the assemble step, picks real audio files from your library, and places them on the timeline at the right moment with proper volume, ducking, fades, and loop behavior.

This is **on top of** the existing tone-driven SFX bed (which still loops under the entire video as atmosphere). The two layers compose: the bed is *atmosphere*, the per-scene tracks are *punctuation*.

## What problem it solves

The old SFX system put one looped sound file across the entire video timeline based on `story_tone`. There was no way to fire a bass drop at the climax, a riser before a reveal, a heartbeat under a moment of fear, or a typing texture under a research montage. Per-scene placement existed only if you manually dragged tracks in the editor.

Now: the LLM that already knows what each scene is *about* tags it with the kind of sound it needs. The renderer turns those tags into real audio at the right timestamps. Zero manual work for the user; the SFX layer becomes part of the AI-generated content.

## Architecture (the three layers)

```
┌──────────────────────────────────────────────────────────────────┐
│ Layer 1: Vocabulary (the contract)                                │
│ resources/sfx-vocabulary.json — 28 hints, edited by hand          │
│ Each hint has: label, description, folder, filename_match,        │
│                placement, volume, loop, fades, fallback_folder    │
└──────────────────────────────────────────────────────────────────┘
            │                                            │
            ▼                                            ▼
┌─────────────────────────────────┐      ┌──────────────────────────────────┐
│ Layer 2: Planner (LLM-side)     │      │ Layer 3: Renderer (Python-side)  │
│ studio/build_scene_blueprints/  │      │ studio/editor/routes.py          │
│   prompts.py                    │      │   _build_per_scene_sfx_tracks()  │
│ Reads vocab → builds prompt     │      │   _pick_sfx_file_for_hint()      │
│   → LLM emits sfx_hint per scene│      │ Reads vocab → picks file         │
│                                 │      │   → places on timeline           │
│ studio/build_scene_blueprints/  │      │                                  │
│   sfx_validator.py              │      │ Tracks layer onto audio_tracks[] │
│ Validates + enforces budget     │      │ alongside voice/music/SFX bed    │
│ post-LLM (defense in depth)     │      │                                  │
└─────────────────────────────────┘      └──────────────────────────────────┘
```

The vocabulary is the **single source of truth**. Change a hint there and both the LLM prompt and the renderer logic update on the next call — no code changes needed.

## The 28 hints (what's available)

| Hint ID | Label | Purpose | Placement |
|---|---|---|---|
| `tension_riser` | RISER | Long swelling drone before a reveal | lead_in (1.0s) |
| `bass_drop_impact` | BASS DROP | Climax sting — heaviest hit, max ONCE per video | scene_start |
| `cinematic_hit` | HIT | Mid-weight stinger for a major reveal | scene_start |
| `whoosh_transition` | WHOOSH | Hard cut marker between scenes | scene_start |
| `rocket_whoosh` | ROCKET | Heavier whoosh with momentum | lead_in (0.4s) |
| `heartbeat_pulse` | HEARTBEAT | Looping heartbeat under tension scenes | scene_duration |
| `clock_tick` | CLOCK | Looping ticking under time/memory scenes | scene_duration |
| `thinking_pad` | THINK | "Hmm" pad under reflection scenes | scene_duration |
| `magic_shimmer` | SHIMMER | Sparkle on insights / aha moments | scene_start |
| `money_sting` | MONEY | Coin/cash sound — only on literal money scenes | scene_start |
| `glass_shatter` | GLASS | Sharp impact for betrayal / shattering belief | scene_start |
| `gunshot_punctuation` | GUNSHOT | Sharp punctuation — only on literal violence | scene_start |
| `rain_ambience` | RAIN | Looping rainstorm under melancholy scenes | scene_duration |
| `nature_ambience` | NATURE | Birds/footsteps for peaceful scenes | scene_duration |
| `crowd_cheer` | CHEER | Applause for triumph beats | scene_start |
| `crowd_laugh` | LAUGH | Sitcom laughter — comedy ONLY | scene_start |
| `camera_shutter` | SHUTTER | Photo snap for evidence/memory beats | scene_start |
| `keyboard_typing` | TYPING | Looping typing under research scenes | scene_duration |
| `telephone_ring` | PHONE | Phone ring — only on literal phone scenes | scene_start |
| `glitch_distort` | GLITCH | Reality-tear sound for jarring transitions | scene_start |
| `viscous_liquid` | VISCOUS | Slow gloopy texture for body horror / dread | scene_duration |
| `notification_ding` | DING | UI alert for social-media beats | scene_start |
| `click_confirm` | CLICK | Sharp UI click for confirmation beats | scene_start |
| `cartoon_pop` | POP | Light cartoon pop — comedy ONLY | scene_start |
| `text_appear` | TEXT IN | Text overlay appearing — text scenes only | scene_start |
| `text_disappear` | TEXT OUT | Text overlay leaving — text scenes only | scene_start |
| `text_emphasis` | TEXT HIT | Highlight word landing — text scenes only | scene_start |
| `silence` | — SILENCE — | Explicit no-op (intentional absence of sound) | (no track) |

The full vocabulary lives at [resources/sfx-vocabulary.json](../../../resources/sfx-vocabulary.json) with full descriptions, fade values, and file-matching regexes.

## Budget rules (the constraints that prevent clutter)

The system enforces **3-4 hints per video maximum** (2-3 for videos under 30 seconds), via two layers:

1. **The LLM prompt tells it the rules upfront** ([prompts.py](../../../studio/build_scene_blueprints/prompts.py)) — Gemini follows numerical caps reliably when stated as numbers ("at most 4", "exactly once") rather than vibes ("sparingly", "not too many").

2. **The validator enforces it post-LLM** ([sfx_validator.py](../../../studio/build_scene_blueprints/sfx_validator.py)) — if the LLM ignores the cap or hallucinates an invalid hint, the validator drops/normalizes the bad data before it reaches the renderer.

Specific rules enforced:

| Rule | What it prevents |
|---|---|
| Max 4 hints (3 for short videos) | The "TikTok overload" feeling where every scene has SFX |
| `bass_drop_impact` ≤1 per video | Multiple climaxes diluting the actual climax |
| `tension_riser` ≤1 per video | Multiple anticipation builds losing impact |
| Two consecutive scenes can't both have hints UNLESS the pattern is `tension_riser → impact` | Adjacent SFX cluttering the ear |
| `cartoon_pop` / `crowd_laugh` forbidden on non-comedy | Tonal mismatches that feel unhinged |
| `text_*` hints only on text-type scenes | Misapplied text accents on image scenes |
| Unknown hints (LLM hallucinations) | Renderer crashes on bad data |

## The three placement modes

Each hint has a `placement` field that controls *when* on the timeline it fires relative to its scene:

### `scene_start` (most common)
Fires once at the moment the scene begins. Used by all impact hits, transitions, and accents.
- Example: `bass_drop_impact` on scene 7 → fires at scene 7's timeline start
- `loop: false` — one-shot only
- Pairs with hard cuts in the visual

### `scene_duration` (textures)
Fires at scene start, plays for the full duration of the scene, loops if the file is shorter than the scene.
- Example: `heartbeat_pulse` on a 4-second scene → plays from second 0 to second 4 of that scene, looped
- `loop: true`, `trimmedDuration: <scene length>`
- For atmospheric beds that should sustain through one scene only

### `lead_in` (the smart one)
Fires *before* the scene starts, so the sound's peak lands on the cut.
- Example: `tension_riser` on scene 7 with `lead_in_seconds: 1.0` → fires at scene 7 start − 1.0s
- `loop: false`
- This is the difference between a riser that "feels intentional" (peak on cut) vs one that "feels late" (peak after cut)
- Clamped to ≥0 so it never produces a negative offset

## The full pipeline flow

What happens end-to-end when a user generates a video:

```
1. User picks niche preset (e.g. Stickman Glow Philosophy)
   ↓
2. Pipeline → Story step → Gemini writes the script
   ↓
3. Pipeline → Scenes step → Scene planner LLM call:
     - System prompt includes the live SFX HINTS section
       (28 hints + budget rules + placement rules + criteria)
     - LLM produces scenes.json with sfx_hint on 3-4 scenes
   ↓
4. finalize_scene_result() runs sfx_validator.validate_and_enforce_sfx():
     - Pass 1: drop unknown / comedy-on-non-comedy / text-on-non-text
     - Pass 2: enforce "at most one bass_drop / tension_riser"
     - Pass 3: drop illegal consecutive collisions
     - Pass 4: enforce hard cap (≤4) by drop priority
     - Writes sfx_report to result dict for debugging
   ↓
5. scenes.json saved to disk with cleaned sfx_hint values
   ↓
6. Pipeline → Assemble step → editor's assemble endpoint
   ↓
7. assemble_project_for_editor():
     - Builds editor_scenes from raw_scenes (copies sfx_hint into them)
     - Computes cumulative timestamps
     - Builds voice track
     - Auto-selects tone-driven music + SFX bed (existing flow)
     - Calls _build_per_scene_sfx_tracks(editor_scenes, raw_scenes, history)
       - For each scene with sfx_hint:
         - Loads vocabulary entry
         - Picks real file via _pick_sfx_file_for_hint()
           (filename_match regex + history dedup + fallback folder)
         - Computes timelineOffset based on placement mode
         - Builds track dict with label/volume/loop/fades from vocab entry
       - Returns (tracks, updated_history)
     - Appends per-scene tracks to audio_tracks[]
   ↓
8. initial.json saved with the full audio_tracks layout
   ↓
9. Pipeline → Export step → renderer reads audio_tracks
   ↓
10. ffmpeg mixes voice + music + sfx_bed + per_scene_sfx_tracks
    Each track is positioned at its timelineOffset
    Voice ducking applies to all non-voice tracks
   ↓
11. Final MP4 has SFX placed at the right narrative moments
```

Every step is implemented. There is **no missing link** between "scene planner LLM" and "final MP4 has SFX at the right places."

## Files involved

### New files (created during this feature)

| File | Purpose |
|---|---|
| [resources/sfx-vocabulary.json](../../../resources/sfx-vocabulary.json) | The 28-hint controlled vocabulary — the contract |
| [resources/sounds/sfx/text_scene/](../../../resources/sounds/sfx/text_scene/) | Empty folder for user-supplied text-scene sounds |
| [studio/build_scene_blueprints/sfx_validator.py](../../../studio/build_scene_blueprints/sfx_validator.py) | Validation + budget enforcement + drop priority |
| [_dev/test_sfx_validator.py](../test_sfx_validator.py) | 10 synthetic regression tests for the validator |
| [_dev/test_per_scene_sfx.py](../test_per_scene_sfx.py) | 7 synthetic regression tests for the placer |
| [_dev/sfx-prompt-preview.md](../sfx-prompt-preview.md) | Auto-generated dump of the SFX section as the LLM sees it |

### Edited files

| File | Change |
|---|---|
| [studio/build_scene_blueprints/prompts.py](../../../studio/build_scene_blueprints/prompts.py) | Added `_build_sfx_section()` helper, wired into `_build_scene_contract()`, added `sfx_hint` to scene object key list and JSON example |
| [studio/build_scene_blueprints/validators.py](../../../studio/build_scene_blueprints/validators.py) | `finalize_scene_result()` now calls `validate_and_enforce_sfx()` and folds its warnings into `coherence_warnings` with `[sfx]` prefix |
| [studio/editor/routes.py](../../../studio/editor/routes.py) | Added `_list_sfx_files_in_folder()`, `_pick_sfx_file_for_hint()`, `_build_per_scene_sfx_tracks()`. Wired into the assemble flow after the existing music/SFX-bed block. Editor scenes now copy `sfx_hint` from raw scenes. |

## How to add a new hint

The vocabulary is the contract. To add a new hint:

1. Open [resources/sfx-vocabulary.json](../../../resources/sfx-vocabulary.json)
2. Add a new entry to the `hints` object with:
   - `label` — short timeline marker (e.g. "ECHO")
   - `description` — written for the LLM, explains when to use the hint
   - `folder` — which `resources/sounds/sfx/<folder>/` to draw from
   - `filename_match` — optional regex to narrow which files in that folder fit
   - `placement` — `scene_start`, `scene_duration`, or `lead_in`
   - `volume` — target volume (0.0-1.0, typically 0.10-0.22)
   - `loop` — true for textures, false for one-shots
   - `fade_in` / `fade_out` — envelope shaping in seconds
   - `fallback_folder` — optional second folder if the primary has no matches
3. Save the file. Done.

Both the LLM prompt and the renderer pick up the new hint on the **next call** with no restart needed (the vocabulary is loaded fresh on each call, with a thread-local cache that you can reset via `reload_sfx_vocabulary()`).

If you want the hint to count differently in the budget rules (e.g. "this is a high-priority climax hit, never drop it"), also add it to the `_DROP_PRIORITY` table in [sfx_validator.py](../../../studio/build_scene_blueprints/sfx_validator.py). Higher numbers = harder to drop. The structural hits like `bass_drop_impact` (50) and `tension_riser` (40) sit at the top; decorative accents like `cartoon_pop` (1) sit at the bottom.

## How to add new sound files to an existing hint

Drop new audio files (mp3 / wav / ogg / m4a / flac) into the `resources/sounds/sfx/<folder>/` directory referenced by the hint. They become available **immediately** on the next project generation:

- The file will only be picked if its name matches the hint's `filename_match` regex (if defined)
- The file will go into the history-dedup pool, so it won't get picked twice in a row
- If the folder has multiple files matching the regex, the picker rotates through them with random selection biased toward unused ones

Example: to add a new heartbeat sound, drop `heart-pounding.mp3` into `resources/sounds/sfx/heartbeat/`. The `heartbeat_pulse` hint has no `filename_match` (so it picks any file in the folder) and the new file becomes part of the rotation immediately.

## How to populate the text_scene folder

The `text_appear`, `text_disappear`, and `text_emphasis` hints all point at `resources/sounds/sfx/text_scene/`, which is **empty** by default. Until you populate it, those three hints will silently skip when the LLM tries to use them (the system gracefully degrades — no crash, no missing audio in the rest of the video).

To populate:

1. Find or create short sound effects (typically <0.5 seconds):
   - For `text_appear`: a soft pop, a shimmer, a click — anything that says "something just appeared"
   - For `text_disappear`: a soft sweep, an airy whoosh, a fade — anything that says "something just left"
   - For `text_emphasis`: a subtle ding, a chime, an accent — anything that says "this word matters"

2. Name the files with hint-matching keywords:
   - `text_appear` regex: `in|appear|enter|on|pop` → name files like `text-pop-in.mp3`, `soft-appear.wav`
   - `text_disappear` regex: `out|disappear|exit|off|sweep` → name files like `text-out-sweep.mp3`, `airy-exit.wav`
   - `text_emphasis` regex: `hit|emphasis|accent|highlight|ding` → name files like `accent-ding.mp3`, `text-hit.wav`

3. Drop them into `resources/sounds/sfx/text_scene/`. They become available immediately.

The naming convention is forgiving — the regexes match anywhere in the filename, case-insensitive — so most natural file names will route correctly.

## How to test the system

### Unit tests (no real generation needed)

```bash
PYTHONPATH=. python _dev/test_sfx_validator.py
PYTHONPATH=. python _dev/test_per_scene_sfx.py
```

10 + 7 synthetic tests covering all rule edge cases. Run after any change to the validator or placer logic. Both test files are designed to be runnable without a Flask server, without an LLM call, and without any real project data — they use hand-built scene dicts and exercise the logic directly.

### Live preview of the LLM prompt

```bash
PYTHONPATH=. python -c "
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from studio.build_scene_blueprints.prompts import _build_sfx_section
print(_build_sfx_section())
" > _dev/sfx-prompt-preview.md
```

Writes the rendered SFX section to a file so you can read exactly what the LLM sees on every scene generation. Useful for prompt iteration without running real videos.

### End-to-end test (real generation)

The only meaningful final test is generating a real video and listening:

1. Pick any niche preset
2. Run the pipeline end-to-end
3. Check the logs for `Per-scene SFX: scene N -> hint_id (file.mp3) @ X.XXs [placement_mode]` lines
4. Open the project in the editor — the new SFX tracks should appear in the audio track stack with their labels visible
5. Export and listen to the MP4

Things to listen for:
- Does the SFX hit the right *moments*?
- Does the riser land its peak on the cut into the climax?
- Are the volumes balanced relative to the voice and music bed?
- Is the bed audible underneath the per-scene accents?
- Are 3-4 hits the right number, or does it feel sparse / cluttered?

### Inspecting what the LLM picked

Open `output/scenes/<project_id>/scenes.json` and look at the `sfx_hint` field on each scene. If the LLM is picking sensible hints, the system is working as designed. If it's picking weird hints (or none at all), the prompt may need tuning.

The validator's report is also persisted on the result dict as `sfx_report`:

```json
{
  "sfx_report": {
    "hint_count": 4,
    "hint_max": 4,
    "hint_min": 3,
    "dropped": [
      {"scene_index": 2, "hint": "cartoon_pop", "reason": "comedy_only_on_non_comedy"}
    ]
  }
}
```

If `dropped` is non-empty, the LLM produced bad hints that the validator cleaned up. If it's persistently dropping the same kind of hint, the prompt instructions for that hint may need tightening.

## Interaction with the existing audio system

The new system **does not replace** any existing audio behavior. It adds a fourth layer on top of three existing layers:

| Layer | What it is | How it's added |
|---|---|---|
| **Voice** | The TTS narration track | From `voice.wav`, always present |
| **Music** | Tone-driven background music | Auto-picked by `select_music(story_tone)`, looped |
| **SFX bed** | Tone-driven ambient SFX | Auto-picked by `select_sfx(story_tone)`, looped |
| **Per-scene SFX** *(new)* | LLM-tagged accents at specific timestamps | Built by `_build_per_scene_sfx_tracks()` from `sfx_hint` fields |

All four coexist via the existing voice-ducking pipeline. When voice is talking, all non-voice tracks duck to 20% volume. When voice is silent, all non-voice tracks return to their full volumes (which differ per layer — music at 0.15, SFX bed at 0.10, per-scene tracks at 0.10-0.22 depending on the hint).

The user can manually edit any of these tracks in the editor like any other audio track. Drag, mute, delete, change volume — the per-scene tracks behave identically to manually-added tracks because they share the same data shape.

## Defense in depth — what protects against failures

The system has multiple layers of protection against malformed data, missing files, and LLM regressions:

| Failure mode | Where it's caught | What happens |
|---|---|---|
| LLM hallucinates an unknown hint | Validator pass 1 | Hint silently dropped, scene's `sfx_hint` set to null |
| LLM emits comedy hint on dramatic content | Validator pass 1 | Hint silently dropped |
| LLM emits text hint on non-text scene | Validator pass 1 | Hint silently dropped |
| LLM emits 7 hints when budget is 4 | Validator pass 4 | Lowest-priority 3 dropped |
| LLM puts adjacent hints (illegal) | Validator pass 3 | Second hint dropped |
| LLM duplicates `bass_drop_impact` | Validator pass 2 | Earlier occurrences dropped, last kept |
| Vocabulary file is missing or corrupt | `load_sfx_vocabulary()` | Returns empty dict, all hints get cleared, system gracefully degrades |
| Hint's primary folder is empty | `_pick_sfx_file_for_hint()` | Falls back to `fallback_folder` |
| Both folders empty | `_pick_sfx_file_for_hint()` | Returns None, scene gets no track, debug log emitted |
| Same file picked twice in a row | History dedup in `_pick_sfx_file_for_hint()` | Picks from `fresh = candidates - history` first |
| Renderer placer crashes mid-build | `try/except` in assemble flow | Logs at WARNING, no per-scene tracks added, rest of project unaffected |
| Regex `filename_match` doesn't match anything | `_pick_sfx_file_for_hint()` | Falls through to fallback folder or returns None |

The design philosophy is **fail silently for individual hints, fail loudly for the system as a whole**. A bad hint should never crash a video generation; the system should produce a working video with one fewer SFX track. A bug in the renderer logic, however, should produce a WARNING log so the developer notices.

Note: the "fail silently for individual hints" rule was a deliberate choice based on the captions debacle earlier this session — when an entire feature was silently broken at debug level for 11+ days because the swallowed exception was logged at `debug` instead of `warning`. The new SFX renderer logs its top-level failures at **warning** level so a regression of that kind cannot happen again.

## Cost analysis

| Cost | Amount |
|---|---|
| Extra LLM tokens per scene generation (the SFX section in the prompt) | ~2200 tokens |
| Extra LLM cost per generation (Gemini Flash @ ~$0.075 / 1M input tokens) | ~$0.0002 |
| Extra disk space for vocabulary | ~10 KB |
| Extra disk space per saved project (sfx_hint fields + per-scene tracks) | ~500 bytes |
| Extra render time per video | ~0 (renderer already handles N audio tracks) |
| Extra memory at runtime | Vocabulary cached once, ~5 KB |

**The total ongoing cost is dominated by the ~2200 extra prompt tokens per generation, which costs roughly $0.0002 per video.** Generating 1000 videos costs about 20 cents in extra LLM input tokens. Effectively free.

## Known limitations

### What v1 does NOT do

1. **No word-anchored placement.** The system places SFX at scene boundaries, not at specific words within a scene. If you want a bass drop on the word "betrayed" specifically, you can't get it from the LLM — only from manual editing.

2. **No history persistence to `initial.json`.** Within a single assemble call, the picker dedups against itself. Across projects, the dedup history starts fresh each time. If you generate 5 videos in a row, the same `magic_shimmer` file might get picked multiple times.

3. **No editor-side hint editing.** Currently the LLM picks the hint and the user can adjust the resulting audio track (move it, mute it, change volume) but cannot *change which hint* a scene uses from the editor UI.

4. **No SFX preview in the planner UI.** When viewing a scene in the editor, you can see the resulting audio track with its label — but there's no way to audition different hint choices for that scene without manually editing the scene data.

5. **No content-aware sound selection within a folder.** If `cinematic/` contains 14 files and the regex matches 4 of them, the picker chooses uniformly at random among the 4 (with history dedup). It doesn't pick the "best" file based on scene content.

6. **`text_scene/` folder is empty.** The three text_* hints will silently skip until the user populates the folder with their own files.

### What COULD be added later

- **Scene-level hint override in the editor** — a dropdown next to each scene that lets the user manually change `sfx_hint` and re-run just the placer for that scene
- **Cross-project history dedup** — persist `sfx_history` to `initial.json` and reload it in subsequent assemble calls
- **Audition preview** — when the user hovers over a hint in the editor, play the file the renderer would pick
- **Per-scene volume override** — let the editor remember a per-scene volume override that's applied on top of the vocabulary entry's default
- **Word-level placement** — a second pass that scans the alignment data and places hints at specific word timestamps within a scene (would require new placement modes and new validator rules)
- **Audio embedding search** — replace the regex `filename_match` with CLAP embeddings for content-aware file selection within a folder (overkill for current library size, would matter at 500+ files per folder)

None of these are needed for the system to be useful. They are future enhancements only if real usage reveals a missing capability.

## How this connects to the rest of the codebase

The SFX system is **almost entirely additive**. It touches:

- **Scene blueprint generation** — adds one optional field to scenes.json
- **Validators** — adds one extra validation pass after the existing coherence scoring
- **Assemble step** — adds one extra audio-track-building loop after the existing music/SFX bed loop
- **Editor data** — copies one extra field from raw scenes into editor scenes

It does **not touch**:

- The scene planner LLM call itself (just the prompt content it receives)
- The pipeline orchestrator
- The TTS step
- The alignment step
- The storyboard image generation
- The animator/grabber
- The export renderer (which already handles arbitrary numbers of audio tracks)
- Any frontend code (the new tracks render via existing audio track UI components)
- The editor's edit history
- The thumbnails / captions / music modules
- Any database (there is no database)

This was a deliberate design constraint. By keeping the integration surface tiny, the chance of regressions in unrelated features is minimized. The only way the new code can break an existing feature is if the assemble step's `try/except` somehow propagates an exception — and that block is already wrapped in defensive error handling.

## TL;DR for someone who skipped the doc

- Scene planner LLM tags scenes with `sfx_hint` from a 28-entry vocabulary
- Validator drops bad hints and enforces a 3-4 hint budget per video
- Renderer picks a real file from the matching folder, places it on the timeline at the right moment with the right loop/volume/fade settings
- Three placement modes: `scene_start` (one-shot at cut), `scene_duration` (looped texture), `lead_in` (one-shot before cut for risers)
- Layered on top of the existing tone-driven SFX bed — both coexist
- Defense in depth: rules in the prompt + rules in the validator + graceful degradation in the picker
- Vocabulary file is the single source of truth — change it and both LLM + renderer update on next call
- 17 synthetic tests cover the rule surface, all passing
- ~$0.0002 extra cost per video, effectively free
- Gracefully no-ops when files are missing (so the empty `text_scene/` folder is fine)
