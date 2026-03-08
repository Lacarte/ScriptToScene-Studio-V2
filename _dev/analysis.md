# Kie AI Image Generation — Project Analysis

## Project pp_OM4NYZ (Photorealistic / Watercolor)

**Story**: Memory reconstruction — "Every time you remember something, your brain doesn't play back a recording."

**Style selected**: Watercolor / Dreamlike
**Style actually sent to Kie AI**: Photorealistic (prompts were edited in UI before grabbing)
**Provider**: Kie AI (`nano-banana-2`) | Resolution: 1K | Format: JPG | Aspect: 9:16
**Scenes**: 8 generated, all status `ready`

### Scene-by-Scene Results

| Scene | Title | Prompt Key Elements | Result |
|-------|-------|-------------------|--------|
| 0 | Memory's Gentle Unfurling | Hand on leather journal + sepia photo + dust motes | Exact match — aged hand, leather journal, sepia photograph, visible dust particles in light |
| 1 | Fading Reel | Hand reaching for reel-to-reel recorder + photo under books | Exact match — model embellished with "Nostalgia" & "Memories" book titles |
| 2 | Reconstruction's Sketch | Quill pen + scattered notes + smoke from pen tip | Exact match — ink-stained hands, quill, handwritten notes, wisps of smoke |
| 3 | Story From Notes | Study with bookshelves + painting on wall + photo on corkboard | Exact match — wide shot, bookshelves, landscape painting, photo pinned to corkboard |
| 4 | Subtle Shifting Pigments | Over-shoulder, drawing on easel + lamp + photo on frame | Exact match — elderly artist sketching woman's portrait, sepia photo on easel |
| 5 | The Editing Hand | Hand holding up old photo showing childhood scene | Exact match — stunning result: torn photo of children, ink-stained fingers |
| 6 | Rewritten Childhood | Stack of copies of same photo, degrading | Exact match — stack of aged photographs, top one showing family |
| 7 | Echoes of Recall | Hand lowering faded photo onto books | Exact match — nearly blank faded photo being placed on old books |

### What Worked Well

- **Visual Consistency**: All 8 images maintain the same world — aged hands, warm sepia/amber lighting, wooden desk, old photographs, study environment
- **Prompt Adherence**: 9/10 — each scene faithfully rendered key elements from the photorealistic prompts sent
- **Shot Variety**: Good range — extreme-close-up, medium, close-up, wide, over-shoulder, centered, low-angle

### Issues Found

1. **Prompt vs Scene Mismatch**: The LLM generated watercolor dreamlike prompts (scenes.json), but the grabber sent photorealistic prompts (grabber_job.json). The watercolor style was never applied.
2. **Unwanted text in images**: Scene 1 has text on books: "Nostalgia", "Tape & Time", "Memories". The model hallucinated readable text.
3. **Hand anatomy**: Scene 3 (blurred foreground hand) has slightly unnatural pose. Minor.
4. **Resolution**: 1K may be slightly soft for 1080x1920 after pan/zoom effects.

### Score Card

| Dimension | Score | Notes |
|-----------|-------|-------|
| Prompt adherence | 9/10 | Extremely faithful to the photorealistic prompts sent |
| Visual consistency | 9/10 | Same world, lighting, character across all 8 |
| Shot variety | 8/10 | Good range, could use more extreme angles |
| Emotional impact | 9/10 | Scene 5 (torn photo) is genuinely moving |
| Technical quality | 7/10 | 1K resolution, minor text artifacts |
| Style fidelity | 5/10 | Watercolor style from LLM was never applied |

---

## Project pp_ZT5FEC (Comic Book Style)

**Story**: Mount Tambora eruption (1816) leads to "Year Without a Summer" which inspires Mary Shelley to write Frankenstein
**Style selected**: Comic Book
**Style actually sent to Kie AI**: Comic Book (prompts match scenes.json)
**Provider**: Kie AI (`nano-banana-2`) | Resolution: 1K | Format: JPG | Aspect: 9:16
**Scenes**: 10 generated, all status `ready`

### LLM Analysis Output

```json
{
  "mood": "dramatic tension, unexpected connections, historical awe",
  "environment": "contrasting scenes of volcanic aftermath and a gothic European villa",
  "color_palette": "ashy grey, dark teal, muted crimson, sepia, deep purple",
  "tone": "narrative, historical, slightly mysterious, revelatory",
  "visual_style": "comic_book style with bold lines, exaggerated expressions, dynamic paneling, and atmospheric cross-hatching",
  "recurring_motif": "a single, stylized lightning bolt appearing in dramatic moments",
  "character": "Mary Shelley, a young woman with dark, flowing hair, intense eyes, a Victorian gothic dress, and an ink-stained quill"
}
```

### Scene-by-Scene Results

