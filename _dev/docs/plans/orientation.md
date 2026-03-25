# ScriptToScene Studio — Current Orientation

**Date:** 2026-03-25
**Mode:** OPERATOR (not builder)
**Rule:** 70% publishing content, 30% improving tool

---

## THE SHIFT

You are no longer in build mode. The pipeline works. The presets work. The
automation browser is ready. The only thing missing is **published videos
generating revenue**.

Every decision from now on answers one question:

> **Does this help me publish a winning video this week?**

If no, it waits.

---

## THIS WEEK (Mar 25-31): First 10 Videos

### Day 1-2: Setup & First Batch
- [ ] Finish Canary: install extensions, log into Grok + Gemini
- [ ] Run 1 full pipeline test through Canary (story → export)
- [ ] Produce 3 videos: 1 psychology, 1 horror, 1 biblical
- [ ] Create YouTube channel (faceless, niche name)
- [ ] Create TikTok account (or buy French account if needed)

### Day 3-4: Publish & Produce More
- [ ] Upload first 3 videos to YouTube Shorts + TikTok
- [ ] Produce 4 more videos across the 3 niches
- [ ] Upload same day — Google Drive → phone → post from mobile
- [ ] Log each video in spreadsheet: niche, hook, duration, platform, date

### Day 5: Produce Final Batch
- [ ] Produce 3 more videos (total = 10 for the week)
- [ ] Upload all
- [ ] Friday cleanup: delete dead code (dna/, scenes/, niche-analyzer/)

### Day 6-7: Rest + Review
- [ ] Check views after 48 hours
- [ ] Note which hooks got traction
- [ ] Decide which niche to double down on

### Exit criteria: 10 videos published across 2 platforms

---

## NEXT WEEK (Apr 1-7): Measure & Optimize

### Analytics Setup (2 hours max)
- [ ] Build simple scoreboard into the app:
  - niche, date, platform, title, hook, views_24h, views_7d
- [ ] Or: use a Google Sheet if faster — don't over-engineer this

### Production Cadence
- [ ] 1 video per niche per day = 3 videos/day
- [ ] Same video → YouTube + TikTok + Facebook = 9 posts/day
- [ ] Use auto-queue with preset rotation

### Kill Decisions
- After 7 days, for each niche:
  - Average views > 1K → SCALE (increase to 2/day)
  - Average views 200-1K → KEEP (maintain 1/day)
  - Average views < 200 → KILL (drop niche, try new one)

### Exit criteria: data on 3 niches, 1 clear winner identified

---

## WEEK 3 (Apr 8-14): Revenue Infrastructure

### Affiliate Setup
- [ ] Audible affiliate link (fits psychology, biblical, horror)
- [ ] Skillshare or relevant course platform per niche
- [ ] Add links to every video description template

### Multi-Platform Delivery
- [ ] Google Drive auto-upload after export (build this)
- [ ] Standardized filename: `{niche}_{date}_{n}.mp4`
- [ ] Description template per niche (title, tags, hashtags, affiliate link)

### First Paid Gig
- [ ] List on Fiverr: "30 viral shorts in 24 hours"
- [ ] Use ScriptToScene as your production engine
- [ ] Price: $50-100 per package

### Exit criteria: affiliate links live, first Fiverr order received or listed

---

## WEEK 4 (Apr 15-21): Double Down

### Scale Winning Niche
- [ ] 2 videos/day in winning niche
- [ ] A/B test: same story, 2 different visual styles
- [ ] Build hook library from your best performers

### First Revenue Check
- [ ] Total views across all videos
- [ ] Any affiliate clicks?
- [ ] Any Fiverr inquiries?
- [ ] YouTube monetization eligibility progress (1K subs, 4K watch hours)

### Niche Expansion
- [ ] If psychology won: add personal finance preset (high CPM)
- [ ] If horror won: add true crime preset
- [ ] If biblical won: add faith/testimony preset

### Exit criteria: clear revenue signal (even $1) or clear pivot data

---

## TOOL IMPROVEMENTS (Only When Blocked)

These are allowed ONLY if you hit them during production:

| Blocker | Fix | Max Time |
|---------|-----|----------|
| Pipeline crashes mid-batch | Auto-retry (2 retries max) | 2 hrs |
| Can't transfer to phone fast | Google Drive upload | 2 hrs |
| Don't know what to make | Viral Scout MVP | 4 hrs |
| Queue runs out of memory | Already fixed (gc.collect) | Done |
| Grok is down | Switch to Gemini (already supported) | 0 |

If it's not on this list, it waits until the monthly review.

---

## WHAT NOT TO DO

- Do not refactor PipelinePage.vue this month
- Do not build SaaS infrastructure (auth, payments, Docker)
- Do not add new visual styles or presets unless a niche test demands it
- Do not polish the editor beyond what's needed to export
- Do not build a landing page
- Do not spend more than 30 min on any single bug

---

## MONTHLY REVIEW (April 1st)

Answer these honestly:

1. How many videos published?
2. Total views?
3. Revenue (ads + affiliate + services)?
4. Which niche won?
5. What blocked production the most?
6. What feature would have saved the most time?
7. Am I still following the 70/30 rule?

Then update this orientation for the next month.

---

## DOCS STATUS

### Active (use these)
| Doc | Purpose |
|-----|---------|
| `plans/orientation.md` | **This file** — weekly action plan |
| `plans/master-plan.md` | Long-term 5-phase roadmap |
| `plans/automation-browser-plan.md` | Chrome Canary → laptop → cloud |
| `plans/niche-style-architecture.md` | Niche preset system design (done) |
| `content-monetization-strategy.md` | Creator playbook for TikTok/FB/YT |
| `project-progression-report-v2.md` | Latest project assessment |
| `security-audit.md` | Vulnerability list (fix before SaaS) |
| `prompt-rules.md` | Scene prompt philosophy |
| `tts-pronunciation-guide.md` | TTS IPA overrides |
| `phonetic-stress-guide.md` | Misaki stress syntax |
| `analysis.md` | Image quality analysis (Kie AI) |
| `plans/test-instructions.md` | How to run tests |

### Archived (historical reference only)
| Doc | Why archived |
|-----|-------------|
| `_archive/project-assessment.md` | Superseded by v2 report (pre-Vue, pre-presets) |
| `_archive/project-progression-report.md` | Superseded by v2 |
| `plans/_archive/roadmap.md` | Superseded by master-plan.md |
| `plans/_archive/init-plan.md` | Historical — project kickoff notes |
