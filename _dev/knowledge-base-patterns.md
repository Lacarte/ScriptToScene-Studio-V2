# ScriptToScene Studio — Knowledge Base
## Patterns, Techniques & Mental Models Learned Through Development

> Every entry below was extracted from the **error → trial → solution** iterations
> visible in the git history (60+ commits, Mar 22 – Mar 31, 2026).
> Each pattern includes the context that triggered it, the mental decision,
> and why it matters for future work.

---

## Table of Contents

1. [Browser Automation Self-Audit](#1-browser-automation-self-audit)
2. [MV3 Service Worker Survival](#2-mv3-service-worker-survival)
3. [CSP Boundary Delegation](#3-csp-boundary-delegation)
4. [Port Scanning Auto-Discovery](#4-port-scanning-auto-discovery)
5. [Dead Client Pruning](#5-dead-client-pruning)
6. [Preflight Gate Pattern](#6-preflight-gate-pattern)
7. [Message Acknowledgment Protocol](#7-message-acknowledgment-protocol)
8. [Escalating Retry with Context Reset](#8-escalating-retry-with-context-reset)
9. [Visual Verification via Remote Screenshot](#9-visual-verification-via-remote-screenshot)
10. [DOM Mutation Recording for Debugging](#10-dom-mutation-recording-for-debugging)
11. [Race Condition Prevention with Thread Locks](#11-race-condition-prevention-with-thread-locks)
12. [Graceful Degradation on Rate Limits](#12-graceful-degradation-on-rate-limits)
13. [Cross-Extension Orchestration](#13-cross-extension-orchestration)
14. [Pipeline Step Isolation](#14-pipeline-step-isolation)
15. [HTML Reference Snapshots as Evidence](#15-html-reference-snapshots-as-evidence)
16. [Background Tab Resilience Testing](#16-background-tab-resilience-testing)
17. [Broadcast-then-Orphan Messaging](#17-broadcast-then-orphan-messaging)
18. [Watermark Sweep as Post-Condition](#18-watermark-sweep-as-post-condition)
19. [Diagnostic Command Infrastructure](#19-diagnostic-command-infrastructure)
20. [Iterative Architecture Renaming](#20-iterative-architecture-renaming)

---

## 1. Browser Automation Self-Audit

**Pattern Name:** Self-Audit / Observability-First Automation

**What triggered it:**
Jobs were silently failing — images not uploading, extensions appearing connected
but actually dead, prompts landing in wrong fields. No way to know what went wrong
without manually opening Chrome DevTools.

**The mental shift:**
> "I can't trust what I can't see. If I automate a browser, I need the same
> visibility I'd have sitting in front of it — screenshots, state dumps, mutation logs."

**What was built (iteratively):**
1. `DIAGNOSE` command — sends WS message, extension responds with full internal state
2. `SCREENSHOT` command — captures the visible tab as PNG via `chrome.tabs.captureVisibleTab`
3. `ScreenshotCapture` utility class — reusable across all Python tests
4. DOM Activity Recorder — separate extension that watches mutations on any XPath
5. Python test suites that combine all of the above: connect → act → screenshot → assert

**Critical thinking applied:**
- Automation without observability is a black box — you're debugging blind
- Screenshots at key moments (before submit, after error, on retry) create a visual audit trail
- Remote diagnostics via WS means you never need to touch the browser manually

**Code example:**
```python
# Take a screenshot at every critical decision point
cap = ScreenshotCapture(ws, test_name="gemini-ws")
cap.take("before-submit")
# ... do work ...
cap.take("after-error", on_fail="warn")
```

---

## 2. MV3 Service Worker Survival

**Pattern Name:** Persistent Connection Keepalive (3-attempt convergence)

**What triggered it:**
Chrome MV3 kills service workers after 30 seconds of inactivity. The WebSocket
connection died silently, jobs were lost, and the extension appeared connected
in the UI but was actually dead.

**The iteration journey (3 failed attempts before success):**

| Attempt | Technique | Result |
|---------|-----------|--------|
| 1 | `setInterval` ping every 25s | Worker still killed — `setInterval` doesn't survive termination |
| 2 | `chrome.alarms` every 24s | Fires after termination, but 30s gap = WS drops + reconnect loop |
| 3 | `chrome.runtime.connect()` persistent port | **Works** — worker stays alive as long as port is open |

**The mental model:**
> "Chrome doesn't care about timers. It cares about **active connections**.
> A port from a content script is Chrome's native concept of 'someone is talking to me'."

**Decision pattern:** When a platform kills your process, don't fight the timer —
find what the platform considers a "reason to stay alive" and use that.

**Code example:**
```javascript
// Content script — keeps service worker alive
const port = chrome.runtime.connect({ name: "sts-gemini-alive" });
port.onDisconnect.addListener(() => {
  // Reconnect after brief delay
  setTimeout(() => chrome.runtime.connect({ name: "sts-gemini-alive" }), 1000);
});
```

**Lesson:** The git history shows 3 commits in 2 days fixing this (`206caab` → `8938e63` → `9421b47`).
Each attempt taught something new about MV3's lifecycle. The winning solution was the simplest.

---

## 3. CSP Boundary Delegation

**Pattern Name:** Privilege Escalation via Architecture Layer

**What triggered it:**
Content scripts running on `gemini.google.com` and `grok.com` could not open
`ws://localhost` connections — the page's Content Security Policy blocked them.

**Error observed:**
```
Refused to connect to 'ws://localhost:5050' because it violates
the Content Security Policy directive: "connect-src ..."
```

**The mental decision:**
> "The content script inherits the PAGE's CSP, not the extension's.
> But the background service worker has its OWN CSP that I control."

**Solution:** Move all WebSocket ownership to the background service worker.
Content scripts communicate via `chrome.runtime.connect()` port messaging.

```
[Flask WS Server] ←→ [Background Worker (owns WS)] ←→ [Content Script (owns DOM)]
```

**Critical thinking:**
- Don't fight the platform's security model — work within its layers
- Each layer (page, content script, background) has different privileges
- Design message relay architecture that respects these boundaries

**Commit:** `f5bf0f0` — 413 lines added, 217 removed. Major architectural pivot.

---

## 4. Port Scanning Auto-Discovery

**Pattern Name:** Resilient Service Discovery via Port Sweep

**What triggered it:**
The Flask server sometimes started on port 5050, sometimes 5051 (if 5050 was busy).
Extensions hardcoded to `ws://localhost:5050` would fail silently.

**The iteration:**
1. First: hardcoded port → fails when port changes
2. Then: manual URL override in extension settings → works but tedious
3. Finally: auto-scan ports 5050–5059 in parallel, connect to first success

**Decision pattern:** When you control both ends of a connection but can't
guarantee the address, sweep a known range.

**Code example:**
```javascript
const _PORT_MIN = 5050;
const _PORT_MAX = 5059; // 5060 blocked by Chrome (SIP port)

for (let p = _PORT_MIN; p <= _PORT_MAX; p++) {
  ws = await _tryPort(p);
  if (ws) break;
}
```

**Hidden lesson:** Port 5060 is blocked by Chrome as a SIP port (`ERR_UNSAFE_PORT`).
This was discovered empirically and documented in code comments. **Always test
your port range against browser restrictions.**

---

## 5. Dead Client Pruning

**Pattern Name:** Zombie Connection Cleanup

**What triggered it:**
`is_extension_connected()` returned `True` because old WebSocket objects were
still in the client list — but the actual TCP connection was dead. The server
thought the extension was alive, queued jobs, and they vanished.

**The mental model:**
> "A reference to a socket is not proof of a connection.
> You must **test** the socket before trusting it."

**Solution:** `_prune_dead_clients()` — iterate the client list, try to ping,
remove any that throw. Called before every connectivity check.

**Applied in:** Both `gemini_ws.py` and `animator.py` WebSocket handlers.
Also in `activate_tab()` with 3-attempt retry (1s apart) to handle mid-reconnect states.

**Commit:** `08ae6b1`

---

## 6. Preflight Gate Pattern

**Pattern Name:** Fail-Fast Precondition Check

**What triggered it:**
Users would click "Run Pipeline" and wait 5 minutes through TTS, alignment, and
segmentation — only to fail at step 5 (storyboard) because the Gemini extension
wasn't connected. All prior work was wasted time.

**The mental decision:**
> "If step 5 needs a browser extension, check at step 0."

**Solution:** `POST /api/pipeline/preflight` — verifies Gemini AND Grok extension
WS connectivity before the pipeline starts. Blocks with toast errors if disconnected.

**Pattern structure:**
```
User clicks RUN → Preflight check → [PASS] → Start pipeline
                                   → [FAIL] → Toast error, don't start
```

**Critical thinking:** The cost of a preflight check is <1 second.
The cost of discovering a broken dependency at step 5 of 8 is minutes of wasted compute.
**Always validate expensive-path dependencies before entering the expensive path.**

**Commit:** `815448a`

---

## 7. Message Acknowledgment Protocol

**Pattern Name:** Reliable Delivery with ACK

**What triggered it:**
The server sent `IMAGE_JOB` to the extension, but if the extension was
mid-reconnect or the content script hadn't loaded yet, the job was lost.
No retry, no error — just silence.

**The iteration:**
1. Fire-and-forget: send `IMAGE_JOB` → hope it arrives → **fails silently**
2. Queue + flush: keep jobs in a pending queue, flush when extension connects → **jobs still lost if WS reconnects mid-job**
3. ACK protocol: keep job in pending queue until extension sends `JOB_RECEIVED` → **reliable**

**Code example:**
```
Server: sends IMAGE_JOB, keeps in _pending_jobs
Extension: receives IMAGE_JOB → sends JOB_RECEIVED
Server: receives JOB_RECEIVED → removes from _pending_jobs
```

**Mental model:** In distributed systems, "sent" ≠ "received". Every important
message needs an acknowledgment. This is the same principle behind TCP, but
applied at the application layer.

**Commit:** `849195f`

---

## 8. Escalating Retry with Context Reset

**Pattern Name:** Progressive Recovery with Fresh State

**What triggered it:**
Gemini image generation would fail for many reasons: send button not ready,
prompt didn't land correctly, generation stopped mid-way, text-only refusal.
Simple retries repeated the same failure.

**The solution (commit `96dde7c`):**
- Retry up to 4 attempts with **escalating delays**: 5s → 7s → 9s → 11s
- **Clear stale state on each retry** (container mappings, focus state)
- **Re-verify preconditions** before each attempt (is editor focused? is button ready?)
- **Different failure modes get different responses:**
  - Button not ready → poll up to 5s
  - Prompt didn't land → verify 80% text match threshold
  - Generation stopped → detect `mat-icon[fonticon=stop]` and fast-fail
  - Text-only refusal → detect and skip immediately (don't waste a retry)

**Pattern structure:**
```
for attempt in [1..4]:
    clear_stale_state()
    verify_preconditions()
    try:
        execute()
    except RecoverableError:
        wait(base_delay + attempt * 2s)
        continue
    except FatalError:
        break  # don't waste retries
```

**Critical thinking:**
- Not all failures are equal — classify them as recoverable vs. fatal
- Stale state from a previous attempt is itself a failure cause — reset it
- Escalating delays give the system time to recover from transient issues

---

## 9. Visual Verification via Remote Screenshot

**Pattern Name:** Screenshot-as-Assert

**What triggered it:**
Logs said "connected" but the UI showed a red dot. Logs said "prompt submitted"
but the wrong text was in the input field. **Text-based assertions couldn't catch
visual/DOM state mismatches.**

**The technique:**
Send a `SCREENSHOT` command over WebSocket → extension captures `chrome.tabs.captureVisibleTab()`
→ returns base64 PNG → test saves to disk with descriptive label.

**How it's used in tests:**
```python
snap("01-before-connect")    # Baseline
# ... trigger connection ...
snap("02-after-connect")     # Should show green dot
# ... send job ...
snap("03-job-in-progress")   # Should show typing state
snap("04-after-error")       # Visual evidence of failure
```

**Mental model:**
> "A screenshot is worth a thousand log lines. When debugging browser automation,
> the DOM state at the moment of failure is the most valuable artifact."

**File:** `screenshot.py` — a clean, reusable utility (123 lines) that any test can import.

---

## 10. DOM Mutation Recording for Debugging

**Pattern Name:** Black Box Flight Recorder for the DOM

**What triggered it:**
Image generation on Gemini involves complex DOM changes: loading skeletons appear,
containers are added/removed, images lazy-load into blobs. When something broke,
there was no record of what the DOM actually did.

**The solution:**
A separate extension ("Section Activity Recorder") that:
1. Takes an XPath target from the user
2. Attaches a `MutationObserver` to that element
3. Records every `childList`, `attributes`, and `characterData` change with timestamps
4. Generates an HTML report with the full timeline

**Why a separate extension:**
- Keeps recording logic decoupled from business logic
- Can be attached to ANY page, not just Gemini
- Exposes `__sarAPI` on `window` for cross-extension programmatic control

**Mental model:**
> "An airplane has a black box. Your browser automation should too.
> When it crashes, you want the last 60 seconds of DOM mutations."

**Commit:** `96dde7c` added cross-extension API (`startDOMMonitor`/`stopDOMMonitor`)

---

## 11. Race Condition Prevention with Thread Locks

**Pattern Name:** Mutex on Shared State Files

**What triggered it:**
Multiple WebSocket handlers writing to `storyboard.json` simultaneously.
Gemini uploads images while the pipeline reads status — both do
read-modify-write on the same file. Result: scenes showing "error"
despite images being on disk.

**The bug:**
```
Thread A: read storyboard.json          → {scene_1: "pending"}
Thread B: read storyboard.json          → {scene_1: "pending"}
Thread A: write {scene_1: "ready"}      → saved
Thread B: write {scene_1: "pending"}    → OVERWRITES Thread A's update!
```

**The fix:**
```python
_storyboard_json_lock = threading.Lock()

with _storyboard_json_lock:
    data = read_json(path)
    data["scenes"][idx]["status"] = "ready"
    write_json(path, data)
```

**Critical thinking:**
- Any shared file written by multiple threads/handlers needs a lock
- "It works most of the time" means you have a race condition
- Make the save **synchronous** so status updates complete before `JOB_COMPLETE` fires

**Commit:** `9918000`

---

## 12. Graceful Degradation on Rate Limits

**Pattern Name:** Pause-Detect-Resume with Visual Feedback

**What triggered it:**
Grok and Gemini both impose rate limits. Without detection, the extension kept
submitting prompts into a "Rate limit reached" toast — wasting time and
potentially getting the account flagged.

**The evolution:**
1. No detection → prompts fail silently
2. Toast detection → pause queue, but no feedback to user
3. Full system:
   - 3 detection methods: sonner toast, `<li>` fallback, TreeWalker text scan
   - Red overlay on tab with 2h countdown timer
   - Queue pauses automatically
   - Retry every 30 min until cleared
   - Pipeline receives `RATE_LIMITED` / `RATE_LIMIT_CLEARED` events
   - Gemini: parse both "until \<date\>" and "resets on \<date\>" format changes

**Mental model:**
> "Rate limits are not errors — they're temporary states. Design for them
> as a first-class state in your queue, not as an exception."

**Critical thinking:** The rate limit format **changed between Gemini versions**
(`c3d672c`). If you parse external UI text, expect the format to change.
Use multiple detection strategies as fallbacks.

---

## 13. Cross-Extension Orchestration

**Pattern Name:** Central Controller Pattern

**What triggered it:**
Running a pipeline required: Gemini tab active for storyboard, then switch to
Grok tab for animation, then back to Studio tab. Manual tab switching broke
the flow.

**The evolution:**
1. Manual tab switching → unreliable, user must babysit
2. `NAVIGATE` command → extension navigates its own tab (limited to same domain)
3. `FOCUS_STUDIO_TAB` → extensions can focus the Studio tab after their job completes
4. **Orchestrator extension** → central controller that can focus ANY tab by ID or name

**Decision pattern:**
> "When you have multiple autonomous agents (extensions), you eventually need
> a conductor. The orchestrator doesn't DO work — it tells others when to be visible."

**The Orchestrator supports:**
- `list_tabs` — inventory of all open tabs
- `focus_tab` — activate by tab ID
- `focus_by_name` — activate by logical name ("gemini", "grok") or URL match
- `screenshot` — capture any tab's visible state
- `diagnose` — full system health report

---

## 14. Pipeline Step Isolation

**Pattern Name:** Resume/Stop-After with Step Boundaries

**What triggered it:**
An 8-step pipeline where step 5 (storyboard) or step 7 (animator) could fail
due to browser extension issues. Restarting from step 1 wasted 10+ minutes
of TTS, alignment, and segmentation work.

**The solution:**
```python
# Pipeline supports surgical re-entry
pipeline.run(resume_from="storyboard")   # skip steps 1-4
pipeline.run(stop_after="scenes")        # stop before storyboard
```

**Mental model:**
> "Each pipeline step should be a pure function: read input from disk,
> produce output to disk. This makes any step independently re-runnable."

**Why it matters:** With browser automation in the loop, failures are expected.
The cost of re-running 4 successful steps because step 5 failed is unacceptable
at production scale (137 storyboard images, 129 videos in one day — production log).

---

## 15. HTML Reference Snapshots as Evidence

**Pattern Name:** DOM State Cataloging

**What triggered it:**
Gemini and Grok change their DOM structure without notice. Selectors that worked
yesterday break today. Without evidence of what the DOM looked like when things
worked (and when they broke), debugging is guesswork.

**The practice:**
Save full HTML snapshots of key DOM states:
```
html-references/
├── html-loading.html          # What the page looks like while generating
├── html-generated.html        # Successful generation state
├── failed.html                # What a failure looks like
├── failed-3-31-2026.html      # Dated failure for regression tracking
├── rate-limit.html            # Rate limit toast DOM
├── prefer-choise-dialog.html  # Grok image preference dialog
└── after-generating.html      # Post-generation DOM
```

**Mental model:**
> "External DOM is a moving target. Snapshot it when things work AND when they break.
> The diff between those snapshots is your debugging guide."

**Critical thinking:** Date your failure snapshots. A selector that broke on March 31
might have worked on March 28 — knowing the timeline helps correlate with
platform updates.

---

## 16. Background Tab Resilience Testing

**Pattern Name:** Adversarial Environment Testing

**What triggered it:**
The realization that users don't stare at the Gemini tab while automation runs.
They switch to another tab. Does generation still complete? Do status messages
still arrive? Does image capture work in a background tab?

**The test (`test_background_tab.py`):**
1. Start a job via WebSocket
2. Prompt user to switch away from Gemini tab
3. Monitor: do `STATUS_UPDATE` messages keep arriving?
4. Monitor: does `IMAGE_UPLOAD` arrive (generation completed)?
5. Compare timing with active-tab baseline

**Pattern structure:**
```
Phase 1: Active tab baseline (generate + capture timing)
Phase 2: Background tab test (same job, tab not focused)
Phase 3: Compare metrics (did it take longer? did it fail?)
```

**Mental model:**
> "Test in the environment your users will actually use, not the ideal environment.
> If your automation only works with a focused tab, it's fragile."

---

## 17. Broadcast-then-Orphan Messaging

**Pattern Name:** Dual-Channel Message Delivery

**What triggered it:**
Some Gemini tabs had an active `chrome.runtime.connect()` port (content script loaded
and connected). Others were "orphans" — the tab existed but the content script hadn't
established a port yet (page still loading, or script crashed).

**The solution:**
```javascript
function _broadcastStatus() {
  // Channel 1: Send via persistent ports (fast, reliable)
  _broadcastToAllPorts(msg);

  // Channel 2: Send via chrome.tabs.sendMessage (catches orphans)
  _sendToOrphanTabs({ url: "https://gemini.google.com/*" }, msg);
}
```

**Mental model:**
> "Don't assume all your consumers are in the same state.
> Use the fast path for connected ones, and a fallback for the rest."

**Guard:** Only send to orphan tabs that have `status === 'complete'` —
tabs still loading will throw errors.

---

## 18. Watermark Sweep as Post-Condition

**Pattern Name:** Verification Sweep Before Handoff

**What triggered it:**
Gemini-generated images had watermarks. The pipeline passed them to Grok for
video generation — Grok then generated videos with watermarks baked in.
Removing watermarks after video generation was impossible.

**The solution:**
`_sweep_watermarks()` runs automatically after storyboard completion,
before pushing to the animator step. It verifies AND cleans every image.

**Pattern structure:**
```
Step 5 (Storyboard) → _sweep_watermarks() → Step 6 (Animator)
                      ↳ re-verify every image
                      ↳ clean any remaining watermarks
                      ↳ only THEN proceed
```

**Mental model:**
> "Never pass dirty data to the next step. Each step boundary is a
> quality gate. Verify the post-conditions of step N before entering step N+1."

---

## 19. Diagnostic Command Infrastructure

**Pattern Name:** Remote Introspection Protocol

**What triggered it:**
Extensions run inside Chrome — you can't `print()` from them, you can't attach a
debugger remotely (not easily). You need a way to ask "what is your internal state?"
from outside the browser.

**Commands built over time:**

| Command | Response | Purpose |
|---------|----------|---------|
| `DIAGNOSE` | Full state dump (WS status, queue, counts) | System health check |
| `SCREENSHOT` | Base64 PNG of visible tab | Visual verification |
| `FORCE_DISCONNECT` | Extension closes its WS | Test reconnection behavior |
| `STOP_TYPING` | Halt any in-progress typing/generation | Abort support |
| `diagnose` (orchestrator) | All tabs + all extension states | Full system inventory |

**Mental model:**
> "Build the debug interface before you need it. When something breaks in
> production at 2 AM, you'll be glad you can send a DIAGNOSE command
> instead of trying to screenshare with a Chrome window."

---

## 20. Iterative Architecture Renaming

**Pattern Name:** Naming as Understanding (Refactor-to-Clarity)

**What triggered it:**
The project's vocabulary evolved as understanding deepened. Early names reflected
initial assumptions. Later names reflected actual behavior.

| Original Name | Renamed To | Why |
|--------------|------------|-----|
| `assets/` (directory) | `resources/` | "assets" conflicted with the module name |
| `studio/assets/` (module) | `studio/animator/` | It doesn't grab assets — it animates images into videos |
| `STS-grok-automation` | `STS-grok-sync` | It syncs, not automates — Grok does the generation |
| `sts-gemini` | `STS-gemini-sync` | Consistency with Grok naming |
| `scenes` module | `build_scene_blueprints` | Scenes are data; the module builds blueprints |
| `Gemini Scraper` | `Gemini Grabber` | Not scraping — grabbing generated images |
| "Step 6: Assets" | "Step 7: Animator" | Reflects what it actually does |

**Mental model:**
> "When you rename something, you're not just changing a word —
> you're crystallizing your understanding of what it actually does.
> If a name feels wrong, your mental model has outgrown the code."

**Critical thinking:** Renaming is expensive (update imports, routes, configs, docs).
But wrong names cause worse damage: new contributors build wrong mental models,
and you yourself forget what things do after a week away.

---

## Summary: Meta-Patterns

Looking across all 20 patterns, three meta-themes emerge:

### 1. Observability Before Automation
You cannot automate what you cannot see. Build screenshots, diagnostics,
and DOM recorders BEFORE scaling up. (Patterns 1, 9, 10, 15, 19)

### 2. Expect Failure at Every Boundary
Browser tabs die, WebSockets disconnect, service workers are killed, rate limits
hit, DOM structures change. Design every boundary crossing as unreliable.
(Patterns 2, 3, 5, 6, 7, 8, 12, 16)

### 3. Pipeline as Assembly Line with Quality Gates
Each step reads from disk, writes to disk, and verifies post-conditions.
Any step can be re-run independently. Dirty data never crosses a gate.
(Patterns 6, 14, 18)

---

*Generated from 60+ git commits across 10 days of development.*
*Last updated: 2026-03-31*
