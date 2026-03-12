---
name: automa-pusher
description: Push Automa browser extension workflows from local JSON files to Chrome. Serves a localhost page that dispatches CustomEvents picked up by Automa's content script. Supports auto-push, web UI dashboard, and duplicate detection. Use when deploying, syncing, or updating Automa workflows.
allowed-tools: Bash, Read, Glob, Grep
author: Mr. Lacarte
---

# Automa Workflow Pusher Skill

Push `.automa.json` workflow files from the project into the Automa Chrome extension — no manual import/export needed.

## Tool Location

```
_dev/automation/automa/automa-pusher/automa-pusher.py
```

Pure Python, zero dependencies. Always run from the project root.

## How It Works — The Full Picture

```
Python script              Chrome Browser              Automa Extension
──────────────              ──────────────              ────────────────

1. Starts a local
   HTTP server on
   localhost:3457
        │
        ▼
2. Serves an HTML page ──► 3. Chrome opens
   with workflow JSON        http://localhost:3457
   + JavaScript code               │
                                   ▼
                            4. The page runs JS that
                               dispatches a CustomEvent:
                               CustomEvent('__automa-ext__',
                                 {detail: {type:'add-workflow',
                                  data:{workflow:...}}})
                                       │
                                       ▼
                                                     5. Automa's content script
                                                        (webService.bundle.js)
                                                        is ALREADY listening on
                                                        ALL localhost pages.
                                                        It catches the event.
                                                            │
                                                            ▼
                                                     6. Automa saves the workflow
                                                        to chrome.storage.local.
                                                        Done!
```

**Key points:**
- Python only serves files on localhost — it's just a web server
- Automa injects `webService.bundle.js` into every `http://localhost/*` page automatically (see its `manifest.json` content_scripts)
- The browser is the bridge — JS on the page talks to Automa's content script via DOM CustomEvents
- No extension file modification needed for basic `add-workflow`
- No CDP, no IndexedDB, no debug port needed — just Chrome with Automa installed

### Automa's Event System

Automa's content script (`webService.bundle.js`) does this on every localhost page:
1. Sets `document.body.setAttribute("data-atm-ext-installed", version)` — used to detect Automa
2. Listens for `window.addEventListener("__automa-ext__", ({detail}) => ...)`
3. Routes `detail.type` to internal handlers: `add-workflow`, `add-team-workflow`, `send-message`, etc.
4. The `add-workflow` handler saves to `chrome.storage.local` and notifies the background script

### Critical Implementation Detail: Page Navigation

When `add-workflow` fires, Automa's background script may **navigate the page away** (e.g., to its dashboard). This means any JavaScript after `dispatchEvent()` may never execute. The solution:

- Use `navigator.sendBeacon("/done")` BEFORE the dispatch — `sendBeacon` survives page unloads
- Only use `fetch("/done")` for cases where no dispatch happens (e.g., all workflows skipped)

### Duplicate Detection (No Patching Needed)

The pusher queries Automa for existing workflows before pushing:
1. Dispatch `CustomEvent('__automa-ext__', {detail: {type:'send-message', data:{type:'get-workflows'}}})`
2. Listen for response on `window.addEventListener('__automa-ext__get-workflows', (e) => ...)`
3. `e.detail` contains the list of existing workflows — check names for duplicates
4. Skip workflows that already exist, only push new ones

## Workflow Files in This Project

Automa workflow JSONs live in subdirectories under `_dev/automation/automa/`:

```
_dev/automation/automa/
├── automa-pusher/           # The pusher tool
│   ├── automa-pusher.py
│   └── README.md
├── grok/                    # Grok workflow JSONs
│   └── *.automa.json
└── midjourney/              # MidJourney workflow JSONs
    └── *.automa.json
```

## Commands

All commands run from the project root. The script path is `_dev/automation/automa/automa-pusher/automa-pusher.py`.

### Push workflows (auto mode — default)

Opens a temporary Chrome tab, pushes the workflow(s), closes automatically.

```bash
# Single file
python _dev/automation/automa/automa-pusher/automa-pusher.py "_dev/automation/automa/grok/Grok Assets Synchronizer.automa.json"

# Multiple files
python _dev/automation/automa/automa-pusher/automa-pusher.py "_dev/automation/automa/grok/Grok Assets Synchronizer.automa.json" "_dev/automation/automa/midjourney/Midjourney Assets Synchronizer.automa.json"
```

### Push all workflows at once

Use glob to find and push all `.automa.json` files:

```bash
python _dev/automation/automa/automa-pusher/automa-pusher.py _dev/automation/automa/grok/*.automa.json _dev/automation/automa/midjourney/*.automa.json
```

### Web UI mode

Starts a persistent dashboard at `http://localhost:3457`. The user opens it in Chrome to push workflows interactively. Has duplicate detection — warns if a workflow already exists.

```bash
python _dev/automation/automa/automa-pusher/automa-pusher.py --ui
```

Note: UI mode serves workflows from a `workflows/` folder next to the script. To use it, copy or symlink `.automa.json` files there.

## What the Pusher Does Automatically

1. **Stamps the description** — appends `| Pushed: YYYY-MM-DD HH:MM` to the workflow description (strips previous stamps)
2. **Saves stamped version** back to the JSON file on disk
3. **Checks for duplicates** — queries Automa for existing workflows by name, skips duplicates
4. **Pushes via `add-workflow`** — dispatches the CustomEvent that Automa's content script handles
5. **Signals completion** — uses `sendBeacon` (survives page navigation) to notify the Python server
6. **Opens Automa dashboard** — auto-opens `chrome-extension://.../newtab.html#/workflows` after push

## When to Use This Skill

- **After editing an `.automa.json` workflow** — push the updated version to Chrome
- **After generating a new Automa workflow** with the `automa` skill — push it to test
- **When the user says "push", "deploy", "sync", or "update" in the context of Automa workflows**

## Typical Flow

1. **Find the workflow file(s):** Glob for `_dev/automation/automa/**/*.automa.json`
2. **Push:** Run the auto-push command with the file path(s)
3. **Confirm:** Output shows "Done!" on success, or "Timed out" if something went wrong
4. If workflow already exists: user must delete it in Automa first, then re-push

## Important Notes

- `add-workflow` always **creates a new** workflow — if the same name exists, the pusher skips it
- To update an existing workflow: delete it in Automa dashboard first, then push again
- Auto mode opens a localhost tab briefly — Chrome must be open and Automa installed
- File paths with spaces must be quoted
- The `data-atm-ext-installed` body attribute confirms Automa is active — the pusher polls for up to 5 seconds
- `get-workflows` query has a 3-second timeout — if Automa doesn't respond, duplicate check is skipped and push proceeds

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Automa extension not detected" | Automa disabled or not installed | Enable Automa in `chrome://extensions` |
| "Timed out" | `/done` callback never received | Check if Chrome opened the localhost page; Automa may have navigated it away too fast |
| "Skipped: already exists" | Workflow with same name in Automa | Delete the workflow in Automa dashboard, then push again |
| Duplicate created | Two workflows with same name | Delete the duplicate in Automa; the pusher now checks for duplicates before pushing |
