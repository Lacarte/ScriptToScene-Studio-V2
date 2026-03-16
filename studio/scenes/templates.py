"""Scene Style Templates — Pre-tuned visual style presets for AI scene generation.

Each template bundles a style_prompt (LLM instructions for generating image prompts)
along with display metadata for the frontend picker.
"""

SCENE_STYLE_TEMPLATES = [
    {
        "id": "cinematic",
        "name": "Cinematic Realistic",
        "description": "Photorealistic, dramatic lighting, film grain",
        "color": "#4ECDC4",
        "style_prompt": (
            "Generate photorealistic image prompts with cinematic composition. "
            "Use dramatic lighting (golden hour, chiaroscuro, volumetric light rays). "
            "Include film grain texture, shallow depth of field, and anamorphic lens flare. "
            "Frame shots like a Hollywood cinematographer — wide establishing shots, "
            "medium close-ups for emotion, extreme close-ups for tension. "
            "Color palette: rich, saturated, with teal-orange contrast."
        ),
    },
    {
        "id": "dark_horror",
        "name": "Dark / Horror",
        "description": "Eerie shadows, desaturated tones, unsettling atmosphere",
        "color": "#FF6B6B",
        "style_prompt": (
            "Generate dark, unsettling image prompts for horror storytelling. "
            "Use heavy shadows, low-key lighting, and desaturated cold tones (blue-grey, sickly green). "
            "Include fog, mist, silhouettes, and partially obscured subjects. "
            "Environments should feel abandoned, decaying, or claustrophobic. "
            "Faces should be partially hidden or lit from below. "
            "Atmosphere: dread, unease, isolation. Think atmospheric horror, not gore."
        ),
    },
    {
        "id": "reddit_story",
        "name": "Reddit Story",
        "description": "Everyday realism, relatable settings, subtle tension",
        "color": "#FF8A50",
        "style_prompt": (
            "Generate realistic, grounded image prompts for Reddit-style personal stories. "
            "Settings are everyday and relatable: apartments, offices, cars, restaurants, suburban homes. "
            "Lighting should feel natural — overhead fluorescents, laptop screen glow, afternoon window light. "
            "People should look like normal, non-glamorous individuals. "
            "Use medium shots and over-the-shoulder angles for conversational scenes. "
            "Mood shifts with the narrative: warm tones for happy moments, cool desaturated for conflict. "
            "Style: modern photorealistic, candid photography feel."
        ),
    },
    {
        "id": "motivational",
        "name": "Motivational",
        "description": "Bright, uplifting, high-contrast inspirational visuals",
        "color": "#FFD93D",
        "style_prompt": (
            "Generate uplifting, inspirational image prompts with high visual energy. "
            "Use bright, warm lighting — sunrise/sunset, golden backlighting, lens flare. "
            "Include expansive landscapes, mountain peaks, open skies, and silhouettes against light. "
            "People should appear determined, triumphant, or in motion (running, climbing, reaching). "
            "Color palette: warm golds, deep blues, vibrant oranges. High contrast. "
            "Composition: epic wide shots, low-angle hero shots, dramatic scale."
        ),
    },
    {
        "id": "nature_doc",
        "name": "Nature Documentary",
        "description": "BBC Earth aesthetics, macro detail, sweeping landscapes",
        "color": "#26DE81",
        "style_prompt": (
            "Generate nature documentary-style image prompts with BBC Earth quality. "
            "Use extreme macro for small subjects (insects, dewdrops, textures) and "
            "sweeping aerial/wide shots for landscapes. "
            "Lighting: natural golden hour, dappled forest light, underwater caustics. "
            "Include wildlife in natural behavior, pristine environments, and ecological detail. "
            "Color palette: lush greens, ocean blues, earth tones. "
            "Composition: rule of thirds, leading lines in nature, shallow DOF on subjects."
        ),
    },
    {
        "id": "anime",
        "name": "Anime / Manga",
        "description": "Japanese animation style, vivid colors, expressive characters",
        "color": "#A78BFA",
        "style_prompt": (
            "Generate image prompts in Japanese anime/manga art style. "
            "Characters should have expressive faces with large eyes, dynamic poses, and stylized hair. "
            "Use vivid, saturated colors with cel-shading and clean line art. "
            "Backgrounds should be detailed and painterly (Makoto Shinkai sky style). "
            "Include speed lines for action, sparkle effects for emotion, "
            "and dramatic camera angles (dutch angles, extreme low/high). "
            "Lighting: rim lighting, dramatic backlighting, neon glows for night scenes."
        ),
    },
    {
        "id": "surreal",
        "name": "Surreal / Dreamlike",
        "description": "Impossible geometry, floating objects, otherworldly scenes",
        "color": "#E879F9",
        "style_prompt": (
            "Generate surreal, dreamlike image prompts with impossible or fantastical elements. "
            "Include floating objects, impossible architecture, melting landscapes, and scale distortions. "
            "Mix unexpected elements: clocks in forests, doors in oceans, stairs to nowhere. "
            "Use soft, diffused lighting with iridescent or bioluminescent accents. "
            "Color palette: pastels mixed with deep jewel tones, gradient skies. "
            "Composition: center-weighted with vast negative space. "
            "Style: between Salvador Dali and modern digital surrealism."
        ),
    },
    {
        "id": "noir",
        "name": "Noir / Mystery",
        "description": "High contrast B&W, venetian blinds, smoky atmosphere",
        "color": "#94A3B8",
        "style_prompt": (
            "Generate film noir-style image prompts with classic detective/mystery atmosphere. "
            "Use high-contrast black and white or very desaturated tones with a single accent color. "
            "Lighting: harsh venetian blind shadows, single-source desk lamps, neon reflections on wet streets. "
            "Include rain-slicked city streets, smoky interiors, long shadows, and trench coat silhouettes. "
            "Composition: dutch angles, deep shadows covering half the frame, mirror/reflection shots. "
            "Atmosphere: mysterious, morally ambiguous, tension without violence."
        ),
    },
    {
        "id": "minimal",
        "name": "Minimalist",
        "description": "Clean compositions, negative space, simple shapes",
        "color": "#6B7F93",
        "style_prompt": (
            "Generate minimalist image prompts with maximum visual impact from minimal elements. "
            "Use vast negative space, single focal subjects, and geometric simplicity. "
            "Color palette: monochromatic or limited to 2-3 colors. "
            "Composition: centered single subject, extreme negative space, "
            "clean horizons, isolated objects on plain backgrounds. "
            "Lighting: soft, even, shadowless OR single dramatic shadow. "
            "Style: modern design photography, architectural minimalism."
        ),
    },
    {
        "id": "cyberpunk",
        "name": "Cyberpunk / Neon",
        "description": "Neon-soaked streets, futuristic tech, rain-slicked chrome",
        "color": "#00FFF7",
        "style_prompt": (
            "Generate cyberpunk-style image prompts with a neon-drenched futuristic aesthetic. "
            "Use vibrant neon lighting in magenta, cyan, and electric blue against dark environments. "
            "Include rain-slicked streets reflecting holographic advertisements, towering megastructures, "
            "augmented humans, and gritty back-alleys filled with steam and wires. "
            "Color palette: deep blacks with saturated neon accents — pink, teal, purple. "
            "Lighting: neon signage, holographic projections, LED strips, underlighting. "
            "Composition: low-angle shots emphasizing scale, tight alleys with depth, Dutch angles."
        ),
    },
    {
        "id": "vintage_retro",
        "name": "Vintage / Retro",
        "description": "70s-80s film stock, warm faded tones, analog nostalgia",
        "color": "#D4A574",
        "style_prompt": (
            "Generate image prompts with a warm vintage aesthetic reminiscent of 1970s-1980s film photography. "
            "Use faded, warm color tones — amber, burnt orange, olive green, mustard yellow. "
            "Include film grain, slight overexposure, light leaks, and soft focus edges. "
            "Settings should feel nostalgic: wood-paneled rooms, analog TVs, station wagons, diners. "
            "Lighting: warm tungsten, late afternoon sun through curtains, golden hour haze. "
            "Composition: slightly off-center, casual framing as if from a family photo album. "
            "Style: Kodachrome and Polaroid aesthetics, analog warmth."
        ),
    },
    {
        "id": "fantasy_epic",
        "name": "Fantasy / Epic",
        "description": "Mythical worlds, dragons, castles, enchanted landscapes",
        "color": "#C084FC",
        "style_prompt": (
            "Generate epic fantasy-style image prompts with grand, mythical world-building. "
            "Include towering castles, enchanted forests, dragons, ancient ruins, and magical creatures. "
            "Use dramatic, painterly lighting — god rays through storm clouds, aurora borealis, fire glow. "
            "Environments should feel vast and awe-inspiring with extreme scale. "
            "Color palette: deep purples, emerald greens, molten golds, sapphire blues. "
            "Composition: sweeping panoramic establishing shots, hero silhouettes against epic backdrops. "
            "Style: high fantasy digital painting, concept art quality, Tolkien-inspired grandeur."
        ),
    },
    {
        "id": "sci_fi",
        "name": "Sci-Fi / Space",
        "description": "Spaceships, alien worlds, futuristic technology, cosmic scale",
        "color": "#38BDF8",
        "style_prompt": (
            "Generate science fiction image prompts with futuristic and cosmic imagery. "
            "Include sleek spacecraft, alien planets, space stations, wormholes, and advanced technology. "
            "Use clean, cool lighting — blue-white ship interiors, starfield illumination, planetary glow. "
            "Environments: vast space vistas, sterile corridors, terraformed landscapes, zero-gravity scenes. "
            "Color palette: steel blues, deep space blacks, white LED accents, holographic teal. "
            "Composition: extreme wide shots for scale, symmetrical interiors, lens flare from distant stars. "
            "Style: hard sci-fi realism, NASA meets Hollywood — Interstellar, The Expanse, Blade Runner 2049."
        ),
    },
    {
        "id": "watercolor",
        "name": "Watercolor / Painted",
        "description": "Soft washes, visible brushstrokes, artistic illustration",
        "color": "#FB923C",
        "style_prompt": (
            "Generate image prompts in a watercolor painting style with artistic, handmade quality. "
            "Use soft color washes that bleed into each other, visible brushstrokes, and wet-on-wet effects. "
            "Leave areas of white paper showing through for highlights and breathing room. "
            "Colors should be luminous and translucent — not opaque or flat. "
            "Include gentle gradients, organic edges, and slightly imprecise details that feel hand-painted. "
            "Subjects should feel delicate and atmospheric rather than photorealistic. "
            "Style: traditional watercolor illustration, children's book art, botanical painting."
        ),
    },
    {
        "id": "comic_book",
        "name": "Comic Book / Pop Art",
        "description": "Bold outlines, halftone dots, vibrant flat colors, action panels",
        "color": "#EF4444",
        "style_prompt": (
            "Generate image prompts in bold comic book and pop art style. "
            "Use thick black outlines, flat vibrant colors, and Ben-Day halftone dot patterns. "
            "Characters should have exaggerated expressions and dynamic superhero-style poses. "
            "Include action lines, impact bursts, onomatopoeia text effects, and dramatic shadows. "
            "Color palette: primary colors — bold red, blue, yellow — with black and white contrast. "
            "Composition: dynamic diagonal layouts, extreme foreshortening, close-up reaction shots. "
            "Style: Marvel/DC comic illustration meets Roy Lichtenstein pop art."
        ),
    },
    {
        "id": "gothic",
        "name": "Gothic / Victorian",
        "description": "Dark elegance, ornate architecture, candlelit atmosphere",
        "color": "#7C3AED",
        "style_prompt": (
            "Generate gothic and Victorian-era image prompts with dark romantic elegance. "
            "Include ornate architecture — pointed arches, gargoyles, stained glass, wrought iron gates. "
            "Use candlelight, moonlight through fog, and fireplace glow as primary light sources. "
            "Settings: crumbling manors, rain-soaked cathedrals, overgrown graveyards, velvet-draped parlors. "
            "Color palette: deep burgundy, midnight blue, antique gold, charcoal, bone white. "
            "Include rich textures: brocade, aged stone, tarnished metal, cobwebs, dried roses. "
            "Style: Pre-Raphaelite painting meets Tim Burton — beautiful darkness, melancholy grandeur."
        ),
    },
    {
        "id": "vaporwave",
        "name": "Vaporwave / Aesthetic",
        "description": "Pastel grids, retro-futurism, glitch art, digital nostalgia",
        "color": "#F472B6",
        "style_prompt": (
            "Generate vaporwave aesthetic image prompts with retro-digital nostalgia. "
            "Include wireframe grids extending to horizon, Greek/Roman marble busts, palm trees, and sunsets. "
            "Use glitch effects, chromatic aberration, scan lines, and VHS distortion. "
            "Color palette: pastel pink, lavender, mint green, coral, with hot pink and cyan accents. "
            "Settings: infinite checkerboard floors, floating geometric shapes, 90s computer interfaces. "
            "Include retro technology: CRT monitors, floppy disks, old Windows UI, Japanese text. "
            "Style: 80s-90s digital nostalgia, liminal mall aesthetics, A E S T H E T I C."
        ),
    },
    {
        "id": "documentary",
        "name": "Documentary / Journalism",
        "description": "Raw authenticity, photojournalistic, handheld camera feel",
        "color": "#78716C",
        "style_prompt": (
            "Generate documentary-style image prompts with raw, authentic photojournalistic quality. "
            "Use natural, unposed compositions as if captured in the moment by a photojournalist. "
            "Lighting should be available light only — harsh midday sun, dim interiors, street lamps. "
            "Include slight motion blur, candid expressions, and environmental context. "
            "Color palette: muted, slightly desaturated — real-world tones without stylization. "
            "Settings should feel genuine and lived-in, not staged or art-directed. "
            "Composition: rule of thirds, environmental portraits, wide establishing context shots. "
            "Style: Magnum Photos, National Geographic — truth-telling through imagery."
        ),
    },
    {
        "id": "3d_render",
        "name": "3D Render / CGI",
        "description": "Clean 3D renders, soft studio lighting, Pixar-quality",
        "color": "#2DD4BF",
        "style_prompt": (
            "Generate image prompts styled as high-quality 3D renders and CGI. "
            "Use soft, even studio lighting with subtle ambient occlusion and global illumination. "
            "Surfaces should have clean materials: glossy plastic, matte rubber, smooth glass, brushed metal. "
            "Characters and objects should have a slightly stylized, rounded quality — Pixar/DreamWorks feel. "
            "Color palette: clean, bright, slightly desaturated pastels OR rich saturated tones. "
            "Include soft depth of field, subtle reflections, and physically accurate shadows. "
            "Composition: product-shot framing, isometric views, centered hero shots. "
            "Style: Octane render, Blender Cycles, high-end product visualization."
        ),
    },
    {
        "id": "dark_academia",
        "name": "Dark Academia",
        "description": "Old libraries, warm lamplight, scholarly atmosphere, autumn tones",
        "color": "#92400E",
        "style_prompt": (
            "Generate dark academia aesthetic image prompts with scholarly, autumnal atmosphere. "
            "Include old libraries with towering bookshelves, ivy-covered stone buildings, lecture halls, and studies. "
            "Use warm, low lighting — desk lamps, candlelight, fireplace glow, autumn afternoon through leaded windows. "
            "Props: leather-bound books, handwritten letters, fountain pens, pocket watches, chess sets, tea cups. "
            "Color palette: deep brown, olive green, burgundy, cream, aged gold, charcoal. "
            "Textures: worn leather, dark wood, tweed fabric, parchment, aged stone. "
            "Composition: intimate and contemplative, still-life elements, reading nooks. "
            "Style: romanticized intellectual life — Oxford/Cambridge meets Donna Tartt."
        ),
    },
    {
        "id": "tropical",
        "name": "Tropical / Paradise",
        "description": "Lush jungles, turquoise waters, golden sunsets, vivid flora",
        "color": "#10B981",
        "style_prompt": (
            "Generate tropical paradise image prompts with lush, vibrant natural beauty. "
            "Include dense jungle canopies, crystal turquoise waters, white sand beaches, and cascading waterfalls. "
            "Use golden hour and magic hour lighting — warm sunsets, dappled light through palm fronds. "
            "Flora: oversized tropical leaves, hibiscus, plumeria, bird of paradise, bougainvillea. "
            "Color palette: vivid emerald greens, ocean blues, coral pinks, sunset oranges, golden yellows. "
            "Water should be impossibly clear with visible sand and reef beneath. "
            "Composition: wide panoramic vistas, overhead canopy shots, underwater-meets-surface split shots. "
            "Style: travel magazine cover, National Geographic Traveler, paradise postcard."
        ),
    },
    {
        "id": "urban_street",
        "name": "Urban / Street",
        "description": "City grit, graffiti walls, street photography, raw energy",
        "color": "#F59E0B",
        "style_prompt": (
            "Generate urban street photography-style image prompts with raw city energy. "
            "Include graffiti-covered walls, concrete underpasses, fire escapes, rooftops, and busy intersections. "
            "Use mixed urban lighting — sodium vapor streetlights, neon shop signs, car headlights, phone screens. "
            "People in motion: walking, skateboarding, performing, hustling — candid and unposed. "
            "Color palette: concrete greys with pops of color from street art, signage, and fashion. "
            "Include puddle reflections, steam from grates, motion blur of passing traffic. "
            "Composition: dynamic street-level angles, reflections in shop windows, leading lines from sidewalks. "
            "Style: Vivian Maier meets modern street photography — gritty, authentic, alive."
        ),
    },
    {
        "id": "dark_psychology",
        "name": "Dark Psychology",
        "description": "Manipulation, mind games, shadowy figures, psychological tension",
        "color": "#6D28D9",
        "style_prompt": (
            "Generate psychologically intense image prompts exploring manipulation, influence, and the darker side of human behavior. "
            "Use claustrophobic framing, distorted reflections, and split-face compositions to show duality. "
            "Lighting: harsh overhead interrogation lights, faces half in shadow, backlit silhouettes with glowing eyes. "
            "Include visual metaphors: puppet strings, chess pieces, masks being worn or removed, cracked mirrors. "
            "Environments: dimly lit rooms, corridors with converging walls, empty chairs facing each other. "
            "Color palette: deep violet, charcoal black, blood red accents, cold steel grey. "
            "Composition: extreme close-ups on eyes, over-the-shoulder power dynamics, dutch angles for unease. "
            "Style: psychological thriller cinematography — Mindhunter, Se7en, Gone Girl."
        ),
    },
    {
        "id": "religion_spiritual",
        "name": "Religion / Spiritual",
        "description": "Sacred imagery, divine light, temples, spiritual transcendence",
        "color": "#D4AF37",
        "style_prompt": (
            "Generate spiritually evocative image prompts with sacred, reverent imagery across world religions. "
            "Include grand places of worship: cathedrals, mosques, temples, monasteries, ancient stone circles. "
            "Use divine lighting — god rays piercing stained glass, golden halos, candlelit vigils, dawn over sacred sites. "
            "Visual motifs: prayer hands, sacred geometry, mandalas, rosary beads, incense smoke, holy water reflections. "
            "Environments: mountain-top monasteries, desert pilgrimages, underwater baptisms, forest shrines. "
            "Color palette: celestial gold, pure white, deep indigo, sacred crimson, earthen ochre. "
            "Composition: symmetrical and reverent, upward gazing angles, light breaking through darkness. "
            "Style: Renaissance religious painting meets modern spiritual photography — Caravaggio lighting, sacred awe."
        ),
    },
    {
        "id": "politics_power",
        "name": "Politics / Power",
        "description": "Podiums, crowds, propaganda, power dynamics, civic drama",
        "color": "#DC2626",
        "style_prompt": (
            "Generate politically charged image prompts depicting power, governance, and civic tension. "
            "Include podiums, marble government halls, protest crowds, war rooms, and campaign trails. "
            "Use dramatic lighting: spotlights on speakers, flash photography, screen-lit debate stages, burning barrel fires at rallies. "
            "Visual motifs: raised fists, flags, gavels, ballot boxes, barbed wire, propaganda posters, shattered glass ceilings. "
            "Show power dynamics through composition: towering figures over crowds, isolated leaders in vast empty rooms. "
            "Color palette: patriotic reds and blues, authoritarian black and gold, revolutionary earth tones. "
            "Composition: low-angle authority shots, wide crowd panoramas, intimate behind-closed-doors tension. "
            "Style: political photojournalism meets House of Cards — gravitas, tension, consequence."
        ),
    },
    {
        "id": "true_crime",
        "name": "True Crime",
        "description": "Evidence boards, cold cases, forensic detail, investigative tension",
        "color": "#991B1B",
        "style_prompt": (
            "Generate true crime-style image prompts with investigative and forensic atmosphere. "
            "Include evidence boards with red string connections, police case files, crime scene tape, forensic labs. "
            "Use cold, clinical lighting — fluorescent morgue lights, detective desk lamps, car dashboard at night. "
            "Visual motifs: fingerprints, redacted documents, surveillance footage stills, newspaper clippings, mugshots. "
            "Environments: interrogation rooms, abandoned crime scenes, courtrooms, rain-soaked parking lots. "
            "Color palette: sickly green-white fluorescents, desaturated reality, red evidence markers, manila folder tan. "
            "Composition: overhead evidence layouts, security camera angles, tight focus on clues with bokeh background. "
            "Style: Making a Murderer meets Zodiac — procedural dread, obsessive detail, unresolved tension."
        ),
    },
    {
        "id": "conspiracy",
        "name": "Conspiracy / Occult",
        "description": "Secret societies, hidden symbols, shadowy agendas, forbidden knowledge",
        "color": "#4A1D96",
        "style_prompt": (
            "Generate conspiracy and occult-themed image prompts with mystery and forbidden knowledge. "
            "Include secret society meetings, hidden symbols carved in stone, underground bunkers, and coded manuscripts. "
            "Use low, secretive lighting — candles in dark chambers, monitor glow in surveillance rooms, moonlit rituals. "
            "Visual motifs: all-seeing eyes, pentagrams, ancient maps, sealed vaults, hooded figures, pyramid structures. "
            "Environments: underground tunnels, hidden libraries, abandoned temples, windowless rooms with monitors. "
            "Color palette: deep black, occult purple, illuminated gold, blood red, parchment cream. "
            "Composition: keyhole perspectives, partially obscured reveals, symmetrical ritual arrangements, extreme wide for isolation. "
            "Style: Eyes Wide Shut meets Da Vinci Code — seductive secrecy, ancient power, hidden truth."
        ),
    },
    {
        "id": "stoicism",
        "name": "Stoicism / Philosophy",
        "description": "Ancient wisdom, marble busts, contemplation, timeless truths",
        "color": "#78716C",
        "style_prompt": (
            "Generate stoic and philosophical image prompts evoking ancient wisdom and contemplation. "
            "Include marble busts and statues of philosophers, Roman columns, open journals, and solitary thinkers. "
            "Use meditative lighting — soft overcast skies, single candle in darkness, dawn breaking over ruins. "
            "Visual motifs: hourglasses, memento mori skulls, still water reflections, weathered stone inscriptions, laurel wreaths. "
            "Environments: Greek agoras, cliff-edge meditation spots, minimalist stone rooms, overgrown Roman ruins. "
            "Color palette: marble white, weathered stone grey, aged bronze, muted olive, warm parchment. "
            "Composition: solitary figures against vast landscapes, still-life arrangements, centered and balanced framing. "
            "Style: neoclassical painting meets modern minimalism — Marcus Aurelius energy, timeless gravitas."
        ),
    },
    {
        "id": "wealth_luxury",
        "name": "Wealth / Luxury",
        "description": "Opulence, designer interiors, supercars, gold accents, high life",
        "color": "#B8860B",
        "style_prompt": (
            "Generate luxury and wealth-themed image prompts with aspirational opulence. "
            "Include penthouses with floor-to-ceiling city views, supercars, private jets, yachts, and designer fashion. "
            "Use glamorous lighting — golden hour on infinity pools, chandelier sparkle, city skyline at blue hour. "
            "Visual motifs: gold accents, marble surfaces, champagne flutes, diamond details, brand logos, leather interiors. "
            "Environments: Monaco harbors, Dubai skylines, Swiss chalets, Maldives overwater villas, Wall Street trading floors. "
            "Color palette: black and gold, pure white, deep navy, champagne rose, emerald green. "
            "Composition: wide establishing shots of estates, detail close-ups on luxury items, reflections in polished surfaces. "
            "Style: luxury brand advertising meets Wolf of Wall Street — aspiration, excess, magnetic allure."
        ),
    },
    {
        "id": "mythology",
        "name": "Mythology / Legends",
        "description": "Gods, heroes, mythical beasts, ancient epics, divine warfare",
        "color": "#CA8A04",
        "style_prompt": (
            "Generate mythology-themed image prompts depicting gods, heroes, and legendary creatures. "
            "Include Olympian thrones, Norse world trees, Egyptian temples, Hindu celestial battles, and underworld rivers. "
            "Use divine and epic lighting — lightning bolts, solar eclipses, volcanic glow, ethereal heavenly radiance. "
            "Visual motifs: tridents, thunderbolts, winged helmets, sacred animals, runes, hieroglyphics, divine weapons. "
            "Creatures: dragons, phoenixes, minotaurs, hydras, krakens, valkyries, celestial serpents. "
            "Color palette: divine gold, storm grey, blood red, ocean teal, volcanic orange, celestial white. "
            "Composition: towering god-scale figures, epic battle panoramas, hero-vs-beast confrontations. "
            "Style: classical mythology painting meets God of War concept art — divine spectacle, mythic grandeur."
        ),
    },
    {
        "id": "children_storybook",
        "name": "Children's Storybook",
        "description": "Whimsical characters, soft pastels, magical worlds, bedtime warmth",
        "color": "#F9A8D4",
        "style_prompt": (
            "Generate children's storybook image prompts with whimsical, heartwarming illustration style. "
            "Characters should be cute, round, and expressive — talking animals, friendly creatures, curious children. "
            "Use warm, soft lighting — cozy bedroom lamps, fairy glow, sunshine through cottage windows. "
            "Visual motifs: mushroom houses, rainbow bridges, magic wands, friendly stars and moons, flower crowns. "
            "Environments: enchanted meadows, treehouse villages, candy-colored towns, cloud castles, friendly forests. "
            "Color palette: soft pastels — baby blue, mint green, peach, lavender, buttercup yellow. "
            "Composition: centered and clear, slightly naive perspective, plenty of open sky and rolling hills. "
            "Style: Beatrix Potter meets Studio Ghibli — gentle wonder, innocence, bedtime story magic."
        ),
    },
    {
        "id": "war_military",
        "name": "War / Military",
        "description": "Battlefields, soldiers, strategy rooms, grit and sacrifice",
        "color": "#4B5320",
        "style_prompt": (
            "Generate war and military-themed image prompts with visceral authenticity and emotional weight. "
            "Include battlefields, trenches, aircraft carriers, strategy war rooms, and soldiers in formation. "
            "Use harsh, unflinching lighting — explosions illuminating smoke, overcast grey skies, harsh desert sun, night flares. "
            "Visual motifs: dog tags, battle maps, barbed wire, ammunition, medals, folded flags, letters from home. "
            "Environments: bombed-out cities, muddy foxholes, vast ocean convoys, jungle patrols, tense border checkpoints. "
            "Color palette: army olive, steel grey, mud brown, gunmetal, muted khaki, occasional blood red. "
            "Composition: wide battlefield chaos, intimate soldier portraits, overhead strategic views, silhouettes against fire. "
            "Style: Saving Private Ryan meets war photojournalism — raw courage, cost of conflict, humanity in crisis."
        ),
    },
    {
        "id": "stickman_animation",
        "name": "Stickman Animation",
        "description": "Stick figures, whiteboard doodles, simple line art, playful sketches",
        "color": "#E5E7EB",
        "style_prompt": (
            "Generate image prompts in stick figure / whiteboard animation style. "
            "Characters are simple stickmen with circle heads, line bodies, and dot eyes — expressive through pose only. "
            "Use a clean white or off-white background like a whiteboard, notebook paper, or chalkboard. "
            "Drawings should look hand-sketched with slightly wobbly lines, as if drawn in real-time. "
            "Include simple props drawn in the same style: speech bubbles, arrows, thought clouds, exclamation marks. "
            "Environments are minimal — a few lines for ground, simple shapes for buildings, stick trees. "
            "Color palette: primarily black lines on white, with occasional single-color highlights (red circle, blue arrow). "
            "Composition: centered action, comic-strip panel layouts, before/after comparisons. "
            "Style: XKCD meets whiteboard explainer videos — charming simplicity, humor through minimalism."
        ),
    },
    {
        "id": "two_choices",
        "name": "Two Things Can Happen",
        "description": "Branching choices, split-screen fates, \"what if\" storytelling",
        "color": "#F97316",
        "style_prompt": (
            "Generate image prompts for a branching-choice narrative where every scene presents TWO possible outcomes. "
            "IMPORTANT: For each scene, create a SPLIT composition showing both paths side by side. "
            "Use a clear visual divider — a vertical split, a forking road, a cracked mirror, or a door with two sides. "
            "Left side shows Choice A (often the safe/expected path), right side shows Choice B (the risky/unexpected path). "
            "Each side should have distinct lighting and color grading: warm/cool, bright/dark, green/red to contrast outcomes. "
            "Visual motifs: forking paths, crossroads, two doors, split screens, parallel timelines, coin flips mid-air. "
            "Include text-friendly space for overlay labels like 'Option A' / 'Option B' or 'Stay' / 'Leave'. "
            "Environments should mirror each other with key differences — same room but one is intact, other destroyed. "
            "Color palette: contrasting dualities — gold vs blue, red vs green, light vs shadow. "
            "Composition: symmetrical split-screen, or a character standing at a literal fork/crossroads center-frame. "
            "Style: interactive story aesthetic, Bandersnatch meets moral dilemma TikToks — suspense of choice, weight of consequence."
        ),
    },
    {
        "id": "lofi_pixel",
        "name": "Lo-Fi Cozy Pixel",
        "description": "Low-resolution pixel art, cozy scenes, retro game aesthetics, warm nostalgia",
        "color": "#7DD3FC",
        "style_prompt": (
            "Generate image prompts in low-resolution pixel art animation style with cozy, lo-fi atmosphere. "
            "Characters and environments should be rendered as chunky pixel sprites — 16-bit to 32-bit era aesthetics. "
            "Use warm, muted color palettes: soft amber, dusty rose, sage green, lavender, warm cream. "
            "Scenes should feel intimate and cozy: rainy window with tea, cat on a desk, sunset rooftop, record player corner. "
            "Include lo-fi details: steam rising from cups, rain streaks on glass, flickering screen glow, gentle leaf falling. "
            "Lighting: warm lamplight, golden hour pixel gradients, neon sign reflections, moonlit bedroom. "
            "Environments: small bedrooms with fairy lights, bookshop interiors, ramen stalls, train window views, rooftop gardens. "
            "Animation cues: describe subtle looping motion — blinking cursor, swaying plants, drifting clouds, flickering candle. "
            "Composition: side-view or 3/4 isometric perspective, cozy framing with detailed pixel interiors. "
            "Style: lo-fi hip hop stream backgrounds meets Stardew Valley — pixelated warmth, gentle nostalgia, quiet comfort."
        ),
    },
]

# Quick lookup by ID
TEMPLATES_BY_ID = {t["id"]: t for t in SCENE_STYLE_TEMPLATES}
