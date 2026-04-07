# Multilingual Niches — French & Spanish Support

Plan for adding French and Spanish languages (with appropriate voices and per-language niche tuning) to the niche/preset system.

## The good news: 80% is already done

Existing infrastructure:

1. **Language is a first-class field in story generation** ([studio/story/schemas.py:15](../../../studio/story/schemas.py#L15)) — `english`, `french`, `spanish` are all valid inputs *today*.
2. **The story prompt already obeys it** ([studio/story/prompts.py:62,85](../../../studio/story/prompts.py#L62)) — `"Write in {language}…"` and `"Write entirely in {language}."` are passed to Gemini. If you generate a story today with `language="french"`, Gemini already produces French text. The webhook works.
3. **Inworld TTS is multilingual** ([studio/tts/inworld.py:35-74](../../../studio/tts/inworld.py#L35-L74)) — `list_voices(language="fr")` already filters voices by language. The API supports it; we just aren't using the filter anywhere.
4. **Story history dedup is already language-aware** ([studio/story/history.py:34](../../../studio/story/history.py#L34)) — `stickman_glow__philosophy__french.json` is a separate file from `stickman_glow__philosophy__english.json`. French stories build their own dedup memory; they don't interfere with English ones.
5. **One French Inworld voice is already mapped in code** ([studio/niches/presets.py:41](../../../studio/niches/presets.py#L41)) — `Alain` is listed as a French narrator.

So the *infrastructure* is there. What's missing is the **content layer**: presets that explicitly target FR/ES, voice mappings per language, and a language picker in the UI for niche selection.

## The four real gaps

### Gap 1 — Niche presets are language-agnostic

Every preset in [studio/niches/presets.py:163+](../../../studio/niches/presets.py#L163) hardcodes a single voice (`af_heart`, `am_fenrir`, etc.) and assumes English. There's no `language` field on the preset itself. Two options:

- **Option A: Add a `language` field to each preset** and triple the preset count (one English, one French, one Spanish version of each).
  - Pro: explicit, clean.
  - Con: ~50 presets becomes ~150 — a lot of duplication.
- **Option B: Make presets language-neutral** and let the user pick language at generation time. The voice gets resolved dynamically by `(category, tone, language)` instead of being hardcoded on the preset.
  - Pro: no duplication, infinite scaling.
  - Con: requires a small refactor to how voice resolution works.

**Recommendation: Option B.** Less code, scales better, matches how multilingual content tools usually work (one preset, three language buttons).

### Gap 2 — Voice mapping is single-language

[INWORLD_VOICE_MAP at presets.py:31-146](../../../studio/niches/presets.py#L31-L146) is keyed by `(category, tone)`. Every entry assumes English-speaking voices (Hades, Vinny, Bella, etc.). Needs to be keyed by `(category, tone, language)`:

```python
INWORLD_VOICE_MAP = {
    ("psychology", "suspenseful", "english"): "Malcolm",
    ("psychology", "suspenseful", "french"):  "Alain",
    ("psychology", "suspenseful", "spanish"): "Mateo",
    # ...
}
```

`resolve_inworld_voice(category, tone, language)` needs to fall back to a sane default per language if a specific combo isn't mapped.

The **research cost** here is real but bounded: list Inworld's available FR/ES voices, pick 4–6 per language across the male-firm / male-deep / female-firm / female-warm spectrum, tag them by best-fit niche category. That's a one-time afternoon of `list_voices(language="fr")` → audition each on the Inworld dashboard → write down which fits "dramatic philosophy" vs "comedic anecdote" etc.

### Gap 3 — Story prompts don't carry language-specific cliché lists

The current story prompt says *"Write in french."* That works, but Gemini's idea of "viral French TikTok narration" is **not the same** as a native French content creator's idea. The same is even more true for Spanish (LATAM vs Iberian sound very different).

Specifically:

- **A short "native voice" instruction per language.**
  - For French: *"Use natural conversational French as spoken in 2024 — not formal academic French, no inversions for questions, contractions encouraged ('j'sais pas', not 'je ne sais pas')."*
  - For Spanish: *"Write in neutral Latin American Spanish unless otherwise specified — accessible to viewers from Mexico to Argentina, avoid Iberian-specific vocabulary like 'vosotros'."*
- **A *per-language* anti-cliché list.** French TikTok narration has its own overused tropes ("Tu vas pas le croire mais…", "Et là, BAM."), and Spanish has different ones ("Pon atención porque esto te va a sorprender"). Mirroring `_ANGLE_STARTERS` per language stops Gemini from defaulting to the same 5 hooks every time.
- Optionally, **language-specific theme pools.** Some philosophy themes that resonate in English ("Stoic confession", "memento mori") map directly. Others ("Camus and the absurd", "existentialism" — these come from French!) are *more* native to a French audience and could be pushed harder there.

### Gap 4 — Frontend has no language picker on niche selection

The pipeline UI ([frontend/src/features/pipeline/views/PipelinePage.vue](../../../frontend/src/features/pipeline/views/PipelinePage.vue)) lets users pick a niche preset, which then locks in voice/tone/style. There's no language toggle next to it. Need a 3-button toggle (EN / FR / ES) that gets passed into the story generation request.

This is a small UI change but it has to be done in two places: niche selection (so users know which language they're generating in) and the story generation call (so the language reaches the backend).

## What to actually do, in order

| Step | What | Effort | Why this order |
|---|---|---|---|
| **1** | Audit Inworld's available FR & ES voices via `list_voices()`, pick 4–6 per language, document by category fit | 1–2 hours of *listening*, ~30 min of code | Can't write the voice map without knowing which voices exist and how they sound. The only step with irreducible human time. |
| **2** | Refactor `INWORLD_VOICE_MAP` to be `(category, tone, language)` keyed; refactor `resolve_inworld_voice()` to take a `language` arg with per-language fallbacks | small | Unblocks every preset generation in any language. |
| **3** | Drop the hardcoded `voice` field from niche presets in `_DEFAULTS` and resolve voice at generation time from `(category, tone, language)`. Keep `voice` as an optional override for edge cases. | small | This is the "Option B" refactor. Eliminates the need to triple the preset count. |
| **4** | Wire `language` through the niche-resolve API call. Frontend sends `niche_id + language` to the backend, the backend hydrates the preset and looks up voice for that language. | small | Backend plumbing only — should be a 10-line change to [studio/niches/routes.py](../../../studio/niches/routes.py). |
| **5** | Add `_ANGLE_STARTERS_FR` and `_ANGLE_STARTERS_ES` lists in [studio/story/prompts.py](../../../studio/story/prompts.py); make `build_story_user_prompt` pick the right list based on `language`. Same for the cliché-avoidance instruction. | small | Cheapest variety win in the new languages. |
| **6** | Add a "native voice" instruction line to the system prompt that switches by language (the FR/ES blurbs above). | trivial | Lifts story quality immediately. |
| **7** | Frontend: add a 3-button language toggle to the pipeline page next to the niche picker; persist the choice in the project. | small UI change | The user-facing capstone. |
| **8** | (Optional) Per-language theme pools for the standout presets (Stickman Glow Philosophy especially). | medium | Polish — defer until shipping FR/ES content regularly. |

## Split of work

**Mechanical / no input needed:** steps 2, 3, 4, 5, 6 — all code refactoring of existing files. Should ship as a single coherent commit so the language-aware path is end-to-end testable.

**Requires human taste calls:** step 1 — picking the actual voices. The API can dump `list_voices(language="fr")`, but auditioning them and deciding that "Mateo sounds right for crime/dramatic in Spanish" is a taste call. A starter map can be generated from sensible-sounding name/description matches from the API metadata, then corrected after listening.

**Frontend (own commit):** step 7. The pipeline page has a lot of state already; this should be scoped as its own commit to avoid mixing with backend changes.

## The minimum viable version

To prove the loop works before investing in the full thing:

1. Pick **one French voice** and **one Spanish voice** from Inworld (just one each, doesn't have to be perfect).
2. Add `language` as a parameter on the niche-resolve call, defaulting to English.
3. Hardcode the voice fallback: `if language == "french": return "Alain"; if language == "spanish": return <chosen>; else: return current map.`
4. Generate a Stickman Glow Philosophy story in French and another preset in Spanish, all the way to TTS output.

If those two videos sound right, the whole pipeline works in a non-English language. Then scale up the voice map and the prompt-quality work.

## Open questions before starting

1. **Inworld dashboard access** — does the user have a dashboard login to audition voices, or should the API dump the FR/ES voice list first so the user can see what's available?
2. **Option A or Option B** for presets — triple the preset count (one per language), or one preset with a language parameter? (Strong recommendation: B.)

## Files that will be touched

- [studio/niches/presets.py](../../../studio/niches/presets.py) — voice map refactor, drop hardcoded voice field
- [studio/niches/routes.py](../../../studio/niches/routes.py) — accept `language` param on resolve
- [studio/story/prompts.py](../../../studio/story/prompts.py) — per-language angle starters, native-voice instruction
- [studio/story/schemas.py](../../../studio/story/schemas.py) — already supports language, no change needed
- [studio/story/history.py](../../../studio/story/history.py) — already language-aware, no change needed
- [studio/tts/inworld.py](../../../studio/tts/inworld.py) — already multilingual, no change needed
- [frontend/src/features/pipeline/views/PipelinePage.vue](../../../frontend/src/features/pipeline/views/PipelinePage.vue) — language toggle UI
