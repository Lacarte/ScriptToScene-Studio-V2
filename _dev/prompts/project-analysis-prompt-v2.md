# Project Analysis Prompt

Use this prompt when you want a fresh, brutally honest project review grounded in both repo evidence and current market reality.

```md
Analyze my project `ScriptToScene-Studio` and give me a deep, honest, evidence-based report.

Important rules:

- Use the local repository as the primary source of truth for timeline, code quality, architecture, testing, and dead code.
- Use `git log`, file counts, hotspot files, test status, and current code structure as evidence.
- For market, monetization, viral-video strategy, platform policy, and creator-economy advice, use current official or primary web sources.
- Clearly separate:
  - measured facts from the repo
  - informed inferences
  - revenue scenarios or assumptions
- Do not pretend to know exact hours worked. Infer only from commit timing and activity windows.
- Be direct. Do not sugarcoat weak areas.

Cover these sections:

## 0. Executive Verdict
- Give 6-8 scores out of 10 for the project
- Summarize the current stage in 1-2 paragraphs
- State the biggest strength and biggest bottleneck

## 1. Time Spent and Progression
- First commit date, latest commit date, total span
- Active days, commit density, peak days, feature/fix/refactor mix
- Author contribution breakdown
- Major phases of the project
- What my development pattern says about me
- How my coding style and brainstorming process have improved
- What I still need to change in style and planning

## 2. Monetization and Profit Audit
- What this app is today: internal tool, service engine, content factory, or SaaS candidate
- Rank the best revenue paths by effort-to-income ratio
- What is missing for each path
- Which app improvements would most directly increase profit
- Revenue scenarios with clear labels that they are estimates, not guarantees

## 3. Rapid Bug Tracking and Fast Implementation
- Current test coverage and what it actually protects
- Whether the current workflow supports fast diagnosis
- Recommended bug-triage system for this project
- Recommended smoke tests and regression fixture strategy
- Practical system for fast implementation without chaos

## 4. Future of the App and Financial Growth
- 30-day, 60-90 day, and 6-12 month roadmap
- Best way the app can help me grow financially
- Biggest financial risk if I continue the current way

## 5. Niche Adaptation Strategy
- Assess current niche and style architecture
- Propose a scoring model for niches
- Explain a repeatable "10-video test"
- Suggest high-value niches to prioritize and low-value ones to deprioritize
- Include policy risk and sponsor fit, not just views

## 6. Viral Video Market Analysis
- Explain current market dynamics for AI-assisted short-form and longer-form creator content
- Show how to find viral opportunities using official trend and keyword tools
- Explain a practical reverse-engineering method for winners
- Show techniques for turning one idea into multiple revenue-bearing assets
- Explain how platform policy changes affect strategy

## 7. What to Remove, Archive, Freeze, or Split
- Modules or folders to delete now
- Experiments to archive unless they are active
- Areas to freeze instead of expanding
- Oversized files that should be split
- Architectural debt that matters most

## 8. Blind Spots I Probably Missed
- Analytics and feedback-loop gaps
- Policy and compliance risks
- Asset licensing or rights risks
- Operational and backup risks
- Burnout or focus risks
- Any other strategic blind spot you see

## 9. Sources
- List every external source used with links
- Prefer official or primary sources
- Keep quotes short and paraphrase when possible

## 10. The One Thing
- End with the single highest-leverage action I should take next

Format requirements:

- Use concise tables where helpful
- Use short paragraphs, not walls of text
- Be precise and concrete
- Save the final report to `_dev/docs/project-progression-report.md`
```
