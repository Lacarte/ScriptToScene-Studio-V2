# Music Analysis & Auto-Classification

Librosa-based audio analysis for categorizing background music tracks.

## How It Works

1. **Analyze** all music files using `librosa` — extracts:
   - Tempo (BPM)
   - RMS energy (loudness)
   - Spectral centroid (brightness)
   - Zero-crossing rate (noisiness/aggression)
   - Spectral rolloff, contrast, MFCCs, chroma

2. **Classify** using a hybrid approach:
   - **Name anchors**: keywords like "slowed", "phonk", "meditation" override audio
   - **Audio features**: thresholds for each category based on extracted features
   - **Fallback**: tracks that don't match any strong signal go to `viral-lofi`

## Categories

| Category       | Audio Profile                                       |
|----------------|-----------------------------------------------------|
| `ambient`      | Very quiet (rms < 0.05), low brightness, calm       |
| `dark`         | Loud (rms > 0.22) + bright (centroid > 1500)        |
| `cinematic`    | Mid-high centroid, moderate energy, complex harmonic |
| `happy`        | Bright (centroid > 2000), energetic, high zcr        |
| `viral-slowed` | Has "slowed/reverb" in name, dreamy features         |
| `viral-lofi`   | Moderate features, chill beats, indie (fallback)     |
| `viral-hiphop` | Very loud + bassy (low centroid < 500)               |

## Usage

```bash
# One-time setup (not included in project requirements)
pip install librosa

# Re-run analysis on all music files
python _dev/music-analysis/analyze.py              # dry run
python _dev/music-analysis/analyze.py --apply      # analyze + move files
```

## Files

- `_analysis.json` — raw feature data for each track
- `analyze.py` — standalone script to re-run analysis + classification
