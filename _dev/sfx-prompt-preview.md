# SFX section as rendered into the scene planner prompt
# (auto-generated, do not edit — regenerate with the script in this directory)

## SFX HINTS (optional `sfx_hint` field)

You may optionally tag scenes with an `sfx_hint` field that requests a
specific sound effect at that scene's position on the timeline. The renderer
will pick a real sound file matching the hint and place it on the timeline
with proper volume, ducking, and timing.

### Available hints (closed list — pick from these or `null`)

- `tension_riser` (RISER): Long swelling drone or build-up that escalates tension before a reveal. Use sparingly — at most once per video, on a build → climax transition. Pairs naturally with hook or build → climax pivots.
- `bass_drop_impact` (BASS DROP): Single deep bass impact — the heaviest sting available. Use ONCE per video, on the climax scene only, on the hardest emotional beat. Never on a build scene; never twice.
- `cinematic_hit` (HIT): Mid-weight cinematic stinger for a strong revelation that isn't the final climax. Use on a major reveal in the build section, or as a softer climax alternative when bass_drop_impact would be too much.
- `whoosh_transition` (WHOOSH): Quick whoosh marking a hard cut between scenes. Use sparingly — at most once every 3 scenes — or it loses impact. Best on perspective shifts (zoom out, jump cut to a new angle, time skip).
- `rocket_whoosh` (ROCKET): Heavier, longer whoosh with momentum. Use for forward motion, escalation, or 'launching into something' beats. More dramatic than whoosh_transition.
- `heartbeat_pulse` (HEARTBEAT): Steady human heartbeat looping under the scene. Use during moments of intimate fear, tension, or vulnerability. Plays for the full scene duration. Most powerful when the scene is short (3-6s).
- `clock_tick` (CLOCK): Quiet ticking clock under the scene. Use during scenes about time, memory, waiting, deadlines, or 'meanwhile…' beats. Plays for the full scene duration.
- `thinking_pad` (THINK): Soft 'hmm' / contemplative pad. Use during reflection, internal monologue, or 'consider this…' moments. Plays for the full scene duration.
- `magic_shimmer` (SHIMMER): Soft sparkle / chime / 'aha moment' shimmer. Use on insights, realizations, idea-having, or 'something beautiful is happening' beats. Light and brief.
- `money_sting` (MONEY): Coin / cash register / value-related ding. Use ONLY on scenes literally about money, wealth, cost, or value. Never decorative.
- `glass_shatter` (GLASS): Sharp, harsh impact suitable for shattering, breaking, or violent rupture. Use on a single moment — a betrayal, a shattering belief, a violent revelation. Maximum once per video.
- `gunshot_punctuation` (GUNSHOT): Single sharp punctuation mark. Use on violence, sudden death, or extremely abrupt narrative breaks. Use only when the script explicitly references such a moment — never decoratively.
- `rain_ambience` (RAIN): Rain or thunderstorm bed under the scene. Use for melancholy, isolation, contemplation, or scenes literally set in bad weather. Plays for the full scene duration.
- `nature_ambience` (NATURE): Birdsong, footsteps in grass, calm outdoor textures. Use for peaceful, wholesome, or rural scenes. Plays for the full scene duration.
- `crowd_cheer` (CHEER): Crowd applause / cheering / stadium energy. Use on triumph, victory, recognition, or shared joy beats. One-shot, not looped.
- `crowd_laugh` (LAUGH): Audible group laughter — sitcom-style. Use ONLY on comedic relief beats or punchlines. Never on dramatic/serious content; the tonal mismatch is jarring.
- `camera_shutter` (SHUTTER): Camera shutter / photo snap. Use on 'a moment captured', evidence reveals, photographic memory beats, or paparazzi/surveillance scenes.
- `keyboard_typing` (TYPING): Keyboard / typewriter typing texture. Use on scenes about writing, coding, messaging, or research montages. Plays for the full scene duration.
- `telephone_ring` (PHONE): Telephone ring or dial tone. Use ONLY when the scene literally involves a phone call. Never decorative.
- `glitch_distort` (GLITCH): Digital glitch / corruption / reality-tear sound. Use on jarring transitions, system breakdowns, surreal pivots, or 'something is wrong' beats. Sharp and disorienting on purpose.
- `viscous_liquid` (VISCOUS): Slow gloopy liquid texture. Use on body horror, dread, things-going-wrong slow burns, or unsettling slow-motion beats. Loops under the scene.
- `notification_ding` (DING): UI notification / alert / 'message received' ding. Use on social-media beats, alarm beats, or 'something just happened' attention-grabs. Modern and short-form-native.
- `click_confirm` (CLICK): Sharp UI click / 'correct answer' / 'done' click. Use on confirmation beats, list items being checked off, decision-made moments. Subtle and structural.
- `cartoon_pop` (POP): Light cartoon pop / boing / appearance sound. Use ONLY on comedic or playful content; tonally wrong for drama, philosophy, or true crime.
- `text_appear` (TEXT IN): Short bright accent marking the moment a text overlay appears on screen. Use ONLY on text-type scenes (scene.type == 'text') — never on image/video scenes. Pairs with the visual pop animation. Keep it gentle: it should support the text reveal, not compete with it. At most one per text scene.
- `text_disappear` (TEXT OUT): Soft sweep marking the moment a text overlay leaves the screen. Use ONLY on text-type scenes (scene.type == 'text') — never on image/video scenes. Should be airy and brief, the audio equivalent of a fade. Pairs with text_appear at the start of the same scene; using one without the other is fine.
- `text_emphasis` (TEXT HIT): Subtle ding/chime that lands on the emphasized word inside a text scene. Use ONLY on hook text scenes where one word is highlighted/animated (scene.type == 'text' AND a hook animation is present). Pairs with the visual emphasis beat. Use sparingly — at most once per text scene, and not on every text scene.
- `silence` (— SILENCE —): Explicit silence — render no SFX on this scene. Use when the absence of sound is itself the effect (a beat of stillness, a held breath before a reveal). Different from leaving sfx_hint null: this is a deliberate creative choice to suppress any ambient/auto SFX during this scene window.

