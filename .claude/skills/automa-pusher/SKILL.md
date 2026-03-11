---
name: automa-pusher
description: Push Automa browser extension workflows from local JSON files to Chrome. Supports auto-push (opens temp tab), web UI dashboard, headless via Chrome DevTools Protocol, and patching Automa for upsert support. Use when deploying, syncing, or updating Automa workflows.
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

## How It Works

Automa injects its `webService.bundle.js` content script on every `localhost` page. That script listens for `__automa-ext__` custom events. The pusher serves a temporary localhost page that dispatches the workflow data via that event — Automa receives it and saves to chrome storage.

**Prerequisite:** Automa must be patched once for upsert (update-or-create) support. Without the patch, every push creates a duplicate.

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

### Patch Automa (one-time setup)

Adds an `upsert-workflow` handler so pushes update existing workflows by name instead of creating duplicates.

```bash
python _dev/automation/automa/automa-pusher/automa-pusher.py patch
```

After patching, the user must reload Automa in `chrome://extensions` (click the reload icon). To revert:

```bash
python _dev/automation/automa/automa-pusher/automa-pusher.py patch --revert
```

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

Starts a persistent dashboard at `http://localhost:3457`. The user opens it in Chrome to push workflows interactively.

```bash
python _dev/automation/automa/automa-pusher/automa-pusher.py --ui
```

Note: UI mode serves workflows from a `workflows/` folder next to the script. To use it, copy or symlink `.automa.json` files there.

### Headless mode (Chrome DevTools Protocol)

No browser tab opened. Requires Chrome running with `--remote-debugging-port=9222`.

```bash
python _dev/automation/automa/automa-pusher/automa-pusher.py --headless "_dev/automation/automa/grok/Grok Assets Synchronizer.automa.json"
```

## When to Use This Skill

- **After editing an `.automa.json` workflow** — push the updated version to Chrome
- **After generating a new Automa workflow** with the `automa` skill — push it to test
- **When the user says "push", "deploy", "sync", or "update" in the context of Automa workflows**
- **When the user asks to patch Automa** for upsert support

## Typical Flow

1. **First time only:** Run `patch` command, tell user to reload Automa in `chrome://extensions`
2. **Find the workflow file(s):** Glob for `_dev/automation/automa/**/*.automa.json`
3. **Push:** Run the auto-push command with the file path(s)
4. **Confirm:** Output shows "Done!" on success, or "Timed out" if something went wrong

## Important Notes

- Upsert matches by **workflow name** — renaming a workflow in the JSON creates a new entry
- The patch survives Chrome sessions but may be overwritten when Automa auto-updates — re-run `patch` if that happens
- Auto mode opens a localhost tab briefly — Chrome must be open and Automa installed
- File paths with spaces must be quoted
