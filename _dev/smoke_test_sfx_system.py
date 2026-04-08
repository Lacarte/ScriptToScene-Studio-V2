"""End-to-end smoke test for the per-scene SFX system.

Exercises the full chain WITHOUT touching the LLM or ffmpeg:
  1. Vocabulary loads
  2. Prompt section renders with all hints + budget rules
  3. Validator runs on a realistic LLM-style scene blueprint
  4. Placer turns validated hints into real audio tracks
  5. The chain produces sane, audible-quality output

Run with: PYTHONPATH=. python _dev/smoke_test_sfx_system.py

Exit code 0 = all green. Non-zero = something is broken.
"""

import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Track failures so we can exit non-zero at the end
_failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    icon = "[OK]  " if ok else "[FAIL]"
    print(f"  {icon} {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures.append(label)


def section(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def main() -> int:
    section("STAGE 1: Vocabulary loads")

    from studio.build_scene_blueprints.sfx_validator import (
        load_sfx_vocabulary,
        SFX_BUDGET_MIN,
        SFX_BUDGET_MAX,
        SFX_BUDGET_MIN_SHORT,
        SFX_BUDGET_MAX_SHORT,
    )

    vocab = load_sfx_vocabulary()
    hints = vocab.get("hints") or {}
    check("vocabulary file loaded", bool(hints), f"{len(hints)} hints")
    check("vocabulary has version field", "version" in vocab, f"v{vocab.get('version')}")
    check("budget constants imported", SFX_BUDGET_MAX > 0,
          f"min={SFX_BUDGET_MIN}, max={SFX_BUDGET_MAX}, "
          f"short_min={SFX_BUDGET_MIN_SHORT}, short_max={SFX_BUDGET_MAX_SHORT}")

    # All 28 expected hints present
    expected_hints = {
        "tension_riser", "bass_drop_impact", "cinematic_hit",
        "whoosh_transition", "rocket_whoosh", "heartbeat_pulse",
        "clock_tick", "thinking_pad", "magic_shimmer", "money_sting",
        "glass_shatter", "gunshot_punctuation", "rain_ambience",
        "nature_ambience", "crowd_cheer", "crowd_laugh", "camera_shutter",
        "keyboard_typing", "telephone_ring", "glitch_distort",
        "viscous_liquid", "notification_ding", "click_confirm",
        "cartoon_pop", "text_appear", "text_disappear", "text_emphasis",
        "silence",
    }
    missing = expected_hints - set(hints.keys())
    check("all 28 expected hints present", not missing,
          f"missing: {missing}" if missing else "")

    # Every entry has a label
    missing_labels = [hid for hid, e in hints.items() if not e.get("label")]
    check("every hint has a label", not missing_labels,
          f"missing labels: {missing_labels}" if missing_labels else "")

    # Every non-silence entry has a folder
    missing_folders = [
        hid for hid, e in hints.items()
        if hid != "silence" and not e.get("folder")
    ]
    check("every non-silence hint has a folder", not missing_folders,
          f"missing folders: {missing_folders}" if missing_folders else "")

    section("STAGE 2: Prompt section renders")

    from studio.build_scene_blueprints.prompts import (
        _build_sfx_section,
        build_scene_system_prompt,
    )

    sfx_section = _build_sfx_section()
    check("SFX section non-empty", len(sfx_section) > 1000,
          f"{len(sfx_section)} chars")
    check("contains '## SFX HINTS' header", "## SFX HINTS" in sfx_section)
    check("contains 'SFX BUDGET (HARD RULES)' header",
          "SFX BUDGET (HARD RULES)" in sfx_section)
    check("contains 'NUCLEAR RULE'", "NUCLEAR RULE" in sfx_section)
    check("contains budget numbers (3-4)", "3-4 hints" in sfx_section)

    # All 28 hint IDs appear in the prompt
    hints_in_prompt = sum(1 for h in expected_hints if h in sfx_section)
    check("all 28 hint IDs appear in prompt",
          hints_in_prompt == 28, f"{hints_in_prompt}/28")

    # Full system prompt builds without errors
    full_prompt = build_scene_system_prompt(
        style_spec={"identity": {"render_mode": "cinematic noir"}},
        visual_bible={"world_anchor": "rain-slicked alley"},
        scene_blueprints=[
            {"index": 0, "narrative_role": "hook", "preferred_scene_type": "image"}
        ],
    )
    check("full system prompt builds", len(full_prompt) > 5000,
          f"{len(full_prompt)} chars")
    check("system prompt includes SFX section",
          "## SFX HINTS" in full_prompt)
    check("system prompt includes sfx_hint in JSON example",
          '"sfx_hint":' in full_prompt)
    check("scene object key list includes sfx_hint",
          "sfx_hint:" in full_prompt)

    section("STAGE 3: Validator runs on realistic LLM-style output")

    from studio.build_scene_blueprints.validators import finalize_scene_result

    # Realistic 8-scene 58-second video. Simulates what a well-behaved LLM
    # following the prompt rules would produce: 4 hints, structurally placed,
    # with one looping texture under a contemplative scene.
    fake_llm_result = {
        "scenes": [
            {
                "index": 0, "type_of_scene": "image", "narrative_role": "hook",
                "image_prompt": "centered shot of glowing stickman in vast purple void",
                "sfx_hint": "magic_shimmer",
            },
            {
                "index": 1, "type_of_scene": "image", "narrative_role": "buildup",
                "image_prompt": "wide shot of dark particles drifting upward",
                "sfx_hint": None,
            },
            {
                "index": 2, "type_of_scene": "image", "narrative_role": "buildup",
                "image_prompt": "close-up of figure's chest glow flickering",
                "sfx_hint": "heartbeat_pulse",
            },
            {
                "index": 3, "type_of_scene": "image", "narrative_role": "buildup",
                "image_prompt": "low-angle of figure tilting back its head",
                "sfx_hint": None,
            },
            {
                "index": 4, "type_of_scene": "text", "narrative_role": "text_accent",
                "image_prompt": "blurred dark purple background",
                "text_content": "everything you believed",
                "sfx_hint": "text_appear",  # legal — text scene
            },
            {
                "index": 5, "type_of_scene": "image", "narrative_role": "buildup",
                "image_prompt": "medium shot of particle storm intensifying",
                "sfx_hint": None,
            },
            {
                "index": 6, "type_of_scene": "image", "narrative_role": "transition",
                "image_prompt": "extreme-close-up of glowing core pulsing brighter",
                "sfx_hint": "tension_riser",
            },
            {
                "index": 7, "type_of_scene": "image", "narrative_role": "peak",
                "image_prompt": "wide shot of figure dissolving into starlight",
                "sfx_hint": "bass_drop_impact",
            },
        ],
        "style": "stickman_glow",
        "total_duration": 58,
        "analysis": {
            "visual_style": "stickman_glow",
            "category": "philosophy",
            "story_tone": "dramatic",
        },
    }

    result = finalize_scene_result(
        fake_llm_result, scene_blueprints=[], visual_bible={}
    )
    sfx_report = result.get("sfx_report", {})
    check("finalize_scene_result returned sfx_report",
          isinstance(sfx_report, dict))
    check("hint count is within budget",
          sfx_report.get("hint_count", 0) <= sfx_report.get("hint_max", 4),
          f"count={sfx_report.get('hint_count')}, max={sfx_report.get('hint_max')}")

    # Verify the legal stack survived
    riser_kept = result["scenes"][6].get("sfx_hint") == "tension_riser"
    impact_kept = result["scenes"][7].get("sfx_hint") == "bass_drop_impact"
    check("legal riser->impact stack preserved",
          riser_kept and impact_kept,
          f"riser={riser_kept}, impact={impact_kept}")

    # Verify the text hint on the text scene survived
    text_hint_kept = result["scenes"][4].get("sfx_hint") == "text_appear"
    check("text_appear on text scene preserved", text_hint_kept)

    section("STAGE 4: Validator catches abuse")

    # Now feed it intentionally bad data to make sure the rules fire
    bad_llm_result = {
        "scenes": [
            {"index": 0, "type_of_scene": "image", "sfx_hint": "church_bells"},  # unknown
            {"index": 1, "type_of_scene": "image", "sfx_hint": "cartoon_pop"},   # comedy on dramatic
            {"index": 2, "type_of_scene": "image", "sfx_hint": "text_appear"},   # text on image
            {"index": 3, "type_of_scene": "image", "sfx_hint": "bass_drop_impact"},
            {"index": 4, "type_of_scene": "image", "sfx_hint": "bass_drop_impact"},  # dup
            {"index": 5, "type_of_scene": "image", "sfx_hint": "bass_drop_impact"},  # dup
        ],
        "style": "stickman_glow",
        "total_duration": 58,
        "analysis": {"visual_style": "stickman_glow", "category": "philosophy",
                     "story_tone": "dramatic"},
    }
    bad_result = finalize_scene_result(
        bad_llm_result, scene_blueprints=[], visual_bible={}
    )
    bad_report = bad_result.get("sfx_report", {})
    drops = bad_report.get("dropped", [])
    drop_reasons = {d["reason"] for d in drops}

    check("unknown hint dropped",
          "unknown_hint" in drop_reasons)
    check("comedy-on-dramatic dropped",
          "comedy_only_on_non_comedy" in drop_reasons)
    check("text-on-image dropped",
          "text_hint_on_non_text_scene" in drop_reasons)
    check("duplicate bass_drop_impact dropped",
          "duplicate_unique_hint" in drop_reasons)

    # Final state: only the LAST bass_drop survives, everything else gone
    final_hints = [s.get("sfx_hint") for s in bad_result["scenes"]]
    check("only the last bass_drop survives",
          final_hints == [None, None, None, None, None, "bass_drop_impact"],
          f"final: {final_hints}")

    section("STAGE 5: Placer turns hints into real audio tracks")

    from studio.editor.routes import _build_per_scene_sfx_tracks

    # Build editor scenes from the GOOD validated result
    editor_scenes = []
    cumulative = 0.0
    for i, s in enumerate(result["scenes"]):
        # Synthetic durations roughly matching a 58-second video
        duration = [3, 6, 7, 8, 4, 7, 9, 14][i]
        editor_scenes.append({
            "id": i,
            "duration": duration,
            "timestamp": cumulative,
            "sfx_hint": s.get("sfx_hint"),
            "type": s.get("type_of_scene", "image"),
        })
        cumulative += duration

    raw_scenes_for_placer = result["scenes"]
    tracks, history = _build_per_scene_sfx_tracks(
        editor_scenes, raw_scenes_for_placer, []
    )

    check("placer returned tracks",
          isinstance(tracks, list) and len(tracks) > 0,
          f"{len(tracks)} tracks")

    # The fake LLM output has 5 hints (magic_shimmer, heartbeat_pulse,
    # text_appear, tension_riser, bass_drop_impact). The validator's budget
    # cap is 4, so it drops the lowest-priority hint — magic_shimmer
    # (priority 8) — leaving 4 hints to reach the placer. The placer then
    # gracefully degrades text_appear because the text_scene/ folder is
    # empty (documented behavior). Final: 3 audible tracks.
    #
    # This stage exercises BOTH the budget enforcement AND the graceful
    # degradation in a single end-to-end pass — the most realistic scenario.
    expected_track_count = 3
    check(f"placer built {expected_track_count} audible tracks",
          len(tracks) == expected_track_count,
          f"got {len(tracks)}, expected {expected_track_count} "
          f"(magic_shimmer dropped by budget cap, text_appear silently degraded)")

    # Confirm magic_shimmer was actually dropped by the validator's budget pass
    drops_in_good_run = result.get("sfx_report", {}).get("dropped", [])
    over_budget_drops = [d for d in drops_in_good_run if d.get("reason") == "over_budget"]
    check("validator dropped magic_shimmer via budget cap",
          any(d.get("hint") == "magic_shimmer" for d in over_budget_drops),
          f"over_budget drops: {[(d['hint'], d['scene_index']) for d in over_budget_drops]}")

    # Spot-check key track properties
    if tracks:
        track_by_hint = {t.get("sfx_hint"): t for t in tracks}

        # All surviving tracks should point at real assets
        for t in tracks:
            check(f"{t['sfx_hint']} points at /assets/sounds/sfx/ URL",
                  t["path"].startswith("/assets/sounds/sfx/"))

        # heartbeat_pulse: scene 2 starts at 3+6=9, plays for 7 seconds
        if "heartbeat_pulse" in track_by_hint:
            t = track_by_hint["heartbeat_pulse"]
            check("heartbeat_pulse at scene 2 start (9.0s)",
                  t["timelineOffset"] == 9.0)
            check("heartbeat_pulse is looped",
                  t["loop"] is True)
            check("heartbeat_pulse trimmed to scene length",
                  t["trimmedDuration"] == 7.0)

        # tension_riser: scene 6 starts at 3+6+7+8+4+7=35, lead_in 1.0s -> 34.0
        if "tension_riser" in track_by_hint:
            t = track_by_hint["tension_riser"]
            check("tension_riser fires BEFORE scene 6 start (lead_in)",
                  t["timelineOffset"] < 35.0,
                  f"offset={t['timelineOffset']}")
            check("tension_riser offset is 34.0s exactly",
                  t["timelineOffset"] == 34.0)

        # bass_drop_impact: scene 7 starts at 35+9=44
        if "bass_drop_impact" in track_by_hint:
            t = track_by_hint["bass_drop_impact"]
            check("bass_drop_impact at scene 7 start (44.0s)",
                  t["timelineOffset"] == 44.0)
            check("bass_drop_impact label is BASS DROP",
                  t["label"] == "BASS DROP")

    # All tracks have history entries (so subsequent picks would dedup)
    check("history grew with each pick",
          len(history) == len(tracks),
          f"history has {len(history)} entries")

    # All track files actually exist on disk
    missing_files = []
    for t in tracks:
        rel = t["path"].replace("/assets/", "resources/").replace("/", os.sep)
        if not os.path.isfile(rel):
            missing_files.append(rel)
    check("all picked files exist on disk",
          not missing_files, f"missing: {missing_files}" if missing_files else "")

    section("STAGE 6: Graceful degradation when folders are empty")

    # text_appear should silently skip because text_scene/ is empty
    text_only_editor = [
        {"id": 0, "duration": 3.0, "timestamp": 0.0, "type": "text"}
    ]
    text_only_raw = [{"index": 0, "type_of_scene": "text", "sfx_hint": "text_appear"}]
    text_tracks, _ = _build_per_scene_sfx_tracks(text_only_editor, text_only_raw, [])
    check("text_appear silently skipped when text_scene/ is empty",
          len(text_tracks) == 0,
          f"got {len(text_tracks)} tracks (expected 0)")

    # silence hint produces no track
    silence_editor = [{"id": 0, "duration": 3.0, "timestamp": 0.0, "type": "image"}]
    silence_raw = [{"index": 0, "sfx_hint": "silence"}]
    silence_tracks, _ = _build_per_scene_sfx_tracks(silence_editor, silence_raw, [])
    check("silence hint produces no track",
          len(silence_tracks) == 0)

    # Empty input doesn't crash
    empty_tracks, _ = _build_per_scene_sfx_tracks([], [], [])
    check("empty input doesn't crash",
          empty_tracks == [])

    section("STAGE 7: Vocabulary file integrity")

    # Re-verify against the live vocabulary that every entry maps to
    # at least one real file (or has a fallback that does, or is silence)
    import re
    sfx_root = os.path.join("resources", "sounds", "sfx")
    integrity_issues = []
    for hid, entry in hints.items():
        if hid == "silence":
            continue
        folder = entry.get("folder")
        if not folder:
            integrity_issues.append(f"{hid}: no folder")
            continue
        folder_path = os.path.join(sfx_root, folder)
        if not os.path.isdir(folder_path):
            integrity_issues.append(f"{hid}: folder {folder}/ does not exist")
            continue
        files = [
            f for f in os.listdir(folder_path)
            if f.lower().endswith((".mp3", ".wav", ".ogg", ".m4a", ".flac"))
        ]
        pattern = entry.get("filename_match")
        if pattern:
            regex = re.compile(pattern, re.IGNORECASE)
            matches = [f for f in files if regex.search(f)]
            if not matches:
                fallback = entry.get("fallback_folder")
                if fallback:
                    fb_path = os.path.join(sfx_root, fallback)
                    if os.path.isdir(fb_path):
                        fb_files = [
                            f for f in os.listdir(fb_path)
                            if f.lower().endswith((".mp3", ".wav", ".ogg", ".m4a", ".flac"))
                        ]
                        fb_matches = [f for f in fb_files if regex.search(f)]
                        if not fb_matches:
                            # Both empty/no-match — this is the text_scene case
                            # which is intentionally empty until user populates it
                            if folder == "text_scene":
                                continue  # acceptable, documented
                            integrity_issues.append(
                                f"{hid}: no matches in {folder}/ or fallback {fallback}/"
                            )
                else:
                    if folder == "text_scene":
                        continue
                    integrity_issues.append(
                        f"{hid}: pattern matches nothing in {folder}/, no fallback"
                    )
        else:
            if not files:
                if folder == "text_scene":
                    continue
                integrity_issues.append(f"{hid}: folder {folder}/ is empty")

    check("all hints map to at least one real file (or text_scene exception)",
          not integrity_issues,
          f"issues: {integrity_issues}" if integrity_issues else "")

    # ── Final summary ────────────────────────────────────────────────────
    print()
    print("=" * 70)
    if _failures:
        print(f"  SMOKE TEST FAILED — {len(_failures)} check(s) failed:")
        for f in _failures:
            print(f"    - {f}")
        print("=" * 70)
        return 1
    else:
        print("  SMOKE TEST PASSED — all stages green")
        print("=" * 70)
        return 0


if __name__ == "__main__":
    sys.exit(main())
