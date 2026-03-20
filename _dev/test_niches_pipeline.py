"""
Test all 22 niche presets through the pipeline (stop_after=scenes).
Judges story quality and scene generation quality for each niche.
No external SSE library needed — parses SSE stream manually.
"""

import json
import sys
import time
import requests

BASE = "http://localhost:5050"
STOP_AFTER = "scenes"
TIMEOUT = 180

# Short test texts per category
TEST_TEXTS = {
    "psychology": "The moment you realize someone has been manipulating you all along, everything changes. Every conversation replays in your mind differently.",
    "crime": "The detective stared at the evidence board. Three victims, one pattern, and a suspect who had been dead for two years.",
    "horror": "The house at the end of Maple Street had been empty for decades. Until the lights turned on last Tuesday.",
    "philosophy": "Marcus Aurelius wrote that the obstacle is the way. But what happens when the obstacle is yourself?",
    "motivation": "At 4:47 AM, while the world sleeps, champions are built. Every rep, every page, every sacrifice compounds.",
    "religion": "The shepherd boy who would become king never forgot the valley where he faced his giant alone.",
    "mystery": "The letter arrived three days after the funeral. Inside was a key and coordinates to a place that shouldn't exist.",
    "romance": "They met at a bookstore on a rainy Tuesday. She was reading his favorite book. He was holding hers.",
    "children": "Lumi the firefly had lost her glow. Without her light, the meadow creatures couldn't find their way home at night.",
    "science": "A single neuron fires. Then another. In milliseconds, a thought emerges from chaos — consciousness from chemistry.",
    "anecdote": "So there I was, stuck in an elevator with my ex and her new boyfriend. The power had been out for twenty minutes.",
}


def get_test_text(category):
    return TEST_TEXTS.get(category, TEST_TEXTS["psychology"])


def parse_sse_stream(resp):
    """Parse SSE events from a streaming response without external library."""
    events = []
    buf = ""
    for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
        buf += chunk
        while "\n\n" in buf:
            raw, buf = buf.split("\n\n", 1)
            data_line = None
            for line in raw.strip().split("\n"):
                if line.startswith("data:"):
                    data_line = line[5:].strip()
            if data_line:
                try:
                    events.append(json.loads(data_line))
                except json.JSONDecodeError:
                    pass
    return events


def run_pipeline(niche_id, niche_info):
    """Run a single pipeline for a niche and return results."""
    category = niche_info.get("category", "psychology")
    text = get_test_text(category)

    payload = {
        "text": text,
        "voice": "af_heart",
        "speed": 1.0,
        "style": niche_info.get("visual_style", "cinematic"),
        "niche_preset": niche_id,
        "stop_after": STOP_AFTER,
        "auto_scenes": True,
    }

    # Start pipeline
    try:
        r = requests.post(f"{BASE}/api/pipeline/run", json=payload, timeout=10)
    except Exception as e:
        return {"error": f"Start failed: {e}"}

    if r.status_code != 202:
        return {"error": f"Start failed: {r.status_code} {r.text[:200]}"}

    data = r.json()
    job_id = data["job_id"]
    project_id = data["project_id"]

    # Stream SSE events
    try:
        resp = requests.get(f"{BASE}/api/pipeline/progress/{job_id}", stream=True, timeout=TIMEOUT)
        resp.encoding = "utf-8"
        events = parse_sse_stream(resp)
    except Exception as e:
        return {"error": f"SSE failed: {e}"}

    # Find terminal event
    final_status = None
    scenes_data = None
    step_statuses = {}

    for evt in events:
        step = evt.get("step")
        status = evt.get("status")
        if step and status and step not in ("done", "error", "stopped"):
            step_statuses[step] = status
        if step == "done":
            final_status = "done"
            scenes_data = evt.get("summary", {}).get("scenes")
        elif step == "error":
            final_status = "error"
        elif step == "stopped":
            final_status = "stopped"

    return {
        "job_id": job_id,
        "project_id": project_id,
        "status": final_status,
        "scenes_data": scenes_data,
        "events": events,
        "step_statuses": step_statuses,
    }