### SFX BUDGET (HARD RULES)

- TOTAL BUDGET per video: 3-4 hints maximum.
  For videos under 30 seconds: 2-3 hints.
- Most scenes (60-80%) MUST have `sfx_hint: null`. SFX is punctuation, not wallpaper.
- `bass_drop_impact` may appear AT MOST ONCE per video, on the FINAL CLIMAX scene only.
- `tension_riser` may appear AT MOST ONCE per video, on the scene IMMEDIATELY BEFORE the climax.
- Two consecutive scenes may NOT both have hints UNLESS the pattern is exactly
  `tension_riser` followed by `bass_drop_impact` / `cinematic_hit` / `glass_shatter` / `gunshot_punctuation`.
  This riser -> impact pair is the only legal back-to-back stack.
- `text_appear`, `text_disappear`, `text_emphasis` may ONLY be used on text-type scenes
  (`type_of_scene: "text"`). Never on image or video scenes.
- `cartoon_pop` and `crowd_laugh` are FORBIDDEN unless the visual style is comedic.
  For dramatic, philosophical, suspenseful, or contemplative content: never use them.
- Looping textures (`heartbeat_pulse`, `clock_tick`, `viscous_liquid`, `keyboard_typing`,
  `rain_ambience`, `nature_ambience`, `thinking_pad`) work best on short scenes (≤4s).
  Do not place a texture on a long scene — it becomes background wallpaper and the ear stops hearing it.

### WHEN TO ADD A HINT (criteria)

A scene gets an `sfx_hint` if and only if AT LEAST ONE of these is true:

1. The script LITERALLY names an event a sound represents — a phone call, a gunshot,
   glass breaking, a clock ticking, applause. Use the matching hint.
2. The scene marks a STRUCTURAL PIVOT - hook to build, build to climax, climax to CTA.
   Use a transition or impact hint.
3. The scene is the SINGLE DOMINANT EMOTIONAL BEAT of the story — the betrayal, the
   revelation, the realization. Use the strongest fitting impact hint.

If a scene doesn't pass any of these tests, leave `sfx_hint: null`. SFX without
a specific reason is decoration and decoration is what makes videos feel cluttered.

### IDEAL ALLOCATION (mental model)

For a typical 60-second video, the 4-hint allocation looks like:
- 1 hit on the HOOK (a bright accent, magic_shimmer or text_appear)
- 1 hit on a BUILD escalation (a subtle marker, whoosh_transition or glitch_distort)
- 1 lead-in RISER on the scene before the climax (`tension_riser`)
- 1 IMPACT on the climax scene itself (`bass_drop_impact` or `cinematic_hit`)

For a 30-second video drop the build-escalation hit and use 3 hints total.

### THE NUCLEAR RULE

Never exceed 4 hints. If you find yourself wanting a 5th hint, REMOVE one of
the existing hints instead. Restraint produces better videos than abundance.
