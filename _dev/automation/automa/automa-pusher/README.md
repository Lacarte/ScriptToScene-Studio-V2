# Automa Workflow Pusher

Push and update Automa browser extension workflows from local JSON files. Pure Python, zero dependencies.

## How It Works

```
automa-pusher.py             Chrome Browser              Automa Extension
────────────────             ──────────────              ────────────────

1. Reads workflow JSON  ──►  2. Opens a temp tab          3. Automa's content script
   and embeds it               on localhost with            (webService.bundle.js)
   inline in an HTML page.     the data already inline.     runs on ALL localhost pages.
                                     │
                               4. Page JS dispatches        It listens for a custom
                                  CustomEvent               DOM event.
                                  '__automa-ext__'  ────────────►│
                                                           5. Automa receives the
                                                              event and saves the
                                                              workflow to chrome
                                                              storage. Done!
```

**Key insight:** Automa automatically injects its `webService.bundle.js` content script on every `localhost` page. That script listens for `__automa-ext__` custom events. We exploit this to push workflow data directly into Automa's storage — no extension APIs, no Chrome debug mode, no manual import/export.

## Setup

### Step 1: Patch Automa (one time only)

By default, Automa only has an `add-workflow` event that always creates a **new** workflow (duplicates every time). The patch adds an `upsert-workflow` handler that:

- Checks if a workflow with the **same name** already exists
- If yes → **updates** it (preserves its ID and creation date)
- If no → **creates** a new one

```bash
python automa-pusher.py patch
```

Then go to `chrome://extensions` in Chrome and click the **reload** icon on Automa (circular arrow). No Chrome restart needed.

The patch is safe — a backup is created automatically. To undo:

```bash
python automa-pusher.py patch --revert
```

### Step 2: Push

**Auto mode** (default — opens a temp tab, pushes, exits):

```bash
python automa-pusher.py grok/my-workflow.json
```

Workflow data is embedded directly in the HTML page — zero API calls, one server request, done.

```bash
python automa-pusher.py workflow1.json workflow2.json  # Push multiple files
```

**Web UI mode** (interactive dashboard):

```bash
python automa-pusher.py --ui
```

Starts a persistent server at `http://localhost:3457`. Open that URL in Chrome to see all workflows and push them individually or all at once. Place `.json` files in the `workflows/` folder next to the script.

**Headless mode** (no browser tab, via Chrome DevTools Protocol):

```bash
python automa-pusher.py --headless grok/my-workflow.json
```

Connects directly to Chrome's DevTools port — no tab opened, no UI. Requires Chrome to be running with remote debugging enabled:

```bash
chrome.exe --remote-debugging-port=9222
```

## Commands Reference

| Command | Description |
|---------|-------------|
| `python automa-pusher.py <file.json> ...` | Auto-push files (opens Chrome tab briefly) |
| `python automa-pusher.py --ui` | Start interactive web UI at localhost:3457 |
| `python automa-pusher.py --headless <file.json> ...` | Push via Chrome DevTools Protocol (no UI) |
| `python automa-pusher.py patch` | Patch Automa for upsert support |
| `python automa-pusher.py patch --revert` | Revert the Automa patch |
| `python automa-pusher.py` | Show help |

## Files

```
_dev/automation/automa/
├── automa-pusher.py          # The tool — single file, no deps
├── automa-pusher-README.md   # This file
├── grok/                     # Grok workflow JSONs
└── midjourney/               # MidJourney workflow JSONs
```

## Requirements

- Python 3.6+
- Chrome with Automa extension installed
- For auto/UI modes: Chrome opens a localhost page (Automa's content script activates automatically)
- For headless mode: Chrome running with `--remote-debugging-port=9222`

## Notes

- **Upsert matches by workflow name.** If you rename a workflow in the JSON, it will be treated as new.
- **The patch survives Chrome sessions** but may be overwritten when Automa auto-updates. Just re-run `python automa-pusher.py patch` if that happens.
- **No Node.js, no pip install, no dependencies.** Just Python and a browser.




The skill activates automatically when you talk about pushing Automa workflows — but you can also invoke it explicitly:


/automa-pusher
Then describe what you want, e.g.:

"push the Grok workflow to Chrome"
"patch Automa for upsert"
"push all workflows"
It also triggers automatically when you say things like "push this workflow to Automa" or "deploy the Grok synchronizer" in normal conversation — Claude will read the skill and know the exact commands to run.