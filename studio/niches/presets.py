"""Niche presets — user-facing combinations of visual style + story tone + defaults.

A niche is a marketable content angle. Selecting a niche auto-fills:
  - category (broad topic)
  - visual_style (template ID for scene rendering)
  - story_tone (narration tone keyword)
  - voice, speed (TTS defaults)
  - editing_style (future: pacing preset)

Presets are stored in _data/niche_presets.json. The Python DEFAULTS below are
used only when the JSON file doesn't exist yet (first run).
"""

import json
import re
from pathlib import Path

from studio.build_scene_blueprints.templates import SCENE_STYLE_TEMPLATES, TEMPLATES_BY_ID

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "_data"
_PRESETS_FILE = _DATA_DIR / "niche_presets.json"
_VALID_TAGS = ("tiktok", "youtube", "shorts", "trending")
_DEFAULT_VOICE = "af_heart"
_DEFAULT_SPEED = 1.0
_DEFAULT_DURATION = 45

# ── Hardcoded defaults (always available as built-in presets) ─────────────────
_DEFAULTS = {
    # ── Minimalist Illustration ──
    "minimal_illustration_psychology": {
        "label": "Minimal Illustration — Psychology",
        "description": "Bold single objects on vast white space. Origami-like flat illustrations as visual metaphors for psychological concepts.",
        "category": "psychology",
        "niche": "dark_psychology",
        "visual_style": "minimal_illustration",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.9,
        "duration": 45,
        "tags": ["trending", "tiktok", "shorts"],
    },
    "minimal_illustration_philosophy": {
        "label": "Minimal Illustration — Philosophy",
        "description": "Clean geometric illustrations with vast negative space. Contemplative, poetic narration exploring philosophical ideas.",
        "category": "philosophy",
        "niche": "stoicism",
        "visual_style": "minimal_illustration",
        "story_tone": "inspirational",
        "voice": "af_heart",
        "speed": 0.85,
        "duration": 60,
        "tags": ["youtube"],
    },
    "minimal_illustration_motivational": {
        "label": "Minimal Illustration — Motivational",
        "description": "Single symbolic objects as metaphors for growth and change. Clean, uplifting, editorial illustration style.",
        "category": "motivation",
        "niche": "motivational",
        "visual_style": "minimal_illustration",
        "story_tone": "inspirational",
        "voice": "af_heart",
        "speed": 0.9,
        "duration": 45,
        "tags": ["trending", "tiktok", "youtube"],
    },
    # ── Dark Psychology ──
    "dark_psychology_stickman": {
        "label": "Stickman Dark Psychology",
        "description": "Minimalist stickman visuals with dark psychological narration. Suspenseful tone, fast-paced for TikTok/Shorts.",
        "category": "psychology",
        "niche": "dark_psychology",
        "visual_style": "stickman_animation",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.95,
        "duration": 35,
        "tags": ["trending", "tiktok", "shorts"],
    },
    "dark_psychology_cinematic": {
        "label": "Cinematic Dark Psychology",
        "description": "Cinematic visuals with psychological tension. Film-quality lighting and dramatic framing.",
        "category": "psychology",
        "niche": "dark_psychology",
        "visual_style": "cinematic",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.95,
        "duration": 60,
        "tags": ["youtube", "shorts"],
    },
    "dark_psychology_noir": {
        "label": "Noir Dark Psychology",
        "description": "Film noir shadows and mystery atmosphere for dark psychology content. Deep male voice, slow pacing.",
        "category": "psychology",
        "niche": "dark_psychology",
        "visual_style": "noir",
        "story_tone": "suspenseful",
        "voice": "bm_daniel",
        "speed": 0.9,
        "duration": 75,
        "tags": ["youtube"],
    },
    # ── True Crime ──
    "true_crime_cinematic": {
        "label": "Cinematic True Crime",
        "description": "Cinematic visuals for true crime investigations. Evidence boards, forensic detail, dramatic narration.",
        "category": "crime",
        "niche": "true_crime",
        "visual_style": "cinematic",
        "story_tone": "dramatic",
        "voice": "bm_daniel",
        "speed": 0.9,
        "duration": 90,
        "tags": ["youtube"],
    },
    "true_crime_noir": {
        "label": "Noir True Crime",
        "description": "Noir-style true crime with rain-slicked streets, venetian blind shadows, and cold case atmosphere.",
        "category": "crime",
        "niche": "true_crime",
        "visual_style": "noir",
        "story_tone": "dramatic",
        "voice": "bm_daniel",
        "speed": 0.85,
        "duration": 90,
        "tags": ["youtube"],
    },
    # ── Horror ──
    "horror_cinematic": {
        "label": "Cinematic Horror",
        "description": "Dark, atmospheric horror with cinematic quality. Eerie shadows, desaturated tones, slow-building dread.",
        "category": "horror",
        "niche": "horror",
        "visual_style": "dark_horror",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.9,
        "duration": 60,
        "tags": ["youtube", "shorts"],
    },
    "horror_stickman": {
        "label": "Stickman Horror",
        "description": "Simple stickman art with unsettling horror stories. Minimal visuals let the narration build tension.",
        "category": "horror",
        "niche": "horror",
        "visual_style": "stickman_animation",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.95,
        "duration": 35,
        "tags": ["tiktok", "shorts"],
    },
    "horror_anime": {
        "label": "Anime Horror",
        "description": "Japanese anime-style horror with expressive characters, vivid colors, and supernatural dread.",
        "category": "horror",
        "niche": "horror",
        "visual_style": "anime",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 1.0,
        "duration": 40,
        "tags": ["shorts"],
    },
    # ── Philosophy ──
    "stoicism_cinematic": {
        "label": "Cinematic Stoicism",
        "description": "Cinematic visuals with stoic philosophy narration. Marble busts, ancient ruins, educational tone.",
        "category": "philosophy",
        "niche": "stoicism",
        "visual_style": "cinematic",
        "story_tone": "educational",
        "voice": "bm_daniel",
        "speed": 0.9,
        "duration": 60,
        "tags": ["youtube", "shorts"],
    },
    "stoicism_stickman": {
        "label": "Stickman Stoicism",
        "description": "Whiteboard-style stickman illustrations for stoic philosophy lessons. Clear, educational, bite-sized.",
        "category": "philosophy",
        "niche": "stoicism",
        "visual_style": "stickman_animation",
        "story_tone": "educational",
        "voice": "bm_daniel",
        "speed": 0.95,
        "duration": 35,
        "tags": ["tiktok", "shorts"],
    },
    "existential_philosophy": {
        "label": "Existential Philosophy",
        "description": "Futuristic abstract visuals with philosophical narration. High-contrast mind exploration for deep-thinking content.",
        "category": "philosophy",
        "niche": "existential",
        "visual_style": "existential",
        "story_tone": "dramatic",
        "voice": "af_heart",
        "speed": 0.9,
        "duration": 60,
        "tags": ["youtube", "shorts"],
    },
    # ── Motivation ──
    "motivation_stickman": {
        "label": "Stickman Motivation",
        "description": "Simple stickman visuals with uplifting, inspirational narration. Call-to-action endings.",
        "category": "motivation",
        "niche": "motivation",
        "visual_style": "stickman_animation",
        "story_tone": "inspirational",
        "voice": "af_heart",
        "speed": 1.0,
        "duration": 30,
        "tags": ["tiktok", "shorts"],
    },
    "motivation_cinematic": {
        "label": "Cinematic Motivation",
        "description": "Epic cinematic visuals with inspirational narration. Sunrise shots, mountain peaks, triumphant moments.",
        "category": "motivation",
        "niche": "motivation",
        "visual_style": "motivational",
        "story_tone": "inspirational",
        "voice": "bm_daniel",
        "speed": 0.95,
        "duration": 60,
        "tags": ["youtube", "shorts"],
    },
    "wealth_cinematic": {
        "label": "Cinematic Wealth & Luxury",
        "description": "Luxury lifestyle visuals with aspirational narration. Penthouses, supercars, golden hour opulence.",
        "category": "motivation",
        "niche": "wealth",
        "visual_style": "cinematic",
        "story_tone": "inspirational",
        "voice": "bm_daniel",
        "speed": 0.95,
        "duration": 60,
        "tags": ["youtube", "shorts"],
    },
    # ── Religion ──
    "biblical_cinematic": {
        "label": "Cinematic Biblical",
        "description": "Cinematic visuals for biblical stories. Divine lighting, sacred imagery, dramatic weight.",
        "category": "religion",
        "niche": "biblical",
        "visual_style": "cinematic",
        "story_tone": "dramatic",
        "voice": "bm_daniel",
        "speed": 0.85,
        "duration": 90,
        "tags": ["youtube"],
    },
    "biblical_gothic": {
        "label": "Gothic Biblical",
        "description": "Gothic cathedral aesthetics for religious content. Candlelight, stained glass, dark Victorian elegance.",
        "category": "religion",
        "niche": "biblical",
        "visual_style": "gothic",
        "story_tone": "dramatic",
        "voice": "bm_daniel",
        "speed": 0.85,
        "duration": 90,
        "tags": ["youtube"],
    },
    "biblical_fear_apocalypse": {
        "label": "Biblical Fear — Apocalypse",
        "description": "Revelation-style apocalyptic terror. Seven seals, four horsemen, lakes of fire, falling stars, and the final judgment.",
        "category": "religion",
        "niche": "biblical_apocalypse",
        "visual_style": "dark_horror",
        "story_tone": "suspenseful",
        "voice": "bm_daniel",
        "speed": 0.8,
        "duration": 90,
        "tags": ["youtube", "shorts"],
    },
    "biblical_curiosity_unknown_facts": {
        "label": "Bible Curiosity — Unknown Facts",
        "description": "Surprising, little-known facts hidden in scripture. Odd laws, forgotten verses, and details most believers never hear about.",
        "category": "religion",
        "niche": "bible_curiosity",
        "visual_style": "cinematic",
        "story_tone": "educational",
        "voice": "bm_daniel",
        "speed": 0.9,
        "duration": 60,
        "tags": ["trending", "shorts", "tiktok"],
    },
    "biblical_unknown_history": {
        "label": "Unknown History in the Bible",
        "description": "Lost civilizations, erased tribes, and historical events recorded in scripture that mainstream history overlooks.",
        "category": "religion",
        "niche": "bible_hidden_history",
        "visual_style": "dark_academia",
        "story_tone": "educational",
        "voice": "bm_daniel",
        "speed": 0.85,
        "duration": 90,
        "tags": ["youtube"],
    },
    "biblical_logic_analogy": {
        "label": "Biblical Logic & Analogy",
        "description": "Breaking down scripture with sharp logic, modern analogies, and thought experiments that make ancient text click.",
        "category": "religion",
        "niche": "bible_logic",
        "visual_style": "minimal_illustration",
        "story_tone": "educational",
        "voice": "bm_daniel",
        "speed": 0.9,
        "duration": 60,
        "tags": ["youtube", "shorts"],
    },
    "biblical_contradictions": {
        "label": "Bible Contradictions",
        "description": "Exploring apparent contradictions in scripture. Two conflicting verses side-by-side, then the deeper context most people miss.",
        "category": "religion",
        "niche": "bible_contradictions",
        "visual_style": "noir",
        "story_tone": "suspenseful",
        "voice": "bm_daniel",
        "speed": 0.85,
        "duration": 75,
        "tags": ["trending", "youtube"],
    },
    "biblical_untrue_history": {
        "label": "Untrue Bible History",
        "description": "Stories everyone thinks are in the Bible but aren't. Common misconceptions, cultural myths, and misquoted scripture debunked.",
        "category": "religion",
        "niche": "bible_myths_debunked",
        "visual_style": "surreal",
        "story_tone": "educational",
        "voice": "bm_daniel",
        "speed": 0.9,
        "duration": 60,
        "tags": ["trending", "tiktok", "shorts"],
    },
    "biblical_unreal_history": {
        "label": "Unreal Bible History",
        "description": "The most unbelievable true events in scripture. Giants, talking animals, sun standing still, iron floating — events too bizarre to be fiction.",
        "category": "religion",
        "niche": "bible_unreal_events",
        "visual_style": "fantasy_epic",
        "story_tone": "dramatic",
        "voice": "bm_daniel",
        "speed": 0.85,
        "duration": 75,
        "tags": ["trending", "youtube", "shorts"],
    },
    # ── Mystery / Conspiracy ──
    "conspiracy_noir": {
        "label": "Noir Conspiracy",
        "description": "Film noir visuals for conspiracy and occult stories. Secret symbols, shadowy agendas, hidden truths.",
        "category": "mystery",
        "niche": "conspiracy",
        "visual_style": "noir",
        "story_tone": "suspenseful",
        "voice": "bm_daniel",
        "speed": 0.9,
        "duration": 75,
        "tags": ["youtube"],
    },
    "conspiracy_cinematic": {
        "label": "Cinematic Conspiracy",
        "description": "Cinematic visuals for conspiracy theories. Underground bunkers, coded manuscripts, suspenseful reveals.",
        "category": "mystery",
        "niche": "conspiracy",
        "visual_style": "cinematic",
        "story_tone": "suspenseful",
        "voice": "bm_daniel",
        "speed": 0.9,
        "duration": 60,
        "tags": ["youtube", "shorts"],
    },
    # ── Romance ──
    "anime_romance": {
        "label": "Anime Romance",
        "description": "Anime-style romance with expressive characters, vivid colors, and emotional story arcs.",
        "category": "romance",
        "niche": "romance",
        "visual_style": "anime",
        "story_tone": "dramatic",
        "voice": "af_heart",
        "speed": 1.0,
        "duration": 45,
        "tags": ["shorts"],
    },
    # ── Children ──
    "children_storybook_wholesome": {
        "label": "Wholesome Storybook",
        "description": "Soft pastel storybook illustrations with gentle, age-appropriate narration. Warm and magical.",
        "category": "children",
        "niche": "children",
        "visual_style": "children_storybook",
        "story_tone": "wholesome",
        "voice": "af_heart",
        "speed": 0.9,
        "duration": 45,
        "tags": ["youtube"],
    },
    # ── Sci-Fi ──
    "scifi_cyberpunk": {
        "label": "Cyberpunk Sci-Fi",
        "description": "Neon-soaked cyberpunk visuals for sci-fi stories. Futuristic tech, rain-slicked chrome, dramatic pacing.",
        "category": "science",
        "niche": "sci_fi",
        "visual_style": "cyberpunk",
        "story_tone": "dramatic",
        "voice": "bm_daniel",
        "speed": 1.0,
        "duration": 60,
        "tags": ["youtube", "shorts"],
    },
    # ── Reddit / Anecdote ──
    "reddit_story_cinematic": {
        "label": "Reddit Story",
        "description": "Relatable everyday visuals for Reddit-style personal stories. Candid, grounded, dramatic twists.",
        "category": "anecdote",
        "niche": "reddit",
        "visual_style": "reddit_story",
        "story_tone": "dramatic",
        "voice": "af_heart",
        "speed": 1.0,
        "duration": 45,
        "tags": ["tiktok", "youtube", "shorts"],
    },
    # ── Two Choices ──
    "two_choices_cinematic": {
        "label": "Two Things Can Happen",
        "description": "Split-screen branching choices. Every scene shows two possible outcomes side by side.",
        "category": "psychology",
        "niche": "two_choices",
        "visual_style": "two_choices",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 1.0,
        "duration": 35,
        "tags": ["tiktok", "shorts"],
    },
    "code_cosmos_science": {
        "label": "Code Cosmos — Science",
        "description": "Earth from space overlaid with floating code and math. Intellectual sci-fi awe.",
        "category": "science",
        "niche": "science_tech",
        "visual_style": "code_cosmos",
        "story_tone": "educational",
        "voice": "am_adam",
        "speed": 0.95,
        "duration": 60,
        "tags": ["science", "tech", "programming", "shorts"],
    },
    "code_cosmos_curiosity": {
        "label": "Code Cosmos — Curiosity",
        "description": "The universe through a programmer's eyes. Cosmic code meets big questions.",
        "category": "curiosity",
        "niche": "curiosity_facts",
        "visual_style": "code_cosmos",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.9,
        "duration": 45,
        "tags": ["curiosity", "facts", "universe", "tiktok"],
    },
    "code_cosmos_philosophy": {
        "label": "Code Cosmos — Philosophy",
        "description": "Are we living in a simulation? Cosmic code meets existential questions.",
        "category": "philosophy",
        "niche": "existential",
        "visual_style": "code_cosmos",
        "story_tone": "dramatic",
        "voice": "bm_george",
        "speed": 0.85,
        "duration": 50,
        "tags": ["philosophy", "simulation", "existential", "shorts"],
    },
    "solitary_path_psychology": {
        "label": "Solitary Path — Psychology",
        "description": "Lone figure on vast desert horizon. Existential isolation, vanishing point symmetry.",
        "category": "psychology",
        "niche": "dark_psychology",
        "visual_style": "solitary_path",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.85,
        "duration": 50,
        "tags": ["psychology", "loneliness", "existential", "shorts"],
    },
    "solitary_path_motivation": {
        "label": "Solitary Path — Motivation",
        "description": "The long road ahead. One person, one path, infinite sky.",
        "category": "motivation",
        "niche": "motivation",
        "visual_style": "solitary_path",
        "story_tone": "inspirational",
        "voice": "am_adam",
        "speed": 0.9,
        "duration": 45,
        "tags": ["motivation", "journey", "perseverance", "tiktok"],
    },
    "crimson_silhouette_horror": {
        "label": "Crimson Silhouette — Horror",
        "description": "Black silhouettes against blood-red sky. Primal, mythic dread.",
        "category": "horror",
        "niche": "horror",
        "visual_style": "crimson_silhouette",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.85,
        "duration": 45,
        "tags": ["horror", "dark", "silhouette", "shorts"],
    },
    "crimson_silhouette_nature": {
        "label": "Crimson Silhouette — Nature",
        "description": "Epic wilderness at sunset. Deer, wolves, eagles as shadow puppets against the red sky.",
        "category": "nature",
        "niche": "nature",
        "visual_style": "crimson_silhouette",
        "story_tone": "dramatic",
        "voice": "bm_george",
        "speed": 0.9,
        "duration": 50,
        "tags": ["nature", "wildlife", "sunset", "epic"],
    },
    "crimson_silhouette_survival": {
        "label": "Crimson Silhouette — Survival",
        "description": "Lone survivor against the dying light. Primal instinct meets vast wilderness.",
        "category": "survival",
        "niche": "survival_adventure",
        "visual_style": "crimson_silhouette",
        "story_tone": "suspenseful",
        "voice": "am_adam",
        "speed": 0.95,
        "duration": 55,
        "tags": ["survival", "wilderness", "primal", "tiktok"],
    },
    "gothic_moonlit_horror": {
        "label": "Gothic Moonlit — Horror",
        "description": "Haunted European city under blood-red moonlit sky. Gothic architecture, dark manga style.",
        "category": "horror",
        "niche": "horror",
        "visual_style": "gothic_moonlit",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.85,
        "duration": 50,
        "tags": ["horror", "gothic", "dark", "shorts"],
    },
    "gothic_moonlit_mystery": {
        "label": "Gothic Moonlit — Mystery",
        "description": "Ancient city secrets beneath the full moon. Cathedrals hide forbidden knowledge.",
        "category": "mystery",
        "niche": "mystery",
        "visual_style": "gothic_moonlit",
        "story_tone": "suspenseful",
        "voice": "bm_george",
        "speed": 0.9,
        "duration": 55,
        "tags": ["mystery", "gothic", "conspiracy", "tiktok"],
    },
    "gothic_moonlit_history": {
        "label": "Gothic Moonlit — History",
        "description": "Medieval European nights. History told through moonlit stone and shadow.",
        "category": "history",
        "niche": "history",
        "visual_style": "gothic_moonlit",
        "story_tone": "dramatic",
        "voice": "bm_george",
        "speed": 0.9,
        "duration": 60,
        "tags": ["history", "medieval", "europe", "dark_academia"],
    },
    # ── Body Signal ──
    "body_signal_psychology": {
        "label": "Body Signal — Psychology",
        "description": "Dark body silhouettes with glowing nervous system lines. The body as a map of the mind.",
        "category": "psychology",
        "niche": "dark_psychology",
        "visual_style": "body_signal",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.85,
        "duration": 50,
        "tags": ["trending", "tiktok", "shorts"],
    },
    "body_signal_science": {
        "label": "Body Signal — Science",
        "description": "Anatomical signal maps glowing in the dark. Educational neuroscience and biology visualization.",
        "category": "science",
        "niche": "science_tech",
        "visual_style": "body_signal",
        "story_tone": "educational",
        "voice": "bm_daniel",
        "speed": 0.9,
        "duration": 60,
        "tags": ["youtube", "shorts"],
    },
    "body_signal_philosophy": {
        "label": "Body Signal — Philosophy",
        "description": "The body as signal, consciousness as light. Existential questions through anatomical contemplation.",
        "category": "philosophy",
        "niche": "existential",
        "visual_style": "body_signal",
        "story_tone": "dramatic",
        "voice": "bm_george",
        "speed": 0.85,
        "duration": 60,
        "tags": ["youtube", "shorts"],
    },
    # ── Neural Glow ──
    "neural_glow_psychology": {
        "label": "Neural Glow — Psychology",
        "description": "Translucent brains and neural structures pulsing with red synaptic fire. Clinical tension, dark psychology.",
        "category": "psychology",
        "niche": "dark_psychology",
        "visual_style": "neural_glow",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.85,
        "duration": 45,
        "tags": ["trending", "tiktok", "shorts"],
    },
    "neural_glow_science": {
        "label": "Neural Glow — Science",
        "description": "Holographic anatomical structures glowing in the void. Medical-grade sci-fi visualization.",
        "category": "science",
        "niche": "science_tech",
        "visual_style": "neural_glow",
        "story_tone": "educational",
        "voice": "bm_daniel",
        "speed": 0.9,
        "duration": 60,
        "tags": ["youtube", "shorts"],
    },
    "neural_glow_horror": {
        "label": "Neural Glow — Horror",
        "description": "Something alive pulses in the dark. Anatomical horror rendered as glowing translucent specimens.",
        "category": "horror",
        "niche": "horror",
        "visual_style": "neural_glow",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.8,
        "duration": 50,
        "tags": ["shorts", "tiktok"],
    },
    # ── Tension Macro ──
    "tension_macro_psychology": {
        "label": "Tension Macro — Psychology",
        "description": "Extreme close-ups of worried eyes and clenched jaws. Dark shadows, painterly stylization, psychological dread.",
        "category": "psychology",
        "niche": "dark_psychology",
        "visual_style": "tension_macro",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.85,
        "duration": 45,
        "tags": ["trending", "tiktok", "shorts"],
    },
    "tension_macro_horror": {
        "label": "Tension Macro — Horror",
        "description": "Something is wrong behind those eyes. Extreme close-up horror with micro-expression tension.",
        "category": "horror",
        "niche": "horror",
        "visual_style": "tension_macro",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.8,
        "duration": 50,
        "tags": ["shorts", "tiktok"],
    },
    "tension_macro_crime": {
        "label": "Tension Macro — True Crime",
        "description": "Interrogation-room intensity. Sweat on brow, darting eyes, the moment before confession.",
        "category": "crime",
        "niche": "true_crime",
        "visual_style": "tension_macro",
        "story_tone": "dramatic",
        "voice": "bm_daniel",
        "speed": 0.85,
        "duration": 60,
        "tags": ["youtube", "shorts"],
    },
    # ── Neon Sigil ──
    "neon_sigil_psychology": {
        "label": "Neon Sigil — Psychology",
        "description": "Glowing occult symbols on dark geometric grids. Forbidden knowledge, dark psychology.",
        "category": "psychology",
        "niche": "dark_psychology",
        "visual_style": "neon_sigil",
        "story_tone": "suspenseful",
        "voice": "af_heart",
        "speed": 0.9,
        "duration": 45,
        "tags": ["trending", "tiktok", "shorts"],
    },
    "neon_sigil_conspiracy": {
        "label": "Neon Sigil — Conspiracy",
        "description": "Illuminati eyes, hidden symbols, secret society iconography on dark grids.",
        "category": "mystery",
        "niche": "conspiracy",
        "visual_style": "neon_sigil",
        "story_tone": "suspenseful",
        "voice": "bm_daniel",
        "speed": 0.9,
        "duration": 60,
        "tags": ["youtube", "shorts"],
    },
    "neon_sigil_philosophy": {
        "label": "Neon Sigil — Philosophy",
        "description": "Abstract philosophical symbols glowing against sacred geometry. Deep existential questions.",
        "category": "philosophy",
        "niche": "existential",
        "visual_style": "neon_sigil",
        "story_tone": "dramatic",
        "voice": "bm_george",
        "speed": 0.85,
        "duration": 60,
        "tags": ["youtube", "shorts"],
    },
    "short_test": {
        "label": "Short Test",
        "description": "Quick pipeline smoke test — 3-5 simple scenes, fast generation.",
        "category": "test",
        "niche": "test",
        "visual_style": "short_test",
        "story_tone": "dramatic",
        "voice": "af_heart",
        "speed": 1.0,
        "duration": 15,
        "tags": ["test", "debug", "quick"],
    },
}

