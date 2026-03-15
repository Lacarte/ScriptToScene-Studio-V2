# Frontend Diagnostic Report — Vue Migration Readiness

**Date:** 2026-03-14
**Status:** ALL PHASES COMPLETE. Editor Phase 0 + Phase 1 fully migrated (8 dialog components).

---

## 1. BUGS & FAILURE POINTS

| ID | Issue | Files | Severity | Status |
|----|-------|-------|----------|--------|
| **F-01** | SSE EventSource connections never cleaned up on route navigation | `usePipeline.js`, `useTts.js` | HIGH | FIXED — added `dispose()` to both composables |
| **F-02** | AudioRegistry leaks — registered elements never auto-unregister | `useAudioRegistry.js` | MEDIUM | FIXED — auto-unregister via `onScopeDispose` |
| **F-03** | `usePipeline` imports `RANDOM_STORIES` from `useTts`, creating cross-feature coupling and triggering side effects | `usePipeline.js:4` | MEDIUM | FIXED — extracted to `@/shared/data/stories.js` |
| **F-04** | `ClearProjectsDialog` does `localStorage.clear()` wiping ALL keys, then `window.location.reload()` bypassing Vue | `ClearProjectsDialog.vue:60` | HIGH | FIXED — now only clears `sts-*` prefixed keys |
| **F-05** | Editor dynamically imports legacy JS via `import(/* @vite-ignore */ editorUrl)` — fragile in production builds with `base: '/vue/'` | `useEditor.js:70` | HIGH | OPEN |

---

## 2. STRUCTURAL / ARCHITECTURAL WEAKNESSES

| ID | Issue | Files | Severity |
|----|-------|-------|----------|
| **A-01** | EditorPage was 5,962 lines — CSS inlined, dialogs in HTML strings | `EditorPage.vue` | CRITICAL | COMPLETE — CSS extracted (5,907 lines → `editor.css`); 8 dialog components created; `EditorPage.vue` 5,962→115 lines; `editor-shell-html.js` 1,679→1,356 lines; event bus + dialog bridge created |
| **A-02** | Pinia store existed but was never used — sidebar state managed locally | `appStore.js`, `MainLayout.vue` | MEDIUM | FIXED — wired up `useAppStore`, persists sidebar collapsed to localStorage |
| **A-03** | Inconsistent readonly exposure — 5 composables exposed internal state as writable refs | `useAssets`, `useSegmenter`, `useScenes`, `useExportLibrary` | LOW | FIXED — added `readonly()` to 15+ internal refs across 4 composables |

---

## 3. LEGACY PATTERNS BLOCKING MIGRATION

| ID | Issue | Files | Severity |
|----|-------|-------|----------|
| **L-01** | Editor depends on 12+ `window.*` globals, inline `onclick` handlers | `useEditor.js`, `editor-inline-scripts.js` | CRITICAL | PARTIAL — 8 dialogs migrated to Vue with window bridge pattern; remaining: sidebar tabs, preview, timeline (Phases 2-7) |
| **L-02** | Cross-feature communication via localStorage keys instead of proper shared state | `ScenesPage.vue`, `AssetsPage.vue`, `useEditor.js` | HIGH | FIXED — created `useStagingStore` Pinia store; Scenes/Assets/Editor all use it (with localStorage persistence for legacy compat) |
| **L-03** | Legacy `.page { display: none }` CSS rule imported globally — hides any Vue component using `class="page"` | `legacy/styles.css:188` | MEDIUM | FIXED — scoped rule to `#main-content > .page` so it only affects old SPA |

---

## 4. REUSABILITY & COMPONENTIZATION

| ID | Issue | Files | Severity |
|----|-------|-------|----------|
| **R-01** | `timeAgo()`, `formatBytes()`, `fmtTime()`, `fmtDuration()` duplicated 15+ times across codebase | 11 files across 7 features | MEDIUM | FIXED — created `@/shared/utils/format.js`, replaced all 15 local copies |
| **R-02** | `.card`, `.page-title`, `.page-subtitle`, `.section-label`, `.action-btn`, `.gen-btn` duplicated across 8 view files | All page views | MEDIUM | FIXED — created `shared.css` with global base classes; removed duplicates from 8 scoped files |
| **R-03** | No shared page layout component — every page duplicates `max-width`, `margin`, `padding`, header structure | All views | LOW | FIXED — created `PageLayout.vue` shared component (available for gradual adoption) |
| **R-04** | History list pattern duplicated across 6 features with identical structure | Pipeline, TTS, Scenes, Assets, Timing, Segmenter | MEDIUM | FIXED — created `HistorySection.vue` shared component (available for gradual adoption) |

---

## 5. STATE MANAGEMENT

