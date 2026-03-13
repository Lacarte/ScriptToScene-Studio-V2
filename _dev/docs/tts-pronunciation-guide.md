# TTS Pronunciation Guide — Foreign & Custom Words

Kokoro TTS uses **misaki** for English phonemization. You can override pronunciation of any word using IPA (International Phonetic Alphabet) via Kokoro's markdown link syntax.

## Syntax

```
[displayed_word](/IPA_phonemes/)
```

Example: `[anicca](/ɐnˈiːkɐ/)` pronounces "anicca" as "ah-NEE-kah".

## Two Ways to Use It

### 1. Inline in the Prompt (no code change)

Type the Kokoro link directly in the TTS text box:

```
The concept of [anicca](/ɐnˈiːkɐ/) teaches that suffering comes from resistance to change.
```

The `[word](/IPA/)` syntax is preserved through the normalization pipeline and passed to misaki G2P.

### 2. Auto-Replace via `_FOREIGN_WORDS` (permanent)

Add an entry to `_FOREIGN_WORDS` in `studio/tts/normalize.py`:

```python
_FOREIGN_WORDS = {
    r'\bANICCA\b': '[anicca](/ɐnˈiːkɐ/)',
    r'\bNEWWORD\b': '[newword](/IPA_HERE/)',
}
```

- The regex pattern is **case-insensitive** (`re.IGNORECASE` flag is applied).
- Use `\b` word boundaries to avoid partial matches.
- The replacement runs **before** Kokoro link protection, so the generated `[word](/IPA/)` syntax is automatically preserved through the rest of the pipeline.

## Finding IPA for a Word

1. Search the word on [Wiktionary](https://en.wiktionary.org/) — most entries include IPA transcriptions.
2. Copy the IPA string between the slashes `/.../)`.

## How It Works Internally

1. `_expand_foreign_words()` replaces the word with `[word](/IPA/)`.
2. `_protect_kokoro()` extracts all `[text](/phonetic/)` links into placeholders.
3. The rest of the normalization pipeline runs without touching the placeholders.
4. `_restore_kokoro()` puts the links back.
5. `_phonemize_with_misaki()` processes the link — misaki reads the IPA directly instead of guessing pronunciation.
