/**
 * TTS voice constants — languages, voice metadata, top picks, blend presets.
 * Extracted from useTts.js to reduce composable size.
 */

export const LANG_NAMES = {
  'en-us': 'American English', 'en-gb': 'British English', 'ja': 'Japanese',
  'zh': 'Chinese', 'es': 'Spanish', 'fr': 'French', 'hi': 'Hindi',
  'it': 'Italian', 'pt-br': 'Portuguese',
}

export const LANG_SHORT = {
  'en-us': 'English US', 'en-gb': 'English UK', 'ja': 'Japanese',
  'zh': 'Chinese', 'es': 'Spanish', 'fr': 'French', 'hi': 'Hindi',
  'it': 'Italian', 'pt-br': 'Portuguese',
}

export const LANG_SHORT_COMPACT = {
  'en-us': 'US', 'en-gb': 'UK', 'ja': 'JA', 'zh': 'ZH', 'es': 'ES',
  'fr': 'FR', 'hi': 'HI', 'it': 'IT', 'pt-br': 'PT',
}

export const LANG_ORDER = ['en-us', 'en-gb', 'ja', 'zh', 'es', 'fr', 'hi', 'it', 'pt-br']

export const VOICE_META = {
  // American Female — coral/pink
  af_alloy:   { g: 'f', hue: '#FF9B9B', lang: 'en-us', name: 'Alloy',   desc: 'Neutral, versatile' },
  af_aoede:   { g: 'f', hue: '#FFB5B5', lang: 'en-us', name: 'Aoede',   desc: 'Soft, melodic' },
  af_bella:   { g: 'f', hue: '#FF8A8A', lang: 'en-us', name: 'Bella',   desc: 'Energetic, engaging' },
  af_heart:   { g: 'f', hue: '#FF7070', lang: 'en-us', name: 'Heart',   desc: 'Warm, friendly, natural' },
  af_jessica: { g: 'f', hue: '#FFA5A5', lang: 'en-us', name: 'Jessica', desc: 'Bright, conversational' },
  af_kore:    { g: 'f', hue: '#FFCECE', lang: 'en-us', name: 'Kore',    desc: 'Gentle, soothing' },
  af_nicole:  { g: 'f', hue: '#FF8080', lang: 'en-us', name: 'Nicole',  desc: 'Clear, professional' },
  af_nova:    { g: 'f', hue: '#FFD0D0', lang: 'en-us', name: 'Nova',    desc: 'Bright, modern' },
  af_river:   { g: 'f', hue: '#FFB0B0', lang: 'en-us', name: 'River',   desc: 'Calm, flowing' },
  af_sarah:   { g: 'f', hue: '#FF9595', lang: 'en-us', name: 'Sarah',   desc: 'Smooth, balanced' },
  af_sky:     { g: 'f', hue: '#FFBABA', lang: 'en-us', name: 'Sky',     desc: 'Light, airy' },
  // American Male — teal
  am_adam:    { g: 'm', hue: '#6FE3DA', lang: 'en-us', name: 'Adam',    desc: 'Warm, approachable' },
  am_echo:    { g: 'm', hue: '#5ED5CC', lang: 'en-us', name: 'Echo',    desc: 'Resonant, clear' },
  am_eric:    { g: 'm', hue: '#7EEFEA', lang: 'en-us', name: 'Eric',    desc: 'Confident, steady' },
  am_fenrir:  { g: 'm', hue: '#4ECDC4', lang: 'en-us', name: 'Fenrir',  desc: 'Bold, dynamic' },
  am_liam:    { g: 'm', hue: '#6DE0D8', lang: 'en-us', name: 'Liam',    desc: 'Friendly, casual' },
  am_michael: { g: 'm', hue: '#8AF0E8', lang: 'en-us', name: 'Michael', desc: 'Deep, authoritative' },
  am_onyx:    { g: 'm', hue: '#5CD8D0', lang: 'en-us', name: 'Onyx',    desc: 'Rich, powerful' },
  am_puck:    { g: 'm', hue: '#7AE8E0', lang: 'en-us', name: 'Puck',    desc: 'Playful, expressive' },
  // British Female — purple/lavender
  bf_alice:    { g: 'f', hue: '#C4B5FD', lang: 'en-gb', name: 'Alice',    desc: 'Refined, poised' },
  bf_emma:     { g: 'f', hue: '#D4C5FF', lang: 'en-gb', name: 'Emma',     desc: 'Elegant, articulate' },
  bf_isabella: { g: 'f', hue: '#B4A5ED', lang: 'en-gb', name: 'Isabella', desc: 'Graceful, warm' },
  bf_lily:     { g: 'f', hue: '#E4D5FF', lang: 'en-gb', name: 'Lily',     desc: 'Soft, gentle' },
  // British Male — steel blue
  bm_daniel: { g: 'm', hue: '#7B90A9', lang: 'en-gb', name: 'Daniel', desc: 'Composed, clear' },
  bm_fable:  { g: 'm', hue: '#8BA0B9', lang: 'en-gb', name: 'Fable',  desc: 'Storytelling, warm' },
  bm_george: { g: 'm', hue: '#6B80A0', lang: 'en-gb', name: 'George', desc: 'Classic narrator' },
  bm_lewis:  { g: 'm', hue: '#9BB0C9', lang: 'en-gb', name: 'Lewis',  desc: 'Thoughtful, measured' },
  // Japanese — sakura pink / muted blue
  jf_alpha:      { g: 'f', hue: '#FFB7C5', lang: 'ja', name: 'Alpha',      desc: 'Clear, natural' },
  jf_gongitsune: { g: 'f', hue: '#FFC7D5', lang: 'ja', name: 'Gongitsune', desc: 'Gentle, expressive' },
  jf_nezumi:     { g: 'f', hue: '#FFD7E5', lang: 'ja', name: 'Nezumi',     desc: 'Soft, delicate' },
  jf_tebukuro:   { g: 'f', hue: '#FFA7B5', lang: 'ja', name: 'Tebukuro',   desc: 'Warm, friendly' },
  jm_kumo:       { g: 'm', hue: '#A0B4C8', lang: 'ja', name: 'Kumo',       desc: 'Calm, steady' },
  // Chinese — gold
  zf_xiaobei:  { g: 'f', hue: '#FFD700', lang: 'zh', name: 'Xiaobei',  desc: 'Bright, cheerful' },
  zf_xiaoni:   { g: 'f', hue: '#FFE740', lang: 'zh', name: 'Xiaoni',   desc: 'Warm, gentle' },
  zf_xiaoxuan: { g: 'f', hue: '#FFC800', lang: 'zh', name: 'Xiaoxuan', desc: 'Clear, professional' },
  zf_xiaoyi:   { g: 'f', hue: '#FFF060', lang: 'zh', name: 'Xiaoyi',   desc: 'Soft, soothing' },
  zm_yunjian:  { g: 'm', hue: '#E8B800', lang: 'zh', name: 'Yunjian',  desc: 'Strong, commanding' },
  zm_yunxi:    { g: 'm', hue: '#D8A800', lang: 'zh', name: 'Yunxi',    desc: 'Warm, rich' },
  zm_yunxia:   { g: 'm', hue: '#C89800', lang: 'zh', name: 'Yunxia',   desc: 'Smooth, mellow' },
  zm_yunyang:  { g: 'm', hue: '#F0C000', lang: 'zh', name: 'Yunyang',  desc: 'Energetic, bright' },
  // Spanish — warm orange
  ef_dora:  { g: 'f', hue: '#FFB074', lang: 'es', name: 'Dora',  desc: 'Warm, expressive' },
  em_alex:  { g: 'm', hue: '#FFA060', lang: 'es', name: 'Alex',  desc: 'Clear, confident' },
  em_santa: { g: 'm', hue: '#FF9050', lang: 'es', name: 'Santa', desc: 'Rich, resonant' },
  // French — soft mauve
  ff_siwis: { g: 'f', hue: '#D4A0D0', lang: 'fr', name: 'Siwis', desc: 'Elegant, smooth' },
  // Hindi — saffron
  hf_alpha: { g: 'f', hue: '#FFB347', lang: 'hi', name: 'Alpha', desc: 'Clear, natural' },
  hf_beta:  { g: 'f', hue: '#FFC370', lang: 'hi', name: 'Beta',  desc: 'Warm, gentle' },
  hm_omega: { g: 'm', hue: '#E0A030', lang: 'hi', name: 'Omega', desc: 'Deep, steady' },
  hm_psi:   { g: 'm', hue: '#D09020', lang: 'hi', name: 'Psi',   desc: 'Rich, expressive' },
  // Italian — warm green
  if_sara:   { g: 'f', hue: '#90D890', lang: 'it', name: 'Sara',   desc: 'Warm, melodic' },
  im_nicola: { g: 'm', hue: '#70C870', lang: 'it', name: 'Nicola', desc: 'Clear, engaging' },
  // Portuguese — ocean blue
  pf_dora:  { g: 'f', hue: '#70B0E0', lang: 'pt-br', name: 'Dora',  desc: 'Bright, friendly' },
  pm_alex:  { g: 'm', hue: '#60A0D0', lang: 'pt-br', name: 'Alex',  desc: 'Warm, clear' },
  pm_santa: { g: 'm', hue: '#5090C0', lang: 'pt-br', name: 'Santa', desc: 'Deep, resonant' },
}

