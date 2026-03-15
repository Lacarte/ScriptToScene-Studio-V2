---
name: Vue Migration Plan
description: Phased plan to merge timeline editor into main app then migrate entire frontend to Vue 3 + Vite + Pinia with feature-based architecture
type: project
---

## Phase 1 — Merge Timeline Editor into Main App ✅ COMPLETE

**1.1** ✅ Eliminated iframe boundary — editor inline in main app
**1.2** ✅ Replaced postMessage with direct function calls
**1.3** ✅ Merged editor state into main app data flow → Pinia `useStagingStore`
**1.4** ✅ Consolidated duplicate CSS → `shared.css` + `theme.css` design tokens
**1.5** ✅ Absorbed editor export backend into `studio/editor/` blueprint
**1.6** ✅ Deleted `timeline-editor/` directory

---

## Phase 2 — Set Up Vue 3 + Vite Scaffold ✅ COMPLETE

**2.1** ✅ Vite + Vue 3 + Vue Router + Pinia initialized in `frontend/`
**2.2** ✅ Vite outputs to `static/dist/`, Flask serves unchanged
**2.3** ✅ Feature-based folder structure established:

```
frontend/src/
├── app/                    # App shell, router, layout
├── features/               # 9 feature modules migrated
│   ├── pipeline/           ✅
│   ├── tts/                ✅
│   ├── timing/             ✅
│   ├── segmenter/          ✅
│   ├── scenes/             ✅
│   ├── assets/             ✅
│   ├── captions/           ✅ (stub)
│   ├── editor/             🔶 Phase 3.5 in progress
│   ├── export-library/     ✅
│   └── settings/           ✅
├── shared/
│   ├── api/client.js       ✅ Typed fetch wrapper
│   ├── composables/        ✅ useToast, useAudioRegistry, useProjectSync
│   ├── components/         ✅ ToastContainer, WelcomeOverlay, PageLayout, HistorySection
│   ├── stores/             ✅ appStore (Pinia), stagingStore (Pinia)
│   ├── data/stories.js     ✅ Shared constants
│   └── utils/format.js     ✅ timeAgo, formatBytes, fmtTime, etc.
└── styles/
    ├── theme.css           ✅ Design tokens + semantic color vars
    ├── shared.css          ✅ .card, .page-title, .section-label, .action-btn, .gen-btn
    └── legacy/             ✅ Scoped to #main-content for old SPA compat
```

---

## Phase 3 — Migrate Feature by Feature

**3.1** ✅ App shell — sidebar, toast, router, MainLayout (Pinia-backed)
**3.2** ✅ Settings + Export Library — migrated, shared components built
**3.3** ✅ TTS, Segmenter, Scenes, Timing, Assets — all migrated with composables
**3.4** ✅ Pipeline — migrated, SSE cleanup, cross-feature routing
**3.5** 🔶 Editor — **IN PROGRESS**:

### Editor Migration Sub-Phases

| Sub-Phase | Status | Details |
|-----------|--------|---------|
| Phase 0: Foundation | ✅ | CSS extracted (5,962→115 lines), `useEditorBus`, dialog bridge |
| Phase 1: Dialogs | ✅ | 8 Vue components: ResetConfirm, ExportJson, ExportProgress, MusicPicker, Share, NoData, AssetPicker, TTSPicker |
| Phase 1b: Inline scripts | ✅ | Updated to use Vue dialog bridge, staging store, removed direct DOM show/hide |
| Phase 2: Sidebar tabs | ⬜ | 8 tab components: Media, Effects, Transitions, Overlays, Text, Caption, Adjustment, TabBar |
| Phase 3: Preview panel | ⬜ | PreviewPanel, PlayerControls, AspectRatioDropdown |
| Phase 4: Properties + toolbar | ⬜ | PropertiesPanel, TimelineToolbar, PanelResizeHandle |
| Phase 5: Timeline tracks | ⬜ | TimelinePanel, VideoTrack, TextTrack, CaptionTrack, AudioTrack, TimeRuler, Playhead, SceneClip |
| Phase 6: EditorState → Pinia | ⬜ | Replace mutable EditorState singleton with Pinia store |
| Phase 7: video-editor.js decomposition | ⬜ | Split 10,266-line file into usePlayback, useTimeline, useSceneEditor, etc. |

**3.6** ✅ Incremental migration working — legacy pages render in wrapper

---

## Phase 4 — Clean Up

**4.1** ✅ Removed 10 vanilla JS files from `static/js/` (405KB total: app, pipeline, tts, scenes, assets, segmenter, timing, captions, export-library, editor.js). Only `static/js/editor/` remains (video-editor.js + modules — still needed by Vue editor wrapper).

**4.2** ✅ Root route `/` now redirects to `/vue/`. Old app accessible at `/legacy` for reference. Old version archived in `_dev/old_version/`.

**4.3** ⬜ TypeScript interfaces matching Pydantic schemas
**4.4** ⬜ Vitest component/store tests

---

## Quality Audit (completed alongside migration)

All items from `VUE-MIGRATION-AUDIT.md` resolved:
- **F-01–F-04**: SSE cleanup, audio leak, cross-feature coupling, localStorage.clear
- **A-01–A-03**: Editor CSS extracted, Pinia wired, readonly consistency
- **L-01–L-03**: Window globals bridged, staging store, legacy CSS scoped
- **R-01–R-04**: Shared utils, shared.css, PageLayout, HistorySection
- **S-01–S-02**: appStore, useProjectSync
- **V-01–V-03**: 20 catch blocks logged, validation, loading refs
- **P-01–P-03**: Editor CSS file, keep-alive, useTts split
- **D-01, D-03**: Legacy CSS scoped, 30+ colors → CSS vars

---

**Current file stats:**
- `EditorPage.vue`: 115 lines (was 5,962)
- `editor-shell-html.js`: 1,356 lines (was 1,679 — dialogs removed)
- `editor-inline-scripts.js`: ~490 lines (updated to use Vue bridge)
- `editor/styles/editor.css`: 5,907 lines (extracted, dedicated)
- `editor/components/`: 8 dialog Vue components
- `editor/composables/`: useEditor, useEditorBus
