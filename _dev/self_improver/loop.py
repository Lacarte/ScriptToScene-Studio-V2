"""Self-Improving Pipeline Loop.

Orchestrates: run -> score -> fix -> re-run -> re-score -> keep/rollback -> report

Usage:
  # Full loop with new text
  python -m _dev.self-improver.loop --text "Your story..." --iterations 5

  # Score existing project (instant, no pipeline run)
  python -m _dev.self-improver.loop --project pp_ABC123 --score-only

  # Score only specific steps
  python -m _dev.self-improver.loop --project pp_ABC123 --score-only --steps segments,scenes

  # Re-run from a specific step
  python -m _dev.self-improver.loop --project pp_ABC123 --resume-from scenes --iterations 3

  # Fix loop on specific steps only
  python -m _dev.self-improver.loop --project pp_ABC123 --steps scenes,storyboard --iterations 3
"""

import argparse
import sys
from typing import Optional

from .config import DEFAULT_MAX_ITERATIONS, ALL_STEPS
from .prepare import run_and_collect, resume_and_collect, collect_snapshot, PipelineSnapshot
from .train import analyze, AnalysisResult
from .program import generate_fixes, apply_and_compare, append_report, generate_comparison_html


def _print_scores(unified):
    """Print a compact score summary."""
    print()
    print(f"  +-------------------------------------+")
    print(f"  |  Style Consistency   {unified.style_consistency:>3}             |")
    print(f"  |  Visual Quality      {unified.visual_quality:>3}             |")
    print(f"  |  Narrative Coherence {unified.narrative_coherence:>3}             |")
    print(f"  |  Audio-Visual Sync   {unified.audio_visual_sync:>3}             |")
    print(f"  |  Viral Score         {unified.viral_score:>3}             |")
    print(f"  |  ----------------------------------- |")
    print(f"  |  Overall             {unified.overall:>5}           |")
    print(f"  +-------------------------------------+")


def run_score_only(
    snap: PipelineSnapshot,
    steps: Optional[list] = None,
):
    """Score an existing snapshot and print results."""
    analysis = analyze(snap, steps)
    _print_scores(analysis.unified)

    if analysis.heuristic.issues:
        print(f"\n  Issues ({len(analysis.heuristic.issues)}):")
        for issue in analysis.heuristic.issues:
            icon = "x" if issue.severity == "critical" else "!" if issue.severity == "warning" else "-"
            print(f"    {icon} [{issue.module.upper()}] {issue.description}")
            print(f"      Fix: {issue.suggested_fix}")

    if analysis.llm_scores.raw_response.get("reasoning"):
        print(f"\n  LLM Reasoning:")
        for k, v in analysis.llm_scores.raw_response["reasoning"].items():
            print(f"    - {k}: {v}")

    return analysis


