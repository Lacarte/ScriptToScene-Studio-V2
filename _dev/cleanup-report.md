# ScriptToScene Studio — Code Cleanup & Efficiency Report

**Generated:** 2026-03-13
**Scope:** Dead code, broken references, inefficient logic, stale comments — post legacy-removal audit

---

## Table of Contents

1. [Backend Python Issues](#1-backend-python-issues)
2. [Frontend JavaScript Issues](#2-frontend-javascript-issues)
3. [Recommended Fix Priority](#3-recommended-fix-priority)

---

## 1. Backend Python Issues

### Duplicate / Redundant Imports

| ID | File | Line(s) | Issue | Fix |
|----|------|---------|-------|-----|
| P1 | `studio/editor/routes.py` | 5, 137, 197 | `shutil` imported 3 times (top-level, aliased as `_shutil`, inside function) | Keep only line 5 top-level import |
| P2 | `studio/tts/audio.py` | 66 | `import json as _json` inside function body | Use module-level `json` import |
| P3 | `studio/tts/routes.py` | 37 | Imports `_find_ffmpeg` from `.audio` but never uses it | Remove from import |
| P4 | `studio/music/routes.py` | 17 | `import shutil` inside `_get_duration()` but shutil never used there | Remove unused import |

### Copy-Paste Duplication

| ID | Files | Issue | Fix |
|----|-------|-------|-----|
| P5 | `studio/tts/audio.py:16-20`, `studio/assets/routes.py:24-26`, `studio/timing/routes.py:55-57` | `_find_ffmpeg()` defined identically in 3 modules | Move to shared `studio/ffmpeg_utils.py` and import |

### Stale Comments (Legacy References)

| ID | File | Line(s) | Issue | Fix |
|----|------|---------|-------|-----|
| P6 | `timeline-editor/backend/video_processor.py` | 564-565 | Docstring says "overlay_entry can be a URL string (legacy)" | Remove "(legacy)" — it's the current format |
| P7 | `timeline-editor/backend/video_processor.py` | 1992-1993 | Comment says "legacy single overlay string" | Update comment to reflect current behavior |

### Silent Exception Swallowing

| ID | File | Line(s) | Issue | Fix |
|----|------|---------|-------|-----|
| P8 | `studio/scenes/routes.py` | Various | `except (json.JSONDecodeError, OSError): pass` — silently swallows errors | Add `logger.debug()` at minimum |
| P9 | `studio/editor/routes.py` | Various | Multiple `except Exception: pass` blocks | Log at debug level |

### TOCTOU Race Conditions (Minor)

| ID | File | Issue | Fix |
|----|------|-------|-----|
| P10 | `studio/editor/routes.py` | `os.path.isfile(path)` check followed by `open(path)` — file could be deleted between | Wrap `open()` in try/except directly, remove pre-check |

### Other

| ID | File | Line(s) | Issue | Fix |
|----|------|---------|-------|-----|
| P11 | `studio/security.py` | 86 | `except Exception:` catches too broadly on `urlparse()` | Catch `ValueError` specifically |
| P12 | `studio/editor/routes.py` | 1278-1400+ | `_process_video()` is 100+ lines with multiple responsibilities | Break into smaller helpers |

---

## 2. Frontend JavaScript Issues

### Console Statements Left in Production (~50+ instances)

| File | Line(s) | Count |
|------|---------|-------|
| `static/js/app.js` | 516, 648 | 2 |
| `static/js/editor.js` | 72, 88, 100, 184, 257, 260 | 6 |
| `static/js/scenes.js` | 615, 663, 850 | 3 |
| `static/js/segmenter.js` | 328, 377, 491 | 3 |
| `static/js/timing.js` | 158, 211, 335 | 3 |
| `static/js/pipeline.js` | 290 | 1 |
| `timeline-editor/frontend/js/app.js` | 20, 56, 176, 432, 444 | 5 |
| `timeline-editor/frontend/js/preview.js` | 106, 144, 146, 182, 187, 192, 200, 211, 216+ | 10+ |

**Fix:** Remove all or replace with centralized error logging.

### Event Listener / Resource Leaks

| ID | File | Line(s) | Issue | Fix |
|----|------|---------|-------|-----|
| J1 | `static/js/app.js` | 326 | `_stsAudioPollId = setInterval(...)` every 100ms, never cleared | Add `clearInterval()` on page unload or convert to event-based |
| J2 | `static/js/scenes.js` | 600-602 | Audio `addEventListener('ended'/'error')` added every `_scnLoadAudio()` without cleanup | Remove old listeners before adding new |
| J3 | `static/js/segmenter.js` | 311-314 | Same audio listener leak pattern | Remove old listeners before adding new |
| J4 | `static/js/timing.js` | 311-325 | Multiple `addEventListener` on audio per load cycle | Unbind before re-binding |

### Global Window Pollution

| ID | File | Variable | Issue | Fix |
|----|------|----------|-------|-----|
| J5 | `static/js/pipeline.js` | `window._pipelineJobs` | Stored globally, no cleanup | Move to module STATE or add cleanup |
| J6 | `static/js/timing.js` | `window._alignTTSPickerItems` | Persists after picker closes | Clean up in `alignCloseTTSPicker()` |

### Redundant Checks / Inefficient Logic

| ID | File | Line(s) | Issue | Fix |
|----|------|---------|-------|-----|
| J7 | `static/js/editor.js` | 198-204 | `STATE.alignResult && STATE.alignResult.alignment && STATE.alignResult.alignment.length` triple check | Use `STATE.alignResult?.alignment?.length` |
| J8 | `static/js/timing.js` | 221, 237 | `STATE.alignResult?.alignment` accessed twice in same function | Cache in local variable |
| J9 | `static/js/scenes.js` | 673, 688 | `_scnSegTimings.length ? _scnSegTimings[_scnSegTimings.length - 1].end : ...` repeated | Extract to local `const totalDuration =` |
| J10 | `static/js/segmenter.js` | 387, 403 | Same pattern — `metadata.total_duration` accessed twice | Cache in local variable |
| J11 | `static/js/app.js` | 785, 757 | `URL.revokeObjectURL()` delays vary (1000ms vs 5000ms) | Standardize to 1000ms |

### Code Duplication Across Files

| Pattern | Files | Approximate Lines Saved |
|---------|-------|------------------------|
| Audio playback init + event listeners | `scenes.js`, `segmenter.js`, `captions.js`, `timing.js` | ~200 lines |
| Play/pause icon SVG toggle | `scenes.js`, `segmenter.js`, `captions.js`, `timing.js` | ~80 lines |
| Playhead/progress bar rendering | `scenes.js`, `segmenter.js`, `timing.js` | ~120 lines |
| Highlight clearing on seek | `scenes.js`, `segmenter.js`, `captions.js`, `timing.js` | ~60 lines |
| History card rendering template | `scenes.js`, `segmenter.js`, `captions.js`, `timing.js` | ~100 lines |

**Total potential savings:** ~560 lines if extracted to shared utilities.

### Dead Code / Stale References

| ID | File | Line(s) | Issue | Fix |
|----|------|---------|-------|-----|
| J12 | `static/js/editor.js` | 5-20 | `getStoredEditorBootProject()` tries 3 storage keys — verify all still used | Audit `sts-staged-timeline`, `sts-editor-boot-project`, `sts-editor-scenes` |
| J13 | `static/js/editor.js` | 65-66 | Comments referencing "backward compatibility" | Remove stale comments |
| J14 | `static/js/export-library.js` | 380-382 | `if (_expLibState.loaded && !force)` then `if (!force)` — redundant | Simplify condition |
| J15 | `static/js/export-library.js` | 104-107 | Uses both `i.video_ratio` and `i.ratio` with fallback | Pick one canonical source |

---

## 3. Recommended Fix Priority

### Phase 1 — Quick Wins (30 min)

1. **P1** Remove duplicate `shutil` imports in editor/routes.py
2. **P3** Remove unused `_find_ffmpeg` import in tts/routes.py
3. **P4** Remove unused `shutil` import in music/routes.py
4. **P6-P7** Update stale "legacy" comments in video_processor.py
5. **J13** Remove stale "backward compatibility" comments in editor.js

### Phase 2 — Resource Leaks (1 hr)

6. **J1** Clear `_stsAudioPollId` interval — convert to event-based or add cleanup
7. **J2-J4** Fix audio event listener leaks — unbind before rebinding in all 4 modules
8. **J5-J6** Clean up global window variables after use

### Phase 3 — Consolidation (2 hrs)

9. **P5** Move `_find_ffmpeg()` to shared `studio/ffmpeg_utils.py`
10. Extract shared audio/timeline utilities from duplicated JS code (~560 lines saved)
11. **J7-J10** Replace verbose null checks with optional chaining

### Phase 4 — Polish

12. **P8-P9** Replace silent `except: pass` with debug logging
13. Remove all `console.log` statements (~50 instances)
14. **P10-P11** Fix TOCTOU patterns and narrow exception types
15. **P12** Break up long `_process_video()` function
