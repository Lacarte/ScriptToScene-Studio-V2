# ScriptToScene Studio — Comprehensive Diagnostic Report

**Generated:** 2026-03-12
**Scope:** Full-stack analysis — backend Python, frontend JavaScript, architecture & data flow
**Status:** Report only — no code changes made

---

## Table of Contents

1. [Backend Python Issues](#1-backend-python-issues)
2. [Frontend JavaScript Issues](#2-frontend-javascript-issues)
3. [Architecture & Data Flow Issues](#3-architecture--data-flow-issues)
4. [Master Summary Table](#4-master-summary-table)
5. [Recommended Fix Priority](#5-recommended-fix-priority)

---

## 1. Backend Python Issues

### CRITICAL

#### B1. Unhandled JSON Parsing in Form Input
- **File:** `studio/timing/routes.py:288`
- **Category:** Error handling / DoS
- **Issue:** `json.loads(seg_config_str)` called without try-except. Malformed JSON in `segment_config` form parameter crashes with `JSONDecodeError`, returning 500.
- **Risk:** Endpoint `/api/timing/align-and-segment` is a DoS vector via malformed JSON.

### HIGH

#### B2. Missing `encoding="utf-8"` in File Operations
- **Files:** `studio/assets/routes.py` (lines 93, 492, 594, 613, 640, 703, 729, 736), `studio/segmenter/routes.py` (70, 98), `studio/timing/routes.py` (114), `studio/tts/routes.py` (multiple)
- **Category:** Data integrity
- **Issue:** `open(path, "r")` without explicit encoding is platform-dependent. On Windows with non-UTF-8 system encoding, files with em-dashes, accented characters, or emojis fail or corrupt silently.

#### B3. Bare Exception Swallowing Critical Errors
- **File:** `studio/assets/organizer.py:98`
- **Category:** Error handling
- **Issue:** Catches `Exception` broadly — swallows disk-full, permission-denied, OOM errors. Doesn't distinguish retryable (network) vs. fatal (permission) errors.

#### B4. No JSON Type Validation After Load
- **Files:** `studio/editor/routes.py:315-316`, `studio/captions/routes.py:297`
- **Category:** Input validation
- **Issue:** After `json.load()`, code calls `.get()` without checking result is a dict. Corrupted JSON (array, string) causes `AttributeError` instead of graceful 400 error.

### MEDIUM

#### B5. Race Condition in Project ID Generation
- **File:** `config.py:73-104`
- **Category:** Race condition
- **Issue:** `_collect_existing_project_ids()` scans directories, but between scan and directory creation another thread can generate the same ID. Two concurrent pipeline jobs could collide.

#### B6. Incomplete Exception Handling in Chapter Generation
- **File:** `studio/scenes/routes.py:373-380`
- **Category:** Error handling / Data loss
- **Issue:** When a chapter (other than first) fails, exception silently ignored and loop continues. User gets incomplete results without clear indication of which scenes are missing.

#### B7. HTTP Response Bodies Logged Without Truncation
- **File:** `studio/scenes/routes.py:431-446`
- **Category:** Information disclosure
- **Issue:** Webhook error responses logged to disk. Could leak API keys, credentials, or PII from n8n error responses.

#### B8. Subprocess Error Silently Swallowed
- **File:** `studio/editor/routes.py:239-242`
- **Category:** Error handling
- **Issue:** ffprobe `except Exception: return {}` — users never know why video metadata is missing.

#### B9. Missing Content-Type Validation on Uploads
- **File:** `studio/timing/routes.py:141-153`
- **Category:** Input validation
- **Issue:** File extension checked but not actual file magic bytes. A `.txt` renamed as `.wav` passes validation.

#### B10. Unbounded Memory in Chapter Generation
- **File:** `studio/scenes/routes.py:302-397`
- **Category:** Resource exhaustion
- **Issue:** Entire script + all segments loaded into memory. 100+ chapters could exhaust RAM with concurrent requests.

#### B11. Inconsistent N8N Webhook Timeouts
- **File:** `studio/scenes/routes.py:358, 417`
- **Category:** Consistency
- **Issue:** 300s for chapter chunks, 180s for single calls, error messages say 300s. Inconsistent behavior depending on code path.

### LOW

#### B12. Missing Null Check in Word Timing
- **File:** `studio/timing/routes.py:117`
- **Issue:** `words[-1]["end"]` — if `"end"` key missing, KeyError raised. Should use `.get("end", 0)`.

---

## 2. Frontend JavaScript Issues

### CRITICAL

#### F1. Unsafe postMessage Origin Validation
- **File:** `static/js/editor.js:71, 95-98, 186, 252-255, 265-273`
- **Category:** Security
- **Issue:** Multiple `postMessage()` calls use wildcard origin `'*'`. Message listener at line 265 checks `event.data.type` but never validates `event.origin`. Any page embedding the app can send navigation commands or intercept scene data.

#### F2. Unescaped HTML in onclick Handlers
- **File:** `static/js/assets.js:28`
- **Category:** XSS
- **Issue:** `onclick="assetsOpenLightbox(${idx},${i})"` — if variables contain quotes or special characters, attacker can break out and inject arbitrary JS.

#### F3. Unhandled Promise Rejections in Audio
- **Files:** `static/js/captions.js:240`, `static/js/timing.js:567`
- **Category:** Error handling
- **Issue:** `.play().catch(() => {})` silently swallows all errors including quota exceeded, permission denied, autoplay violations. User thinks audio is playing when it's not.

### HIGH

#### F4. Audio Element Memory Leak
- **Files:** `static/js/scenes.js:599`, `segmenter.js:310`, `captions.js:92`, `timing.js:140`, `assets.js:1434`
- **Category:** Memory leak
- **Issue:** Audio elements created and registered but when replaced, old elements retain event listeners. `scnStopAudio()` sets `_scnAudio = null` without removing listeners. Prolonged usage accumulates objects.

#### F5. RequestAnimationFrame Race Condition
- **Files:** `static/js/scenes.js:614`, `segmenter.js:327`, `captions.js:238`, `timing.js:156`
- **Category:** Race condition
- **Issue:** `requestAnimationFrame()` called without checking if already scheduled. Rapid play clicks queue multiple RAF callbacks, causing UI jank and excessive redraws.

#### F6. Missing Null Checks After DOM Queries
- **File:** `static/js/scenes.js:691-708`
- **Category:** Safety
- **Issue:** Playhead and timeline block queries may return null if timeline hasn't fully rendered when playback starts. Accessing `.style` on null throws TypeError and breaks playback.

#### F7. localStorage Without Try-Catch
- **File:** `static/js/scenes.js:829-835`
- **Category:** Error handling
- **Issue:** 4 sequential `localStorage.setItem()` calls without try-catch. `QuotaExceededError` on first call leaves remaining keys unset. Editor boot state partially stored, recovery fails.

#### F8. Event Listener Accumulation in Timeline
- **File:** `static/js/segmenter.js:231-262`
- **Category:** Memory leak
- **Issue:** `renderSegTimeline()` rebuilds entire HTML with inline `onmouseenter`/`onmouseleave` handlers. Repeated calls accumulate closure references. Browser becomes sluggish.

#### F9. EventSource Not Closed on Navigation
- **File:** `static/js/pipeline.js:82-97`
- **Category:** Resource leak
- **Issue:** `EventSource` created but only closes on `done`/`error` steps. If user navigates away mid-pipeline, connection stays open server-side. Server accumulates open connections.

### MEDIUM

#### F10. Concurrent Scene Save Race Condition
- **File:** `timeline-editor/frontend/js/editor.js:14, 368`
- **Category:** Race condition
- **Issue:** Debounced save at 500ms — rapid edits to field A then B, plus manual submit, can fire `saveScene()` twice concurrently. Last-write-wins can lose recent edits.

#### F11. Image URL XSS in Scene Editor
- **File:** `timeline-editor/frontend/js/editor.js:139`
- **Category:** XSS
- **Issue:** `<img src="${scene.image_url}">` directly interpolated without validation. Malicious URLs with `javascript:` or `data:` scheme could execute.

#### F12. Missing Boundary Checks in Word Timing
- **File:** `static/js/timing.js:252-254`
- **Category:** Logic error
- **Issue:** Word timing lookup assumes `word.begin`/`word.end` are defined numbers. NaN or undefined from data corruption causes silent highlighting failure.

#### F13. State Mutation Without Immutability
- **File:** `timeline-editor/frontend/js/state.js:34`
- **Category:** State management
- **Issue:** `Object.assign(this.store, updates)` directly mutates store. Subscribers checking shallow equality miss nested changes.

#### F14. postMessage Origin Not Validated in Listener
- **File:** `static/js/editor.js:265`
- **Category:** Security
- **Issue:** Message listener doesn't validate `event.origin`. Any frame can send `{type: 'switch-page'}` to navigate user.

#### F15. Inefficient DOM Queries at 60fps
- **File:** `static/js/segmenter.js:721-726`
- **Category:** Performance
- **Issue:** `querySelectorAll('.seg-timeline-block')` called every animation frame without caching. Unnecessary DOM traversal.

### LOW

#### F16. Silent API Error Display
- **File:** `static/js/export-library.js:391`
- **Issue:** `e.message` might be undefined for non-Error objects. Shows "Failed to load export library undefined".

#### F17. Inconsistent XSS Protection
- **File:** `static/js/scenes.js:57-213`
- **Issue:** `esc()` used for text but `t.color` used directly in style attributes. Inconsistent sanitization.

#### F18. Pipeline SSE Timing Assumption
- **File:** `static/js/pipeline.js:184`
- **Issue:** `setTimeout(500ms)` assumes disk write completes within 500ms. Under load, reads stale data.

#### F19. Unbounded SSE Log Array
- **File:** `static/js/pipeline.js:86`
- **Issue:** `_plLog.push(event)` without size limit. Long pipelines grow array indefinitely.

#### F20. iframe.contentWindow Race
- **File:** `static/js/editor.js:59-68`
- **Issue:** `contentWindow` checked once, then used after delay. If iframe reloads between checks, throws null reference.

---

## 3. Architecture & Data Flow Issues

### CRITICAL

#### A1. Concurrent Write Race on app-config.json
- **Files:** `app.py:83-89`, `studio/editor/routes.py:168-207`
- **Category:** Concurrent access
- **Issue:** `PUT /api/settings` and `PATCH /api/settings` can both write concurrently. No file-level locking. Two threads read-modify-write → one overwrites the other's changes.
- **Risk:** User settings silently lost (sidebar state vs. audio volume).

#### A2. Non-Atomic Project Assembly Chain
- **File:** `studio/editor/routes.py:716-884`
- **Category:** Atomicity
- **Issue:** Assembly performs 7 sequential operations (read scenes, alignments, assets, captions, create initial.json) without transactional guarantees. Failure mid-chain leaves partial state with no rollback.

#### A3. SessionStorage/localStorage Bridge Fragility
- **Files:** `static/js/editor.js:4-22`, `static/js/app.js`
- **Category:** Storage
- **Issue:** Editor boot data in 3 places (sessionStorage, 2x localStorage) with no versioning. Browser restart loses sessionStorage, fallback loads stale data. Multiple tabs cause collisions.

#### A4. Stale Captions Cross-Project Contamination
- **File:** `studio/editor/routes.py:356-409`
- **Category:** Data isolation
- **Issue:** Caption resolution scans ALL caption folders matching `source_folder`. Two projects with same source_folder name load each other's captions silently.

### HIGH

#### A5. Migration Deadlock Between Concurrent Threads
- **File:** `studio/editor/routes.py:49-123`
- **Category:** Migration risk
- **Issue:** Three independent migration functions with no coordinated locking. Thread A moves folder, Thread B tries to rename files in already-moved folder → FileNotFoundError.

#### A6. ZIP Import Without Size Limits
- **File:** `studio/editor/routes.py:1089-1142`
- **Category:** DoS
- **Issue:** Extracted JSON files have no size validation. Attacker uploads ZIP with 1GB project.json → consumes all server memory.

#### A7. Pipeline Job Orphaning
- **File:** `studio/pipeline/routes.py:49-56`
- **Category:** Resource leak
- **Issue:** Failed pipeline jobs remain in `_jobs` dict forever. Cleanup only runs at start of next pipeline, not periodically. `pp_*` folders accumulate.

#### A8. Asset Numbering Instability After Reorder
- **File:** `studio/editor/routes.py:756-778`
- **Category:** Schema mismatch
- **Issue:** Assembly tries both array position and scene index for asset lookup. If scenes reordered, media lookups find wrong asset or none. Export generates video with placeholder images.

#### A9. Export Job Cleanup Race
- **File:** `studio/editor/routes.py:260-273`
- **Category:** Race condition
- **Issue:** Jobs evicted after 3600s. Long-running export (90min) completes but gets evicted before frontend polls result. Video exists on disk but frontend shows failure.

#### A10. Project Metadata Desynchronization
- **File:** `studio/editor/routes.py:586-706`
- **Category:** Consistency
- **Issue:** `project.json` manifest written only if `initial.json` doesn't exist. Manual deletion of initial.json causes stale manifest. Frontend shows "0 scenes" when actual data has 10.

### MEDIUM

#### A11. Webhook Response Normalization Too Lenient
- **File:** `studio/scenes/routes.py:53-78`
- **Issue:** If both `segments` and `scenes` fields exist, normalization skipped. Could load outdated format missing critical fields.

#### A12. Captions Auto-Generation Without Validation
- **File:** `static/js/editor.js:91-102`
- **Issue:** Auto-generation fires even if `source_folder` is empty string. No validation that API succeeded before continuing.

#### A13. Legacy Filename Encoding Collision
- **File:** `studio/editor/routes.py:46, 557-561`
- **Issue:** `-work@in@progress` suffix naming can collide with user-created files. Migration logic misidentifies files.

#### A14. Auto-Assemble Timing Vulnerability
- **File:** `static/js/assets.js`
- **Issue:** Assembly reads scenes.json that may still be mid-write by n8n webhook. Race between scene generation and assembly.

#### A15. TTS Metadata Cross-Project Leak
- **File:** `studio/editor/routes.py:672-685`
- **Issue:** Project discovery matches TTS by `source_folder`, not `project_id`. Shared source folders cause metadata cross-contamination.

#### A16. Grabber Job Persistence Race
- **File:** `studio/assets/routes.py:70-101`
- **Issue:** `_save_job()` writes unguarded. Concurrent update + save → status mismatch. Restart loses "completed" status.

#### A17. Editor WIP Stale Reference Loading
- **File:** `studio/editor/routes.py:464-508`
- **Issue:** WIP preferred on load but may reference deleted assets. No validation that WIP references are still valid.

#### A18. Import ZIP Unbounded Rename Loop
- **File:** `studio/editor/routes.py:1065-1073`
- **Issue:** Duplicate ID handling increments suffix without upper bound. 1000 imports of same ZIP = O(n^2) collision checking.

---

## 4. Master Summary Table

| ID | Issue | Severity | Category | Area |
|----|-------|----------|----------|------|
| **B1** | Unhandled json.loads() crash | CRITICAL | Error handling | Backend |
| **F1** | Unsafe postMessage origin | CRITICAL | Security | Frontend |
| **F2** | Unescaped onclick handlers | CRITICAL | XSS | Frontend |
| **F3** | Swallowed audio play() errors | CRITICAL | Error handling | Frontend |
| **A1** | app-config.json write race | CRITICAL | Race condition | Architecture |
| **A2** | Non-atomic project assembly | CRITICAL | Atomicity | Architecture |
| **A3** | SessionStorage bridge fragility | CRITICAL | Storage | Architecture |
| **A4** | Caption cross-project contamination | CRITICAL | Data isolation | Architecture |
| **B2** | Missing UTF-8 encoding | HIGH | Data integrity | Backend |
| **B3** | Bare exception swallowing | HIGH | Error handling | Backend |
| **B4** | No JSON type validation | HIGH | Input validation | Backend |
| **F4** | Audio element memory leak | HIGH | Memory leak | Frontend |
| **F5** | RAF race condition | HIGH | Race condition | Frontend |
| **F6** | Missing DOM null checks | HIGH | Safety | Frontend |
| **F7** | localStorage no try-catch | HIGH | Error handling | Frontend |
| **F8** | Event listener accumulation | HIGH | Memory leak | Frontend |
| **F9** | EventSource not closed | HIGH | Resource leak | Frontend |
| **A5** | Migration deadlock | HIGH | Migration risk | Architecture |
| **A6** | ZIP import DoS | HIGH | Input validation | Architecture |
| **A7** | Pipeline job orphaning | HIGH | Resource leak | Architecture |
| **A8** | Asset numbering instability | HIGH | Schema mismatch | Architecture |
| **A9** | Export cleanup race | HIGH | Race condition | Architecture |
| **A10** | Project metadata desync | HIGH | Consistency | Architecture |
| **B5** | Project ID race condition | MEDIUM | Race condition | Backend |
| **B6** | Silent chapter failure | MEDIUM | Error handling | Backend |
| **B7** | Response bodies in logs | MEDIUM | Info disclosure | Backend |
| **B8** | Subprocess error swallowed | MEDIUM | Error handling | Backend |
| **B9** | No magic byte validation | MEDIUM | Input validation | Backend |
| **B10** | Unbounded chapter memory | MEDIUM | Resource exhaustion | Backend |
| **B11** | Inconsistent timeouts | MEDIUM | Consistency | Backend |
| **F10** | Concurrent save race | MEDIUM | Race condition | Frontend |
| **F11** | Image URL XSS | MEDIUM | XSS | Frontend |
| **F12** | Word timing boundary check | MEDIUM | Logic error | Frontend |
| **F13** | State mutation | MEDIUM | State management | Frontend |
| **F14** | postMessage origin in listener | MEDIUM | Security | Frontend |
| **F15** | 60fps DOM queries | MEDIUM | Performance | Frontend |
| **A11-A18** | Various medium issues | MEDIUM | Mixed | Architecture |
| **B12** | Missing null check | LOW | Error handling | Backend |
| **F16-F20** | Various low issues | LOW | Mixed | Frontend |

**Totals:** 8 Critical, 16 High, 19 Medium, 6 Low = **49 issues**

---

## 5. Recommended Fix Priority

### Phase 1 — Critical Security & Data Integrity
1. **F1/F14** — Add `event.origin` validation to all postMessage listeners
2. **F2** — Escape HTML attributes in dynamic onclick handlers
3. **B1** — Wrap `json.loads()` in try-except in timing routes
4. **A4** — Scope caption resolution by `project_id`, not just `source_folder`
5. **B2** — Add `encoding="utf-8"` to all file `open()` calls

### Phase 2 — Stability & Reliability
6. **A1** — Add file-level locking for app-config.json writes
7. **A2** — Add rollback capability to project assembly chain
8. **F4** — Clean up old audio elements before creating new ones
9. **F9** — Close EventSource on page navigation
10. **F7** — Wrap all localStorage calls in try-catch
11. **B3** — Use specific exception types in organizer.py
12. **B4** — Validate JSON structure after loading

### Phase 3 — Resource Management
13. **A7** — Add periodic pipeline job cleanup
14. **A6** — Add size limits to ZIP import extraction
15. **A9** — Persist export job status to disk
16. **F5** — Cancel existing RAF before scheduling new one
17. **F8** — Cache DOM queries, avoid rebuilding inline handlers

### Phase 4 — Consistency & Polish
18. **A3** — Version sessionStorage data with schema validation
19. **A5** — Coordinate migration functions with file locks
20. **B5** — Thread-safe project ID generation
21. **B11** — Standardize webhook timeouts
22. Remaining MEDIUM and LOW issues
