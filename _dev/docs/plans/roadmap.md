# ScriptToScene Studio — Roadmap

> Merged from: project roadmap, phased improvement plan, and quality improvement plan.

---

## Infrastructure Roadmap

### Phase 1 — Lock the Door (Week 1)
Goal: Prevent unauthorized access and credit burn

| # | Task | Effort | Impact |
|---|------|--------|--------|
| 1 | API key auth middleware — shared key in .env, @app.before_request | 30 min | Blocks unauthorized access to all 76 routes |
| 2 | Flask-Limiter on TTS, export, image gen routes | 20 min | Prevents unlimited credit burn |
| 3 | Fix CORS — restrict to known origins | 15 min | Blocks cross-origin abuse |
| 4 | Remove .env from repo, add .env.example | 15 min | Protects API keys |

Exit criteria: No public endpoint, rate-limited expensive ops, secrets secured.

### Phase 2 — Stop Silent Failures (Weeks 2–3)
Goal: Make the pipeline resilient and debuggable

| # | Task | Effort | Impact |
|---|------|--------|--------|
| 5 | Webhook retry — n8n calls with 3 retries + exponential backoff | 30 min | Scene generation stops failing silently |
| 6 | Image download retry + error propagation in Asset Pipeline | 1 hr | Asset pipeline stops losing images |
| 7 | Export error recovery — clean up orphaned jobs, report failures | 1 hr | Users know when export fails and why |
| 8 | Input validation (Pydantic) on top 10 routes | 2–3 hrs | Rejects bad data at the boundary |
| 9 | Path traversal / subprocess injection hardening | 1 hr | Closes medium-severity security gaps |

Exit criteria: No silent failures, bad input rejected, security holes patched.

### Phase 3 — Prove It Works (Weeks 3–4)
Goal: Automated quality gate, catch regressions

| # | Task | Effort | Impact |
|---|------|--------|--------|
| 10 | Pytest for TTS normalization (contractions, dates, units, ordinals) | 1 hr | Catches 80% of regressions in most complex module |
| 11 | Pytest for Segmentation (filler detection, duration targets, chapter breaks) | 1 hr | Second most logic-dense module |
| 12 | Integration tests for core API routes (project CRUD, pipeline trigger) | 2 hrs | Validates happy paths |
| 13 | CI pipeline — GitHub Actions: ruff lint + pytest on push | 1 hr | Automated quality gate |

Exit criteria: Core logic tested, CI blocks broken commits.

### Phase 4 — Make It Deployable (Weeks 4–5)
Goal: Anyone can run it, state survives restarts

| # | Task | Effort | Impact |
|---|------|--------|--------|
| 14 | Dockerfile + docker-compose | 30 min | Reproducible single-command setup |
| 15 | Persistent job state — move in-memory dicts to SQLite or Redis | 2–3 hrs | Jobs survive server restart |
| 16 | CSP headers + HTTPS config | 30 min | Closes remaining security items |
| 17 | README with setup instructions, env vars, architecture diagram | 1 hr | Others can onboard |

Exit criteria: docker compose up works, state persists, documented.

### Phase 5 — Production Polish (Weeks 6–8)
Goal: Monitoring, full auth, operational maturity

| # | Task | Effort | Impact |
|---|------|--------|--------|
| 18 | Sentry or equivalent error tracking | 1 hr | Know when things break in the wild |
| 19 | Metrics / health endpoint | 1 hr | Uptime monitoring |
| 20 | Full user auth (JWT or session-based) replacing API key | 3–4 hrs | Multi-user support |
| 21 | SQLite migration from JSON file storage | 3–4 hrs | Eliminates race conditions |
| 22 | Music module hardening — duration validation, metadata | 1 hr | Completes weakest module |
| 23 | DNA Analysis — confidence scores, validation | 2 hrs | Completes analysis pipeline |

Exit criteria: Production-grade — monitored, multi-user, persistent, fully tested.

### Infrastructure Summary

