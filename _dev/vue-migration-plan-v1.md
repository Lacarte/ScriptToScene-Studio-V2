---
name: Vue Migration Plan
description: Phased plan to merge timeline editor into main app then migrate entire frontend to Vue 3 + Vite + Pinia with feature-based architecture
type: project
---

## Phase 1 — Merge Timeline Editor into Main App

**1.1 Eliminate the iframe boundary.** Move `timeline-editor/frontend/` content (HTML, JS, CSS) into the main `static/` tree. The editor becomes just another page section (`page-editor`) rendered inline instead of inside an iframe.

**1.2 Replace postMessage bridge with direct function calls.** Currently `static/js/editor.js` sends data via `postMessage` and the editor listens in `app.js`. Convert these to direct imports — the editor JS modules (`state.js`, `timeline.js`, `preview.js`, etc.) get loaded as ES6 modules from the main app.

**1.3 Merge the editor's reactive state (`state.js`) into the main app's data flow.** Remove sessionStorage/localStorage shuttling (`sts-staged-timeline`, `sts-editor-boot-project`, `sts-editor-captions`). Data passes directly from pipeline/scenes/segmenter into the editor state.

**1.4 Consolidate duplicate CSS.** Merge `timeline-editor/frontend/css/editor.css` and `styles.css` into the main stylesheet, keeping `shared-theme.css` as the single source of design tokens. Remove the duplicated copy.

**1.5 Absorb the editor's standalone export backend** (`timeline-editor/backend/server.py`, `video_processor.py`) into the existing `studio/editor/` blueprint — it already has 71KB of routes, so the export endpoints fold in naturally.

**1.6 Delete `timeline-editor/` directory.** Everything now lives under `static/` and `studio/`.

---

## Phase 2 — Set Up Vue 3 + Vite Scaffold

**2.1 Initialize Vite + Vue 3 project** inside a new `frontend/` directory at project root. Install Vue 3, Vue Router, Pinia, and Vite.

**2.2 Configure Vite to output built assets to `static/dist/`.** Flask serves them from the same `/static/` path — zero backend changes needed.

**2.3 Set up the folder structure** using feature-based architecture:

```
frontend/src/
├── app/                    # App shell (layout, sidebar, router)
│   ├── App.vue
│   ├── router.ts
│   └── layouts/
│       └── MainLayout.vue  # Sidebar + content area
├── features/               # One folder per domain
│   ├── pipeline/
│   │   ├── views/PipelinePage.vue
│   │   ├── composables/usePipeline.ts
│   │   └── components/
│   ├── tts/
│   ├── timing/
│   ├── segmenter/
│   ├── scenes/
│   ├── assets/
│   ├── captions/
│   ├── editor/             # The merged timeline editor
│   │   ├── views/EditorPage.vue
│   │   ├── composables/useEditorState.ts
│   │   ├── composables/useTimeline.ts
│   │   ├── composables/usePreview.ts
│   │   ├── components/
│   │   │   ├── Timeline.vue
│   │   │   ├── SceneEditor.vue
│   │   │   ├── VideoPreview.vue
│   │   │   └── ExportDialog.vue
│   │   └── stores/editorStore.ts
│   ├── export-library/
│   └── settings/
├── shared/                 # Cross-feature utilities
│   ├── api/                # Typed API client (wraps fetch)
│   ├── composables/        # useToast, useConfirm, useProject
│   ├── components/         # Toast, ConfirmDialog, Modal
│   └── stores/             # appStore (current project, nav state)
└── styles/
    └── theme.css           # Design tokens (from shared-theme.css)
```

---

## Phase 3 — Migrate Feature by Feature

**3.1 Start with the app shell.** Port sidebar navigation, toast system, confirm dialogs, and welcome overlay into `App.vue` / `MainLayout.vue`. Vue Router replaces the manual `showPage()` function.

**3.2 Migrate the simplest pages first** — Settings, Export Library — to validate the pattern and build shared components (API client, toast composable).

**3.3 Migrate data-producing pages next** — TTS, Segmenter, Scenes, Timing, Assets — each becomes a feature folder with its own Pinia store. The store replaces the per-module state that currently lives in vanilla JS closures.

**3.4 Migrate Pipeline page** — it orchestrates the other features, so it comes after them. It uses the other stores rather than having its own heavy state.

**3.5 Migrate the Editor last** — it's the most complex. The editor's existing `state.js` (subscribe/update reactive pattern) maps cleanly onto a Pinia store. Canvas rendering (`preview.js`, `video-editor.js`) stays imperative inside composables that hook into Vue's lifecycle (`onMounted`, `watchEffect`).

**3.6 Each feature migrates behind the existing route.** During migration, unmigrated pages can still render as raw HTML inside a wrapper component, so the app stays functional at every step.

---

## Phase 4 — Clean Up

**4.1 Remove all vanilla JS files** from `static/js/` once every feature is ported.

**4.2 Remove the monolithic `index.html`** — Vue's `index.html` is now the entry point, served by Flask's catch-all route.

**4.3 Type the API layer.** Add TypeScript interfaces matching the Pydantic schemas in each blueprint's `schemas.py` — single source of truth stays in Python, but the frontend gets type safety.

**4.4 Add Vitest for component/store tests** on critical paths (editor state, pipeline orchestration).

---

**Why this architecture:** Feature-based folders keep each domain self-contained (editor code doesn't bleed into scenes code). Pinia stores replace both the vanilla JS module state and the editor's reactive `state.js`. Composables wrap imperative logic (canvas, FFmpeg preview) so Vue components stay declarative. Vue Router gives deep-linkable pages for free. Vite gives HMR during development while Flask serves the production build unchanged.
