# Pipeline Modular Refactor Plan

**Date**: 2026-03-27
**Status**: Phase 1-2 in progress

## Problem

- `PipelinePage.vue` is 3,797 lines (901 script, 693 template, 2,202 CSS)
- `usePipeline.js` is 811 lines exposing 50+ items
- 8+ responsibilities in a single file
- Code duplication between job queue and saved stories runners

## Phase 1: Extract Constants and Utilities (no UI changes)

Create focused constant/utility files:

```
features/pipeline/
  constants/
    steps.js          — ALL_STEPS, HISTORY_STEP_LABELS
    colors.js         — CATEGORY_COLORS, withAlpha, status color helpers
    providerUrls.js   — PROVIDER_URLS map
```

Move from `usePipeline.js`:
- `ALL_STEPS` array
- `providerTabLoadingHTML` → static file or remove

Move from `PipelinePage.vue`:
- `CATEGORY_COLORS` object
- `withAlpha()` function
- `dotColor()`, `dotTextColor()`, `dotIcon()`, `connectorColor()` functions
- `logIcon()`, `logColor()`, `statusColor()` functions

## Phase 2: Split the God Composable (no UI changes)

Split `usePipeline.js` (811 lines) into:

| New File | ~Lines | Responsibility |
|----------|--------|---------------|
| `usePipeline.js` (slimmed) | ~250 | `start`, `stop`, `retry`, `resumeStopped`, SSE, `resetProgress`, `globalStatus`, `running`, `stopping`, `jobId` |
| `useNiches.js` | ~150 | Niche state, CRUD, preset selection, persistence |
| `usePipelineForm.js` | ~80 | `text`, `voice`, `speed`, `style`, `autoScenes`, `autoStoryboard`, `stopAfter`, `imageModel`, `templates`, `VOICES`, localStorage sync |
| `useAudioPreview.js` | ~120 | Extract from PipelinePage.vue: `previewAudio`, `stopPreview`, Web Audio streaming |
| `useJobQueue.js` | ~150 | Extract from PipelinePage.vue: `jobQueue`, `savedStories`, queue runners |
| `usePipelineHistory.js` | ~80 | `jobs`, `loadHistory`, `loadFromHistory` |
| `useProviderTabs.js` | ~50 | `_activateProviderTab`, `maybeOpenProviderLoadingTab` |
| `useStepStatus.js` | ~60 | `stepStatus`, visual helpers (dot colors, icons, animations) |

### Backward Compatibility

The slimmed `usePipeline.js` will compose the other composables internally and re-export everything for backward compat. `PipelinePage.vue` import stays the same initially:

```js
// usePipeline.js re-exports for backward compat
import { useNiches } from './useNiches.js'
import { usePipelineForm } from './usePipelineForm.js'
// ... etc
export function usePipeline() {
  const niches = useNiches()
  const form = usePipelineForm()
  return { ...niches, ...form, /* execution stuff */ }
}
```

## Future Phases (not in scope now)

- **Phase 3-6**: Extract Vue components (StoryInput, CreativeSetup, etc.)
- **Phase 7**: UX polish (accordions, unified progress panel, responsive)