# ── Story tones — narration style keywords for the LLM ──────────────────────
STORY_TONES = {
    "suspenseful": "Dark, tense, slow-building dread. Use short punchy sentences. Build unease.",
    "dramatic": "Emotional weight, vivid imagery, strong narrative arc. Vary sentence rhythm.",
    "educational": "Clear, authoritative, insightful. Teach through story, not lecture.",
    "inspirational": "Uplifting, empowering, forward-looking. End with a call to action.",
    "comedic": "Witty, unexpected twists, conversational. Subvert expectations.",
    "wholesome": "Warm, gentle, age-appropriate. Simple language, positive resolution.",
}

# ── All valid categories ─────────────────────────────────────────────────────
CATEGORIES = [
    "test",
    "psychology", "crime", "horror", "motivation", "philosophy",
    "religion", "mystery", "science", "history", "nature",
    "romance", "comedy", "children", "anecdote", "politics",
    "survival", "curiosity", "space",
]


# ── Load / Save ──────────────────────────────────────────────────────────────

def _clean_text(value, *, max_length=120) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text[:max_length].strip()


def _normalize_slug(value) -> str:
    text = _clean_text(value, max_length=80).lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _normalize_speed(value, *, default=_DEFAULT_SPEED) -> float:
    try:
        speed = float(value)
    except (TypeError, ValueError):
        return float(default)
    return max(0.5, min(2.0, round(speed, 2)))


