# Self-Improving Pipeline Analyzer

## Context

As a pro short-form video editor targeting TikTok/Reels (< 60s), you want an automated system that runs the STS pipeline, scores the output quality, identifies issues, applies fixes, re-runs, and keeps only improvements. This closes the feedback loop without manual intervention.

**v1 scope**: TTS > Alignment > Segment > Scenes > Storyboard (stops before Animator). Full autopilot with rolling markdown report.

## File Structure

```
_dev/self_improver/
    __init__.py
    __main__.py         # Entry point (loads .env, calls loop.main)
    config.py           # Paths, thresholds, scoring weights, API URLs
    prepare.py          # Runs pipeline via HTTP, collects outputs from disk
    llm.py              # Gemini 2.5 Flash client (OpenRouter direct)
    train.py            # Heuristic checks + LLM scoring > unified scores
    program.py          # Fix generation, apply & compare, report append
    loop.py             # Main orchestrator + CLI entry point
    self-improvement-report.md   # Rolling report (auto-generated)
```

## Data Flow

```
loop.py (flexible entry points)
  |
  |  Entry A: --text "..."              > run full pipeline, then score
  |  Entry B: --project pp_ABC123      > skip pipeline, load from disk, then score
  |  Entry C: --project ... --resume-from scenes  > re-run from specific step
  |
  +-[1] prepare: get or create snapshot
  |      Option 1: run_and_collect(text, config)  > POST /api/pipeline/run, poll SSE, read disk
  |      Option 2: collect_snapshot(project_id)   > read existing output from disk (instant)
  |      Option 3: resume_and_collect(project_id, resume_from)  > re-run from step, reuse prior
  |      > PipelineSnapshot dataclass
  |
  +-[2] train.analyze(snapshot, steps=["tts","segments","scenes",...])
  |      Only runs checks for requested steps (default: all)
  |      Phase A: heuristic checks (zero cost) > issues + metrics
  |      Phase B: LLM scoring (Gemini 2.5 Flash) > subjective scores
  |      Merge > UnifiedScores
  |
  |  -- if --score-only: stop here, print report --
  |
  +-[3] program.generate_fixes(analysis, snapshot, steps=...)
  |      Only generates fixes for requested steps
  |      Determines earliest step that needs re-running (resume_from)
  |      > FixPlan {fixes, modified_config, resume_from}
  |
  +-[4] program.apply_and_compare(fix_plan, original)
  |      Re-run pipeline with resume_from (only re-runs changed steps)
  |      Re-analyze > compare scores
  |      Keep if improved, rollback if not
  |
  +-[5] program.append_report(...)
         Loop back to [3] if iterations remain and score improved
```

## Module Details

### `config.py`
- `BASE_URL = "http://localhost:5050"`
- Paths derived from `PROJECT_ROOT / "output" / {module}`
- Threshold dataclasses: `TTSThresholds`, `AlignmentThresholds`, `SegmentThresholds`, `SceneThresholds`, `StoryboardThresholds`, `CrossModuleThresholds`
- `ScoringWeights` (style=0.20, visual=0.20, narrative=0.25, sync=0.15, viral=0.20)

### `prepare.py`
- `run_pipeline(text, **kwargs)` > POST to `/api/pipeline/run` with `stop_after="storyboard"`
- `run_pipeline_resume(project_id, resume_from, **kwargs)` > POST with `resume_from` + `resume_project_id` (only re-runs from that step)
- `wait_for_completion(job_id)` > parse SSE stream, return terminal status
- `collect_snapshot(project_id)` > read all JSON outputs into `PipelineSnapshot` dataclass (instant, no pipeline run)
- `run_and_collect(text, **kwargs)` > convenience: run + wait + collect, retry once on error
- `resume_and_collect(project_id, resume_from, **kwargs)` > convenience: resume + wait + collect

### `llm.py`
- `call_llm(system_prompt, user_prompt)` > call OpenRouter directly (Gemini 2.5 Flash)
- Uses `OPENROUTER_API_KEY` from env (already in `.env`)
- JSON response mode, temperature 0.3
- Strips markdown fences from response before parsing

### `train.py` -- Heuristic Checks

| Module | Check | Formula | Threshold |
|--------|-------|---------|-----------|
| TTS | Words/sec | `words / duration` | 2.0-4.5 wps |
| TTS | Duration | raw seconds | 10-60s |
| Alignment | Zero-duration words | `zero_count / total * 100` | max 5% |
| Alignment | Word drift | `abs(word[i+1].begin - word[i].end) * 1000` | max 200ms |
| Segment | Hard_max break % | `hard_max_breaks / total * 100` | max 20% |
| Segment | Duration CV | `std(durations) / mean(durations)` | max 0.6 |
| Segment | Count | segment count | 4-25 |
| Scenes | Prompt length | `len(image_prompt)` | 40-500 chars |
| Scenes | Consecutive same shot | longest run of identical shot type | max 2 |
| Scenes | Required roles | must have `hook` + `peak` | mandatory |
| Storyboard | Error rate | `errors / total * 100` | max 10% |
| Cross | Scene-segment count | `abs(scene_count - segment_count)` | must be 0 |
| Cross | Timing drift | `abs(scene.segment_start - segment.start) * 1000` | max 500ms |

