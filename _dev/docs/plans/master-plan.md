# ScriptToScene Studio — Master Plan

**Created:** 2026-03-25
**Status:** Active — update monthly

---

## WHERE WE ARE (Day 29)

### What's Built
- Full pipeline: Story → TTS → Alignment → Segmentation → Scenes → Storyboard → Animation → Export
- 22 niche presets with duration, voice, speed, visual style, story tone
- Auto-queue: batch generate videos from presets
- Chrome extensions: Grok (images + video), Gemini (images)
- Vue 3 frontend with 11 feature modules
- Video editor with timeline, captions, overlays, SFX, export
- TTS with Kokoro + misaki G2P, voice blending, pronunciation overrides

### What's Not Built
- Zero monetization infrastructure (no auth, payments, analytics)
- No publishing pipeline (videos stay on disk)
- No content performance tracking
- No Docker / deployment
- No automated tests running in CI
- No long-form video support (max 180s)

### Current Bottlenecks
1. **Grok rate limits** — 1 image every ~20s, kills batch speed
2. **Memory leaks** — TTS OOM on long queues (gc.collect fix is a band-aid)
3. **PipelinePage.vue** — 3,800 lines, hard to maintain
4. **No fallback** when Grok/Gemini are down

---

## PHASE 1: PRODUCTION MODE (Week 5-6)
> Goal: Produce and publish 5 videos/day reliably

### 1A. Dedicated Automation Browser
| Task | Effort | Status |
|------|--------|--------|
| Chrome Canary launcher script | 15 min | Done |
| Install extensions + log into Grok/Gemini | 15 min | TODO |
| Test full pipeline through Canary | 30 min | TODO |
| Add auto-launch Canary from Flask startup (optional) | 30 min | TODO |

### 1B. Job Queue Reliability
| Task | Effort |
|------|--------|
| Add "Run All Saved" button for saved stories | 1 hr |
| Auto-retry failed pipeline jobs (max 2 retries) | 2 hrs |
| Pipeline failure notification (sound + toast) | 30 min |
| Memory cleanup between queue jobs (gc + del arrays) | Done |
| Cooldown timer between jobs (respect Grok rate limits) | 1 hr |

### 1C. Long-Form Video Support
| Task | Effort |
|------|--------|
| Extend max duration to 900s (15 min) | 30 min |
| Chain story segments into multi-part narrative | 3 hrs |
| Add chapter markers to export | 2 hrs |
| Long-form preset tier: 8-12 min YouTube videos | 1 hr |

### 1D. Publishing Pipeline (New Module)
| Task | Effort |
|------|--------|
| YouTube upload via API (OAuth2 + youtube-dl/yt-dlp) | 4 hrs |
| TikTok upload via unofficial API or Automa | 3 hrs |
| Auto-generate title, description, tags from story metadata | 2 hrs |
| Schedule posts (queue with publish times) | 2 hrs |
| Multi-channel support (map niche → channel) | 1 hr |

**Phase 1 Exit Criteria:** 5 videos published/day with one command.

---

## PHASE 2: MULTI-CHANNEL SCALING (Week 7-10)
> Goal: 3-5 niche channels producing daily content, first revenue

### 2A. Content Strategy Engine
| Task | Effort |
|------|--------|
| Niche performance tracker (views, CPM, retention per preset) | 3 hrs |
| A/B test mode: same story, 2 visual styles → compare | 2 hrs |
| Content calendar: daily schedule per channel | 2 hrs |
| Seasonal niche rotation config | 1 hr |
| Hook library: top-performing opening lines per niche | 2 hrs |

### 2B. New High-CPM Niches
| Niche | Est. CPM | Preset Work |
|-------|----------|-------------|
| Personal Finance | $8-15 | 2 presets (cinematic + stickman) |
| AI/Tech Explainers | $5-10 | 2 presets (cyberpunk + clean) |
| History Deep Dives | $4-8 | 2 presets (cinematic + noir) |
| Health/Wellness | $6-12 | 1 preset (wholesome) |
| Unsolved Mysteries | $3-6 | 1 preset (noir) |

### 2C. Content Multiplication
| Task | Effort |
|------|--------|
| Clip extractor: auto-cut 3-5 shorts from 1 long-form | 4 hrs |
| Aspect ratio presets: 16:9 → 9:16 auto-crop | 2 hrs |
| Blog post generator from script (SEO stacking) | 3 hrs |
| Thumbnail A/B variant generator | 2 hrs |