def _normalize_duration(value, *, default=_DEFAULT_DURATION) -> int:
    try:
        duration = int(value)
    except (TypeError, ValueError):
        return int(default)
    return max(15, min(180, duration))


def _normalize_tags(tags) -> list[str]:
    if not isinstance(tags, list):
        return []
    seen = set()
    normalized = []
    for raw_tag in tags:
        tag = _normalize_slug(raw_tag)
        if not tag or tag not in _VALID_TAGS or tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
    return normalized[:4]


def get_visual_styles() -> list[dict]:
    """Return the list of selectable visual styles for niche presets."""
    return [
        {"id": t["id"], "name": t["name"], "color": t.get("color", "#888")}
        for t in SCENE_STYLE_TEMPLATES
        if t.get("type") in ("visual", "hybrid")
    ]


def is_known_template(style_id: str) -> bool:
    return _normalize_slug(style_id) in TEMPLATES_BY_ID


def is_valid_visual_style(style_id: str) -> bool:
    candidate = _normalize_slug(style_id)
    return any(style["id"] == candidate for style in get_visual_styles())


def is_valid_story_tone(tone_id: str) -> bool:
    return _normalize_slug(tone_id) in STORY_TONES


def is_valid_category(category_id: str) -> bool:
    return _normalize_slug(category_id) in CATEGORIES