### `train.py` -- LLM Scoring (Gemini 2.5 Flash)

Sends transcript + scenes + analysis to LLM, receives:
- `hook_strength` (0-100) -- does scene 0 grab attention?
- `narrative_flow` (0-100) -- does arc work for <60s?
- `visual_consistency` (0-100) -- same world/palette?
- `emotional_progression` (0-100) -- buildup>peak>resolution?
- `style_adherence` (0-100) -- match requested style?

### `train.py` -- Unified Score Formulas

```
style_consistency   = 0.6 * llm.style_adherence + 0.4 * (100 - shot_repetition_penalty)
visual_quality      = 0.4 * llm.visual_consistency + 0.3 * prompt_quality + 0.3 * (100 - storyboard_error_penalty)
narrative_coherence = 0.5 * llm.narrative_flow + 0.3 * role_arc_score + 0.2 * (100 - segment_evenness_penalty)
audio_visual_sync   = 0.5 * timing_accuracy + 0.3 * (100 - cross_module_penalty) + 0.2 * pacing_score
viral_score         = 0.30 * hook_strength + 0.25 * retention_pacing + 0.20 * emotional_progression + 0.15 * climax_clarity + 0.10 * cta_effectiveness
overall             = weighted average (0.20/0.20/0.25/0.15/0.20)
```

### `program.py` -- Fix Mapping

| Issue | Fix |
|-------|-----|
| Too many hard_max breaks | Raise `segment_config.hard_max` to 6.0, `target_max` to 5.0 |
| Too few segments | Lower `target_max` to 3.5, `target_min` to 1.2 |
| Too many segments | Raise `target_min` to 2.0, `target_max` to 4.5 |
| Uneven durations (high CV) | Tighten target range to midpoint +/- 0.75 |
| Speech too slow/fast | Adjust `speed` by +/-0.15 |
| Short scene prompts | Add style note requesting detailed descriptions |
| Consecutive same shot | Add style note forbidding repeated shot types |
| Missing hook/peak role | Add style note requiring specific roles |

### `loop.py` -- CLI

**Full loop (run pipeline + score + fix + re-run):**
```bash
python -m _dev.self_improver --text "Your story text here..." --style cinematic --iterations 5
```

**Score an existing project (no pipeline run, instant):**
```bash
python -m _dev.self_improver --project pp_ABC123 --score-only
```

**Score only specific steps:**
```bash
python -m _dev.self_improver --project pp_ABC123 --score-only --steps segments,scenes
```

**Re-run only specific steps (resume from a step, reuse prior outputs):**
```bash
python -m _dev.self_improver --project pp_ABC123 --resume-from scenes --iterations 3
```

**Score + fix loop on specific steps only:**
```bash
python -m _dev.self_improver --project pp_ABC123 --steps scenes,storyboard --iterations 3
```

**All CLI flags:**
| Flag | Description |
|------|-------------|
| `--text` / `--text-file` | Input text (required for fresh runs) |
| `--project` | Use existing project instead of running pipeline |
| `--score-only` | Score and report, no fixes or re-runs |
| `--steps` | Comma-separated: `tts,alignment,segments,scenes,storyboard` |
| `--resume-from` | Re-run pipeline starting at this step |
| `--style` | Visual style preset (default: cinematic) |
| `--voice` | TTS voice (default: af_heart) |
| `--speed` | TTS speed (default: 1.0) |
| `--niche` | Niche preset ID |
| `--iterations` | Max improvement iterations (default: 5) |

## Stopping Conditions

The loop exits when **any** of these is true:

1. **Max iterations reached** -- default 5 (configurable via `--iterations`)
2. **Score plateau** -- if the last fix attempt produced delta <= 0 (no improvement), stop immediately.
3. **No fixable issues** -- if `generate_fixes()` returns an empty FixPlan, the pipeline is optimal for the given text.

Worst case = 5 iterations x ~8 min each = ~40 minutes. Typical = 2-3 iterations before plateau.

## Critical Files (read-only, not modified)

- studio/pipeline/routes.py -- Pipeline API endpoints + step implementations
- studio/pipeline/schemas.py -- PipelineRunRequest Pydantic schema
- studio/timing/segmenter.py -- Segmenter algorithm + DEFAULT_CONFIG
- studio/build_scene_blueprints/prompts.py -- Scene prompt builder
- config.py -- Output directory paths, webhook URLs