### 2D. Image Provider Fallbacks
| Provider | Type | Cost | Status |
|----------|------|------|--------|
| Grok | Free, rate-limited | $0 | Active |
| Gemini | Free, rate-limited | $0 | Active |
| Replicate (FLUX) | API, fast | ~$0.003/image | TODO |
| Together.ai | API, fast | ~$0.002/image | TODO |
| Local SDXL | Free, slow | $0 (GPU needed) | Future |

Add fallback chain: Grok → Gemini → Replicate → fail gracefully.

**Phase 2 Exit Criteria:** 3 channels, 15 videos/day, $300-1K/mo ad revenue.

---

## PHASE 3: MONETIZATION LAYERS (Week 11-16)
> Goal: Multiple revenue streams beyond ad revenue

### 3A. Affiliate Integration
| Task | Effort |
|------|--------|
| Affiliate link database (niche → product → link) | 2 hrs |
| Auto-insert affiliate links in video descriptions | 1 hr |
| Track click-through per niche per video | 2 hrs |
| Top affiliates: Audible, Skillshare, NordVPN, Amazon | Research |

### 3B. Digital Products
| Product | Price | Effort |
|---------|-------|--------|
| Niche preset packs (Gumroad) | $19-49 | 2 hrs per pack |
| "Faceless YouTube Starter Kit" course | $97 | 2 weeks |
| Custom video production (Fiverr) | $50-200/order | 0 (use your tool) |
| SaaS access (monthly) | $29-99/mo | See Phase 4 |

### 3C. Email List / Lead Magnet
| Task | Effort |
|------|--------|
| Lead magnet: "50 Viral Story Hooks" PDF | 2 hrs |
| Link in every video description | 30 min |
| Email sequence → upsell preset packs / course | 4 hrs |

**Phase 3 Exit Criteria:** $2-5K/mo from ads + affiliates + products.

---

## PHASE 4: PRODUCTIZE AS SAAS (Month 4-6)
> Goal: Others pay to use ScriptToScene

### 4A. Infrastructure (Prerequisites)
| Task | Effort | Priority |
|------|--------|----------|
| Docker + docker-compose | 2 hrs | P0 |
| SQLite → PostgreSQL for multi-user | 4 hrs | P0 |
| User auth (JWT or Clerk) | 4 hrs | P0 |
| Stripe payments + usage metering | 4 hrs | P0 |
| Rate limiting per user tier | 2 hrs | P0 |
| HTTPS + CORS lockdown | 1 hr | P0 |
| Landing page | 1 day | P1 |
| Onboarding flow | 1 day | P1 |

### 4B. SaaS Tiers
| Tier | Price | Limits |
|------|-------|--------|
| Free | $0 | 3 videos/day, watermark, shorts only |
| Creator | $29/mo | 20 videos/day, no watermark, all niches |
| Pro | $79/mo | Unlimited, API access, custom presets, long-form |
| Agency | $199/mo | Multi-channel, white-label, priority support |

### 4C. Competitive Moat
| Feature | Pictory | InVideo | Opus Clip | ScriptToScene |
|---------|---------|---------|-----------|----------------|
| AI story generation | No | No | No | Yes |
| Niche presets | No | Generic | No | 22+ specialized |
| Full pipeline automation | No | Partial | Clip only | End-to-end |
| Self-hosted option | No | No | No | Yes |
| Price | $23/mo | $25/mo | $15/mo | $29/mo |

**Your edge:** Full story-to-publish pipeline. Others only do one piece.

**Phase 4 Exit Criteria:** Live SaaS, 50+ paying users, $5-10K MRR.

---

## PHASE 5: SCALE (Month 6-12)
> Goal: Sustainable business

### 5A. Advanced Pipeline
| Feature | Impact |
|---------|--------|
| AI voice cloning (custom voices per channel) | Brand identity |
| Real-time trend detection → auto-generate trending topics | First-mover content |
| Multi-language auto-dub (translate + TTS in 5 languages) | 5x audience |
| Thumbnail AI (auto-generate from first frame + text) | Higher CTR |

