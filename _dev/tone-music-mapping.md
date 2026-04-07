# Tone → Music Folder Mapping

Reference for which music folders are picked for each story tone in `studio/music/selector.py`.

## Mapping

| Tone | Primary | Fallbacks | Why |
|------|---------|-----------|-----|
| suspenseful | dark | ambient, chill | Terror/dread → dark; ambient as backup |
| dramatic | dark | ambient, chill, historic | Heavy emotion → dark; broad fallbacks |
| religious | religion | ambient, dark | Sacred → religion; dark for somber |
| educational | ambient | chill, historic | Neutral background → ambient |
| inspirational | chill | ambient, romantic | Smooth uplift → chill |
| comedic | chill | ambient, romantic | Light energy → chill (hip-hop kick) |
| wholesome | romantic | chill, ambient | Warm/feel-good → romantic lofi |

## Notes

All folders are used. **ambient** appears in every tone as a universal fallback (matches the "fits any story" description). **chill** is positioned as the upbeat-but-smooth option for inspirational/comedic. **romantic** is the warm/wholesome go-to.

## Folder definitions

- **ambient** — universal, fits any story (chill background presence)
- **chill** — smooth ambient-like with hip-hop kick, modern relaxed
- **dark** — terror, sad, scary, dread, suspense
- **romantic** — chill lofi for love/wholesome/feel-good
- **historic** — period/historical narration
- **religion** — sacred, reverent

## Selection behavior

1. Pipeline picks **primary** folder first
2. Falls back to next folder if primary is empty
3. Random pick within the chosen folder
4. **No-repeat history** (last 10 picks stored in `output/music_history.json`) prevents same track twice in a row
