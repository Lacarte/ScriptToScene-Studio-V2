# Story Length Report

## Formula

From `studio/story/prompts.py`: **2.5 words per second** of narration.

```
word_target = duration_seconds × 2.5
```

## Character Estimates

Assuming ~5 characters per word (English average):

| Duration | Words | ~Characters |
|----------|-------|-------------|
| **15s** (min) | 38 | ~190 |
| **30s** | 75 | ~375 |
| **45s** (default) | 113 | ~563 |
| **60s** (most niches) | 150 | ~750 |
| **90s** (some niches) | 225 | ~1,125 |
| **180s** (max) | 450 | ~2,250 |

## Niche Preset Defaults

Most niche presets in `studio/niches/presets.py` use **60s duration**, with a few at **90s** and one at **30s**.

## Summary

- **Average story: ~750–1,125 characters** (150–225 words), targeting 60–90 second narrations.
- Allowed range (`studio/story/schemas.py`): 15–180 seconds, default 45 seconds (~563 characters).