export const TOP_PICKS = [
  { voice: 'af_heart',   badge: '#1 Narration',  bestFor: 'Audiobooks, narration, general purpose' },
  { voice: 'af_bella',   badge: 'Dynamic',       bestFor: 'Dynamic narration, marketing' },
  { voice: 'af_nicole',  badge: 'Professional',  bestFor: 'Non-fiction, tutorials, professional' },
  { voice: 'af_sarah',   badge: 'Versatile',     bestFor: 'General audiobooks, balanced delivery' },
  { voice: 'am_adam',    badge: 'Male Lead',     bestFor: 'Male narration, approachable tone' },
  { voice: 'am_michael', badge: 'Authoritative', bestFor: 'Deep narration, documentary' },
  { voice: 'bf_emma',    badge: 'British',       bestFor: 'British female, elegant narration' },
  { voice: 'bm_george',  badge: 'Classic',       bestFor: 'British male, classic narrator' },
]

export const BLEND_PRESETS = [
  { name: 'Narrator',    a: 'af_heart',  b: 'am_michael', ratio: 35, desc: 'Warm + authoritative' },
  { name: 'Podcast',     a: 'af_bella',  b: 'am_adam',    ratio: 50, desc: 'Energetic duo' },
  { name: 'Storyteller', a: 'bf_emma',   b: 'bm_fable',   ratio: 40, desc: 'British elegance' },
  { name: 'Newscast',    a: 'af_nicole', b: 'am_eric',    ratio: 30, desc: 'Clear + confident' },
  { name: 'Gentle',      a: 'af_kore',   b: 'af_river',   ratio: 50, desc: 'Soothing blend' },
  { name: 'Bold',        a: 'am_fenrir', b: 'am_onyx',    ratio: 50, desc: 'Dynamic power' },
  { name: 'Velvet',      a: 'af_bella',  b: 'am_adam',    ratio: 80, desc: 'Bella-forward warmth' },
]
