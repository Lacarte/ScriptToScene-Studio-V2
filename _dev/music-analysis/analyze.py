"""
Music analysis & auto-classification using librosa.

Analyzes all tracks in resources/sounds/music/ and optionally
reclassifies them into the correct category subfolder.

Usage:
    python _dev/music-analysis/analyze.py              # analyze only
    python _dev/music-analysis/analyze.py --apply      # analyze + move files
"""

import argparse
import json
import pathlib
import shutil
import warnings

import librosa
import numpy as np

warnings.filterwarnings("ignore")

MUSIC_ROOT = pathlib.Path(__file__).resolve().parents[2] / "resources" / "sounds" / "music"
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}
OUTPUT_FILE = pathlib.Path(__file__).resolve().parent / "_analysis.json"


def analyze_track(path: pathlib.Path) -> dict | None:
    """Extract audio features from a single track."""
    try:
        y, sr = librosa.load(str(path), sr=22050, duration=60, offset=15)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        tempo = float(np.atleast_1d(tempo)[0])

        return {
            "file": path.name,
            "tempo": round(tempo, 1),
            "rms": round(float(np.mean(librosa.feature.rms(y=y))), 5),
            "centroid": round(float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))), 1),
            "zcr": round(float(np.mean(librosa.feature.zero_crossing_rate(y=y))), 5),
            "rolloff": round(float(np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr))), 1),
            "contrast": round(float(np.mean(librosa.feature.spectral_contrast(y=y, sr=sr))), 1),
            "chroma_std": round(float(np.std(librosa.feature.chroma_stft(y=y, sr=sr))), 4),
            "mfcc1": round(float(np.mean(librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)[0])), 1),
        }
    except Exception as e:
        print(f"  FAIL: {path.name}: {e}")
        return None


def classify(t: dict) -> tuple[str, str]:
    """Hybrid classifier: audio features + name heuristics."""
    tempo, rms, centroid, zcr = t["tempo"], t["rms"], t["centroid"], t["zcr"]
    name = t["file"].lower()

    # --- Strong name anchors ---
    if any(w in name for w in ["happy", "comedy", "kids-", "optimistic", "upbeat"]):
        return "happy", "name"
    if any(w in name for w in ["religion", "religious", "biblical", "sacred"]):
        return "religion", "name"
    if any(w in name for w in ["meditation", "sound bath", "calm", "healing", "drone", "angelic", "choir"]):
        return "ambient", "name"
    if any(w in name for w in ["kendrick", "carti", "peep", "xxx", "lil-"]):
        return "viral-hiphop", "name"
    if any(w in name for w in ["orchestral", "classical", "inspiring-flight", "ivory and iron", "rising current"]):
        return "cinematic", "name"
    if any(w in name for w in ["suspense", "suspenseful", "terror"]):
        return "dark", "name"

    has_slowed = any(w in name for w in ["slowed", "reverb", "muffled"])
    has_phonk = "phonk" in name

    if has_phonk:
        return ("dark", "phonk-loud") if rms > 0.35 else ("viral-slowed", "phonk")

    if has_slowed:
        if rms > 0.35 and centroid > 1400:
            return "dark", "slowed-but-aggressive"
        return "viral-slowed", "slowed-name"

    # --- Pure audio ---
    if rms < 0.05 and centroid < 1000:
        return "ambient", "audio-quiet"
    if rms < 0.08 and centroid < 800 and zcr < 0.04:
        return "ambient", "audio-calm"
    if rms > 0.22 and centroid > 1500:
        return "dark", "audio-aggressive"
    if rms > 0.18 and centroid > 1600 and zcr > 0.04:
        return "dark", "audio-tense"
    if rms > 0.30 and centroid < 500:
        return "viral-hiphop", "audio-bass-heavy"
    if centroid > 2000 and rms > 0.15 and zcr > 0.07:
        return "happy", "audio-bright-energetic"
    if centroid > 1300 and rms > 0.08 and rms < 0.20 and zcr > 0.05:
        return "cinematic", "audio-cinematic"
    if 0 < tempo < 75 and centroid < 500 and 0.08 < rms < 0.22:
        return "viral-slowed", "audio-slow-dreamy"

    return "viral-lofi", "fallback"


def main():
    parser = argparse.ArgumentParser(description="Analyze and classify music tracks")
    parser.add_argument("--apply", action="store_true", help="Apply reclassifications (move files)")
    args = parser.parse_args()

    results = []
    for d in sorted(MUSIC_ROOT.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        for f in sorted(d.iterdir()):
            if f.suffix.lower() not in AUDIO_EXTS:
                continue
            print(f"Analyzing [{d.name}] {f.name}...")
            features = analyze_track(f)
            if features:
                features["current_cat"] = d.name
                features["path"] = str(f)
                results.append(features)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fp:
        json.dump(results, fp, indent=2, ensure_ascii=False)
    print(f"\nAnalyzed {len(results)} tracks -> {OUTPUT_FILE}")

    # Classify and report
    changes = []
    for t in results:
        suggested, reason = classify(t)
        if suggested != t["current_cat"]:
            changes.append({"file": t["file"], "from": t["current_cat"], "to": suggested,
                            "reason": reason, "path": t["path"]})

    if not changes:
        print("\nNo reclassifications needed.")
        return

    print(f"\n{'='*60}")
    print(f"SUGGESTED RECLASSIFICATIONS: {len(changes)}")
    print(f"{'='*60}")
    for c in sorted(changes, key=lambda x: (x["from"], x["to"])):
        print(f"  [{c['reason']}] {c['from']} -> {c['to']}: {c['file']}")

    if args.apply:
        moved = 0
        for c in changes:
            src = pathlib.Path(c["path"])
            dest_dir = MUSIC_ROOT / c["to"]
            dest_dir.mkdir(exist_ok=True)
            dest = dest_dir / src.name
            if not dest.exists() and src.exists():
                shutil.move(str(src), str(dest))
                moved += 1
        print(f"\nApplied {moved}/{len(changes)} moves.")
    else:
        print("\nDry run. Use --apply to move files.")


if __name__ == "__main__":
    main()