| Phase | Focus | Timeline | Score After |
|-------|-------|----------|-------------|
| 1 — Lock the Door | Security | Week 1 | ~70% |
| 2 — Stop Silent Failures | Reliability | Weeks 2–3 | ~75% |
| 3 — Prove It Works | Testing & CI | Weeks 3–4 | ~80% |
| 4 — Make It Deployable | Deployment | Weeks 4–5 | ~85% |
| 5 — Production Polish | Ops & scale | Weeks 6–8 | ~95% |

---

## Prompt & Asset Quality Improvement

### Priority Matrix

| Priority | Problem | Impact | Effort |
|----------|---------|--------|--------|
| P0 | Schema mismatch across planner/writer/validator | Breaks output validity | Medium |
| P0 | Null `text_content` in all scenes | Missing captions/overlays | Low |
| P1 | Style drift within projects | Inconsistent visual output | Medium |
| P1 | No character consistency across scenes | Breaks narrative coherence | Medium |
| P2 | Weak variant selection (default index) | Sub-optimal scene picks | Medium |
| P2 | Lazy final scenes ("blurred background") | Low-quality endings | Low |
| P2 | No motion/camera direction in prompts | Static slideshow feel | Medium |
| P3 | Duplicate scene indices in output | Minor data integrity | Low |

### Quality Phase 1 — Schema & Data Integrity
- Define canonical schema contract (single source of truth for enums)
- Fix null `text_content`, fix duplicate scene indices
- Patch all prompt files to unified contract

### Quality Phase 2 — Visual Consistency (Style & Character Lock)
- Add `style_anchor`, `forbidden_styles`, `style_keywords_lock` per run
- Add `character_signature`, `recurring_motif`, `palette_lock` per project
- Fix lazy final scenes (ban "blurred background" patterns)

### Quality Phase 3 — Smart Selection (Variant Scoring)
- Multi-criteria variant scoring (semantic match, style consistency, continuity, shot diversity)
- Shot-type diversity enforcement (no 3+ consecutive same-shot-type)
- A/B evaluation harness

### Quality Phase 4 — Motion & Video
- Motion generation stage for video scenes
- Role-aware motion presets (hook=fast, buildup=controlled, peak=strongest)
- Camera direction fields: `camera_movement`, `movement_intensity`, `movement_direction`

### Quality Phase 5 — Workflow Polish
- Prompt file cleanup (archive deprecated, single active per role)
- Pipeline observability (per-stage timing, quality scores in UI)
- Template management improvements

### Quality Execution Summary

| Phase | Focus | Dependencies |
|-------|-------|-------------|
| Q1 | Schema & Data Integrity | None |
| Q2 | Visual Consistency | Q1 |
| Q3 | Smart Selection | Q2 |
| Q4 | Motion & Video | Q1 |
| Q5 | Workflow Polish | Q1–Q3 |

---

## Provider Plans

### Kie AI Image Generation Provider
- Direct Python API implementation (not via n8n)
- `POST /api/v1/jobs/createTask` → poll → download
- Files: `config.py`, `studio/assets/providers/kie_ai.py`, `studio/assets/routes.py`

### Midjourney --cref Character Reference Chaining
- Chain `--cref <previous_scene_url>` in Automa typing loop
- `waitForSceneImages()` polls MJ page until images appear
- UI toggle for `--cref chain` in Automa synchronizer settings

---

## Session Log (2026-03-09)

### Features Implemented
- Style template display across all modules (colored dot + bold name)
- Scene generator: clear on regen/style change, race fix, style sync
- Pipeline: auto-scenes toggle, dynamic style dropdown, style in history
- Video Editor: style display, Web Audio GainNode (300% boost), track persistence
- Clear All Projects: full STATE reset across all modules

### Bugs Fixed
- Pipeline using wrong webhook URL
- Style showing as raw prompt text for old projects
- Race condition: history rendering before templates loaded
- `_scnTemplates` not populated when pipeline init runs before scenes.js

### Prompt.py Upgrade Priorities
1. Continuity lock fields + enforcement
2. Style lock (prefix + fixed keywords)
3. Hard structural gates with rewrite requirement
4. Motion triplet requirement for all video prompts