| Scene | Title | Prompt Key Elements | Result |
|-------|-------|-------------------|--------|
| 0 | Fiery Genesis | Wide shot, Tambora erupting, villagers fleeing, lightning bolt, speed lines | Perfect — even added caption boxes and onomatopoeia ("BOOOM!", "KRA-TA-KOOM!") |
| 1 | Endless Winter | Twilight, barren fields, ash falling, farmers huddling | Perfect — haunting desolation, cross-hatching, caption "TWILIGHT OF ASH..." |
| 2 | Failed Harvests | Low-angle, withered crops, hands reaching, rain | Perfect — desperate hands reaching up through dying corn stalks |
| 3 | Famine's Shadow | Over-shoulder, gaunt horse, ragged figure, lightning | Perfect — emaciated horse, rain, lone figure with staff |
| 4 | Sheltered Muse | Wide shot, Mary Shelley at gothic window, Lake Geneva, Victorian dress | Exceptional — wallpaper detail, candles, storm through gothic arch window |
| 5 | The Spark of Creation | Close-up, lightning across face, candle, parchment | Outstanding — lightning bolt connecting to quill is brilliant composition |
| 6 | First Words | Extreme-close-up, quill on parchment, lightning on feather | Great — lightning emblem on feather, "Birth" written on page |
| 7 | Immortal Story | Mary holding Frankenstein pages, lightning radiating | Stunning — "FRANKENSTEIN: THE MODERN PROMETHEUS" on manuscript |
| 8 | Global Cascade | Split panel: Tambora left / Villa right, lightning connecting | Incredible — model understood "split panel" and executed perfectly with lightning-bolt divider |
| 9 | Season Erased | Desolate landscape, withered tree, lightning in distance | Clean atmospheric closer |

### What Worked Exceptionally Well

- **Style Fidelity: 10/10** — Every image has bold ink outlines, cross-hatching, comic panel borders, dynamic compositions, and even onomatopoeia text effects
- **Recurring Motif: 10/10** — The stylized lightning bolt appears in every single scene as requested
- **Character Consistency: 9/10** — Mary Shelley looks like the same person across scenes 4, 5, 6, 7 (dark hair, Victorian dress, quill). Remarkable without reference images
- **The Split Panel (Scene 8)** — The prompt asked for "a dynamic split panel showing Mount Tambora on one side and Mary Shelley's villa on the other, connected by a lightning bolt." Kie AI delivered this exactly, with a lightning-bolt-shaped divider and location captions

### Issues Found

1. **Text Hallucination** — Heavy but contextually fitting for comic style:
   - Scene 0: "MOUNT TAMBORA ERUPTED ON AN INDONESIAN ISLAND", "BOOOM!", "KRA-TA-KOOM!", "PANIC!"
   - Scene 1: "TWILIGHT OF ASH...", "DESPERATION GROWS"
   - Scene 6: "Birth", "Geneva"
   - Scene 7: "FRANKENSTEIN: THE MODERN PROMETHEUS"
   - Scene 8: "MOUNT TAMBORA, INDONESIA - 1816", "LAKE GENEVA, SWITZERLAND - 1816"
   - For comic book style some text is desirable (onomatopoeia, captions) but it's unpredictable
2. **Hand Anatomy (Minor)** — Scene 6 quill-writing hand has slightly odd finger proportions, acceptable for comic style

### Score Card

| Dimension | Score | Notes |
|-----------|-------|-------|
| Prompt adherence | 10/10 | Every element requested was rendered |
| Visual consistency | 10/10 | Same world, palette, cross-hatching across all 10 |
| Style fidelity | 10/10 | Comic book style perfectly executed |
| Character consistency | 9/10 | Mary Shelley recognizable across 4 scenes |
| Shot variety | 9/10 | Wide, medium, close-up, extreme-close-up, over-shoulder, low-angle, high-angle, split panel |
| Emotional impact | 10/10 | Eruption → famine → inspiration → creation arc is compelling |
| Technical quality | 8/10 | 1K resolution, text hallucination (partially desirable) |
| **Overall** | **9.4/10** | Production-ready content |

---

## Comparative Analysis

| Dimension | pp_OM4NYZ (Photorealistic) | pp_ZT5FEC (Comic Book) |
|-----------|---------------------------|----------------------|
| Style fidelity | 5/10 (watercolor lost) | 10/10 (comic style perfect) |
| Prompt adherence | 9/10 | 10/10 |
| Visual consistency | 9/10 | 10/10 |
| Character consistency | N/A (hands only) | 9/10 (Mary Shelley across 4 scenes) |
| Shot variety | 8/10 | 9/10 |
| Emotional impact | 7/10 | 10/10 |
| Text artifacts | Minor (book titles) | Heavy but contextually fitting |
| Recurring motif | Not tested | 10/10 (lightning in every scene) |

---

## Recommendations for Prompt System Improvement

### For `prompts.py` (system prompt)

1. **Add anti-text rule**: Add to SHARED RULES: `"NEVER include readable text, words, letters, numbers, or signage in the image. All text elements must be illegible or absent."` — with a style-specific override for comic_book allowing onomatopoeia
2. **Formalize recurring_motif and character fields**: The LLM generated these in pp_ZT5FEC's analysis and they drove excellent visual consistency. Add them to the required analysis schema
3. **Add negative prompt guidance**: Consider appending `"avoid: text, watermarks, logos, extra fingers"` as standard suffix for Kie AI

### For the pipeline flow

4. **Prompt source verification**: pp_OM4NYZ had different prompts in scenes.json vs grabber_job.json. Verify that `assetsStartGrabber()` pulls from `scene.image_prompt` correctly, or track UI edits explicitly
5. **Resolution default**: Consider defaulting to 2K for production runs (1K for previews/drafts)

### For Kie AI provider

6. **Comic book is Kie AI's strongest style** — The model clearly has strong training data for comic/graphic novel art. Results are publication-quality
7. **Style prefix pattern works** — Starting every prompt with `comic_book style,` or `photorealistic,` gives Kie AI a clear signal. Keep enforcing this in the prompt system
8. **Split-panel concept works** — Opens up possibilities for triptychs, before/after panels, parallel narratives. The LLM should use these more for transition scenes
