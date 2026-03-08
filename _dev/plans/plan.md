# Plan: Add Kie AI Provider + Midjourney --cref Character Chaining

---

## Part 1: Kie AI Image Generation Provider

### Context

The asset generation module currently uses **Midjourney via browser automation** (Automa extension). The user wants to add **Kie AI** (`api.kie.ai`) as a second provider. A working n8n workflow demonstrates the API flow:

1. `POST /api/v1/jobs/createTask` → returns `taskId`
2. `GET /api/v1/jobs/recordInfo?taskId=...` → poll until `resultJson` populated
3. Download image from `resultJson.resultUrls[0]`

### Recommendation: Implement directly in Python (not via n8n)

| Factor | Python (direct API) | n8n webhook |
|--------|-------------------|-------------|
| Dependencies | None (just `requests`) | Requires n8n running |
| Debugging | Python logs, breakpoints | Separate n8n execution history |
| Per-scene tracking | Full control via existing job system | Must build callback mechanism |
| Error handling | Direct try/catch + retries | Webhook failure = lost context |
| Modularity | Clean provider alongside Midjourney | Logic split across two systems |
| Maintainability | One codebase | Must check n8n + Python |

### Implementation

**Step 1: Config** — `config.py`, `.env.example`
- Add `KIE_AI_API_KEY`, `KIE_AI_MODEL` (`nano-banana-2`), `KIE_AI_BASE_URL` (`https://api.kie.ai/api/v1`)

**Step 2: Provider module** — new `studio/assets/providers/kie_ai.py`
- `generate_image(prompt, aspect_ratio, resolution, output_format, api_key)` → create task, poll, return URL
- `_create_task(...)` → POST `/jobs/createTask` with Bearer auth
- `_poll_result(task_id, ...)` → GET `/jobs/recordInfo` loop (3s interval, 120s timeout)

**Step 3: Backend grabber** — `studio/assets/routes.py`
- When `provider == "kie-ai"`: spawn background thread that loops scenes sequentially
- Status flow: `pending → generating → downloading → ready`
- Downloads via existing `organizer.py` logic
- No Automa needed — fully server-side

**Step 4: Frontend** — `static/js/assets.js`, `static/index.html`
- Add "Kie AI" to provider dropdown
- Hide Midjourney-specific UI when Kie AI selected
- Show resolution (1K/2K) and format (jpg/png) options
- Add `"generating"` status badge

---

## Part 2: Midjourney --cref Character Reference Chaining

### Context

Midjourney V7 supports `--cref <url>` (Character Reference) to maintain visual consistency across scenes. Each scene (except the first) should use the **previous scene's generated image URL** as its `--cref`, creating a chain:

```
Scene 0: [prompt] --v 7 --ar 9:16                              (no --cref)
Scene 1: [prompt] --v 7 --ar 9:16 --cref <scene0_cdn_url> --cw 100
Scene 2: [prompt] --v 7 --ar 9:16 --cref <scene1_cdn_url> --cw 100
...
```

### Architecture: Automa-only (no backend changes)

The Automa synchronizer's `startTyping()` engine **already processes scenes sequentially** (one at a time with delays/cooldowns). The `--cref` chaining logic fits naturally inside this typing loop:

1. Type scene 0 prompt (no `--cref`)
2. Wait for scene 0's images to appear on the MJ page (poll/scan)
3. Grab the CDN URL of scene 0's first image
4. Append `--cref <url> --cw 100` to scene 1's `fullPrompt`
5. Type scene 1 → wait → grab URL → inject into scene 2 → repeat

**No backend changes needed.** The backend sends all scenes at once as before. The Automa JS handles the chaining client-side during the typing loop.

```
Backend: sends all scenes via /grabber/pending (unchanged)
  ↓
Automa: receives all scenes, stores in typing queue
  ↓
Typing loop (sequential):
  Scene 0: typeIntoMJ(prompt) → wait for images → scanPage() → grab CDN URL
  Scene 1: inject --cref <scene0_url> → typeIntoMJ(prompt + --cref) → wait → scan → grab
  Scene 2: inject --cref <scene1_url> → typeIntoMJ(prompt + --cref) → wait → scan → grab
  ...
```

### Implementation — Only file: `Assets Synchronizer.automa.json`

All changes are in the `sync_js` node's JavaScript code.

**1. Add `crefChain` state flag**

In the `S` state object (line ~10), add:
```javascript
crefChain: true,          // --cref chaining enabled
crefWeight: 100,          // --cw value (0-100)
lastGeneratedUrl: null,   // CDN URL of previous scene's first image
```

**2. Add `waitForSceneImages(sceneNum)` function**

After typing a scene, poll the MJ page DOM until images for that scene appear. The synchronizer already uses `scanPage()` to scrape `sts-picked` elements. New function:

```javascript
async function waitForSceneImages(sceneNum, timeoutMs = 180000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (!S.typing.active) return null; // stopped
    scanPage();
    const sc = S.scenes[String(sceneNum)];
    if (sc && sc.urls && sc.urls.length > 0) {
      return sc.urls[0]; // Return first CDN URL
    }
    await sleep(5000); // Poll every 5s
  }
  console.warn('Timeout waiting for scene', sceneNum, 'images');
  return null;
}
```

**3. Modify `startTyping()` loop (line ~672)**

Current flow:
```javascript
await typeIntoMJ(item.fullPrompt);
item.status = 'typed';
// ... delay/cooldown ...
```

