"""Self-Correction Engine.

Takes analysis results, generates config fixes, re-runs pipeline,
compares scores, and maintains the rolling report.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import base64

from .config import REPORT_PATH, PIPELINE_STEP_ORDER, STORYBOARD_DIR
from .prepare import PipelineSnapshot, run_and_collect, resume_and_collect, collect_snapshot
from .train import AnalysisResult, Issue, UnifiedScores, ImageScores, analyze


@dataclass
class Fix:
    target_module: str    # segment_config, style_notes, speed
    parameter: str
    old_value: str
    new_value: str
    reason: str
    source_issue: Issue


@dataclass
class FixPlan:
    fixes: list = field(default_factory=list)
    modified_config: dict = field(default_factory=dict)
    resume_from: Optional[str] = None  # earliest pipeline step to re-run


@dataclass
class ComparisonResult:
    improved: bool
    before_overall: float
    after_overall: float
    delta: float
    before_scores: UnifiedScores
    after_scores: UnifiedScores
    fixes_applied: list = field(default_factory=list)
    new_project_id: str = ""


# ── Fix Generation ───────────────────────────────────────────────────────

def _earliest_step(modules: set) -> Optional[str]:
    """Given a set of module names that need fixing, return the earliest pipeline step."""
    # Map fix module → pipeline step
    module_to_step = {
        "tts": "tts",
        "alignment": "timing",
        "segments": "segment",
        "scenes": "scenes",
        "storyboard": "storyboard",
        "speed": "tts",
        "segment_config": "segment",
        "style_notes": "scenes",
    }
    steps_needed = set()
    for m in modules:
        step = module_to_step.get(m)
        if step:
            steps_needed.add(step)

    for step in PIPELINE_STEP_ORDER:
        if step in steps_needed:
            return step
    return None


def generate_fixes(
    analysis: AnalysisResult,
    snap: PipelineSnapshot,
    steps: Optional[list] = None,
) -> FixPlan:
    """Map analysis issues to concrete config changes."""
    fixes = []
    config = dict(snap.config)
    segment_config = dict(config.get("segment_config") or {})
    current_notes = config.get("custom_style_notes") or config.get("style_prompt") or ""
    fix_modules = set()

    for issue in analysis.heuristic.issues:
        if issue.severity == "info":
            continue
        if steps and issue.module not in steps and issue.module != "cross":
            continue

        # ── Segmenter fixes ──
        if issue.module == "segments":
            if "hard_max" in issue.metric_name:
                old_hm = segment_config.get("hard_max", 5.0)
                segment_config["hard_max"] = 6.0
                segment_config["target_max"] = max(segment_config.get("target_max", 4.0), 5.0)
                fixes.append(Fix("segment_config", "hard_max", str(old_hm), "6.0", issue.suggested_fix, issue))
                fix_modules.add("segment_config")

            elif issue.metric_name == "seg_count":
                if issue.metric_value < issue.metric_threshold:
                    old_tm = segment_config.get("target_max", 4.0)
                    segment_config["target_max"] = 3.5
                    segment_config["target_min"] = min(segment_config.get("target_min", 1.5), 1.2)
                    fixes.append(Fix("segment_config", "target_max", str(old_tm), "3.5", "Lower target_max for more segments", issue))
                    fix_modules.add("segment_config")
                else:
                    old_tm = segment_config.get("target_min", 1.5)
                    segment_config["target_min"] = 2.0
                    segment_config["target_max"] = max(segment_config.get("target_max", 4.0), 4.5)
                    fixes.append(Fix("segment_config", "target_min", str(old_tm), "2.0", "Raise target_min for fewer segments", issue))
                    fix_modules.add("segment_config")

            elif issue.metric_name == "seg_duration_cv":
                mid = (segment_config.get("target_min", 1.5) + segment_config.get("target_max", 4.0)) / 2
                new_min = round(mid - 0.75, 1)
                new_max = round(mid + 0.75, 1)
                old_range = f"{segment_config.get('target_min', 1.5)}-{segment_config.get('target_max', 4.0)}"
                segment_config["target_min"] = new_min
                segment_config["target_max"] = new_max
                fixes.append(Fix("segment_config", "target_range", old_range, f"{new_min}-{new_max}", "Tighten range for even splits", issue))
                fix_modules.add("segment_config")

        # ── TTS speed fixes ──
        elif issue.module == "tts" and "wps" in issue.metric_name:
            current_speed = config.get("speed", 1.0)
            if issue.metric_value < issue.metric_threshold:
                new_speed = min(current_speed + 0.15, 2.0)
            else:
                new_speed = max(current_speed - 0.15, 0.5)
            fixes.append(Fix("speed", "speed", str(current_speed), str(round(new_speed, 2)), issue.suggested_fix, issue))
            config["speed"] = round(new_speed, 2)
            fix_modules.add("speed")

        # ── Scene prompt quality fixes ──
        elif issue.module == "scenes" or (issue.module == "storyboard" and "img_" in issue.metric_name):
            additions = []
            if "prompt" in issue.description.lower() and "short" in issue.description.lower():
                additions.append("Write detailed, vivid image prompts (100+ characters). Include specific lighting, mood, camera details.")
            if "consecutive" in issue.description.lower() and "shot" in issue.description.lower():
                additions.append("CRITICAL: Never use the same shot type for consecutive scenes. Alternate wide/close-up/medium/POV.")
            if "missing" in issue.description.lower() and "role" in issue.description.lower():
                additions.append("First scene MUST have narrative_role='hook'. Include at least one 'peak'. Last scene should be 'cta'.")
            if "type" in issue.description.lower() and "scene type" in issue.description.lower():
                additions.append("Include at least one text_accent scene for visual variety.")
            # Image-based fixes
            if "img_style_consistency" in issue.metric_name:
                additions.append("CRITICAL: All scenes must share identical color palette, lighting direction, and render style. Describe the exact same style keywords in every prompt.")
            if "img_prompt_adherence" in issue.metric_name:
                additions.append("Write prompts with concrete, specific visual details. Avoid abstract concepts. Describe exactly what should be visible: subject, action, setting, lighting, camera angle.")
            if "img_visual_flow" in issue.metric_name:
                additions.append("Maintain visual continuity across scenes. Keep consistent environment, subject appearance, and color temperature. Each scene should visually connect to the previous one.")

            if additions:
                new_notes = (current_notes + " " + " ".join(additions)).strip()
                fixes.append(Fix(
                    "style_notes", "custom_style_notes",
                    current_notes[:60] + "..." if len(current_notes) > 60 else current_notes or "(empty)",
                    new_notes[:60] + "...",
                    "Improve LLM scene generation via style constraints",
                    issue,
                ))
                current_notes = new_notes
                fix_modules.add("style_notes")

    # Build modified config
    modified = dict(snap.config)
    if segment_config and fix_modules & {"segment_config"}:
        modified["segment_config"] = segment_config
    if current_notes != (config.get("custom_style_notes") or config.get("style_prompt") or ""):
        modified["custom_style_notes"] = current_notes
    if "speed" in fix_modules:
        modified["speed"] = config["speed"]

    resume_from = _earliest_step(fix_modules)

    return FixPlan(fixes=fixes, modified_config=modified, resume_from=resume_from)


# ── Apply & Compare ──────────────────────────────────────────────────────

def apply_and_compare(
    fix_plan: FixPlan,
    original_snap: PipelineSnapshot,
    original_analysis: AnalysisResult,
    steps: Optional[list] = None,
) -> ComparisonResult:
    """Re-run pipeline with fixes, re-analyze, compare scores."""
    if not fix_plan.fixes:
        return ComparisonResult(
            improved=False,
            before_overall=original_analysis.unified.overall,
            after_overall=original_analysis.unified.overall,
            delta=0,
            before_scores=original_analysis.unified,
            after_scores=original_analysis.unified,
        )

    mc = fix_plan.modified_config
    print(f"\n  Re-running pipeline with {len(fix_plan.fixes)} fix(es)...")

    # Use resume if we have a project and a resume point
    if original_snap.project_id and fix_plan.resume_from:
        new_snap = resume_and_collect(
            original_snap.project_id,
            fix_plan.resume_from,
            text=mc.get("text", ""),
            voice=mc.get("voice", "af_heart"),
            speed=mc.get("speed", 1.0),
            style=mc.get("style", "cinematic"),
            niche_preset=mc.get("niche_preset"),
            segment_config=mc.get("segment_config"),
            custom_style_notes=mc.get("custom_style_notes"),
        )
    else:
        new_snap = run_and_collect(
            mc.get("text", ""),
            voice=mc.get("voice", "af_heart"),
            speed=mc.get("speed", 1.0),
            style=mc.get("style", "cinematic"),
            niche_preset=mc.get("niche_preset"),
            segment_config=mc.get("segment_config"),
            custom_style_notes=mc.get("custom_style_notes"),
        )

    if new_snap.error:
        print(f"  Re-run failed: {new_snap.error}")
        return ComparisonResult(
            improved=False,
            before_overall=original_analysis.unified.overall,
            after_overall=0,
            delta=-original_analysis.unified.overall,
            before_scores=original_analysis.unified,
            after_scores=UnifiedScores(),
            fixes_applied=fix_plan.fixes,
            new_project_id=new_snap.project_id,
        )

    new_analysis = analyze(new_snap, steps)
    delta = round(new_analysis.unified.overall - original_analysis.unified.overall, 1)

    return ComparisonResult(
        improved=delta > 0,
        before_overall=original_analysis.unified.overall,
        after_overall=new_analysis.unified.overall,
        delta=delta,
        before_scores=original_analysis.unified,
        after_scores=new_analysis.unified,
        fixes_applied=fix_plan.fixes,
        new_project_id=new_snap.project_id,
    )


# ── Report Generation ────────────────────────────────────────────────────

def append_report(
    run_num: int,
    style: str,
    project_id: str,
    before: UnifiedScores,
    after: UnifiedScores,
    issues: list,
    fixes: list,
    comparison: ComparisonResult,
):
    """Append a run summary to the rolling self-improvement-report.md."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    status = "Applied" if comparison.improved else "Rolled back"
    d_sign = "+" if comparison.delta >= 0 else ""

    lines = [
        f"\n## Run #{run_num} -- {now} -- {style} -- {project_id}\n",
        "### Scores\n",
        "| Metric | Before | After | Delta |",
        "|--------|--------|-------|-------|",
    ]

    for metric in ["style_consistency", "visual_quality", "narrative_coherence",
                    "audio_visual_sync", "viral_score"]:
        b = getattr(before, metric, 0)
        a = getattr(after, metric, 0)
        d = a - b
        ds = f"+{d}" if d >= 0 else str(d)
        lines.append(f"| {metric.replace('_', ' ').title()} | {b} | {a} | {ds} |")

    lines.append(f"| **Overall** | **{before.overall}** | **{after.overall}** | **{d_sign}{comparison.delta}** |")
    lines.append("")

    if issues:
        lines.append("### Issues Found\n")
        for issue in issues[:10]:
            lines.append(f"- **[{issue.module.upper()}]** {issue.description}")
            lines.append(f"  - Root cause: {issue.root_cause}")
            lines.append(f"  - Fix: {issue.suggested_fix}")
        lines.append("")

    if fixes:
        lines.append("### Fixes Applied\n")
        for fix in fixes:
            lines.append(f"- `{fix.target_module}.{fix.parameter}`: "
                         f"`{fix.old_value}` -> `{fix.new_value}` ({fix.reason})")
        lines.append("")

    lines.append("### Result\n")
    lines.append(f"**{status}**. Net score change: {d_sign}{comparison.delta}\n")
    lines.append("---\n")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    header = ""
    if not REPORT_PATH.exists():
        header = "# Self-Improvement Report\n\nAuto-generated by ScriptToScene Studio self-improver.\n\n---\n"

    with open(REPORT_PATH, "a", encoding="utf-8") as f:
        if header:
            f.write(header)
        f.write("\n".join(lines))


