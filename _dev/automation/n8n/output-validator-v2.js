// n8n Code Node: Validate LLM Scene Output v2.0
// Place after the LLM Chain node

const raw = $input.first().json.text;
const errors = [];
const warnings = [];

// ──────────────────────────────────────
// 1. PARSE JSON
// ──────────────────────────────────────
let data;
try {
  data = JSON.parse(raw);
} catch (e) {
  const match = raw.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (match) {
    try {
      data = JSON.parse(match[1].trim());
    } catch (e2) {
      return { json: { valid: false, errors: ['Failed to parse JSON: ' + e2.message], warnings: [] } };
    }
  } else {
    return { json: { valid: false, errors: ['Failed to parse JSON: ' + e.message], warnings: [] } };
  }
}

// ──────────────────────────────────────
// 2. VALIDATE ANALYSIS
// ──────────────────────────────────────
if (!data.analysis || typeof data.analysis !== 'object') {
  errors.push('Missing "analysis" object');
} else {
  const requiredAnalysis = ['mood', 'environment', 'color_palette', 'tone', 'visual_style', 'recurring_motif', 'character'];
  requiredAnalysis.forEach(key => {
    if (!data.analysis[key] || typeof data.analysis[key] !== 'string') {
      warnings.push(`analysis.${key} missing or empty`);
    }
  });
}

// ──────────────────────────────────────
// 3. VALIDATE SCENES ARRAY
// ──────────────────────────────────────
if (!data.scenes || !Array.isArray(data.scenes)) {
  return { json: { valid: false, errors: ['Missing "scenes" array'], warnings } };
}

if (data.scenes.length === 0) {
  return { json: { valid: false, errors: ['Scenes array is empty'], warnings } };
}

// ──────────────────────────────────────
// 4. VALIDATE EACH SCENE
// ──────────────────────────────────────
const VALID_ROLES = ['hook', 'buildup', 'peak', 'transition', 'cta'];
const VALID_TYPES = ['image', 'video'];
const NON_ASCII = /[^\x00-\x7F]/;

const seenIndexes = new Set();

data.scenes.forEach((scene, i) => {
  const label = `Scene ${i} (index ${scene.index})`;

  // index
  if (scene.index === undefined || typeof scene.index !== 'number') {
    errors.push(`${label}: missing or invalid index`);
  }
  if (seenIndexes.has(scene.index)) {
    errors.push(`${label}: duplicate index ${scene.index}`);
  }
  seenIndexes.add(scene.index);

  // title
  if (!scene.title || typeof scene.title !== 'string') {
    errors.push(`${label}: missing title`);
  } else if (scene.title.split(/\s+/).length > 8) {
    warnings.push(`${label}: title "${scene.title}" is long`);
  }

  // narrative_role
  if (!VALID_ROLES.includes(scene.narrative_role)) {
    errors.push(`${label}: invalid narrative_role "${scene.narrative_role}"`);
  }

  // type_of_scene — auto-fix legacy "text" type to "video"
  if (scene.type_of_scene === 'text') {
    scene.type_of_scene = 'video';
    warnings.push(`${label}: auto-fixed type "text" → "video"`);
  }
  if (!VALID_TYPES.includes(scene.type_of_scene)) {
    errors.push(`${label}: invalid type_of_scene "${scene.type_of_scene}"`);
  }

  // image_prompt
  if (!scene.image_prompt || typeof scene.image_prompt !== 'string') {
    errors.push(`${label}: missing image_prompt`);
  } else {
    // Check for non-ASCII
    if (NON_ASCII.test(scene.image_prompt)) {
      warnings.push(`${label}: image_prompt contains non-ASCII — auto-cleaned`);
      scene.image_prompt = scene.image_prompt.replace(/[^\x00-\x7F]/g, '');
    }

    // Check prompt length
    if (scene.image_prompt.length < 30) {
      warnings.push(`${label}: image_prompt very short (${scene.image_prompt.length} chars)`);
    }

    // Video scenes should have motion cues
    if (scene.type_of_scene === 'video') {
      const motionWords = /\b(slowly|gently|drift\w*|float\w*|flicker\w*|swirl\w*|trembl\w*|roll\w*|curl\w*|slid\w*|ris\w*|fall\w*|blow\w*|shift\w*|creep\w*|twitch\w*|puls\w*|breath\w*|sway\w*|drip\w*|turn\w*|reach\w*|lift\w*|clos\w*|open\w*|lean\w*|push\w*|pull\w*|walk\w*|runn\w*|glow\w*|fad\w*|spin\w*|wobbl\w*|rustl\w*|buzz\w*|filter\w*|stream\w*|crawl\w*|land\w*|rippl\w*|quiver\w*|danc\w*|whip\w*|streak\w*|orbit\w*|ascend\w*|descend\w*|emerg\w*|scatter\w*|settl\w*|melt\w*|bloom\w*|wilt\w*|crack\w*|spread\w*|pour\w*|seep\w*|billow\w*|flutter\w*|tilt\w*|zoom\w*|pan\w*|track\w*)\b/i;
      if (!motionWords.test(scene.image_prompt)) {
        warnings.push(`${label}: video scene may lack motion cues in prompt`);
      }
    }
  }

  // Clean up legacy keys
  delete scene.text_content;
  delete scene.motion_in_image;
  delete scene.fx;
  delete scene.segment_index;
});