### 5B. Distribution
| Channel | Action |
|---------|--------|
| YouTube API | Auto-upload, schedule, SEO optimization |
| TikTok | Auto-post via automation |
| Instagram Reels | Repurpose shorts |
| Facebook Reels | Repurpose shorts |
| X/Twitter | Clip highlights |
| Blog (WordPress) | SEO stacking from scripts |

### 5C. Team / Delegation
| Role | When | Cost |
|------|------|------|
| VA for channel management | $500/mo revenue | $300-500/mo |
| Freelance editor for quality passes | $1K/mo revenue | Per-video |
| Marketing (landing page, ads) | SaaS launch | $500-1K/mo |

**Phase 5 Exit Criteria:** $10-20K/mo, semi-automated, team support.

---

## LAPTOP WORKER PLAN

### Phase A: Chrome Canary on Main PC (Now)
- Dedicated profile, extensions loaded
- Same machine, separate browser
- Good for: testing, 5-10 videos/day

### Phase B: Dedicated Laptop (When Scaling)
```
Main PC (Flask server)  ◄──── WiFi/LAN ────►  Laptop (Chrome worker)
  bind 0.0.0.0:5050                              Extensions connect to
  pipeline orchestrator                           ws://PC_IP:5050
  content calendar                                Grok + Gemini logged in
  monitoring dashboard                            Runs 24/7, lid closed
```

| Setup Task | Effort |
|------------|--------|
| Install Chrome Canary on laptop | 15 min |
| Install extensions + log into accounts | 15 min |
| Change extension WS URLs to LAN IP | 5 min |
| Bind Flask to 0.0.0.0 | 5 min |
| Test pipeline cross-machine | 30 min |
| Auto-start Chrome on laptop boot | 15 min |
| Wake-on-LAN for remote start (optional) | 30 min |

### Phase C: Cloud Worker (When Profitable)
- VPS ($15-30/mo) running Chrome + extensions
- Multiple instances = parallel generation
- Different Grok/Gemini accounts per instance = bypass rate limits

---

## CODE HEALTH (Ongoing)

### Cleanup Backlog
| Task | Effort | Impact |
|------|--------|--------|
| Delete `studio/dna/` (empty) | 1 min | Clean tree |
| Delete `studio/scenes/` (empty, renamed) | 1 min | Clean tree |
| Delete `assets/niche-analyzer/` (unused) | 1 min | Clean tree |
| Split PipelinePage.vue (3,800 lines) | 3 hrs | Maintainability |
| Extract editor export logic | 2 hrs | Maintainability |
| Merge timing/ + segmenter/ | 2 hrs | Simpler architecture |
| Merge thumbnails/ into assets/ | 1 hr | Simpler architecture |
| Add 1 integration test (story → export) | 2 hrs | Confidence |
| GitHub Actions: lint on push | 1 hr | Quality gate |

### Architecture Principles
1. **No feature without a revenue path** — ask "does this make money?"
2. **70/30 rule** — 70% producing content, 30% building tool
3. **One commit = one change** — atomic, reversible
4. **Test the pipeline, not the units** — 1 end-to-end test > 50 unit tests
5. **Ship, measure, iterate** — don't perfect in isolation

---

## DECISION LOG

| Date | Decision | Reason |
|------|----------|--------|
| 2026-02-24 | Flask + Vue 3 SPA | Fast to build, Python for ML/TTS integration |
| 2026-03-10 | Vue migration from vanilla JS | Vanilla couldn't scale, cost 1 week |
| 2026-03-15 | Chrome extensions for Grok/Gemini | No API available, browser automation required |
| 2026-03-22 | Automa for asset sync | Visual workflow builder, non-code automation |
| 2026-03-24 | Gemini as second image provider | Reduce Grok dependency, faster rate limits |
| 2026-03-25 | Chrome Canary as dedicated browser | Separate from daily browsing, persist sessions |
| 2026-03-25 | Duration per preset | Shorts vs long-form optimization |

---

## MONTHLY REVIEW CHECKLIST

Run this on the 1st of each month:

- [ ] How many videos published this month?
- [ ] Total views across all channels?
- [ ] Revenue (ads + affiliates + products)?
- [ ] Which niche performed best/worst?
- [ ] Pipeline success rate (% of jobs completed without error)?
- [ ] Biggest time waster this month?
- [ ] What feature would have saved the most time?
- [ ] Update this plan with new decisions and learnings
