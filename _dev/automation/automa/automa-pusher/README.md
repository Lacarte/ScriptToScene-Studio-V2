# Automa Workflow Pusher

Push Automa browser extension workflows from local JSON files. Pure Python, zero dependencies.

## How It Works

```
automa-pusher.py             Chrome Browser              Automa Extension
----------------             --------------              ----------------

1. Reads workflow JSON  -->  2. Opens a temp tab          3. Automa's content script
   and embeds it                on localhost with            (webService.bundle.js)
   inline in an HTML page.      the data already inline.     runs on ALL localhost pages.
                                      |
                               4. Page JS dispatches        It listens for a custom
                                  CustomEvent               DOM event.
                                  '__automa-ext__'  ------------>|
                                                          5. Automa receives the
                                                             event and saves the
                                                             workflow to chrome
                                                             storage. Done!
```

**Key insight:** Automa injects its `webService.bundle.js` content script on every `localhost` page. That script listens for `__automa-ext__` custom events. We use this to push workflow data directly into Automa's storage — no extension modification, no Chrome debug mode, no manual import/export.

## Usage

### Auto mode (default — opens a temp tab, pushes, exits):

```bash
python automa-pusher.py workflow.json
python automa-pusher.py workflow1.json workflow2.json   # Multiple files
```

Workflow data is embedded directly in the HTML page — one server request, done. The page:
1. Detects if Automa is present (checks `data-atm-ext-installed` on `document.body`)
2. Queries existing workflows to skip duplicates
3. Pushes new workflows via `add-workflow` event

### Web UI mode (interactive dashboard):

```bash
python automa-pusher.py --ui
```

Starts a persistent server at `http://localhost:3457`. Open that URL in Chrome to see all workflows and push them individually or all at once. Place `.json` files in the `workflows/` folder next to the script.

## Features

- Detects if Automa extension is present before pushing
- Checks for duplicate workflows by name (skips existing ones)
- Auto mode: opens browser, pushes, opens Automa dashboard, exits
- UI mode: persistent web dashboard for manual pushing
- Timestamps each push in the workflow description

## Commands Reference

| Command | Description |
|---------|-------------|
| `python automa-pusher.py <file.json> ...` | Auto-push files (opens Chrome tab briefly) |
| `python automa-pusher.py --ui` | Start interactive web UI at localhost:3457 |
| `python automa-pusher.py` | Show help |

## Requirements

- Python 3.6+
- Chrome with Automa extension installed
- The localhost page must be opened in Chrome (not another browser)

## Limitations

- Cannot update an existing workflow (Automa has no built-in update event)
- To re-push a workflow, delete the old one from Automa dashboard first
- Duplicate check matches by workflow **name** — renamed workflows are treated as new

## Notes

- **No patching needed.** Uses Automa's built-in `add-workflow` event. No extension files are modified.
- **No Node.js, no pip install, no dependencies.** Just Python and a browser.
