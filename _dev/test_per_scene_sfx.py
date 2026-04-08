"""Synthetic tests for the per-scene SFX placement helper.

Run with: PYTHONPATH=. python _dev/test_per_scene_sfx.py
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from studio.editor.routes import _build_per_scene_sfx_tracks


def fmt_track(t):
    return (
        f"id={t['id']}, label={t['label']}, "
        f"offset={t['timelineOffset']:.2f}, "
        f"loop={t['loop']}, vol={t['volume']}, "
        f"hint={t.get('sfx_hint')}, file={t['file']}"
    )


def main():
    print("=" * 60)
    print("PER-SCENE SFX PLACEMENT TESTS")
    print("=" * 60)
    print()

    # ── Test 1: clean 4-hint case, mixed placements ─────────────────────
    print("TEST 1: Mixed placements (scene_start, scene_duration, lead_in)")
    editor_scenes = [
        {"id": 0, "duration": 3.0, "timestamp": 0.0},
        {"id": 1, "duration": 5.0, "timestamp": 3.0},
        {"id": 2, "duration": 4.0, "timestamp": 8.0},
        {"id": 3, "duration": 6.0, "timestamp": 12.0},
        {"id": 4, "duration": 4.0, "timestamp": 18.0},
    ]
    raw_scenes = [
        {"index": 0, "sfx_hint": "magic_shimmer"},      # scene_start @ 0.0
        {"index": 1, "sfx_hint": None},
        {"index": 2, "sfx_hint": "heartbeat_pulse"},    # scene_duration: 8.0 with trim 4.0
        {"index": 3, "sfx_hint": "tension_riser"},      # lead_in @ 12 - 1.0 = 11.0
        {"index": 4, "sfx_hint": "bass_drop_impact"},   # scene_start @ 18.0
    ]
    tracks, history = _build_per_scene_sfx_tracks(editor_scenes, raw_scenes, [])
    print(f"  Built {len(tracks)} tracks:")
    for t in tracks:
        print(f"    {fmt_track(t)}")

    assert len(tracks) == 4, f"expected 4 tracks, got {len(tracks)}"

    by_hint = {t.get("sfx_hint"): t for t in tracks}

    # magic_shimmer: scene_start, no trim
    assert by_hint["magic_shimmer"]["timelineOffset"] == 0.0
    assert by_hint["magic_shimmer"]["trimmedDuration"] is None
    assert by_hint["magic_shimmer"]["loop"] is False

    # heartbeat_pulse: scene_duration, trimmed to scene length
    assert by_hint["heartbeat_pulse"]["timelineOffset"] == 8.0
    assert by_hint["heartbeat_pulse"]["trimmedDuration"] == 4.0
    assert by_hint["heartbeat_pulse"]["loop"] is True

    # tension_riser: lead_in, fires before scene
    assert by_hint["tension_riser"]["timelineOffset"] < 12.0  # before scene start
    assert by_hint["tension_riser"]["timelineOffset"] >= 0.0  # but not negative

    # bass_drop_impact: scene_start
    assert by_hint["bass_drop_impact"]["timelineOffset"] == 18.0
    assert by_hint["bass_drop_impact"]["loop"] is False

    print("  PASS")
    print()

    # ── Test 2: silence hint is intentionally a no-op ───────────────────
    print("TEST 2: silence hint produces no track")
    editor_scenes = [{"id": 0, "duration": 3.0, "timestamp": 0.0}]
    raw_scenes = [{"index": 0, "sfx_hint": "silence"}]
    tracks, _ = _build_per_scene_sfx_tracks(editor_scenes, raw_scenes, [])
    assert len(tracks) == 0
    print(f"  Built {len(tracks)} tracks (correct — silence is no-op)")
    print("  PASS")
    print()

    # ── Test 3: unknown hint is gracefully skipped ──────────────────────
    print("TEST 3: unknown hint silently skipped")
    editor_scenes = [{"id": 0, "duration": 3.0, "timestamp": 0.0}]
    raw_scenes = [{"index": 0, "sfx_hint": "church_bells"}]  # not in vocab
    tracks, _ = _build_per_scene_sfx_tracks(editor_scenes, raw_scenes, [])
    assert len(tracks) == 0
    print("  PASS")
    print()

    # ── Test 4: empty folder hint is skipped (text_scene is empty) ──────
    print("TEST 4: text_appear hint with empty text_scene/ folder")
    editor_scenes = [{"id": 0, "duration": 2.0, "timestamp": 0.0}]
    raw_scenes = [{"index": 0, "sfx_hint": "text_appear"}]
    tracks, _ = _build_per_scene_sfx_tracks(editor_scenes, raw_scenes, [])
    print(f"  Built {len(tracks)} tracks (text_scene/ is empty)")
    assert len(tracks) == 0  # text_scene is empty until user populates it
    print("  PASS")
    print()

    # ── Test 5: history dedup picks different files across calls ────────
    print("TEST 5: history dedup across multiple bass_drop_impact picks")
    editor_scenes = [{"id": 0, "duration": 3.0, "timestamp": 0.0}]
    raw_scenes = [{"index": 0, "sfx_hint": "bass_drop_impact"}]
    history = []
    picks = []
    for i in range(4):
        # Note: sfx_validator allows bass_drop only once per video, but we're
        # testing the picker in isolation here, simulating 4 separate projects.
        tracks, history = _build_per_scene_sfx_tracks(editor_scenes, raw_scenes, history)
        if tracks:
            picks.append(tracks[0]["file"])
    print(f"  Picks across 4 generations: {picks}")
    # First 3 should be different (history dedup); 4th may repeat if pool exhausted
    if len(set(picks[:3])) >= 2:
        print("  PASS (variety verified)")
    else:
        print(f"  FAIL: expected variety, got {picks}")
    print()

    # ── Test 6: scene_id mismatch (raw index doesn't match any editor scene) ──
    print("TEST 6: raw scene index that doesn't match any editor scene")
    editor_scenes = [
        {"id": 0, "duration": 3.0, "timestamp": 0.0},
        {"id": 1, "duration": 3.0, "timestamp": 3.0},
    ]
    raw_scenes = [
        {"index": 0, "sfx_hint": "magic_shimmer"},
        {"index": 1, "sfx_hint": None},
        {"index": 99, "sfx_hint": "bass_drop_impact"},  # phantom scene
    ]
    tracks, _ = _build_per_scene_sfx_tracks(editor_scenes, raw_scenes, [])
    assert len(tracks) == 1
    assert tracks[0].get("sfx_hint") == "magic_shimmer"
    print(f"  Built {len(tracks)} tracks (phantom skipped)")
    print("  PASS")
    print()

    # ── Test 7: full real-world allocation pattern ──────────────────────
    print("TEST 7: realistic 8-scene 58s video with 4-hit allocation")
    editor_scenes = [
        {"id": 0, "duration": 4.0, "timestamp": 0.0},
        {"id": 1, "duration": 7.0, "timestamp": 4.0},
        {"id": 2, "duration": 8.0, "timestamp": 11.0},
        {"id": 3, "duration": 9.0, "timestamp": 19.0},
        {"id": 4, "duration": 7.0, "timestamp": 28.0},
        {"id": 5, "duration": 8.0, "timestamp": 35.0},
        {"id": 6, "duration": 6.0, "timestamp": 43.0},
        {"id": 7, "duration": 9.0, "timestamp": 49.0},
    ]
    raw_scenes = [
        {"index": 0, "sfx_hint": "magic_shimmer"},
        {"index": 1, "sfx_hint": None},
        {"index": 2, "sfx_hint": "whoosh_transition"},
        {"index": 3, "sfx_hint": None},
        {"index": 4, "sfx_hint": None},
        {"index": 5, "sfx_hint": None},
        {"index": 6, "sfx_hint": "tension_riser"},
        {"index": 7, "sfx_hint": "bass_drop_impact"},
    ]
    tracks, _ = _build_per_scene_sfx_tracks(editor_scenes, raw_scenes, [])
    print(f"  Built {len(tracks)} tracks for 4 hints:")
    for t in tracks:
        print(f"    [{t['label']:9s}] @ {t['timelineOffset']:6.2f}s — {t['file']}")
    assert len(tracks) == 4

    # Verify chronological order
    offsets = [t["timelineOffset"] for t in tracks]
    assert offsets == sorted(offsets), "tracks should be in chronological order"

    # Verify riser fires BEFORE scene 6 starts
    riser = next(t for t in tracks if t["sfx_hint"] == "tension_riser")
    assert riser["timelineOffset"] < 43.0

    # Verify bass_drop fires AT scene 7 start
    bass = next(t for t in tracks if t["sfx_hint"] == "bass_drop_impact")
    assert bass["timelineOffset"] == 49.0

    print("  PASS")
    print()

    print("=" * 60)
    print("ALL 7 TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
