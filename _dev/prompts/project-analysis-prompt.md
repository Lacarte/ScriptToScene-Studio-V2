# Project Analysis Prompt

Use this prompt to get a deep project analysis from Claude Code at any point in time. Copy-paste or reference it.

---

```
Analyze my project ScriptToScene-Studio and give me an honest, data-driven report. Use git log, file counts, and codebase structure as evidence.

Cover these sections:

## 1. TIMELINE & VELOCITY
- Total commits, commit frequency, sprint patterns
- Feature-to-fix ratio (how much time is spent building vs repairing?)
- Dead code ratio (code built then removed)
- Commit quality (are messages atomic or kitchen-sink?)
- What's my development pattern? Am I improving or repeating mistakes?

## 2. MONETIZATION AUDIT
- Current revenue potential: $0, SaaS-ready, or content-factory?
- Revenue paths ranked by effort-to-income ratio
- What's missing for each path? (auth, payments, deployment, etc.)
- CPM analysis by niche — which presets are optimized for money vs vanity?
- Time-to-first-dollar estimate for each path

## 3. BUG TRACKING & DEV WORKFLOW
- Current testing coverage (files, automation, CI)
- Error handling patterns — are failures caught or silent?
- What's the meantime-to-fix for recent bugs?
- Recommended lightweight tracking setup
- The 15-minute bug rule: reproduce → find → fix → verify

## 4. FINANCIAL GROWTH ROADMAP
- Phase 1 (month 2-3): content production targets
- Phase 2 (month 4-6): multi-channel scaling
- Phase 3 (month 6-12): productization
- Key metrics to track at each phase
- Risk factors and dependencies

## 5. NICHE STRATEGY
- Current preset inventory — gaps and overlaps
- Niche scoring framework (search volume, CPM, competition, production fit)
- The 10-Video Test methodology
- Seasonal rotation calendar
- Missing high-CPM niches to add

## 6. VIRAL MARKET ANALYSIS
- Where to find trending content (tools, sources, frequency)
- Hook formula breakdown
- Content multiplication techniques (1 video → 5 assets)
- Cross-platform arbitrage (YouTube, TikTok, Shorts)
- SEO stacking and affiliate layering

## 7. CODE CLEANUP
- Dead modules to remove
- Modules to consolidate
- Files that are too large and should be split
- Architecture debt that will slow future development

## 8. BLIND SPOTS
- What am I NOT thinking about that will bite me?
- Infrastructure risks (backups, deployment, dependencies)
- Market risks (platform changes, competition, AI policy)
- Process risks (burnout, feature creep, no testing)

## FORMAT
- Use tables for comparisons
- Use scores out of 10 for each area
- Be brutally honest — I want actionable truth, not encouragement
- End with "The One Thing" — the single highest-impact action I should take right now
- Save the full report to _dev/docs/project-progression-report.md
```
