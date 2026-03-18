# Why V2 Is Better Than the Previous Plan

This note summarizes why [prompts-templates-integration-plan-v2.md](./prompts-templates-integration-plan-v2.md) is stronger than the original [prompts-templates-integration-plan.md](./prompts-templates-integration-plan.md).

## Main Improvement

The biggest upgrade in V2 is that it treats scene coherence as a system problem, not only a prompt-format problem.

The original plan mainly improves how `prompts.py` and `templates.py` fit together. That is useful, but V2 goes further and addresses the full generation flow:

- template design
- prompt structure
- project-level continuity
- chapter/chunk continuity
- deterministic planning before generation
- validation after generation

## What V2 Does Better

### 1. Adds a visual bible

V2 introduces a project-level `visual_bible` between the reusable style template and the final scene prompts.

This is important because the system needs a story-specific continuity layer that defines:

- world anchor
- anchor subject
- recurring motifs
- palette guardrails
- lighting baseline
- camera grammar

This is the strongest improvement in the V2 plan.

### 2. Moves more structure out of the LLM

The current prompt asks the LLM to decide too many things at once:

- analysis
- role assignment
- scene type mix
- shot progression
- continuity

V2 proposes `scene_blueprints` so the app can pre-plan more of the structure and let the model focus on creative execution.

This should make outputs less random and more stable.

### 3. Fixes long-script drift

The original plan correctly notices missing continuity, but it does not fully solve long-script generation.

V2 adds continuity state across chapter/chunk generation, including:

- recent shot types
- type counts so far
- anchor coverage
- active environment thread
- recent motif usage

That is important because long scripts are where coherence breaks most often.

### 4. Adds validation and repair

The current implementation validates indexes well, but it does not validate visual coherence.

V2 proposes a post-generation validation layer that can check:

- shot repetition
- text-scene policy
- anchor coverage
- palette drift
- environment drift
- role progression

It also proposes repair/retry logic instead of treating the first response as final.

### 5. Fits the actual app architecture better

V2 is more grounded in the current codebase because it accounts for:

- direct scene generation
- pipeline mode
- chapter mode
- saved `analysis` in `scenes.json`
- backward compatibility with `style_prompt`

The original plan is conceptually good, but V2 is more operationally complete.

### 6. Handles rollout risks better

V2 explicitly calls out migration concerns, including:

- preserving current request fields
- keeping `style_prompt` as a compatibility path during migration
- avoiding accidental exposure of internal `style_spec` through `/api/scenes/templates`

That makes it safer to implement incrementally.

## Best Idea To Keep If Scope Is Limited

If only one new idea from V2 is adopted, it should be:

project-level `visual_bible` plus chunk continuity state

That is the shortest path to visibly stronger scene coherence, especially for longer scripts.

## Practical Takeaway

The original plan is still a good Phase 1 refactor.

V2 is better if the real goal is production-quality scene coherence, because it upgrades the system from:

- prose templates + one large prompt

to:

- structured templates
- a visual bible
- deterministic scene blueprints
- continuity across chapters
- validation after generation