def run_improvement_loop(
    text: str = "",
    *,
    project_id: Optional[str] = None,
    resume_from: Optional[str] = None,
    style: str = "cinematic",
    voice: str = "af_heart",
    speed: float = 1.0,
    niche_preset: Optional[str] = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    steps: Optional[list] = None,
    segment_config: Optional[dict] = None,
    custom_style_notes: Optional[str] = None,
):
    """Full self-improvement loop."""
    target_steps = steps or ALL_STEPS

    print(f"\n{'=' * 55}")
    print(f"  ScriptToScene Self-Improver")
    print(f"  Style: {style} | Voice: {voice} | Speed: {speed}")
    print(f"  Steps: {', '.join(target_steps)}")
    print(f"  Max iterations: {max_iterations}")
    print(f"{'=' * 55}\n")

    # ── Get initial snapshot ──
    if project_id and not resume_from and not text:
        # Load existing project
        print(f"[Init] Loading existing project {project_id}...")
        snap = collect_snapshot(project_id)
        if not snap.pipeline:
            print(f"  ERROR: No pipeline data for {project_id}")
            return
    elif project_id and resume_from:
        # Resume from a specific step
        print(f"[Init] Resuming {project_id} from {resume_from}...")
        snap = resume_and_collect(
            project_id, resume_from,
            text=text, style=style, voice=voice, speed=speed,
            niche_preset=niche_preset, segment_config=segment_config,
            custom_style_notes=custom_style_notes,
        )
    elif text:
        # Fresh pipeline run
        print("[Init] Running initial pipeline...")
        snap = run_and_collect(
            text, style=style, voice=voice, speed=speed,
            niche_preset=niche_preset, segment_config=segment_config,
            custom_style_notes=custom_style_notes,
        )
    else:
        print("ERROR: Provide --text or --project")
        return

    if snap.error:
        print(f"\n  FATAL: Pipeline failed: {snap.error}")
        return

    print(f"\n  Project: {snap.project_id}")
    analysis = analyze(snap, target_steps)
    _print_scores(analysis.unified)

    best_snap = snap
    best_analysis = analysis

    # Track iterations for HTML comparison report
    iteration_history = [{
        "project_id": snap.project_id,
        "scores": analysis.unified,
        "image_scores": analysis.image_scores,
        "scene_count": len(snap.scenes.get("scenes", [])),
        "label": "Initial",
    }]

    for iteration in range(1, max_iterations + 1):
        print(f"\n{'-' * 55}")
        print(f"[Iteration {iteration}/{max_iterations}] Current overall: {best_analysis.unified.overall}")

        # Generate fixes
        fix_plan = generate_fixes(best_analysis, best_snap, target_steps)
        if not fix_plan.fixes:
            print("  No fixable issues found. Pipeline is optimal.")
            append_report(
                iteration, style, best_snap.project_id,
                best_analysis.unified, best_analysis.unified,
                best_analysis.heuristic.issues, [],
                type("CR", (), {"improved": False, "delta": 0,
                                "before_overall": best_analysis.unified.overall,
                                "after_overall": best_analysis.unified.overall})(),
            )
            break

        print(f"  {len(fix_plan.fixes)} fix(es) planned (resume from: {fix_plan.resume_from}):")
        for fix in fix_plan.fixes:
            print(f"    - {fix.target_module}.{fix.parameter}: {fix.old_value} -> {fix.new_value}")

        # Apply and compare
        comparison = apply_and_compare(fix_plan, best_snap, best_analysis, target_steps)

        # Report
        append_report(
            iteration, style, best_snap.project_id,
            comparison.before_scores, comparison.after_scores,
            best_analysis.heuristic.issues,
            comparison.fixes_applied,
            comparison,
        )

        # Always track iteration for HTML comparison (even rolled back)
        if comparison.new_project_id:
            from .train import ImageScores
            iter_snap = collect_snapshot(comparison.new_project_id)
            status_label = "Kept" if comparison.improved else "Rolled back"
            iteration_history.append({
                "project_id": comparison.new_project_id,
                "scores": comparison.after_scores,
                "image_scores": ImageScores(),  # images already visible in HTML
                "scene_count": len(iter_snap.scenes.get("scenes", [])),
                "label": f"Iter {iteration} ({status_label}, {comparison.delta:+.1f})",
            })

        if comparison.improved:
            print(f"\n  IMPROVED! +{comparison.delta} overall")
            print(f"  Keeping: {comparison.new_project_id}")
            _print_scores(comparison.after_scores)
            best_snap = collect_snapshot(comparison.new_project_id)
            best_analysis = analyze(best_snap, target_steps)
        else:
            print(f"\n  No improvement ({comparison.delta}). Stopping.")
            print(f"  Best remains: {best_snap.project_id}")
            break

    # Generate HTML comparison report if we have storyboard images
    if len(iteration_history) >= 1:
        generate_comparison_html(iteration_history)

    print(f"\n{'=' * 55}")
    print(f"  Loop complete")
    print(f"  Best project: {best_snap.project_id}")
    print(f"  Final overall: {best_analysis.unified.overall}")
    print(f"{'=' * 55}\n")


def main():
    parser = argparse.ArgumentParser(
        description="ScriptToScene Self-Improving Pipeline Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--text", type=str, help="Input text")
    parser.add_argument("--text-file", type=str, help="Path to text file")
    parser.add_argument("--project", type=str, help="Existing project ID (skip pipeline run)")
    parser.add_argument("--score-only", action="store_true", help="Score only, no fixes")
    parser.add_argument("--steps", type=str, help="Comma-separated steps: tts,alignment,segments,scenes,storyboard")
    parser.add_argument("--resume-from", type=str, help="Resume pipeline from this step")
    parser.add_argument("--style", type=str, default="cinematic")
    parser.add_argument("--voice", type=str, default="af_heart")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--niche", type=str, default=None)
    parser.add_argument("--iterations", type=int, default=DEFAULT_MAX_ITERATIONS)
    args = parser.parse_args()

    # Parse steps
    steps = None
    if args.steps:
        steps = [s.strip() for s in args.steps.split(",") if s.strip()]
        invalid = [s for s in steps if s not in ALL_STEPS]
        if invalid:
            print(f"ERROR: Invalid steps: {invalid}. Valid: {ALL_STEPS}")
            sys.exit(1)

    # Get text
    text = ""
    if args.text_file:
        with open(args.text_file, "r", encoding="utf-8") as f:
            text = f.read().strip()
    elif args.text:
        text = args.text

    # Score-only mode
    if args.score_only:
        if not args.project:
            print("ERROR: --score-only requires --project")
            sys.exit(1)
        snap = collect_snapshot(args.project)
        if not snap.tts and not snap.scenes:
            print(f"ERROR: No data found for {args.project}")
            sys.exit(1)
        run_score_only(snap, steps)
        return

    # Validate input
    if not text and not args.project:
        print("ERROR: Provide --text, --text-file, or --project")
        sys.exit(1)

    run_improvement_loop(
        text=text,
        project_id=args.project,
        resume_from=args.resume_from,
        style=args.style,
        voice=args.voice,
        speed=args.speed,
        niche_preset=args.niche,
        max_iterations=args.iterations,
        steps=steps,
    )


if __name__ == "__main__":
    main()
