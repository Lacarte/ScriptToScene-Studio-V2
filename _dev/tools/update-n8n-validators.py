"""One-shot script to update input_validator and output_validator
JS Code nodes in the n8n Scene-generator workflow."""

import json, requests, sys

API_URL = "https://n8n-production-6197.up.railway.app"
API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2M2MyYTA3Ny02NDY2LTQxYTktYWViYi05OWRmYWM0ZGQ5YmIiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiYjgzY2NjZTgtOGZhYi00OWFmLThkMDctNTNjNTUyYzhiZjhmIiwiaWF0IjoxNzcyMzI4NDgwfQ.NubhLzSy-rojNBPMwVh4Gv-NZ_8acHaLTbGJYhe3oxA"
WORKFLOW_ID = "1ga5ercqD130rcAH"

HEADERS = {
    "X-N8N-API-KEY": API_KEY,
    "Content-Type": "application/json",
}

# ── New input_validator JS code ──────────────────────────────────
INPUT_VALIDATOR_JS = r"""
// ── Input Validator ─────────────────────────────────────────────
// Normalizes and validates the incoming webhook payload.
// Accepts segments as [{index, words, ...}] OR ["text1", "text2"].
// Strips everything except {index, words} before forwarding to LLM.

const body = $input.first().json.body || $input.first().json;

const script = (body.script || '').trim();
const style  = (body.style  || 'cinematic').trim();
const system_prompt = body.system_prompt || '';
const rawSegments   = body.segments || [];

// ── Validate required fields ────────────────────────────────────
const errors = [];
if (!script)            errors.push('Missing or empty "script"');
if (!rawSegments.length) errors.push('Missing or empty "segments"');

if (errors.length) {
  return [{
    json: {
      valid: false,
      error: errors.join('; '),
      payload: null,
      system_prompt: null
    }
  }];
}

// ── Normalize segments ──────────────────────────────────────────
// Accept both string arrays and object arrays; output {index, words} only.
const segments = rawSegments.map((seg, i) => {
  if (typeof seg === 'string') {
    return { index: i, words: seg };
  }
  return {
    index: seg.index ?? i,
    words: seg.words || String(seg)
  };
});

// ── Build clean payload for LLM ─────────────────────────────────
return [{
  json: {
    valid: true,
    error: null,
    payload: { script, style, segments },
    system_prompt
  }
}];
"""

# ── New output_validator JS code ─────────────────────────────────
OUTPUT_VALIDATOR_JS = r"""
// ── Output Validator ────────────────────────────────────────────
// Parses LLM JSON, validates structure, strips timing fields,
// normalises field names, and sorts scenes by index.

const VALID_ROLES = new Set([
  'hook', 'buildup', 'peak', 'transition', 'text_accent', 'cta'
]);
const VALID_TYPES = new Set(['image', 'video', 'text']);

// ── 1. Extract raw text from LLM ───────────────────────────────
let raw = $input.first().json;

// The LLM Chain node may nest output in .text or .output
let text = typeof raw === 'string' ? raw
         : raw.text   || raw.output || raw.response || '';

if (typeof text !== 'string') {
  text = JSON.stringify(text);
}

// ── 2. Clean & parse ────────────────────────────────────────────
// Strip markdown fences
text = text.replace(/```json\s*/gi, '').replace(/```/g, '').trim();

// Always sanitize control characters BEFORE parsing.
// LLMs emit raw newlines/tabs inside JSON string values which break JSON.parse.
text = text.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g, '');  // strip non-whitespace ctrl chars
text = text.replace(/(?<=":[ ]*"[^"]*)\n(?=[^"]*")/g, ' ');  // newlines inside strings -> space

let parsed;
try {
  parsed = JSON.parse(text);
} catch (e) {
  // Aggressive fallback: replace ALL newlines/tabs with spaces, then parse
  const flat = text.replace(/[\n\r\t]/g, ' ');
  try {
    parsed = JSON.parse(flat);
  } catch (e2) {
    // Last resort: extract the outermost JSON object
    const match = flat.match(/\{[\s\S]*\}/);
    if (match) {
      try { parsed = JSON.parse(match[0]); }
      catch (e3) { throw new Error('Failed to parse LLM JSON: ' + e3.message); }
    } else {
      throw new Error('No JSON object found in LLM response');
    }
  }
}

// ── 3. Validate analysis ────────────────────────────────────────
const analysis = parsed.analysis || {};

// ── 4. Validate scenes array ────────────────────────────────────
const scenes = parsed.scenes || [];
if (!scenes.length) {
  throw new Error('LLM returned no scenes');
}

// ── 5. Normalise, validate, and clean each scene ────────────────
const cleaned = scenes.map((s, i) => {
  const role = VALID_ROLES.has(s.narrative_role) ? s.narrative_role : 'buildup';
  const type = VALID_TYPES.has(s.type_of_scene)  ? s.type_of_scene  : 'video';

  // Auto-fix: text type needs text_content
  const textContent = (type === 'text' && !s.text_content) ? null : (s.text_content || null);

  return {
    index:          s.index ?? i,
    title:          s.title || '',
    narrative_role: role,
    type_of_scene:  type,
    image_prompt:   s.image_prompt || s.prompt || '',
    text_content:   textContent,
  };
});

// ── 6. Sort by index ────────────────────────────────────────────
cleaned.sort((a, b) => a.index - b.index);

// ── 7. Return clean response ────────────────────────────────────
return [{
  json: {
    analysis,
    scenes: cleaned
  }
}];
"""