def judge_result(niche_id, niche_info, result):
    """Judge the quality of story and scene generation."""
    issues = []
    scores = {}

    if result.get("error"):
        return {"verdict": "FAIL", "reason": result["error"], "scores": {}}

    if result["status"] != "done":
        return {"verdict": "FAIL", "reason": f"Pipeline ended: {result['status']}", "scores": {}}

    # ── Verify step_statuses ──
    expected_done = {"tts", "timing", "segment", "scenes"}
    for step in expected_done:
        st = result.get("step_statuses", {}).get(step)
        if st != "done" and st != "skipped":
            issues.append(f"Step '{step}' status: {st} (expected done)")

    # Steps that should NOT have run
    should_not_run = {"assets", "assemble", "export"}
    for step in should_not_run:
        st = result.get("step_statuses", {}).get(step)
        if st and st not in (None, "pending"):
            issues.append(f"Step '{step}' ran unexpectedly (status: {st})")

    scenes_data = result.get("scenes_data") or {}
    scenes = scenes_data.get("scenes", [])

    # ── Scene count ──
    if not scenes:
        issues.append("No scenes generated")
        scores["scene_count"] = 0
    else:
        scores["scene_count"] = len(scenes)

    # ── Scene structure ──
    required_keys = {"index", "type", "image_prompt", "duration"}
    valid_scenes = 0
    has_image_prompts = 0
    total_duration = 0

    for i, scene in enumerate(scenes):
        missing = required_keys - set(scene.keys())
        if missing:
            issues.append(f"Scene {i}: missing {missing}")
        else:
            valid_scenes += 1
        if scene.get("image_prompt") and len(str(scene["image_prompt"])) > 20:
            has_image_prompts += 1
        total_duration += scene.get("duration", 0)

    scores["valid_scenes"] = valid_scenes
    scores["scenes_with_prompts"] = has_image_prompts
    scores["total_duration"] = round(total_duration, 1)

    # ── Style consistency ──
    style_id = niche_info.get("visual_style", "")
    scene_style = scenes_data.get("style", "")
    if style_id and scene_style and style_id != scene_style:
        issues.append(f"Style mismatch: expected '{style_id}', got '{scene_style}'")

    # ── TTS info ──
    tts_events = [e for e in result.get("events", []) if e.get("step") == "tts" and e.get("status") == "done"]
    if tts_events:
        scores["tts_info"] = tts_events[0].get("message", "")

    # ── Verdict ──
    if not scenes:
        verdict = "FAIL"
    elif issues:
        verdict = "WARN"
    else:
        verdict = "PASS"

    return {"verdict": verdict, "issues": issues, "scores": scores}


def main():
    # Load niches
    try:
        r = requests.get(f"{BASE}/api/niches", timeout=5)
    except Exception as e:
        print(f"Cannot reach server: {e}")
        sys.exit(1)

    niches = r.json().get("presets", {})
    print(f"Testing {len(niches)} niches (stop_after={STOP_AFTER})\n")
    print("=" * 90)

    results = {}
    pass_count = warn_count = fail_count = 0

    for i, (niche_id, niche_info) in enumerate(niches.items(), 1):
        style = niche_info.get("visual_style", "?")
        cat = niche_info.get("category", "?")
        tone = niche_info.get("story_tone", "?")
        print(f"\n[{i}/{len(niches)}] {niche_id}")
        print(f"  style={style}  cat={cat}  tone={tone}")

        t0 = time.time()
        result = run_pipeline(niche_id, niche_info)
        elapsed = time.time() - t0

        judgment = judge_result(niche_id, niche_info, result)
        verdict = judgment["verdict"]
        scores = judgment.get("scores", {})

        symbol = {"PASS": "[OK]", "WARN": "[!!]", "FAIL": "[XX]"}[verdict]
        if verdict == "PASS":
            pass_count += 1
        elif verdict == "WARN":
            warn_count += 1
        else:
            fail_count += 1

        print(f"  {symbol} {verdict} ({elapsed:.1f}s) -- {scores.get('scene_count', 0)} scenes, "
              f"{scores.get('scenes_with_prompts', 0)} with prompts, "
              f"dur={scores.get('total_duration', 0)}s")

        if judgment.get("issues"):
            for issue in judgment["issues"]:
                print(f"    ! {issue}")
        if judgment.get("reason"):
            print(f"    ✗ {judgment['reason']}")
        if scores.get("tts_info"):
            print(f"    TTS: {scores['tts_info']}")

        results[niche_id] = {
            "verdict": verdict,
            "elapsed": round(elapsed, 1),
            "scores": scores,
            "issues": judgment.get("issues", []),
            "project_id": result.get("project_id"),
        }

        # Wait for previous run to fully clean up
        if i < len(niches):
            time.sleep(2)

    # ── Summary ──
    print("\n" + "=" * 90)
    print(f"\nSUMMARY: {pass_count} PASS / {warn_count} WARN / {fail_count} FAIL  (total: {len(niches)})")
    print()
    print(f"{'Niche':<35} {'Result':<7} {'Time':>6} {'Scenes':>7} {'Prompts':>8} {'Duration':>9}")
    print("-" * 80)
    for niche_id, r in results.items():
        s = r["scores"]
        print(f"{niche_id:<35} {r['verdict']:<7} {r['elapsed']:>5.1f}s {s.get('scene_count',0):>7} "
              f"{s.get('scenes_with_prompts',0):>8} {s.get('total_duration',0):>8.1f}s")

    # Save full results
    out_path = "_dev/test_niches_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to {out_path}")


if __name__ == "__main__":
    main()
