"""Synthetic end-to-end tests for studio.build_scene_blueprints.sfx_validator.

Run with: python _dev/test_sfx_validator.py
"""

from studio.build_scene_blueprints.sfx_validator import (
    load_sfx_vocabulary,
    validate_and_enforce_sfx,
    _allowed_hint_keys,
)


def fmt_final(scenes):
    return [(s.get("index"), s.get("sfx_hint")) for s in scenes if s.get("sfx_hint")]


def main():
    vocab = load_sfx_vocabulary()
    keys = _allowed_hint_keys()
    print(f"vocab loaded: version={vocab.get('version')}, hints={len(keys)}")
    print()

    # ── Test 1: clean case ───────────────────────────────────────────────
    print("TEST 1: clean 3-hint video (no rules broken)")
    scenes = [
        {"index": 0, "type": "image", "sfx_hint": "magic_shimmer"},
        {"index": 1, "type": "image", "sfx_hint": None},
        {"index": 2, "type": "image", "sfx_hint": None},
        {"index": 3, "type": "image", "sfx_hint": "tension_riser"},
        {"index": 4, "type": "image", "sfx_hint": "bass_drop_impact"},
    ]
    r = validate_and_enforce_sfx(scenes, visual_style="cinematic", total_duration_seconds=58)
    print(f"  hint_count={r['hint_count']}, dropped={len(r['dropped'])}, warnings={r['warnings']}")
    print(f"  final: {fmt_final(scenes)}")
    assert r["hint_count"] == 3, "expected 3 hints retained"
    assert not r["dropped"], "expected no drops"
    print("  PASS")
    print()

    # ── Test 2: unknown hint ─────────────────────────────────────────────
    print("TEST 2: unknown hint hallucinated by LLM")
    scenes = [
        {"index": 0, "type": "image", "sfx_hint": "church_bells"},
        {"index": 1, "type": "image", "sfx_hint": "magic_shimmer"},
    ]
    r = validate_and_enforce_sfx(scenes, visual_style="cinematic", total_duration_seconds=58)
    print(f"  dropped={r['dropped']}")
    assert r["hint_count"] == 1
    assert r["dropped"][0]["reason"] == "unknown_hint"
    print("  PASS")
    print()

    # ── Test 3: comedy hint on non-comedy ────────────────────────────────
    print("TEST 3: cartoon_pop + crowd_laugh on dramatic content (both drop)")
    scenes = [
        {"index": 0, "type": "image", "sfx_hint": "cartoon_pop"},
        {"index": 1, "type": "image", "sfx_hint": "crowd_laugh"},
    ]
    r = validate_and_enforce_sfx(
        scenes, visual_style="stickman_glow", category="philosophy",
        story_tone="dramatic", total_duration_seconds=58,
    )
    print(f"  dropped={r['dropped']}")
    assert r["hint_count"] == 0
    assert all(d["reason"] == "comedy_only_on_non_comedy" for d in r["dropped"])
    print("  PASS")
    print()

    # ── Test 4: comedy hint on actual comedy (should keep) ───────────────
    print("TEST 4: cartoon_pop on stickman_animation comedy (legal)")
    scenes = [{"index": 0, "type": "image", "sfx_hint": "cartoon_pop"}]
    r = validate_and_enforce_sfx(
        scenes, visual_style="stickman_animation", category="comedy",
        story_tone="comedic", total_duration_seconds=58,
    )
    print(f"  hint_count={r['hint_count']}, dropped={len(r['dropped'])}")
    assert r["hint_count"] == 1
    print("  PASS")
    print()

    # ── Test 5: text hint on non-text scene ──────────────────────────────
    print("TEST 5: text_appear on image scene (illegal) + on text scene (legal)")
    scenes = [
        {"index": 0, "type": "image", "sfx_hint": "text_appear"},
        {"index": 1, "type": "text", "sfx_hint": "text_appear"},
    ]
    r = validate_and_enforce_sfx(scenes, visual_style="cinematic", total_duration_seconds=58)
    print(f"  dropped={r['dropped']}")
    print(f"  final: {fmt_final(scenes)}")
    assert r["hint_count"] == 1
    assert r["dropped"][0]["reason"] == "text_hint_on_non_text_scene"
    assert scenes[1]["sfx_hint"] == "text_appear"
    print("  PASS")
    print()

    # ── Test 6: duplicate bass_drop_impact ───────────────────────────────
    print("TEST 6: bass_drop_impact appears 3 times (should keep last only)")
    scenes = [
        {"index": 0, "type": "image", "sfx_hint": "bass_drop_impact"},
        {"index": 1, "type": "image", "sfx_hint": None},
        {"index": 2, "type": "image", "sfx_hint": "bass_drop_impact"},
        {"index": 3, "type": "image", "sfx_hint": None},
        {"index": 4, "type": "image", "sfx_hint": "bass_drop_impact"},
    ]
    r = validate_and_enforce_sfx(scenes, visual_style="cinematic", total_duration_seconds=58)
    print(f"  hint_count={r['hint_count']}, final: {fmt_final(scenes)}")
    assert r["hint_count"] == 1
    assert scenes[4]["sfx_hint"] == "bass_drop_impact"
    assert scenes[0]["sfx_hint"] is None
    assert scenes[2]["sfx_hint"] is None
    print("  PASS")
    print()

    # ── Test 7: consecutive collision rules ─────────────────────────────
    print("TEST 7: legal riser->impact survives, illegal whoosh->hit drops second")
    scenes = [
        {"index": 0, "type": "image", "sfx_hint": "tension_riser"},
        {"index": 1, "type": "image", "sfx_hint": "bass_drop_impact"},
        {"index": 2, "type": "image", "sfx_hint": None},
        {"index": 3, "type": "image", "sfx_hint": "whoosh_transition"},
        {"index": 4, "type": "image", "sfx_hint": "cinematic_hit"},
    ]
    r = validate_and_enforce_sfx(scenes, visual_style="cinematic", total_duration_seconds=58)
    print(f"  hint_count={r['hint_count']}, final: {fmt_final(scenes)}")
    assert scenes[0]["sfx_hint"] == "tension_riser"
    assert scenes[1]["sfx_hint"] == "bass_drop_impact"
    assert scenes[3]["sfx_hint"] == "whoosh_transition"
    assert scenes[4]["sfx_hint"] is None  # dropped due to consecutive collision
    print("  PASS")
    print()

    # ── Test 8: over budget — 7 hints, cap=4 ─────────────────────────────
    # The consecutive pass runs first and resolves adjacency:
    #   (0,1) magic+whoosh        → drop whoosh (the second)
    #   (1,2) null+click          → skip
    #   (2,3) click+noti          → drop noti (the second)
    #   (3,4) null+riser          → skip
    #   (4,5) riser+bass          → LEGAL stack, keep both
    #   (5,6) bass+camera         → drop camera (the second)
    # After consecutive: magic, click, riser, bass = 4 hints — exactly at cap
    # Budget pass: 4 == 4, no drops
    # Final: magic, click, riser, bass (4 hits, chronologically distributed)
    #
    # Note: click_confirm survives despite being lowest priority, because
    # it landed in a gap left by the consecutive pass. This is the documented
    # trade-off — pass order favors legal-stack preservation and chronology
    # over global priority optimization.
    print("TEST 8: over budget (7 hints on 58s, cap=4)")
    scenes = [
        {"index": 0, "type": "image", "sfx_hint": "magic_shimmer"},      # priority 8
        {"index": 1, "type": "image", "sfx_hint": "whoosh_transition"},  # priority 18
        {"index": 2, "type": "image", "sfx_hint": "click_confirm"},      # priority 3
        {"index": 3, "type": "image", "sfx_hint": "notification_ding"},  # priority 4
        {"index": 4, "type": "image", "sfx_hint": "tension_riser"},      # priority 40
        {"index": 5, "type": "image", "sfx_hint": "bass_drop_impact"},   # priority 50
        {"index": 6, "type": "image", "sfx_hint": "camera_shutter"},     # priority 5
    ]
    r = validate_and_enforce_sfx(scenes, visual_style="cinematic", total_duration_seconds=58)
    print(f"  hint_count={r['hint_count']}, dropped={[d['hint'] for d in r['dropped']]}")
    print(f"  final: {fmt_final(scenes)}")
    dropped_hints = {d["hint"] for d in r["dropped"]}
    assert "whoosh_transition" in dropped_hints
    assert "notification_ding" in dropped_hints
    assert "camera_shutter" in dropped_hints
    # The narrative skeleton survives intact
    assert scenes[0]["sfx_hint"] == "magic_shimmer"
    assert scenes[4]["sfx_hint"] == "tension_riser"
    assert scenes[5]["sfx_hint"] == "bass_drop_impact"
    assert r["hint_count"] == 4
    print("  PASS")
    print()

    # ── Test 9: short video gets tighter cap ─────────────────────────────
    print("TEST 9: 25s video (cap=3 instead of 4)")
    scenes = [
        {"index": 0, "type": "image", "sfx_hint": "magic_shimmer"},
        {"index": 1, "type": "image", "sfx_hint": "whoosh_transition"},
        {"index": 2, "type": "image", "sfx_hint": "tension_riser"},
        {"index": 3, "type": "image", "sfx_hint": "bass_drop_impact"},
    ]
    r = validate_and_enforce_sfx(scenes, visual_style="cinematic", total_duration_seconds=25)
    print(f"  hint_max={r['hint_max']}, hint_count={r['hint_count']}, dropped={len(r['dropped'])}")
    assert r["hint_max"] == 3
    assert r["hint_count"] == 3
    print("  PASS")
    print()

    # ── Test 10: under-budget warning ────────────────────────────────────
    print("TEST 10: only 1 hint on 8 scenes (under floor of 3)")
    scenes = [{"index": i, "type": "image", "sfx_hint": None} for i in range(8)]
    scenes[4]["sfx_hint"] = "cinematic_hit"
    r = validate_and_enforce_sfx(scenes, visual_style="cinematic", total_duration_seconds=58)
    print(f"  hint_count={r['hint_count']}, warnings={r['warnings']}")
    assert any("under-budget" in w for w in r["warnings"])
    print("  PASS")
    print()

    print("=" * 60)
    print("ALL 10 TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