def normalize_preset_id(value) -> str:
    return _normalize_slug(value)


def normalize_story_tone(value) -> str:
    return _normalize_slug(value)


def normalize_category(value) -> str:
    return _normalize_slug(value)


def normalize_visual_style(value) -> str:
    return _normalize_slug(value)


def is_builtin_preset(preset_id: str) -> bool:
    return normalize_preset_id(preset_id) in _DEFAULTS


def preset_exists(preset_id: str) -> bool:
    return normalize_preset_id(preset_id) in get_presets()


def normalize_preset_payload(preset_id: str, data: dict) -> tuple[str, dict]:
    """Normalize and validate a niche preset payload."""
    preset_key = normalize_preset_id(preset_id)
    if not preset_key:
        raise ValueError("Preset id is required")

    label = _clean_text((data or {}).get("label"), max_length=60)
    if len(label) < 3:
        raise ValueError("Preset label must be at least 3 characters")

    category = normalize_category((data or {}).get("category"))
    if not is_valid_category(category):
        raise ValueError(f"Unknown category '{data.get('category', '')}'")

    niche = normalize_preset_id((data or {}).get("niche") or category)
    if not niche:
        raise ValueError("Preset niche is required")

    visual_style = normalize_visual_style((data or {}).get("visual_style"))
    if not is_valid_visual_style(visual_style):
        raise ValueError(f"Unknown visual style '{data.get('visual_style', '')}'")

    story_tone = normalize_story_tone((data or {}).get("story_tone"))
    if not is_valid_story_tone(story_tone):
        raise ValueError(f"Unknown story tone '{data.get('story_tone', '')}'")

    normalized = {
        "label": label,
        "description": _clean_text((data or {}).get("description"), max_length=240),
        "category": category,
        "niche": niche,
        "visual_style": visual_style,
        "story_tone": story_tone,
        "voice": _clean_text((data or {}).get("voice"), max_length=40) or _DEFAULT_VOICE,
        "speed": _normalize_speed((data or {}).get("speed"), default=_DEFAULT_SPEED),
        "duration": _normalize_duration((data or {}).get("duration"), default=_DEFAULT_DURATION),
        "tags": _normalize_tags((data or {}).get("tags", [])),
        "thumbnail": _clean_text((data or {}).get("thumbnail"), max_length=120),
        "custom": bool((data or {}).get("custom", False)),
    }

    if not normalized["thumbnail"]:
        normalized.pop("thumbnail")
    if not normalized["description"]:
        normalized.pop("description")
    if not normalized["tags"]:
        normalized["tags"] = []

    return preset_key, normalized