# ── HTML Comparison Report ───────────────────────────────────────────────

def _img_to_data_uri(path) -> str:
    """Convert image file to data URI for embedding in HTML."""
    from pathlib import Path
    p = Path(path)
    if not p.is_file():
        return ""
    ext = p.suffix.lower().lstrip(".")
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/jpeg")
    b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _get_project_images(project_id: str, scene_count: int) -> list:
    """Get list of (scene_index, image_path_or_None) for a project."""
    images = []
    for i in range(scene_count):
        img = STORYBOARD_DIR / project_id / str(i) / "image.jpeg"
        if not img.is_file():
            img = STORYBOARD_DIR / project_id / str(i) / "image.png"
        images.append((i, img if img.is_file() else None))
    return images


def generate_comparison_html(
    iterations: list,
    output_path=None,
):
    """Generate an HTML report comparing storyboard images across iterations.

    iterations: list of dicts with keys:
        - project_id: str
        - scores: UnifiedScores
        - image_scores: ImageScores
        - scene_count: int
        - label: str (e.g. "Initial", "Iteration 1")
    """
    if not iterations:
        return

    if output_path is None:
        output_path = REPORT_PATH.parent / "comparison-report.html"

    max_scenes = max(it.get("scene_count", 0) for it in iterations)

    rows_html = []
    for scene_idx in range(max_scenes):
        cells = []
        for it in iterations:
            pid = it["project_id"]
            imgs = _get_project_images(pid, it.get("scene_count", 0))
            if scene_idx < len(imgs) and imgs[scene_idx][1]:
                uri = _img_to_data_uri(imgs[scene_idx][1])
                cells.append(f'<td><img src="{uri}" alt="Scene {scene_idx}"></td>')
            else:
                cells.append('<td class="no-img">No image</td>')
        rows_html.append(f'<tr><td class="scene-num">Scene {scene_idx}</td>{"".join(cells)}</tr>')

    header_cells = "".join(
        f'<th>{it["label"]}<br><small>{it["project_id"]}</small><br>'
        f'<span class="score">Overall: {it["scores"].overall}</span>'
        f'{"<br><span class=img-score>Images: " + str(it["image_scores"].overall) + "</span>" if it["image_scores"].overall > 0 else ""}'
        f'</th>'
        for it in iterations
    )

    # Score comparison table
    score_rows = []
    if len(iterations) >= 2:
        first = iterations[0]["scores"]
        last = iterations[-1]["scores"]
        for metric in ["style_consistency", "visual_quality", "narrative_coherence", "audio_visual_sync", "viral_score"]:
            b = getattr(first, metric, 0)
            a = getattr(last, metric, 0)
            d = a - b
            color = "#4ECDC4" if d > 0 else "#ff6b6b" if d < 0 else "#888"
            ds = f"+{d}" if d > 0 else str(d)
            score_rows.append(f'<tr><td>{metric.replace("_", " ").title()}</td><td>{b}</td><td>{a}</td><td style="color:{color};font-weight:700">{ds}</td></tr>')
        d = round(last.overall - first.overall, 1)
        color = "#4ECDC4" if d > 0 else "#ff6b6b" if d < 0 else "#888"
        ds = f"+{d}" if d > 0 else str(d)
        score_rows.append(f'<tr style="border-top:2px solid #333"><td><strong>Overall</strong></td><td><strong>{first.overall}</strong></td><td><strong>{last.overall}</strong></td><td style="color:{color};font-weight:700"><strong>{ds}</strong></td></tr>')

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Self-Improver Comparison</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0a0a0a; color:#ccc; font-family:system-ui,-apple-system,sans-serif; padding:24px; }}
h1 {{ color:#4ECDC4; font-size:20px; margin-bottom:4px; }}
h2 {{ color:#888; font-size:14px; font-weight:400; margin-bottom:24px; }}
h3 {{ color:#4ECDC4; font-size:16px; margin:24px 0 12px; }}
table {{ border-collapse:collapse; width:100%; margin-bottom:24px; }}
th, td {{ padding:8px 12px; text-align:center; border:1px solid #222; }}
th {{ background:#111; color:#4ECDC4; font-size:12px; }}
.scene-num {{ background:#111; color:#888; font-size:11px; width:70px; text-align:center; }}
td img {{ max-width:200px; max-height:360px; border-radius:6px; display:block; margin:0 auto; }}
.no-img {{ color:#555; font-style:italic; font-size:11px; }}
.score {{ color:#4ECDC4; font-weight:700; }}
.img-score {{ color:#a78bfa; }}
.score-table {{ max-width:500px; }}
.score-table td {{ text-align:left; }}
.score-table td:nth-child(n+2) {{ text-align:center; }}
small {{ color:#666; }}
</style></head><body>
<h1>ScriptToScene Self-Improver</h1>
<h2>Storyboard Comparison - {len(iterations)} iteration(s)</h2>

{"<h3>Score Progression</h3><table class=score-table><tr><th>Metric</th><th>Initial</th><th>Final</th><th>Delta</th></tr>" + "".join(score_rows) + "</table>" if score_rows else ""}

<h3>Storyboard Images</h3>
<table>
<tr><th></th>{header_cells}</tr>
{"".join(rows_html)}
</table>

</body></html>"""

    from pathlib import Path
    Path(output_path).write_text(html, encoding="utf-8")
    print(f"  HTML comparison report: {output_path}")
    return output_path
