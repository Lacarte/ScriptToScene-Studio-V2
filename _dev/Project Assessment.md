# ScriptToScene Studio — Project Assessment

> Last updated: March 8, 2026 | ~20,000 LOC | 51 commits | Solo developer

---

## Overall Score: ~65% Production-Ready

| Dimension              | Score  |
|------------------------|--------|
| Feature completeness   | 80-85% |
| Architecture & code    | 80%    |
| Reliability & errors   | 55%    |
| Security & auth        | 15%    |
| Testing & CI           | 5%     |
| Deployment & ops       | 20%    |

---

## Stack Overview

- **Backend:** Flask + 10 Blueprints, 76 routes, file-based JSON storage
- **Frontend:** Vanilla JS SPA (9 tabs), Tailwind CSS, no build step
- **Pipeline:** TTS (Kokoro ONNX) → Alignment (Whisper) → Segmentation → Scenes (n8n) → Assets (Kie AI/MJ) → Captions → Editor → Export (FFmpeg)
- **External deps:** ffmpeg, n8n webhooks, Kie AI API, Automa (browser automation)

---

## Module Maturity

### Production-Ready

| Module | Score | Why |
|--------|-------|-----|
| TTS (Kokoro) | 9/10 | Streaming, multi-voice, blending, normalization, loudnorm, history |
| Force Alignment | 8/10 | Whisper + Stable-TS, word-level timing, multi-format input |
| Segmentation | 7/10 | Filler detection, tunable duration targets, chapter breaks |
| Config & Logging | 8/10 | Centralized config.py, loguru with rotation, structured output |
| Architecture | 8/10 | Clean blueprint separation, modular, readable, conventional commits |
| Pipeline Orchestration | 8/10 | SSE progress streaming, job tracking, chapter-based generation |
| Frontend UI | 7/10 | 9 tabs, dark theme, toasts, karaoke playback, canvas editor |

### Developing (Works, Needs Hardening)

| Module | Score | Gap |
|--------|-------|-----|
| Scene Generation | 6/10 | No retry on webhook failure, hard 120s timeout, no fallback |
| Asset Pipeline | 6/10 | Automa dependency, no download retry, fragile state machine |
| Timeline Editor | 6/10 | Functional, persistence recently fixed, overlay support added |
| Video Export | 5/10 | Core works (motion, overlay, captions, BGM) but weak error recovery |
| DNA Analysis | 5/10 | Extractors work but no validation, no confidence scores |
| Music | 4/10 | Basic upload/serve only, no duration validation |

---

## What's Blocking Production

### Critical — Blocks Real Users

1. **No Authentication**
   Every endpoint is public. Anyone with your URL can generate unlimited TTS, burn Kie AI credits, delete all projects. Single biggest blocker.

2. **No Rate Limiting**
   TTS, image generation, and export are expensive operations with zero throttling.

3. **No Input Validation**
   No schema validation on request bodies. Unlimited text length. No file size enforcement beyond Flask's 50MB global.

### Important — Blocks Reliability

4. **Zero Tests**
   0% coverage. TTS normalization has dozens of regex rules, segmentation has tunable algorithms — one regression cascades silently.

5. **No Retry/Resilience**
   Webhook calls to n8n fail silently. Image downloads fail silently. Export errors leave orphaned jobs.

6. **In-Memory Job State**
   Pipeline and asset jobs stored in Python dicts. Server restart = all state lost.

### Nice to Have — Blocks Scaling

7. **File-Based Storage** — JSON on disk works for 1-2 users but race conditions possible. SQLite would be a simple upgrade.
8. **No Docker** — Manual setup only, not reproducible.
9. **No CI/CD** — No automated linting, testing, or deployment.
10. **No Monitoring** — No metrics, alerting, or error tracking (Sentry).

---

## Security Concerns

| Issue | Severity | Detail |
|-------|----------|--------|
| No authentication | HIGH | All 76 routes are public |
| API keys in .env (committed) | HIGH | Kie AI key visible to anyone with repo access |
| No HTTPS | HIGH | Dev mode only |
| CORS wide open | MEDIUM | `CORS(app)` allows any origin |
| Path traversal risk | MEDIUM | Some routes don't validate folder names |
| Subprocess injection | MEDIUM | User-influenced filenames passed to ffmpeg |
| No CSP headers | LOW | XSS possible |

---

## Timeline Estimate

*Based on ~51 commits, 1-2 features/day when active.*

| Milestone | ETA | What It Means |
|-----------|-----|---------------|
| Personal tool | **Now** | Works end-to-end on your machine |
| Shareable demo | **2-3 weeks** | Basic auth, input validation, Docker, README |
| Beta (small team) | **1-2 months** | Tests, retry logic, rate limiting, job queue |
| Production-grade | **3-4 months** | Full auth, monitoring, CI/CD, error tracking, docs |

---

## Recommended Next Steps (in order)

| # | Task | Effort | Impact |
|---|------|--------|--------|
| 1 | **API key auth middleware** — single shared key in `.env`, checked via `@app.before_request` | 30 min | Blocks unauthorized access |
| 2 | **Flask-Limiter** — `@limiter.limit("5/minute")` on TTS, export, image gen routes | 20 min | Prevents credit burn |
| 3 | **Pytest for TTS normalization** — test contractions, dates, units, ordinals, edge cases | 1 hour | Catches 80% of regressions |
| 4 | **Webhook retry** — wrap n8n calls with 3 retries + exponential backoff | 30 min | Pipeline resilience |
| 5 | **Dockerfile + docker-compose** — straightforward with current requirements.txt | 30 min | Reproducible deployment |
| 6 | **Persistent job state** — move job dicts to SQLite or Redis | 2-3 hours | Survives restarts |
| 7 | **CI pipeline** — GitHub Actions: ruff lint + pytest on push | 1 hour | Quality gate |
| 8 | **Input validation** — Pydantic schemas for top 10 most-used routes | 2-3 hours | Security + reliability |

---

## Bottom Line

You've built a genuinely impressive full AI video pipeline — from text to final MP4 — with clean modular architecture. The gap isn't features, it's **operational maturity**. The features work; what's missing is the infrastructure to make them work reliably for others. The good news: your clean architecture makes every item above straightforward. None require rearchitecting anything.
