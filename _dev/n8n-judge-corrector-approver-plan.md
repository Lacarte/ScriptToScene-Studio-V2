# n8n Judge + Corrector + Approver Plan

This note captures the proposed `judge -> corrector -> approver` loop for scene generation quality control in n8n.

It is intended to extend, not replace, the planning work in:

- [prompts-templates-integration-plan-v2.md](./prompts-templates-integration-plan-v2.md)
- [prompts-templates-integration-plan-v2-comparison.md](./prompts-templates-integration-plan-v2-comparison.md)

## Recommendation

Use a hybrid system:

1. backend planner builds deterministic structure
2. writer LLM generates scenes
3. judge LLM scores the result
4. corrector LLM rewrites only failed scenes
5. approver gate decides accept, retry, or stop

This is stronger than a single writer pass, but safer than relying on LLMs alone.

## Why This Is Better

A writer-only flow is good at creativity, but weak at consistency. The system needs a second pass that asks:

- does this still follow the story?
- did the character drift?
- does the visual style still match the intended edit language?
- are the scenes escalating or just repeating?

The key is to keep hard rules in code and let LLM judges handle fuzzy quality checks.

## Recommended Architecture

```text
script + style + timings
        |
        v
backend planner
  - story spine
  - character bible
  - visual/style bible
  - scene blueprints
  - continuity state
        |
        v
n8n writer LLM
        |
        v
n8n judge LLM
  - scores
  - findings
  - pass/fail
        |
        +--> pass --> approver --> final output
        |
        +--> fail --> corrector LLM --> approver
                               |
                               +--> pass --> final output
                               |
                               +--> fail --> optional one more repair or reject
```

## What Must Stay In Code

These should remain deterministic and enforced by the backend:

- scene count and indexes
- timing alignment
- first-scene and last-scene structural rules
- allowed scene types
- repetition detection for shot patterns
- named-character ontology locks
- forbidden mutations and forbidden motifs
- chapter continuity state
- output schema validation

The judge should not invent or redefine these rules.

## What The Judge Should Evaluate

The judge is useful for scoring questions that are important but not fully deterministic:

- story alignment
- character consistency
- visual coherence
- style/editing consistency
- pacing escalation
- hook strength
- payoff quality
- overall viral impact potential

## Node Responsibilities

### 1. Writer

The writer should generate scenes using:

- story spine
- character bible
- style bible
- edit bible
- scene blueprint

The writer should not be asked to decide everything from scratch.

### 2. Judge

The judge should return structured output, not prose only.

Suggested fields:

```json
{
  "pass": false,
  "scores": {
    "story_alignment": 0.72,
    "character_consistency": 0.41,
    "visual_coherence": 0.68,
    "style_consistency": 0.74,
    "pacing_progression": 0.59,
    "hook_strength": 0.83,
    "payoff_strength": 0.61
  },
  "hard_failures": [
    "Named character Nimbus drifted from cloud ontology into creature-like design."
  ],
  "warnings": [
    "Scene 8 repeats the same emotional beat as scene 7.",
    "Final payoff is weaker than mid-video reveal."
  ],
  "scene_fixes": [
    {
      "scene_index": 8,
      "reason": "Character drift",
      "instruction": "Preserve Nimbus as a rounded cumulus cloud. Remove animal or dragon traits."
    },
    {
      "scene_index": 10,
      "reason": "Weak payoff",
      "instruction": "Increase emotional release and make the village transformation more visually decisive."
    }
  ]
}
```

### 3. Corrector

The corrector should only rewrite failed scenes, not the entire sequence, unless the judge marks structural collapse.

The corrector input should include:

- original scene
- failing rule
- required correction
- neighboring scenes for continuity
- character bible and style/edit bible

This keeps repairs focused and reduces collateral drift.

### 4. Approver

The approver is the final gate. It should be stricter than the judge on hard failures and simpler on soft preferences.

The approver should answer:

- did all hard constraints pass?
- did the corrected scenes actually fix the reported issue?
- did the correction create new inconsistencies?
- is the final output good enough to ship?

## Suggested Scoring Rules

Suggested thresholds:

- `character_consistency >= 0.90`
- `story_alignment >= 0.85`
- `visual_coherence >= 0.80`
- `style_consistency >= 0.80`
- `pacing_progression >= 0.75`

Hard fail if any of these happen:

- recurring character changes ontology
- scene contradicts story beat
- tone collapses into the wrong genre
- final scene fails to resolve the promised arc
- prompt introduces forbidden elements not present in the story

## Special Rule For Abstract Or Non-Human Characters

This matters for cases like:

- cloud
- star
- shadow
- flame
- moon
- wind

These are high-drift subjects for image models.

For those characters, the backend should provide a strict `character_bible` and the judge should validate against it directly.

Example:

```json
{
  "name": "Nimbus",
  "ontology": "small rounded cumulus cloud",
  "allowed_traits": [
    "soft vapor edges",
    "expressive eyes",
    "gentle glow",
    "rain-bearing fullness"
  ],
  "forbidden_traits": [
    "dragon",
    "animal",
    "humanoid",
    "horns",
    "wings",
    "scales",
    "tail",
    "ears",
    "paws",
    "limbs"
  ]
}
```

If the judge sees a scene drifting toward creature morphology, it should trigger a hard fail.

## Viral / Retention Methodology

If the product goal includes stronger retention and more shareable visuals, the judge should also score:

- opening hook clarity
- curiosity gap in early scenes
- contrast escalation in the middle
- peak-image memorability
- emotional payoff at the end
- callback or loop potential

This should remain secondary to story fidelity. Viral strength should improve the story, not distort it.

## Practical n8n Flow

Suggested workflow shape:

1. `Prepare Context` node
2. `Writer LLM` node
3. `Schema Validator` node
4. `Judge LLM` node
5. `Judge Decision` node
6. `Corrector LLM` node if needed
7. `Approver LLM` node
8. `Final Validator` node
9. `Persist Output` node

Recommended guardrails:

- allow at most 1 full correction pass by default
- allow at most 2 scene-level repairs for minor issues
- stop on repeated hard failures
- persist judge findings for debugging

## Best Overall Pattern

Best pattern:

`planner/code -> writer -> judge -> selective corrector -> approver`

Avoid this pattern:

`writer -> writer -> writer until it looks okay`

The second pattern increases latency, cost, and drift, and makes debugging much harder.

## Implementation Order

If implemented incrementally, the best order is:

1. add deterministic `character_bible` and stronger planner rules
2. add judge rubric with structured scores
3. add scene-level corrector for failed scenes only
4. add approver gate
5. add metrics logging and failure analytics

## Bottom Line

Yes, adding `judge + corrector + approver` nodes in n8n would be better than a writer-only flow.

But it is best when used as a hybrid quality-control layer on top of strong backend planning, not as the primary source of truth.