def _normalize_presets_map(raw_presets: dict) -> dict:
    if not isinstance(raw_presets, dict):
        return {}

    normalized = {}
    for preset_id, data in raw_presets.items():
        try:
            key, value = normalize_preset_payload(preset_id, data or {})
        except ValueError:
            continue
        normalized[key] = value
    return normalized


def _load_presets() -> dict:
    """Load presets from JSON file, merging in any new built-in defaults."""
    raw_presets = None
    if _PRESETS_FILE.exists():
        try:
            with open(_PRESETS_FILE, "r", encoding="utf-8") as f:
                raw_presets = json.load(f)
        except (OSError, json.JSONDecodeError):
            raw_presets = None
    normalized = _normalize_presets_map(raw_presets or _DEFAULTS)
    if not normalized:
        normalized = _normalize_presets_map(_DEFAULTS)
    # Merge any new built-in defaults that aren't in the saved file
    defaults_normalized = _normalize_presets_map(_DEFAULTS)
    for key, value in defaults_normalized.items():
        if key not in normalized:
            normalized[key] = value
    return normalized


def _save_presets(presets: dict) -> None:
    """Write presets to JSON file."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_PRESETS_FILE, "w", encoding="utf-8") as f:
        json.dump(_normalize_presets_map(presets), f, indent=2, ensure_ascii=False)


def get_presets() -> dict:
    """Get all niche presets (always fresh from disk)."""
    return _load_presets()


def save_preset(preset_id: str, data: dict) -> dict:
    """Save or update a single niche preset. Returns the full presets dict."""
    if is_builtin_preset(preset_id):
        raise ValueError("Built-in presets cannot be overwritten")
    presets = _load_presets()
    key, normalized = normalize_preset_payload(preset_id, data)
    if key in presets:
        raise ValueError(f"Preset '{key}' already exists")
    presets[key] = normalized
    _save_presets(presets)
    return presets


def delete_preset(preset_id: str) -> dict:
    """Delete a niche preset by ID. Returns the full presets dict."""
    key = normalize_preset_id(preset_id)
    if not key:
        raise ValueError("Preset id is required")
    if is_builtin_preset(key):
        raise ValueError("Built-in presets cannot be deleted")
    presets = _load_presets()
    if key not in presets:
        raise ValueError(f"Unknown preset '{key}'")
    presets.pop(key, None)
    _save_presets(presets)
    return presets


# ── Backward-compat module-level export ──────────────────────────────────────
NICHE_PRESETS = _load_presets()


# ── Resolve niche → pipeline dimensions ──────────────────────────────────────

def resolve_niche(config: dict) -> dict:
    """Resolve a niche preset into pipeline dimensions.

    Accepts a config dict with any combination of:
      - niche_preset: preset ID (auto-fills everything)
      - style: legacy template ID (backward compat)
      - visual_style: override visual template
      - story_tone: override narration tone
      - voice, speed: override TTS defaults

    Returns dict with resolved: visual_style, story_tone, category, voice, speed
    """
    presets = get_presets()
    preset_id = normalize_preset_id((config or {}).get("niche_preset"))
    preset = presets.get(preset_id) if preset_id else None

    legacy_style = normalize_visual_style((config or {}).get("style")) or "cinematic"
    requested_visual_style = normalize_visual_style((config or {}).get("visual_style"))
    requested_story_tone = normalize_story_tone((config or {}).get("story_tone"))
    requested_category = normalize_category((config or {}).get("category"))
    voice = _clean_text((config or {}).get("voice"), max_length=40)
    speed = _normalize_speed((config or {}).get("speed"), default=preset.get("speed", _DEFAULT_SPEED) if preset else _DEFAULT_SPEED)

    visual_style = requested_visual_style if is_valid_visual_style(requested_visual_style) else ""
    if not visual_style and preset and is_valid_visual_style(preset.get("visual_style")):
        visual_style = preset["visual_style"]
    if not visual_style and is_known_template(legacy_style):
        visual_style = legacy_style
    if not visual_style:
        visual_style = "cinematic"

    story_tone = requested_story_tone if is_valid_story_tone(requested_story_tone) else ""
    if not story_tone and preset and is_valid_story_tone(preset.get("story_tone")):
        story_tone = preset["story_tone"]

    category = requested_category if is_valid_category(requested_category) else ""
    if not category and preset and is_valid_category(preset.get("category")):
        category = preset["category"]

    return {
        "visual_style": visual_style,
        "story_tone": story_tone or None,
        "category": category or None,
        "niche": preset.get("niche") if preset else None,
        "voice": voice or (preset.get("voice", _DEFAULT_VOICE) if preset else _DEFAULT_VOICE),
        "speed": speed,
    }
