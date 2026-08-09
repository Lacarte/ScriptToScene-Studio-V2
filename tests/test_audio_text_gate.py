"""Step 15.3 — Audio/text-output integration gate.

Proves the Phase 15 TTS migration is complete without spending live credits:

  * Narration Only and Full Video templates complete through the generic TTS
    path (fixture/mock providers; cloud calls stay mocked);
  * TTS port payloads never carry absolute filesystem paths (§36 L7);
  * `timing.align` resolves audio through `resolve_ref` / `artifact_refs`;
  * provider version and options change cache fingerprints;
  * provider errors stay isolated to their node/run;
  * untouched Music and Captions nodes still execute and are accepted by
    assemble/export;
  * no route/adapter *branch* compares a concrete TTS provider id;
  * a playable fixture export (local FFmpeg) proves end-to-end media
    compatibility;
  * `ADAPTER_CACHE_SCHEMA_VERSION` is 2 (L7 output-shape invalidation).

Music and Captions are the regression risk of this phase, not its subject —
their adapter blobs are pinned to the step-3.2 commit so a silent edit fails
the gate.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from config import OUTPUT_DIR, ROOT_DIR
from studio.shared.providers_common.hub import hub
from studio.shared.providers_common.results import resolve_ref
from studio.workflows.adapters import captions as captions_adapter
from studio.workflows.adapters import music as music_adapter
from studio.workflows.adapters import timing as timing_adapter
from studio.workflows.adapters import tts as tts_adapter
from studio.workflows.adapters.common import AdapterContext, AdapterError
from studio.workflows.cache import (
    ADAPTER_CACHE_SCHEMA_VERSION,
    canonical_fingerprint,
    fingerprint_components,
)
from studio.workflows.registry import get_node_type
from studio.workflows.scheduler import WorkflowScheduler
from studio.workflows.templates import (
    full_video_template,
    narration_only_template,
    serialize_templates,
)


PROJECT_ID = "pm_GATE15"
FIXTURES = Path(ROOT_DIR) / "studio" / "workflows" / "fixtures"
SCRIPT = "A short script for the audio gate."

# git hash-object of the music/captions adapters at step 3.2 (last intentional
# edit). Any content change fails this pin so Phase 15 cannot silently rewrite
# the local-only services the plan left out of the provider platform.
MUSIC_ADAPTER_BLOB = "3dcc9282d01483744482a1c274595312bb011c00"
CAPTIONS_ADAPTER_BLOB = "a0049ddcbc0d04b9b11ce8946c42618697644c23"

# Surfaces that must not branch on a concrete TTS provider id for dispatch.
_SCAN_PATHS = (
    Path(ROOT_DIR) / "studio" / "workflows" / "adapters",
    Path(ROOT_DIR) / "studio" / "tts" / "dispatch.py",
    Path(ROOT_DIR) / "studio" / "tts" / "routes.py",
    Path(ROOT_DIR) / "studio" / "pipeline" / "services.py",
    Path(ROOT_DIR) / "studio" / "pipeline" / "routes.py",
)
_BRANCH_RE = re.compile(
    r"""(?:provider(?:_id)?|tts_provider|engine)\s*==\s*['\"](?:kokoro|inworld)['\"]"""
    r"""|['\"](?:kokoro|inworld)['\"]\s*==\s*(?:provider(?:_id)?|tts_provider|engine)""",
)


# -- helpers ----------------------------------------------------------------


