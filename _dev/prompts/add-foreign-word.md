# Add Foreign Word Pronunciation

When I give you a word and its desired pronunciation, return the word wrapped in Kokoro's pronunciation link syntax so I can paste it directly into my TTS prompt.

## Format

```
[word](/IPA/)
```

## Example

If I say: "anicca, pronounced ah-NEE-kah"

You return:

```
[anicca](/ɐnˈiːkɐ/)
```

## Rules

1. Always search Wiktionary for accurate IPA — don't guess.
2. Keep the word inside `[]` lowercase.
3. Return ONLY the `[word](/IPA/)` snippet — nothing else.
4. If I provide a sentence, return the full sentence with the foreign word(s) replaced with the link syntax.