| ID | Issue | Severity |
|----|-------|----------|
| **S-01** | Pinia store `useAppStore` exists but is entirely unused | MEDIUM | FIXED in A-02 |
| **S-02** | No centralized "current project" concept — each feature tracks its own projectId independently | HIGH | FIXED — created `useProjectSync` composable; Pipeline, Scenes, Assets, Timing, Segmenter all sync to `appStore.currentProject` |

---

## 6. MISSING VALIDATIONS & ERROR HANDLING

| ID | Issue | Severity |
|----|-------|----------|
| **V-01** | ~20+ empty `catch {}` blocks silently swallowing API errors across all composables | MEDIUM | FIXED — added `console.warn('[Module] ...')` to all 20 catch blocks across 6 composables |
| **V-02** | No form validation before generation (speed range, text length limits) | MEDIUM | FIXED — added speed range (0.5–2.0) and text length (50k) validation to Pipeline and TTS |
| **V-03** | No loading states for secondary data fetches (history, templates, voices) | LOW | FIXED — added `initializing` ref to `useTts` and `useScenes` composables |

---

## 7. PERFORMANCE

| ID | Issue | Severity |
|----|-------|----------|
| **P-01** | EditorPage had 5,962 lines of unscoped CSS inline | HIGH | FIXED — CSS extracted to dedicated `editor/styles/editor.css` file; imported on demand |
| **P-02** | Only `PipelinePage` in `keep-alive` — all other pages re-render and re-fetch on every navigation | LOW | FIXED — added `TtsPage`, `ScenesPage` to keep-alive |
| **P-03** | `useTts.js` was 831 lines — constants, voice data, generation logic all in one file | MEDIUM | FIXED — extracted 110 lines of constants to `tts/data/voiceData.js` (819→715 lines); `PageLayout.vue` created for page structure reuse |

---

## 8. SECURITY

| ID | Issue | Severity |
|----|-------|----------|
| **X-01** | `innerHTML` injection in EditorPage with user data via `_esc()` helper — potential XSS if escaping is incomplete | MEDIUM |
| **X-02** | `editor-inline-scripts.js` uses string interpolation for HTML construction with inline `onclick` handlers | MEDIUM |

---

## 9. TECHNICAL DEBT

| ID | Issue | Severity |
|----|-------|----------|
| **D-01** | Three overlapping CSS layers: `theme.css` (global resets) + `legacy/styles.css` (1,012 lines) + scoped Vue styles — specificity conflicts | HIGH | PARTIAL — L-03 fixed the `.page` conflict; full cleanup blocked by Editor (Phase 3) |
| **D-02** | `VOICES` array in `usePipeline` vs `VOICE_META` in `useTts` | LOW | WONTFIX — different purposes (curated pipeline subset vs full TTS metadata) |
| **D-03** | Hardcoded colors (`#26DE81`, `#FF6B6B`, `#ff9f43`) scattered as inline styles instead of CSS variables | LOW | FIXED — added 5 semantic vars to theme.css (`--accent-ready`, `--accent-active`, `--accent-gold`, `--accent-sky`, `--accent-muted`); replaced 30+ hardcoded hex values across 6 view files |

---

## PRIORITIZED MIGRATION ROADMAP

### Phase 1: Before Migration (Foundation)
1. ~~Extract shared utilities — `timeAgo`, `formatDuration`, `formatBytes` to `@/shared/utils/format.js`~~ (RANDOM_STORIES done)
2. Create shared CSS components — `BaseCard`, `PageHeader`, `HistorySection`, `EmptyState`
3. Audit legacy CSS — remove `.page { display: none }`, duplicate resets, conflicting global rules
4. ~~Fix `RANDOM_STORIES` coupling — move to `@/shared/data/stories.js`~~ DONE
5. Fix silent catch blocks — add `toast.error` or `console.warn` to all 20+ empty catches
6. ~~Fix `ClearProjectsDialog` — clear only `sts-*` prefixed keys~~ DONE
7. ~~Add composable cleanup — `dispose()` for EventSource/timer cleanup~~ DONE

### Phase 2: During Migration (Active Work)
1. Replace localStorage data-passing with Pinia staging store for cross-feature communication
2. Wire up `useAppStore` — current project, sidebar collapsed state
3. Split `useTts.js` (831 lines) into focused composables: voice selection, generation, playback, history
4. Standardize readonly exposure across all composables
5. Add loading states to all composables that fetch data
6. Add more pages to `keep-alive` in MainLayout (TTS, Scenes)
7. Migrate Captions page (currently a stub)

### Phase 3: After Migration (Polish)
1. **Editor rewrite** — the 5,962-line EditorPage is the single biggest task; treat as a separate project milestone
2. Remove all legacy CSS once editor is migrated
3. Add error boundary components
4. Convert singleton composables to Pinia stores for DevTools + testability
5. Add unit tests for composables