def main():
    # 1. GET current workflow
    url = f"{API_URL}/api/v1/workflows/{WORKFLOW_ID}"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code != 200:
        print(f"GET failed: {resp.status_code} — {resp.text[:300]}")
        sys.exit(1)

    wf = resp.json()
    print(f"Fetched workflow: {wf.get('name', '?')} ({len(wf.get('nodes', []))} nodes)")

    # 2. Find and update the two validator nodes
    updated = {"input_validator": False, "output_validator": False}
    for node in wf["nodes"]:
        if node.get("name") == "input_validator":
            node["parameters"]["jsCode"] = INPUT_VALIDATOR_JS.strip()
            updated["input_validator"] = True
            print("  [OK] Updated input_validator code")

        elif node.get("name") == "output_validator":
            node["parameters"]["jsCode"] = OUTPUT_VALIDATOR_JS.strip()
            updated["output_validator"] = True
            print("  [OK] Updated output_validator code")

    if not all(updated.values()):
        missing = [k for k, v in updated.items() if not v]
        print(f"WARNING: Could not find node(s): {missing}")
        sys.exit(1)

    # 3. Strip fields the n8n API rejects on PUT
    # Also clean each node — remove runtime-only keys
    NODE_ALLOWED = {"id", "name", "type", "typeVersion", "position", "parameters",
                    "credentials", "disabled", "notesInFlow", "notes", "webhookId",
                    "extendsCredential", "onError", "continueOnFail", "retryOnFail",
                    "maxTries", "waitBetweenTries", "alwaysOutputData"}
    clean_nodes = []
    for node in wf["nodes"]:
        clean = {k: v for k, v in node.items() if k in NODE_ALLOWED}
        clean_nodes.append(clean)

    # Clean settings too
    raw_settings = wf.get("settings", {})
    SETTINGS_ALLOWED = {"executionOrder", "saveManualExecutions", "callerPolicy",
                        "errorWorkflow", "timezone", "saveExecutionProgress"}
    clean_settings = {k: v for k, v in raw_settings.items() if k in SETTINGS_ALLOWED}

    payload = {
        "name": wf["name"],
        "nodes": clean_nodes,
        "connections": wf["connections"],
        "settings": clean_settings,
    }

    # 4. PUT updated workflow
    put_resp = requests.put(url, headers=HEADERS, json=payload)
    if put_resp.status_code == 200:
        print(f"Workflow updated successfully (status {put_resp.status_code})")
    else:
        print(f"PUT failed: {put_resp.status_code} — {put_resp.text[:500]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
