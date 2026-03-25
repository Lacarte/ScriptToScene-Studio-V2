# Automation Browser Plan

**Created:** 2026-03-25
**Status:** Phase A active

---

## Architecture

```
┌─────────────────────────────┐         ┌──────────────────────────────┐
│  MAIN PC (dev + server)     │         │  AUTOMATION BROWSER          │
│                             │         │  (Canary or Chromium)        │
│  ScriptToScene Studio       │◄══WS═══►│  ├─ Grok extension           │
│  Flask on :5050             │         │  ├─ Gemini extension         │
│  Pipeline orchestrator      │         │  └─ Automa workflows         │
│                             │         │  Debug port: 9222            │
└─────────────────────────────┘         └──────────────────────────────┘
```

Required extensions:
- **Grok** — `_dev/automation/extensions/grok/STS-grok-automation` (load unpacked)
- **Gemini** — `_dev/automation/extensions/gemini/sts-gemini` (load unpacked)
- **Automa** — Chrome Web Store or sideload .crx

Required logins:
- `grok.com` (X/Twitter account)
- `gemini.google.com` (Google account)

---

## Phase A: Copy Canary Portable (Current)

Copy the installed Chrome Canary to a portable location on D: drive.

### Setup

```bat
:: One-time copy
xcopy "%LOCALAPPDATA%\Google\Chrome SxS\Application" "D:\@Workspace\chrome-sts-canary\" /E /I

:: Launch
"D:\@Workspace\chrome-sts-canary\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="D:\@Workspace\chrome-sts-profile" ^
  --no-first-run
```

### Evaluation

| Factor | Detail |
|--------|--------|
| Size | ~453 MB browser + ~15 MB profile |
| Setup time | 5 minutes |
| Auto-updates | No — recopy from installed Canary manually |
| Extension support | 100% — identical to Chrome |
| Stability | Proven — tested and working |
| Google bloat | Yes — Hangouts, Translate, telemetry |

### Pros
- Zero download, already installed
- Guaranteed to work (just tested)
- Can copy to laptop via USB
- No dependency on external projects

### Cons
- No auto-updates — manual recopy needed
- Canary channel = occasional experimental bugs
- 453 MB per copy
- Google telemetry active

---

## Phase B: Chromium Portable via chrlauncher (Future)

Download a clean Chromium build via chrlauncher. Truly portable, auto-updates.

### Setup

```
1. Download chrlauncher: github.com/nicedoc/chromium-portable
2. Extract to D:\@Workspace\chrome-sts-chromium\
3. Run chrlauncher.exe — it downloads latest Chromium (~150 MB)
4. Launch with same --user-data-dir and --remote-debugging-port flags
```

### Evaluation

| Factor | Detail |
|--------|--------|
| Size | ~200 MB browser + ~15 MB profile |
| Setup time | 10 minutes (includes download) |
| Auto-updates | Yes — chrlauncher fetches latest on launch |
| Extension support | 99% — no Chrome Web Store direct (sideload .crx) |
| Stability | Needs testing with STS extensions |
| Google bloat | None — clean Chromium |

### Pros
- Auto-updates to latest stable Chromium
- Lighter (~200 MB vs 453 MB)
- No Google telemetry/tracking
- Truly portable — no registry, no AppData
- Best for laptop transfer scenario

### Cons
- Needs internet for initial download
- No Widevine DRM (irrelevant for Grok/Gemini)
- No direct Chrome Web Store — must sideload Automa .crx
- Depends on chrlauncher maintainer
- Untested with STS extensions

---

## Phase C: Laptop Worker (When Scaling)

Move the automation browser to a dedicated laptop.

```
Main PC (Flask :5050)  ◄──── WiFi/LAN ────►  Laptop (Chrome worker)
  bind 0.0.0.0:5050                            Extensions connect to
  pipeline orchestrator                         ws://PC_LAN_IP:5050
  monitoring                                    Runs 24/7, lid closed
```

### Setup tasks
| Task | Effort |
|------|--------|
| Copy portable browser to laptop (USB) | 10 min |
| Install extensions + log into accounts | 15 min |
| Change extension WS URLs from localhost to LAN IP | 5 min |
| Bind Flask to 0.0.0.0 in config | 5 min |
| Test full pipeline cross-machine | 30 min |
| Set Chrome to auto-start on laptop boot | 15 min |
| Wake-on-LAN for remote start (optional) | 30 min |

### Laptop requirements
- WiFi connected to same LAN as main PC
- Chrome Canary or Chromium Portable installed
- Extensions loaded + accounts logged in
- Power settings: never sleep when plugged in

---

## Comparison Matrix

| Factor | A: Copy Canary | B: Chromium Portable | C: Laptop |
|--------|:-:|:-:|:-:|
| Setup effort | 5 min | 10 min | 1 hr |
| Cost | Free | Free | Free (have laptop) |
| Auto-updates | No | Yes | Depends on A or B |
| Extension compat | 100% | 99% | Same as chosen browser |
| Isolation from daily browsing | Yes | Yes | Full hardware isolation |
| Parallel with dev work | Shares CPU/RAM | Shares CPU/RAM | Independent |
| Scale to 20+ videos/day | Limited by PC resources | Limited by PC resources | Dedicated resources |
| Laptop transferable | USB copy | USB copy | Already there |

---

## Decision

| Date | Choice | Reason |
|------|--------|--------|
| 2026-03-25 | Phase A (Copy Canary) | Already tested, works now, zero friction |
| TBD | Phase B (Chromium) | When updating Canary becomes annoying |
| TBD | Phase C (Laptop) | When scaling past 10 videos/day or need PC resources free |

---

## Launcher

Script: `bin/launch-canary.bat`

Pre-flight checks:
1. Chrome Canary executable exists
2. Profile directory exists (auto-creates if missing)
3. Profile initialized (Default/Preferences exists)
4. Grok extension detected in Preferences
5. Gemini extension detected in Preferences
6. Automa extension detected in Preferences
7. Cookie store exists (login sessions)

Launches with `--remote-debugging-port=9222` for CDP access.