def _git_blob_hash(path: Path) -> str:
    raw = path.read_bytes()
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def _rmtree(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


def _managed_temp(prefix: str) -> str:
    root = os.path.join(OUTPUT_DIR, "_gate15")
    os.makedirs(root, exist_ok=True)
    return tempfile.mkdtemp(prefix=prefix, dir=root)


def _absolute_path_in(value) -> list[str]:
    """Collect string values that look like absolute or UNC filesystem paths."""
    found: list[str] = []
    pattern = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|//[^/]|/(?!/))")
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "artifact_refs":
                # refs are relative by contract; still walk them for safety
                found.extend(_absolute_path_in(child))
            else:
                found.extend(_absolute_path_in(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_absolute_path_in(child))
    elif isinstance(value, str) and pattern.match(value):
        found.append(value)
    return found


def _write_minimal_wav(path: str, *, duration_s: float = 0.5, rate: int = 8000) -> str:
    """Deterministic tiny WAV so FFmpeg and alignment consumers see real media."""
    import struct
    import wave

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    n_frames = max(1, int(rate * duration_s))
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        # Quiet sine-ish tone so loudnorm / ffprobe treat it as audio.
        frames = bytearray()
        for i in range(n_frames):
            sample = int(8000 * (1 if (i // 40) % 2 == 0 else -1))
            frames += struct.pack("<h", sample)
        handle.writeframes(frames)
    return path


# -- L7 + adapter unit surface ----------------------------------------------


class AbsolutePathRetirementTests(unittest.TestCase):
    """tts.generate emits relative refs; timing.align reads them via resolve_ref."""

    def setUp(self):
        self.tmp = _managed_temp("sts_gate15_l7_")
        self.addCleanup(_rmtree, self.tmp)
        self.tts_dir = os.path.join(self.tmp, "tts", PROJECT_ID)
        os.makedirs(self.tts_dir, exist_ok=True)
        self.wav = _write_minimal_wav(os.path.join(self.tts_dir, "voice.wav"))
        with open(os.path.join(self.tts_dir, "tts.json"), "w", encoding="utf-8") as handle:
            json.dump({"provider": "fixture"}, handle)

    def test_adapter_cache_schema_bumped_for_l7_output_change(self):
        self.assertEqual(ADAPTER_CACHE_SCHEMA_VERSION, 2)

    def test_tts_ports_carry_relative_refs_only(self):
        import studio.workflows.adapters.common as adapter_common

        service_result = {
            "wav_path": self.wav,
            "filename": "voice.wav",
            "folder": PROJECT_ID,
            "duration_seconds": 0.5,
            "sample_rate": 8000,
            "voice": "fx_calm",
            "provider": "fixture_artifact",
            "words": 4,
        }
        with mock.patch.object(adapter_common, "OUTPUT_DIR", self.tmp), \
                mock.patch.object(tts_adapter, "_step_tts", return_value=service_result):
            outputs = tts_adapter.generate(
                {"script": SCRIPT},
                {"provider_id": "fixture_artifact", "voice": "fx_calm"},
                AdapterContext(project_id=PROJECT_ID),
            )
        for port in ("audio", "metadata"):
            payload = outputs[port]
            self.assertFalse(_absolute_path_in(payload), payload)
            self.assertIn("artifact_refs", payload)
            self.assertTrue(payload["artifact_refs"][0].endswith("voice.wav"))
            self.assertEqual(payload["wav_path"], payload["artifact_refs"][0])
            self.assertNotIn("path", payload)
            # resolve_ref must recover the real file
            resolved = resolve_ref(payload["wav_path"], output_dir=self.tmp)
            self.assertTrue(os.path.isfile(resolved), resolved)

    def test_timing_prefers_artifact_refs_over_relative_wav_path(self):
        seen = {}

        def capture(metadata, config, pid):
            seen.update(metadata)
            return {
                "folder": pid,
                "alignment": [
                    {"word": "A", "begin": 0.0, "end": 0.1},
                    {"word": "short", "begin": 0.1, "end": 0.3},
                ],
                "word_count": 2,
                "transcript": SCRIPT,
            }

        audio = {
            "artifact_refs": [
                f"tts/{PROJECT_ID}/voice.wav",
                f"tts/{PROJECT_ID}/tts.json",
            ],
            "wav_path": f"tts/{PROJECT_ID}/voice.wav",
            "filename": "voice.wav",
            "folder": PROJECT_ID,
        }
        align_dir = os.path.join(self.tmp, "alignments")
        with mock.patch.object(timing_adapter, "_step_timing", side_effect=capture), \
                mock.patch.object(timing_adapter, "ALIGN_DIR", align_dir), \
                mock.patch(
                    "studio.shared.providers_common.results.OUTPUT_DIR", self.tmp
                ), mock.patch(
                    "config.OUTPUT_DIR", self.tmp
                ):
            # resolve_ref reads OUTPUT_DIR from results module at call time
            from studio.shared.providers_common import results as results_mod
            with mock.patch.object(results_mod, "OUTPUT_DIR", self.tmp):
                outputs = timing_adapter.align(
                    {"audio": audio, "script": SCRIPT},
                    {},
                    AdapterContext(project_id=PROJECT_ID),
                )
        self.assertEqual(
            os.path.normpath(seen["wav_path"]),
            os.path.normpath(self.wav),
        )
        self.assertIn("alignment", outputs)
        self.assertFalse(_absolute_path_in(outputs["alignment"].get("artifact_refs", [])))

    def test_timing_rejects_absolute_path_keys_without_a_relative_ref(self):
        with self.assertRaises(AdapterError) as caught:
            timing_adapter.align(
                {
                    "audio": {"wav_path": self.wav, "path": self.wav},
                    "script": SCRIPT,
                },
                {},
                AdapterContext(project_id=PROJECT_ID),
            )
        self.assertEqual(caught.exception.code, "ARTIFACT_MISSING")


# -- No concrete TTS provider-id branches -----------------------------------


class NoConcreteProviderBranchTests(unittest.TestCase):
    def test_adapters_and_dispatch_routes_do_not_branch_on_tts_provider_ids(self):
        offenders: list[str] = []
        files: list[Path] = []
        for entry in _SCAN_PATHS:
            if entry.is_file():
                files.append(entry)
            else:
                files.extend(sorted(entry.rglob("*.py")))
        for path in files:
            if "__pycache__" in path.parts or path.name == "generated":
                continue
            text = path.read_text(encoding="utf-8")
            # Skip pure comments / docstrings that mention the historical branch.
            # Parse the AST and only flag comparison nodes.
            try:
                tree = ast.parse(text, filename=str(path))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare):
                    continue
                segment = ast.get_source_segment(text, node) or ""
                if _BRANCH_RE.search(segment):
                    rel = path.relative_to(ROOT_DIR)
                    offenders.append(f"{rel}:{node.lineno}: {segment.strip()}")
        self.assertEqual(offenders, [], "concrete TTS provider-id branches:\n" + "\n".join(offenders))


# -- Fingerprints + error isolation -----------------------------------------


class FingerprintAndIsolationTests(unittest.TestCase):
    def test_provider_id_and_options_affect_tts_cache_fingerprint(self):
        node = {"type": "tts.generate", "type_version": 2}
        base = fingerprint_components(
            node,
            {"provider_id": "kokoro", "voice": "af_heart", "speed": 1.0, "provider_options": {}},
            {"script": SCRIPT},
            {},
        )
        other_provider = fingerprint_components(
            node,
            {"provider_id": "inworld", "voice": "af_heart", "speed": 1.0, "provider_options": {}},
            {"script": SCRIPT},
            {},
        )
        other_options = fingerprint_components(
            node,
            {
                "provider_id": "kokoro",
                "voice": "af_heart",
                "speed": 1.0,
                "provider_options": {"lang": "en-gb"},
            },
            {"script": SCRIPT},
            {},
        )
        self.assertNotEqual(canonical_fingerprint(base), canonical_fingerprint(other_provider))
        self.assertNotEqual(canonical_fingerprint(base), canonical_fingerprint(other_options))
        # Schema version is part of the fingerprint (L7 cache invalidation).
        self.assertEqual(base["adapter_cache_schema_version"], ADAPTER_CACHE_SCHEMA_VERSION)

    def test_provider_error_fails_only_the_tts_node(self):
        def resolver(node):
            node_type = node["type"]

            def execute(inputs, config, context):
                definition = get_node_type(node_type)
                if node_type == "tts.generate":
                    raise AdapterError("PROVIDER_FAILED", "synthetic TTS failure")
                outputs = {}
                for port in definition["outputs"]:
                    if port["type"] == "control":
                        outputs[port["id"]] = {"ok": True}
                    elif port["id"] in ("script",) or port["type"] == "script":
                        outputs[port["id"]] = SCRIPT
                    else:
                        outputs[port["id"]] = {"ok": True, "project_id": PROJECT_ID}
                return outputs

            return execute

        workflow = deepcopy(narration_only_template())
        workflow.pop("template_id", None)
        workflow.update({
            "workflow_id": "wf_GT15ER",
            "created_at": "2026-08-09T00:00:00Z",
            "updated_at": "2026-08-09T00:00:00Z",
        })
        for node in workflow["nodes"]:
            if node["type"] == "script.input":
                node["configuration"]["text"] = SCRIPT
        tmp = _managed_temp("sts_gate15_err_")
        self.addCleanup(_rmtree, tmp)
        result = WorkflowScheduler(
            workflow,
            project_id=PROJECT_ID,
            lock_root=os.path.join(tmp, "locks"),
            output_dir=tmp,
            executor_resolver=resolver,
        ).run()
        self.assertEqual(result.status, "failed", result.errors)
        nodes = result.execution_record["nodes"]
        self.assertEqual(nodes["n_script"]["status"], "succeeded")
        self.assertEqual(nodes["n_tts"]["status"], "failed")
        self.assertEqual(nodes["n_tts"]["error"]["code"], "PROVIDER_FAILED")
        # Downstream never succeeded — skipped/absent is fine.
        output = nodes.get("n_output")
        if output is not None:
            self.assertIn(output["status"], ("skipped", "pending", "cancelled", "failed"))


# -- Music / captions unchanged + assemble acceptance -----------------------


class MusicCaptionsRegressionTests(unittest.TestCase):
    def test_music_and_captions_adapters_are_byte_identical_to_step_3_2(self):
        music_path = Path(ROOT_DIR) / "studio" / "workflows" / "adapters" / "music.py"
        captions_path = Path(ROOT_DIR) / "studio" / "workflows" / "adapters" / "captions.py"
        self.assertEqual(_git_blob_hash(music_path), MUSIC_ADAPTER_BLOB)
        self.assertEqual(_git_blob_hash(captions_path), CAPTIONS_ADAPTER_BLOB)

    def test_music_select_and_captions_generate_still_run(self):
        ctx = AdapterContext(project_id=PROJECT_ID)
        # Captions: real adapter over fixture-shaped alignment.
        captions_tmp = _managed_temp("sts_gate15_cap_")
        self.addCleanup(_rmtree, captions_tmp)
        with mock.patch.object(captions_adapter, "CAPTIONS_DIR", captions_tmp):
            cap_out = captions_adapter.generate(
                {
                    "alignment": {
                        "folder": PROJECT_ID,
                        "alignment": [
                            {"word": "A", "begin": 0.0, "end": 0.2},
                            {"word": "short", "begin": 0.2, "end": 0.5},
                            {"word": "script", "begin": 0.5, "end": 0.9},
                        ],
                    }
                },
                {"preset_id": "bold_popup", "words_per_group": 2},
                ctx,
            )
        self.assertTrue(cap_out["captions"]["captions"])
        self.assertTrue(os.path.isfile(os.path.join(captions_tmp, PROJECT_ID, "captions.json")))

        # Music: tone mode over the real library (or skip if library empty).
        try:
            music_out = music_adapter.select(
                {"settings": {"tone": "educational"}},
                {"mode": "tone", "volume": 0.15},
                ctx,
            )
        except AdapterError as exc:
            if exc.code == "MUSIC_NOT_FOUND":
                self.skipTest("music library has no tone-matching tracks")
            raise
        self.assertTrue(str(music_out["track"]["path"]).startswith("/assets/sounds/music/"))
        self.assertEqual(music_out["track"]["volume"], 0.15)

    def test_assemble_accepts_music_and_captions_port_payloads(self):
        from studio.workflows.adapters import editor as editor_adapter

        captions_payload = {
            "project_id": PROJECT_ID,
            "captions": [{"start": 0.0, "end": 0.5, "text": "A short"}],
            "preset": "bold_popup",
        }
        music_payload = {
            "project_id": PROJECT_ID,
            "path": "/assets/sounds/music/ambient/soft.mp3",
            "filename": "soft.mp3",
            "volume": 0.15,
            "fade_in": 2.0,
            "fade_out": 3.0,
            "loop": True,
            "ducking_enabled": True,
            "ducking_level": 0.2,
            "pending_history": ["soft.mp3"],
            "artifact_refs": [],
        }
        assembled = {
            "scenes": [{"id": 0, "duration": 1.0, "mediaUrl": "/output/x.png"}],
            "audio_tracks": [
                {"id": "at_voice", "type": "voice", "path": "/output/tts/x/voice.wav"},
            ],
            "total_duration": 1.0,
        }
        seen = {}

        def fake_assemble(pid):
            seen["pid"] = pid
            return {"assembled_data": deepcopy(assembled), "scene_count": 1, "total_duration": 1.0}

        projects = _managed_temp("sts_gate15_asm_")
        self.addCleanup(_rmtree, projects)
        with mock.patch.object(editor_adapter, "_step_assemble", fake_assemble), \
                mock.patch.object(editor_adapter, "PROJECTS_DIR", projects), \
                mock.patch.object(editor_adapter, "persist_project_audio_history", lambda *a, **k: None):
            out = editor_adapter.assemble(
                {
                    "assets": {"ready": 1},
                    "metadata": {"voice": "af_heart"},
                    "scenes": {"scenes": []},
                    "captions": captions_payload,
                    "music": music_payload,
                    "settings": {"project_name": "Gate"},
                },
                {},
                AdapterContext(project_id=PROJECT_ID),
            )
        self.assertEqual(seen["pid"], PROJECT_ID)
        project = out["project"]["assembled_data"]
        self.assertTrue(project.get("captionsEnabled"))
        self.assertEqual(project["captions"]["captions"][0]["text"], "A short")
        music_tracks = [t for t in project["audio_tracks"] if t.get("type") == "music"]
        self.assertEqual(len(music_tracks), 1)
        self.assertEqual(music_tracks[0]["path"], music_payload["path"])


# -- Template gates ---------------------------------------------------------


class TemplateGateTests(unittest.TestCase):
    """Narration Only + Full Video complete with real audio-side adapters stubbed cleanly."""

    def setUp(self):
        self.tmp = _managed_temp("sts_gate15_tpl_")
        self.addCleanup(_rmtree, self.tmp)
        self.tts_dir = os.path.join(self.tmp, "tts", PROJECT_ID)
        os.makedirs(self.tts_dir, exist_ok=True)
        self.wav = _write_minimal_wav(os.path.join(self.tts_dir, "voice.wav"), duration_s=1.0)
        with open(os.path.join(self.tts_dir, "tts.json"), "w", encoding="utf-8") as handle:
            json.dump({"provider": "fixture", "filename": "voice.wav"}, handle)

    def _resolver(self):
        def resolver(node):
            node_type = node["type"]

            if node_type == "tts.generate":
                def execute(inputs, config, context):
                    import studio.workflows.adapters.common as adapter_common

                    service = {
                        "wav_path": self.wav,
                        "filename": "voice.wav",
                        "folder": PROJECT_ID,
                        "duration_seconds": 1.0,
                        "sample_rate": 8000,
                        "voice": config.get("voice") or "af_heart",
                        "provider": config.get("provider_id") or "kokoro",
                        "words": len(str(inputs.get("script", "")).split()),
                        "job_meta": {
                            "provider_id": config.get("provider_id") or "kokoro",
                            "provider_version": "1.0.0",
                        },
                    }
                    with mock.patch.object(adapter_common, "OUTPUT_DIR", self.tmp), \
                            mock.patch.object(tts_adapter, "_step_tts", return_value=service):
                        return tts_adapter.generate(inputs, config, context)
                return execute

            if node_type == "music.select":
                def execute(inputs, config, context):
                    return {
                        "control": {"ok": True},
                        "track": {
                            "project_id": PROJECT_ID,
                            "path": "/assets/sounds/music/gate/tone.wav",
                            "filename": "tone.wav",
                            "volume": 0.15,
                            "fade_in": 2.0,
                            "fade_out": 3.0,
                            "loop": True,
                            "ducking_enabled": True,
                            "ducking_level": 0.2,
                            "artifact_refs": [],
                        },
                    }
                return execute

            if node_type == "captions.generate":
                def execute(inputs, config, context):
                    alignment = inputs.get("alignment") or {}
                    words = alignment.get("alignment") or [
                        {"word": "A", "begin": 0.0, "end": 0.2},
                        {"word": "short", "begin": 0.2, "end": 0.5},
                    ]
                    cap_dir = os.path.join(self.tmp, "captions", PROJECT_ID)
                    os.makedirs(cap_dir, exist_ok=True)
                    with mock.patch.object(captions_adapter, "CAPTIONS_DIR", os.path.join(self.tmp, "captions")):
                        return captions_adapter.generate(
                            {"alignment": {"folder": PROJECT_ID, "alignment": words}},
                            config,
                            context,
                        )
                return execute

            def execute(inputs, config, context):
                definition = get_node_type(node_type)
                outputs = {}
                for port in definition["outputs"]:
                    if port["type"] == "control":
                        outputs[port["id"]] = {"ok": True}
                    elif port["id"] == "script" or port["type"] == "script":
                        outputs[port["id"]] = SCRIPT
                    elif port["type"] == "project_settings" or port["id"] == "settings":
                        outputs[port["id"]] = {
                            "project_name": "Phase 15 gate",
                            "aspect_ratio": "9:16",
                            "tone": "educational",
                            "style": "cinematic",
                        }
                    elif port["type"] == "audio_file" or port["id"] == "audio":
                        ref = f"tts/{PROJECT_ID}/voice.wav"
                        outputs[port["id"]] = {
                            "wav_path": ref,
                            "filename": "voice.wav",
                            "folder": PROJECT_ID,
                            "duration_seconds": 1.0,
                            "artifact_refs": [ref],
                        }
                    elif port["type"] == "tts_metadata" or port["id"] == "metadata":
                        ref = f"tts/{PROJECT_ID}/voice.wav"
                        outputs[port["id"]] = {
                            "voice": "af_heart",
                            "duration_seconds": 1.0,
                            "folder": PROJECT_ID,
                            "filename": "voice.wav",
                            "wav_path": ref,
                            "artifact_refs": [ref, f"tts/{PROJECT_ID}/tts.json"],
                        }
                    elif port["type"] == "alignment" or port["id"] == "alignment":
                        outputs[port["id"]] = {
                            "transcript": SCRIPT,
                            "folder": PROJECT_ID,
                            "alignment": [
                                {"word": "A", "begin": 0.0, "end": 0.2},
                                {"word": "short", "begin": 0.2, "end": 0.5},
                                {"word": "script", "begin": 0.5, "end": 0.9},
                            ],
                            "word_count": 3,
                        }
                    elif port["type"] == "segments" or port["id"] == "segments":
                        outputs[port["id"]] = {
                            "segments": [
                                {"start": 0.0, "end": 0.5, "words": "A short"},
                                {"start": 0.5, "end": 1.0, "words": "script"},
                            ]
                        }
                    elif port["type"] == "scenes" or port["id"] == "scenes":
                        outputs[port["id"]] = {
                            "scenes": [
                                {"index": 0, "image_prompt": "a lighthouse"},
                                {"index": 1, "image_prompt": "a harbour"},
                            ]
                        }
                    elif port["type"] == "storyboard_images" or port["id"] == "images":
                        outputs[port["id"]] = {
                            "total": 2, "ready": 2, "errors": 0,
                            "project_id": PROJECT_ID,
                            "artifact_refs": [
                                f"storyboard/{PROJECT_ID}/0/image.png",
                                f"storyboard/{PROJECT_ID}/1/image.png",
                            ],
                        }
                    elif port["type"] == "animation_assets" or port["id"] == "assets":
                        outputs[port["id"]] = {
                            "total": 2, "ready": 2, "errors": 0,
                            "project_id": PROJECT_ID,
                            "artifact_refs": [
                                f"animator/{PROJECT_ID}/0/0.png",
                                f"animator/{PROJECT_ID}/1/0.png",
                            ],
                        }
                    elif port["type"] == "captions" or port["id"] == "captions":
                        outputs[port["id"]] = {
                            "captions": [{"start": 0.0, "end": 0.5, "text": "A short"}],
                            "project_id": PROJECT_ID,
                        }
                    elif port["type"] == "music_track" or port["id"] == "track":
                        outputs[port["id"]] = {
                            "path": "/assets/sounds/music/gate/tone.wav",
                            "volume": 0.15,
                        }
                    elif port["type"] == "editor_project" or port["id"] == "project":
                        outputs[port["id"]] = {
                            "project_id": PROJECT_ID,
                            "assembled_data": {
                                "project_id": PROJECT_ID,
                                "scenes": [
                                    {
                                        "id": 0, "duration": 1.0,
                                        "mediaUrl": f"/output/animator/{PROJECT_ID}/0/0.png",
                                    },
                                ],
                                "audio_tracks": [
                                    {
                                        "id": "at_voice", "type": "voice",
                                        "path": f"/output/tts/{PROJECT_ID}/voice.wav",
                                        "volume": 1.0,
                                    },
                                    {
                                        "id": "at_music", "type": "music",
                                        "path": "/assets/sounds/music/gate/tone.wav",
                                        "volume": 0.15,
                                    },
                                ],
                                "captions": {
                                    "captions": [{"start": 0.0, "end": 0.5, "text": "A short"}],
                                },
                                "captionsEnabled": True,
                                "total_duration": 1.0,
                            },
                        }
                    elif port["type"] == "video_file" or port["id"] == "video":
                        outputs[port["id"]] = {
                            "path": f"exports/{PROJECT_ID}/final.mp4",
                            "artifact_refs": [f"exports/{PROJECT_ID}/final.mp4"],
                        }
                    else:
                        outputs[port["id"]] = {"ok": True, "project_id": PROJECT_ID}
                return outputs

            return execute

        return resolver

    def _run(self, document: dict):
        workflow = deepcopy(document)
        workflow.pop("template_id", None)
        workflow.update({
            "workflow_id": "wf_GATE15",
            "created_at": "2026-08-09T00:00:00Z",
            "updated_at": "2026-08-09T00:00:00Z",
        })
        for node in workflow["nodes"]:
            if node["type"] == "script.input":
                node["configuration"]["text"] = SCRIPT
            if node["type"] == "project.setup":
                node["configuration"]["tone"] = "educational"
                node["configuration"]["project_name"] = "Phase 15 gate"
            if node["type"] == "tts.generate":
                # Shipped provider so save-time voice-option validation succeeds
                # without registering the tests-only fixture provider.
                node["configuration"]["provider_id"] = "kokoro"
                node["configuration"]["voice"] = "af_heart"
        return WorkflowScheduler(
            workflow,
            project_id=PROJECT_ID,
            lock_root=os.path.join(self.tmp, "locks"),
            output_dir=self.tmp,
            executor_resolver=self._resolver(),
        ).run()

    def test_narration_only_template_completes(self):
        result = self._run(narration_only_template())
        self.assertEqual(result.status, "succeeded", result.errors)
        tts_node = result.execution_record["nodes"]["n_tts"]
        self.assertEqual(tts_node["status"], "succeeded")
        # Artifact refs recorded without absolute paths.
        refs = tts_node.get("artifact_refs") or []
        self.assertTrue(any(str(r).endswith("voice.wav") for r in refs), refs)
        self.assertFalse(_absolute_path_in(refs))

    def test_full_video_template_completes_with_music_and_captions(self):
        result = self._run(full_video_template())
        self.assertEqual(result.status, "succeeded", result.errors)
        statuses = {
            node_id: node["status"]
            for node_id, node in result.execution_record["nodes"].items()
        }
        self.assertTrue(all(s == "succeeded" for s in statuses.values()), statuses)
        self.assertEqual(statuses["n_music"], "succeeded")
        self.assertEqual(statuses["n_captions"], "succeeded")
        self.assertEqual(statuses["n_tts"], "succeeded")
        self.assertEqual(statuses["n_export"], "succeeded")

    def test_built_in_templates_still_serialize(self):
        ids = [item["template_id"] for item in serialize_templates()]
        self.assertIn("narration_only", ids)
        self.assertIn("full_video", ids)


# -- Legacy TTS surface + playable export -----------------------------------


class LegacyTtsSurfaceTests(unittest.TestCase):
    def test_generate_response_omits_absolute_wav_path(self):
        from flask import Flask
        from studio.tts.routes import tts_bp
        from studio.tts import dispatch
        from studio.shared.providers_common import settings_manager
        from studio.shared.providers_common.domains import DOMAINS

        tmp = _managed_temp("sts_gate15_legacy_")
        self.addCleanup(_rmtree, tmp)
        tts_dir = os.path.join(tmp, "tts")
        cache_dir = os.path.join(tmp, "tts_cache")
        os.makedirs(cache_dir, exist_ok=True)

        settings = {
            "version": settings_manager.SETTINGS_VERSION,
            "general": {},
            "domains": {
                domain: {"selected_provider": None, "per_provider": {}}
                for domain in DOMAINS
            },
        }
        settings["domains"]["tts"]["selected_provider"] = "fixture_artifact"

        import config
        import studio.workflows.adapters.common as adapter_common
        from studio.shared.providers_common import results as results_mod

        patches = [
            mock.patch.object(settings_manager, "load_settings", return_value=settings),
            mock.patch.object(settings_manager, "save_settings", lambda data: None),
            mock.patch.object(config, "OUTPUT_DIR", tmp),
            mock.patch.object(config, "TTS_DIR", tts_dir),
            mock.patch.object(dispatch, "TTS_DIR", tts_dir),
            mock.patch.object(dispatch, "TTS_CACHE_DIR", cache_dir),
            mock.patch.object(results_mod, "OUTPUT_DIR", tmp),
            mock.patch.object(adapter_common, "OUTPUT_DIR", tmp),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        # Ensure the fixture provider is on the hub (tests package path).
        if hub.get("tts", "fixture_artifact") is None:
            self.skipTest("fixture_artifact TTS provider is not registered")

        app = Flask(__name__)
        app.register_blueprint(tts_bp)
        client = app.test_client()
        response = client.post("/api/tts/generate", json={
            "prompt": "hello gate",
            "provider": "fixture_artifact",
            "voice": "fx_calm",
        })
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = response.get_json()
        self.assertNotIn("wav_path", body)
        self.assertFalse(_absolute_path_in(body))
        self.assertEqual(body["provider"], "fixture_artifact")


class PlayableExportTests(unittest.TestCase):
    """Local FFmpeg export from fixture media proves assemble/export still accept audio."""

    def test_fixture_project_exports_a_playable_mp4(self):
        from studio.editor import video_processor
        from studio.ffmpeg_utils import find_ffmpeg, find_ffprobe

        ffmpeg = find_ffmpeg()
        ffprobe = find_ffprobe()
        if not ffmpeg or not ffprobe:
            self.skipTest("ffmpeg/ffprobe unavailable")

        scene = FIXTURES / "media" / "scene.mp4"
        voice = FIXTURES / "media" / "voice.wav"
        music = FIXTURES / "media" / "music.wav"
        if not (scene.is_file() and voice.is_file() and music.is_file()):
            self.skipTest("workflow fixtures media missing")

        tmp = tempfile.mkdtemp(prefix="sts_gate15_export_")
        self.addCleanup(_rmtree, tmp)
        out = os.path.join(tmp, "gate15.mp4")

        # Copy fixtures into a layout VideoProcessor understands (absolute paths).
        scene_path = os.path.join(tmp, "scene.mp4")
        voice_path = os.path.join(tmp, "voice.wav")
        music_path = os.path.join(tmp, "music.wav")
        shutil.copy2(scene, scene_path)
        shutil.copy2(voice, voice_path)
        shutil.copy2(music, music_path)

        payload = {
            "project_id": PROJECT_ID,
            "scenes": [{
                "id": 0,
                "duration": 2.0,
                "media": {"path": scene_path, "type": "video"},
                "effect": {"type": "none"},
                "transition": {"type": "none", "duration": 0},
            }],
            "output": {
                "resolution": {"width": 320, "height": 568},
                "fps": 24,
                "quality": "draft",
                "preset": "ultrafast",
            },
            "timeline": {"total_duration": 2.0},
            "audio": {
                "path": voice_path,
                "volume": 1.0,
                "start_offset": 0,
                "timeline_offset": 0,
                "fade_in": 0,
                "fade_out": 0.1,
            },
            "bgMusic": {
                "path": music_path,
                "volume": 0.15,
                "loop": True,
                "fade_in": 0.1,
                "fade_out": 0.1,
            },
            "captions": {
                "captions": [
                    {"start": 0.0, "end": 1.0, "text": "A lighthouse keeper"},
                    {"start": 1.0, "end": 2.0, "text": "climbs the spiral"},
                ],
                "style": {"preset": "bold_popup"},
            },
            "profile": "yt_shorts",
            "aspect_ratio": "9:16",
        }

        video_processor.VideoProcessor(payload).process(out)
        self.assertTrue(os.path.isfile(out), out)
        self.assertGreater(os.path.getsize(out), 1000)

        probe = subprocess.run(
            [
                ffprobe, "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", out,
            ],
            capture_output=True, text=True, timeout=60, check=True,
        )
        data = json.loads(probe.stdout)
        kinds = {stream["codec_type"] for stream in data["streams"]}
        self.assertIn("video", kinds)
        self.assertIn("audio", kinds)
        self.assertGreater(float(data["format"]["duration"]), 0.5)


if __name__ == "__main__":
    unittest.main()