// ──────────────────────────────────────
// 5. STRUCTURE CHECKS
// ──────────────────────────────────────

// First scene should be hook
if (data.scenes[0] && data.scenes[0].narrative_role !== 'hook') {
  warnings.push(`First scene role is "${data.scenes[0].narrative_role}" — expected "hook"`);
}

// Last scene should be cta
const lastScene = data.scenes[data.scenes.length - 1];
if (lastScene && lastScene.narrative_role !== 'cta') {
  warnings.push(`Last scene role is "${lastScene.narrative_role}" — expected "cta"`);
}

// Type mix check
const typeCounts = { video: 0, image: 0 };
data.scenes.forEach(s => { if (typeCounts[s.type_of_scene] !== undefined) typeCounts[s.type_of_scene]++; });
const total = data.scenes.length;

const videoPct = Math.round(typeCounts.video / total * 100);
const imagePct = Math.round(typeCounts.image / total * 100);

if (videoPct < 55) {
  warnings.push(`Video at ${videoPct}% — target >=60%`);
}

const maxImages = Math.floor(total * 0.2) || 1;
if (typeCounts.image > maxImages) {
  warnings.push(`${typeCounts.image} image scenes — max recommended ${maxImages} for ${total} scenes`);
}

// Narrative role distribution
const roleCounts = {};
data.scenes.forEach(s => { roleCounts[s.narrative_role] = (roleCounts[s.narrative_role] || 0) + 1; });

const maxBuildup = Math.floor(total * 0.4);
if ((roleCounts.buildup || 0) > maxBuildup) {
  warnings.push(`${roleCounts.buildup} buildup scenes — max recommended ${maxBuildup} for ${total} scenes`);
}

if (!roleCounts.peak) {
  warnings.push('No peak scene — at least 1 recommended');
}

if (total >= 6 && !roleCounts.transition) {
  warnings.push('No transition scene — at least 1 recommended for 6+ scenes');
}

// Consecutive same shot type check (no two image scenes back-to-back)
for (let i = 1; i < data.scenes.length; i++) {
  if (data.scenes[i].type_of_scene === 'image' && data.scenes[i - 1].type_of_scene === 'image') {
    warnings.push(`Scenes ${i - 1} and ${i} are both image — avoid back-to-back images`);
  }
}

// ──────────────────────────────────────
// 6. VALIDATE / FIX DURATION
// ──────────────────────────────────────
const DURATION_RANGES = {
  hook:       { min: 2.5, max: 3.5, fallback: 3.0 },
  buildup:    { min: 2.0, max: 3.5, fallback: 2.5 },
  peak:       { min: 3.0, max: 4.0, fallback: 3.5 },
  transition: { min: 2.0, max: 3.0, fallback: 2.5 },
  cta:        { min: 2.5, max: 3.5, fallback: 3.0 },
};
const IMAGE_DURATION = { min: 1.8, max: 3.0, fallback: 2.5 };

data.scenes.forEach(scene => {
  const isImage = scene.type_of_scene === 'image';
  const range = isImage ? IMAGE_DURATION : (DURATION_RANGES[scene.narrative_role] || { min: 3.0, max: 5.0, fallback: 3.5 });

  if (typeof scene.duration === 'number' && scene.duration >= range.min && scene.duration <= range.max) {
    // LLM duration is valid — keep it, just round to 1 decimal
    scene.duration = +scene.duration.toFixed(1);
  } else {
    // Missing or out of range — use role-appropriate fallback
    scene.duration = range.fallback;
  }
});

// ──────────────────────────────────────
// 7. OUTPUT
// ──────────────────────────────────────
const valid = errors.length === 0;

return {
  json: {
    valid,
    errors,
    warnings,
    type_mix: {
      video: `${typeCounts.video} (${videoPct}%)`,
      image: `${typeCounts.image} (${imagePct}%)`
    },
    analysis: data.analysis || {},
    scenes: data.scenes,
    scene_count: data.scenes.length
  }
};