New flow with `--cref` chaining:
```javascript
// Inject --cref from previous scene (if chaining enabled and not first scene)
let promptToType = item.fullPrompt;
if (S.crefChain && S.lastGeneratedUrl && i > 0) {
  promptToType += ` --cref ${S.lastGeneratedUrl} --cw ${S.crefWeight}`;
  console.log('Injected --cref from previous scene:', S.lastGeneratedUrl);
}

await typeIntoMJ(promptToType);
item.status = 'typed';
S.typing.typedCount++;
S.typing.batchCount++;
render();

// If cref chaining, wait for this scene's images before proceeding
if (S.crefChain) {
  const hasMore = tq.slice(i + 1).some(q => q.status !== 'typed');
  if (hasMore) {
    // Wait for MJ to generate images for this scene
    S.typing.countdownType = 'waiting_cref';
    render();
    const url = await waitForSceneImages(item.scene);
    if (url) {
      S.lastGeneratedUrl = url;
      console.log('Scene', item.scene, 'ready, --cref URL:', url);
      // Also send results immediately so backend tracks progress
      await sendResults(item.scene, S.scenes[item.scene].urls);
    } else {
      console.warn('No image URL for scene', item.scene, '- continuing without --cref');
    }
  }
} else {
  // Original delay/cooldown logic (unchanged)
  const hasMore = tq.slice(i + 1).some(q => q.status !== 'typed');
  if (!hasMore) break;
  if (S.typing.batchCount >= 3) {
    S.typing.batchCount = 0;
    await doCountdown(120, 'cooldown');
  } else {
    await doCountdown(10, 'delay');
  }
}
```

**4. Add `waiting_cref` countdown type rendering**

In `render()` (line ~550), add handling for the `waiting_cref` countdown type:
```javascript
if (S.typing.countdownType === 'waiting_cref') {
  $id('sts-prog-label').textContent = 'Waiting for scene ' + (ci + 1) + ' images...';
  $id('sts-prog-cd').textContent = '⏳';
  $id('sts-prog-cd').className = 'sts-cd cool';
}
```

**5. Add UI toggle for cref chaining**

In the settings panel HTML, add a toggle:
```html
<label class="sts-toggle" id="sts-cref-toggle">
  <div class="sts-toggle-track on" id="sts-cref-track">
    <div class="sts-toggle-thumb"></div>
  </div>
  <span class="sts-toggle-label">--cref chain</span>
</label>
```

Event listener:
```javascript
$id('sts-cref-toggle').addEventListener('click', () => {
  S.crefChain = !S.crefChain;
  $id('sts-cref-track').classList.toggle('on', S.crefChain);
  localStorage.setItem('sts-cref-chain', S.crefChain);
});
```

Load saved preference:
```javascript
S.crefChain = localStorage.getItem('sts-cref-chain') !== 'false'; // default ON
```

**6. Reset `lastGeneratedUrl` on new job**

In `fetchPending()` (line ~770), when a new project is loaded:
```javascript
if (d.projectId !== S.projectId) {
  S.lastGeneratedUrl = null; // Reset chain for new project
}
```

### Key Details

- **Image URL source**: `scanPage()` already scrapes `sts-picked` elements on the MJ page, extracting CDN URLs like `https://cdn.midjourney.com/...`. The first URL from a scene's results is used as the `--cref` for the next scene.
- **Timeout**: `waitForSceneImages()` polls every 5s with a 3-minute timeout. MJ typically generates in 30-90s.
- **Fallback**: If no image URL is found after timeout, the next scene is typed without `--cref` (graceful degradation).
- **`--sref` (Style Reference)**: Can be added globally via the arguments field (e.g. user types `--v 7 --ar 9:16 --sref <url>` in the Studio arguments box). No special handling needed.

---

## Files to Modify/Create

| File | Action |
|------|--------|
| `config.py` | Add `KIE_AI_API_KEY`, `KIE_AI_MODEL`, `KIE_AI_BASE_URL` |
| `.env.example` | Add `KIE_AI_API_KEY=` placeholder |
| `studio/assets/providers/__init__.py` | **New** — package init |
| `studio/assets/providers/kie_ai.py` | **New** — Kie AI API client (~80 lines) |
| `studio/assets/routes.py` | Add `kie-ai` branch in `grabber_start()`, `"generating"` status |
| `studio/assets/organizer.py` | Minor — reuse download for Kie AI URLs |
| `static/js/assets.js` | Provider toggle, `"generating"` status badge |
| `static/index.html` | Provider dropdown, Kie AI options panel |
| `_dev/automation/automa/Assets Synchronizer.automa.json` | `--cref` chaining in typing loop, `waitForSceneImages()`, UI toggle |

## Existing code to reuse
- `studio/assets/organizer.py::organize_grabber_assets()` — download image URL to disk
- `studio/assets/routes.py::grabber_jobs` dict — in-memory job tracking
- `studio/assets/routes.py::_save_job()` — persist job to disk
- `studio/assets/routes.py::grabber_status()` — existing polling endpoint works as-is
- Automa `scanPage()` — already scrapes MJ page for CDN image URLs per scene
- Automa `sendResults()` — already uploads scraped URLs to backend
- Automa `typeIntoMJ()` — already types prompts into MJ textarea

## Verification

### Kie AI
1. Set `KIE_AI_API_KEY` in `.env`
2. Load scenes → select "Kie AI" → Start Grabber
3. No browser tab opens, images generate server-side
4. Status badges: `pending → generating → downloading → ready`
5. Images saved to `output/assets/{project_id}/{scene_num}/`

### --cref Chaining
1. Open MJ tab with Automa synchronizer active
2. Verify `--cref chain` toggle is ON in sync settings
3. Start Grabber in Studio → Start Typing in Automa
4. Scene 0 typed without `--cref`
5. Automa waits for scene 0 images (progress shows "Waiting for scene 1 images...")
6. Once scene 0 images appear, scene 1 typed with `--cref <scene0_cdn_url> --cw 100`
7. Chain continues through all scenes
8. Toggle OFF → original behavior (type all prompts with delays, no `--cref`)
