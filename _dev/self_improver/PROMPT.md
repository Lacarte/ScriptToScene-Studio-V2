# Self-Improving Pipeline Analyzer (Module-Aware)

Design a self-improving system analyzer for the Script-to-Scene Studio pipeline using the following modules:

## Pipeline Modules

### Audio Layer
- TTS
- ALIGNMENT
- SEGMENTER

### Visual Layer
- SCENES
- STORYBOARD
- ANIMATOR
- EDITOR

## Objective

Create a system that continuously:
- Ensures cross-module consistency
- Optimizes visual + narrative quality
- Improves timing synchronization (audio <-> visuals)
- Maximizes viral performance (hook, pacing, payoff)
- Learns and adapts per style preset

## Core Concept

The system must act as:
Observer > Evaluator > Optimizer > Self-Corrector > Memory Keeper

## System Architecture

Root directory:
```
D:\@Workspace\@Development\@Scripts\@Python\ScriptToScene-Studio\_dev\self_improver
```

## Module Responsibilities

### 1. prepare.py -- Pipeline Orchestrator & Test Harness

Runs full pipeline simulations:
TTS > ALIGNMENT > SEGMENTER > SCENES > STORYBOARD > ANIMATOR > EDITOR

Responsibilities:
- Generate controlled test cases per style preset
- Capture full intermediate outputs per module
- Produce structured logs:
```json
{
  "tts": {...},
  "alignment": {...},
  "segments": [...],
  "scenes": [...],
  "storyboard": [...],
  "animation": [...],
  "final_video": {...}
}
```
- Validate:
  - Audio duration vs scene timing
  - Segment boundaries vs narrative units
  - Scene count vs storyboard expectations

### 2. train.py -- Cross-Module Analyzer & Pattern Detector

Analyzes outputs across runs and modules:

#### Detect Issues Per Module

**TTS**
- unnatural pacing
- inconsistent tone vs style

**ALIGNMENT**
- word-timestamp drift
- mismatch with visual cuts

**SEGMENTER**
- bad segmentation (cutting sentences/emotions)
- uneven segment lengths

**SCENES**
- prompt inconsistency
- style drift

**STORYBOARD**
- weak structure (no hook/climax/CTA)
- poor visual progression

**ANIMATOR**
- motion inconsistency
- style break between clips

**EDITOR**
- bad transitions
- rhythm mismatch with audio

#### Cross-Module Checks
- Alignment <-> Segmenter: are cuts meaningful?
- Scenes <-> Storyboard: are prompts respecting narrative intent?
- Animator <-> Scenes: is visual continuity preserved?
- Editor <-> Audio: are beats respected?

#### Outputs
- Issue clusters
- Root cause attribution (which module caused it)
- Optimization suggestions

### 3. program.py -- Self-Correction Engine

Applies improvements safely:

#### Capabilities
Adjust:
- prompts
- segmentation rules
- timing offsets
- style constraints

Re-run pipeline with improved parameters. Compare before/after.

#### Includes
- Scoring system
- Versioning of improvements
- Rollback mechanism
- A/B testing engine

### 4. self-improvement-report.md -- Persistent Intelligence

Tracks:
```
[ISSUE]
Scene style drift in ANIMATOR

[ROOT CAUSE]
SCENES prompt lacked fixed palette constraint

[FIX]
Enforced palette lock in SCENES module

[RESULT]
+18% style consistency score
```

Also includes:
- Best configs per style preset
- Known failure patterns
- Optimization history

## Scoring System (Critical)

Define a unified scoring model:
```json
{
  "style_consistency": "0-100",
  "visual_quality": "0-100",
  "narrative_coherence": "0-100",
  "audio_visual_sync": "0-100",
  "viral_score": "0-100"
}
```

### Viral Score Breakdown
- Hook strength (first 3-5 seconds)
- Retention pacing
- Emotional progression
- Climax clarity
- CTA effectiveness

## Self-Improvement Loop

1. Run pipeline (prepare.py)
2. Analyze results (train.py)
3. Detect issues + root causes
4. Apply fixes (program.py)
5. Re-run pipeline
6. Compare scores
7. Store learnings (report.md)
8. Repeat

## Key Engineering Requirements

- Full traceability per module
- Deterministic baseline runs
- JSON schema for every module output
- Plug-in scoring evaluators (LLM + heuristic)
- Non-destructive improvement strategy
- Modular + extensible design

## Advanced Enhancements (High Value)

### Style Fingerprint System
- Each style = vector embedding
- Compare scene outputs vs expected style

### Prompt Mutation Engine
- Auto-test variations of prompts
- Keep best-performing ones

### Beat Detection Integration
- Align animation + cuts to audio energy peaks

### Scene Consistency Validator
- Compare color palette, lighting, composition across scenes

## Decisions Made During Implementation

- **Format**: TikTok/Reels < 60s
- **Evaluation**: Hybrid (heuristics for measurable, Gemini 2.5 Flash for subjective)
- **Autonomy**: Full autopilot (runs loops, applies fixes, stores learnings)
- **Scope v1**: Full loop (score + fix + re-run), TTS through Storyboard only
- **LLM**: Gemini 2.5 Flash via OpenRouter
- **Animator**: Skipped in v1 test runs (resume manually after first 5 steps pass)
- **Storage**: Rolling markdown report
- **Stopping**: 5 iterations max, auto-stop on plateau or no fixable issues
