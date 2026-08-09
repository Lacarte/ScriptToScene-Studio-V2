"""Step 14.5 — Visual-provider compatibility and live gate.

Proves the Phase 14 migration is complete without spending live credits:

  * every shipped visual provider runs through the generic dispatch path with
    a fixture-backed / mocked transport;
  * the Storyboard-only and Full Video templates complete when visual nodes
    use that path;
  * legacy Storyboard and Animator page routes keep their wire envelopes;
  * job envelopes, progress totals, managed artifacts, and cache fingerprints
    match the pre-migration public contracts (diffs below are approved);
  * providers blocked by credentials or human browser interaction stay gated
    behind `STS_LIVE` / `STS_LIVE_STORYBOARD` and never weaken deterministic
    suites (see `_dev/loop-engineering/live-verification/README.md`).

Approved compatibility diffs (before → after migration):

  | surface | preserved | intentional change |
  |---|---|---|
  | public job id | still the project id | `media_job.json` sits *beside* the domain manifest |
  | storyboard.json / grabber_job.json | same counters + scene_statuses | `provider_id` metadata field recorded on seed |
  | node port payload | `{total, ready, errors}` (+ scene_statuses for storyboard) | animator still strips `scene_statuses` (remote URLs, D38) |
  | progress | `{ready, total}` | submit progress now carries the real unit count from pydantic requests |
  | cache fingerprint | config + inputs + upstream | includes `provider_id` / `provider_options` via node configuration |
  | legacy aliases | gemini/webhook/direct, grok/kie-ai/midjourney | reverse-normalized at the route boundary only |
  | pipeline id_to_legacy tables | removed | routes accept both spellings via the hub |
"""

from __future__ import annotations

import inspect
import json
import os
import re
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from config import OUTPUT_DIR, ROOT_DIR
from studio.animator import jobs as anim_jobs
from studio.io_utils import safe_json_read
from studio.shared.providers_common.domains import DOMAINS, DomainSpec
from studio.shared.providers_common.hub import ProviderHub, hub
from studio.shared.providers_common.jobs import JobHandle, RUNNING, SUCCEEDED
from studio.shared.providers_common.media_jobs import (
    RECORD_FILENAME,
    MediaJobService,
    MediaJobStore,
    _request_total,
)
from studio.storyboard import jobs as sb_jobs
from studio.workflows.adapters import animator as animator_adapter
from studio.workflows.adapters import storyboard as storyboard_adapter
from studio.workflows.adapters.common import AdapterContext, AdapterError
from studio.workflows.cache import canonical_fingerprint, fingerprint_components
from studio.workflows.registry import get_node_type
from studio.workflows.scheduler import WorkflowScheduler
from studio.workflows.templates import (
    full_video_template,
    serialize_templates,
    storyboard_only_template,
)


PROJECT_ID = "pm_GATE14"
PNG = b"\x89PNG\r\n\x1a\n"

STORYBOARD_PROVIDERS = ("gemini_ws", "wavespeed_webhook", "wavespeed_direct")
ANIMATOR_PROVIDERS = ("grok_automa", "kie_ai")
STORYBOARD_ALIASES = {
    "gemini": "gemini_ws",
    "webhook": "wavespeed_webhook",
    "direct": "wavespeed_direct",
}
ANIMATOR_ALIASES = {
    "grok": "grok_automa",
    "midjourney": "grok_automa",
    "kie-ai": "kie_ai",
}

SCENES = {
    "scenes": [
        {"index": 0, "image_prompt": "a lighthouse at dusk"},
        {"index": 1, "image_prompt": "a harbour at dawn"},
    ]
}


# -- helpers ----------------------------------------------------------------


class ProgressLog:
    """Records message-only progress frames (AdapterContext.progress contract)."""

    def __init__(self):
        self.messages: list[str] = []

    def __call__(self, message: str = ""):
        if message:
            self.messages.append(str(message))


def _context(progress: ProgressLog | None = None) -> AdapterContext:
    return AdapterContext(
        project_id=PROJECT_ID,
        execution_id="ex_gate14",
        node_id="n_visual",
        progress=progress,
        stop_requested=lambda: False,
    )


def _fast_media_job_service():
    """Zero-sleep service so the gate suite does not pay real poll delays."""
    return MediaJobService(MediaJobStore(), sleeper=lambda _seconds: None)


def _managed_temp(prefix: str) -> str:
    """Temp dir under OUTPUT_DIR so artifact_ref accepts the written paths."""
    root = os.path.join(OUTPUT_DIR, "_gate14")
    os.makedirs(root, exist_ok=True)
    return tempfile.mkdtemp(prefix=prefix, dir=root)


def _clear_grabber_jobs() -> None:
    for key, _value in list(anim_jobs.grabber_jobs.items()):
        anim_jobs.grabber_jobs.pop(key)


def _rmtree(path: str) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)


def _write_png(path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(PNG)
    return path


class ManifestStoryboardProvider:
    """Fixture-shaped storyboard body that writes the public legacy manifest."""

    def __init__(self, provider_id: str, root: str):
        self.provider_id = provider_id
        self.root = root
        self.submitted = []

    def submit(self, request, invocation):
        self.submitted.append((request, invocation))
        project_id = invocation.project_id
        # Point the domain store at the private root for this provider instance.
        sb_jobs.seed(project_id, request, provider_id=self.provider_id)
        for scene in request.scenes:
            local = sb_jobs.local_path(project_id, scene.index, "image.png")
            abs_path = os.path.join(
                self.root, project_id, str(scene.index), "image.png"
            )
            _write_png(abs_path)
            sb_jobs.mark_scene(
                project_id, scene.index, "ready", local_path=local
            )
        sb_jobs.mark_done(project_id)
        return JobHandle(
            job_id=project_id,
            domain="storyboard",
            provider_id=self.provider_id,
            project_id=project_id,
            invocation_id=invocation.invocation_id,
        )

    def poll(self, job_id, invocation):
        return sb_jobs.status(invocation.project_id or job_id, job_id)

    def cancel_job(self, job_id, invocation):
        return None


class ManifestAnimatorProvider:
    """Fixture-shaped animator body that writes grabber_job.json."""

    def __init__(self, provider_id: str, root: str):
        self.provider_id = provider_id
        self.root = root
        self.submitted = []

    def submit(self, request, invocation):
        self.submitted.append((request, invocation))
        project_id = invocation.project_id
        anim_jobs.seed(
            project_id, request, provider_id=self.provider_id, status="waiting"
        )
        for scene in request.scenes:
            abs_path = os.path.join(
                self.root, project_id, str(scene.index), "0.png"
            )
            _write_png(abs_path)
            anim_jobs.mark_scene(
                project_id,
                scene.index,
                "ready",
                local_files=[f"/output/animator/{project_id}/{scene.index}/0.png"],
            )
        anim_jobs.mark_done(project_id)
        return JobHandle(
            job_id=project_id,
            domain="animator",
            provider_id=self.provider_id,
            project_id=project_id,
            invocation_id=invocation.invocation_id,
        )

    def poll(self, job_id, invocation):
        return anim_jobs.status(invocation.project_id or job_id, job_id)

    def cancel_job(self, job_id, invocation):
        return None


# -- request total / progress envelope --------------------------------------


class RequestTotalTests(unittest.TestCase):
    def test_pydantic_storyboard_request_reports_unit_count_at_submit(self):
        from studio.storyboard.providers.contract import StoryboardRequest

        request = StoryboardRequest.from_scenes(SCENES["scenes"])
        self.assertEqual(_request_total(request, ()), 2)

    def test_pydantic_animator_request_reports_unit_count_at_submit(self):
        from studio.animator.providers.contract import AnimatorRequest

        request = AnimatorRequest.from_scenes(SCENES["scenes"])
        self.assertEqual(_request_total(request, ()), 2)

    def test_mapping_unit_count_still_wins(self):
        self.assertEqual(_request_total({"unit_count": 4, "scenes": []}, ()), 4)


# -- per-provider fixture-backed adapter paths ------------------------------


class StoryboardProviderPathTests(unittest.TestCase):
    """Every shipped storyboard provider completes through generic dispatch."""

    def setUp(self):
        self.tmp = _managed_temp("sts_gate_sb_")
        self.addCleanup(_rmtree, self.tmp)
        patch = mock.patch.object(sb_jobs, "STORYBOARD_DIR", self.tmp)
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(storyboard_adapter, "STORYBOARD_DIR", self.tmp)
        patch.start()
        self.addCleanup(patch.stop)

    def _run(self, provider_id: str, progress: ProgressLog | None = None):
        provider = ManifestStoryboardProvider(provider_id, self.tmp)
        with mock.patch.object(
            storyboard_adapter, "resolve_provider", return_value=provider
        ), mock.patch.object(
            storyboard_adapter, "_resolved_settings", return_value={}
        ), mock.patch.object(
            storyboard_adapter, "provider_run_options", return_value={}
        ), mock.patch(
            "studio.workflows.adapters.media_job.MediaJobService",
            _fast_media_job_service,
        ):
            return storyboard_adapter.generate(
                {"scenes": SCENES},
                {"provider_id": provider_id, "aspect_ratio": "9:16"},
                _context(progress),
            ), provider

    def test_every_shipped_provider_produces_compatible_artifacts(self):
        for provider_id in STORYBOARD_PROVIDERS:
            with self.subTest(provider=provider_id):
                progress = ProgressLog()
                result, provider = self._run(provider_id, progress)
                images = result["images"]
                self.assertEqual(images["total"], 2)
                self.assertEqual(images["ready"], 2)
                self.assertEqual(images["errors"], 0)
                # SCENE_SENTINEL_KEY ("-1") is the extension's job-done marker;
                # counters and unit keys ignore it (status_from_scenes).
                scene_keys = {
                    key for key in images["scene_statuses"] if key != "-1"
                }
                self.assertEqual(scene_keys, {"0", "1"})
                for key, entry in images["scene_statuses"].items():
                    if key == "-1":
                        continue
                    self.assertEqual(entry["status"], "ready")
                    self.assertTrue(str(entry["local_path"]).startswith("/output/storyboard/"))
                # Managed artifact refs never carry a leading /output/ and stay relative.
                scene_refs = [
                    ref for ref in images.get("artifact_refs") or []
                    if ref.endswith((".png", ".jpeg", ".jpg", ".webp"))
                ]
                self.assertTrue(scene_refs, images.get("artifact_refs"))
                for ref in images.get("artifact_refs") or []:
                    self.assertFalse(ref.startswith("/output/"), ref)
                    self.assertFalse(os.path.isabs(ref), ref)
                    self.assertIn("storyboard", ref.replace("\\", "/"))
                # Public job id is still the project id.
                self.assertEqual(provider.submitted[0][1].project_id, PROJECT_ID)
                self.assertEqual(provider.submitted[0][1].provider_id, provider_id)
                # Progress messages were emitted (AdapterContext is message-only).
                self.assertTrue(progress.messages, progress.messages)
                # Legacy manifest remains authoritative; provider field recorded on seed.
                manifest = safe_json_read(
                    os.path.join(self.tmp, PROJECT_ID, "storyboard.json")
                )
                self.assertEqual(manifest["total"], 2)
                self.assertEqual(manifest["ready"], 2)
                self.assertEqual(manifest.get("provider"), provider_id)
                self.assertTrue(os.path.isfile(
                    os.path.join(self.tmp, PROJECT_ID, "storyboard.json")
                ))
                # media_job.json is written *beside* the domain manifest during the
                # run and dropped after terminal aggregation on success.
                self.assertEqual(RECORD_FILENAME, "media_job.json")

    def test_legacy_alias_resolves_before_dispatch(self):
        for alias, canonical in STORYBOARD_ALIASES.items():
            with self.subTest(alias=alias):
                provider = ManifestStoryboardProvider(canonical, self.tmp)
                with mock.patch.object(
                    storyboard_adapter, "resolve_provider", return_value=provider
                ), mock.patch.object(
                    storyboard_adapter, "_resolved_settings", return_value={}
                ), mock.patch.object(
                    storyboard_adapter, "provider_run_options", return_value={}
                ), mock.patch.object(
                    storyboard_adapter,
                    "_canonical_provider_id",
                    return_value=canonical,
                ), mock.patch(
                    "studio.workflows.adapters.media_job.MediaJobService",
                    _fast_media_job_service,
                ):
                    storyboard_adapter._step_storyboard(
                        SCENES,
                        {"storyboard_provider_override": alias},
                        PROJECT_ID,
                        _context(),
                    )
                self.assertEqual(provider.submitted[0][1].provider_id, canonical)


class AnimatorProviderPathTests(unittest.TestCase):
    """Every shipped animator provider completes through generic dispatch."""

    def setUp(self):
        self.tmp = _managed_temp("sts_gate_an_")
        self.addCleanup(_rmtree, self.tmp)
        _clear_grabber_jobs()
        patch = mock.patch.object(anim_jobs, "ANIMATOR_DIR", self.tmp)
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(animator_adapter, "ANIMATOR_DIR", self.tmp)
        patch.start()
        self.addCleanup(patch.stop)

    def _run(self, provider_id: str, progress: ProgressLog | None = None):
        provider = ManifestAnimatorProvider(provider_id, self.tmp)
        with mock.patch.object(
            animator_adapter, "resolve_provider", return_value=provider
        ), mock.patch.object(
            animator_adapter, "_resolved_settings", return_value={}
        ), mock.patch.object(
            animator_adapter, "provider_run_options", return_value={}
        ), mock.patch(
            "studio.workflows.adapters.media_job.MediaJobService",
            _fast_media_job_service,
        ):
            return animator_adapter.generate(
                {"scenes": SCENES},
                {"provider_id": provider_id, "aspect_ratio": "9:16", "mode": "image"},
                _context(progress),
            ), provider

    def test_every_shipped_provider_produces_compatible_artifacts(self):
        for provider_id in ANIMATOR_PROVIDERS:
            with self.subTest(provider=provider_id):
                progress = ProgressLog()
                result, provider = self._run(provider_id, progress)
                assets = result["assets"]
                self.assertEqual(assets["total"], 2)
                self.assertEqual(assets["ready"], 2)
                self.assertEqual(assets["errors"], 0)
                self.assertEqual(assets["provider"], provider_id)
                # D38: remote scene_statuses never cross the port.
                self.assertNotIn("scene_statuses", assets)
                media = [
                    ref for ref in assets.get("artifact_refs") or []
                    if ref.lower().endswith((".png", ".jpg", ".jpeg", ".mp4", ".webm"))
                ]
                self.assertTrue(media, assets.get("artifact_refs"))
                for ref in media:
                    self.assertTrue(ref.startswith("animator/"), ref)
                self.assertTrue(progress.messages, progress.messages)
                job = safe_json_read(
                    os.path.join(self.tmp, PROJECT_ID, "grabber_job.json")
                )
                self.assertEqual(job["project_id"], PROJECT_ID)
                self.assertIn(job["status"], ("done", "completed"))
                self.assertEqual(set(job["scene_statuses"]), {"0", "1"})
                self.assertEqual(job.get("provider"), provider_id)


# -- template gates through the real scheduler ------------------------------


class TemplateGateTests(unittest.TestCase):
    """Storyboard-only and Full Video complete via the generic visual path."""

    def setUp(self):
        self.tmp = _managed_temp("sts_gate_tpl_")
        self.addCleanup(_rmtree, self.tmp)
        self.sb_root = os.path.join(self.tmp, "storyboard")
        self.an_root = os.path.join(self.tmp, "animator")
        os.makedirs(self.sb_root, exist_ok=True)
        os.makedirs(self.an_root, exist_ok=True)
        _clear_grabber_jobs()

    def _resolver(self, *, storyboard_provider="wavespeed_direct", animator_provider="kie_ai"):
        """Execute real visual adapters; stub every other node deterministically."""

        def resolver(node):
            node_type = node["type"]

            if node_type == "storyboard.generate":
                def execute(inputs, config, context):
                    provider = ManifestStoryboardProvider(storyboard_provider, self.sb_root)
                    with mock.patch.object(sb_jobs, "STORYBOARD_DIR", self.sb_root), \
                            mock.patch.object(storyboard_adapter, "STORYBOARD_DIR", self.sb_root), \
                            mock.patch.object(
                                storyboard_adapter, "resolve_provider", return_value=provider
                            ), mock.patch.object(
                                storyboard_adapter, "_resolved_settings", return_value={}
                            ), mock.patch.object(
                                storyboard_adapter, "provider_run_options", return_value={}
                            ), mock.patch(
                                "studio.workflows.adapters.media_job.MediaJobService",
                                _fast_media_job_service,
                            ):
                        return storyboard_adapter.generate(inputs, {
                            **config,
                            "provider_id": storyboard_provider,
                        }, context)
                return execute

            if node_type == "animator.generate":
                def execute(inputs, config, context):
                    provider = ManifestAnimatorProvider(animator_provider, self.an_root)
                    with mock.patch.object(anim_jobs, "ANIMATOR_DIR", self.an_root), \
                            mock.patch.object(animator_adapter, "ANIMATOR_DIR", self.an_root), \
                            mock.patch.object(
                                animator_adapter, "resolve_provider", return_value=provider
                            ), mock.patch.object(
                                animator_adapter, "_resolved_settings", return_value={}
                            ), mock.patch.object(
                                animator_adapter, "provider_run_options", return_value={}
                            ), mock.patch(
                                "studio.workflows.adapters.media_job.MediaJobService",
                                _fast_media_job_service,
                            ):
                        return animator_adapter.generate(inputs, {
                            **config,
                            "provider_id": animator_provider,
                            "mode": "image",
                        }, context)
                return execute

            def execute(inputs, config, context):
                definition = get_node_type(node_type)
                outputs = {}
                for port in definition["outputs"]:
                    if port["type"] == "control":
                        outputs[port["id"]] = {"ok": True}
                    elif port["id"] == "script" or port["type"] == "script":
                        outputs[port["id"]] = "A short script for the gate."
                    elif port["type"] == "scenes" or port["id"] == "scenes":
                        outputs[port["id"]] = deepcopy(SCENES)
                    elif port["type"] == "project_settings" or port["id"] == "settings":
                        outputs[port["id"]] = {
                            "project_name": "Gate",
                            "aspect_ratio": "9:16",
                            "tone": "educational",
                            "style": "cinematic",
                        }
                    elif port["type"] == "storyboard_images" or port["id"] == "images":
                        outputs[port["id"]] = {
                            "total": 2, "ready": 2, "errors": 0,
                            "scene_statuses": {
                                "0": {"status": "ready", "local_path": f"/output/storyboard/{PROJECT_ID}/0/image.png"},
                                "1": {"status": "ready", "local_path": f"/output/storyboard/{PROJECT_ID}/1/image.png"},
                            },
                            "project_id": PROJECT_ID,
                            "artifact_refs": [
                                f"storyboard/{PROJECT_ID}/0/image.png",
                                f"storyboard/{PROJECT_ID}/1/image.png",
                            ],
                        }
                    elif port["type"] == "animation_assets" or port["id"] == "assets":
                        outputs[port["id"]] = {
                            "total": 2, "ready": 2, "errors": 0,
                            "provider": animator_provider,
                            "project_id": PROJECT_ID,
                            "artifact_refs": [
                                f"animator/{PROJECT_ID}/0/0.png",
                                f"animator/{PROJECT_ID}/1/0.png",
                            ],
                        }
                    elif port["type"] == "editor_project" or port["id"] == "project":
                        outputs[port["id"]] = {
                            "project_id": PROJECT_ID,
                            "scenes": [
                                {"index": 0, "duration": 2.0},
                                {"index": 1, "duration": 2.0},
                            ],
                            "audio_tracks": [
                                {"type": "voice", "id": "voice"},
                                {"type": "music", "id": "music"},
                            ],
                            "captionsEnabled": True,
                        }
                    elif port["type"] == "video_file" or port["id"] == "video":
                        outputs[port["id"]] = {
                            "path": f"exports/{PROJECT_ID}/final.mp4",
                            "artifact_refs": [f"exports/{PROJECT_ID}/final.mp4"],
                        }
                    elif port["type"] == "audio_file" or port["id"] == "audio":
                        outputs[port["id"]] = {
                            "wav_path": f"tts/{PROJECT_ID}/voice.wav",
                            "duration_seconds": 4.0,
                        }
                    elif port["type"] == "tts_metadata" or port["id"] == "metadata":
                        outputs[port["id"]] = {"voice": "af_heart", "duration_seconds": 4.0}
                    elif port["type"] == "alignment" or port["id"] == "alignment":
                        outputs[port["id"]] = {
                            "transcript": "A short script for the gate.",
                            "alignment": [
                                {"word": "A", "begin": 0.0, "end": 0.2},
                                {"word": "short", "begin": 0.2, "end": 0.5},
                            ],
                            "word_count": 2,
                        }
                    elif port["type"] == "segments" or port["id"] == "segments":
                        outputs[port["id"]] = {
                            "segments": [
                                {"start": 0.0, "end": 2.0, "words": "A short"},
                                {"start": 2.0, "end": 4.0, "words": "script"},
                            ]
                        }
                    elif port["type"] == "captions" or port["id"] == "captions":
                        outputs[port["id"]] = {"captions": []}
                    elif port["type"] == "music_track" or port["id"] == "track":
                        outputs[port["id"]] = {"track_ref": "media/music.wav", "volume": 0.3}
                    else:
                        outputs[port["id"]] = {"ok": True, "project_id": PROJECT_ID}
                return outputs

            return execute

        return resolver

    def _run_template(self, document: dict):
        workflow = deepcopy(document)
        workflow.pop("template_id", None)
        workflow.update({
            "workflow_id": "wf_GATE14",
            "created_at": "2026-08-09T00:00:00Z",
            "updated_at": "2026-08-09T00:00:00Z",
        })
        for node in workflow["nodes"]:
            if node["type"] == "script.input":
                node["configuration"]["text"] = "A short script for the gate."
            if node["type"] == "project.setup":
                node["configuration"]["tone"] = "educational"
                node["configuration"]["project_name"] = "Phase 14 gate"
            if node["type"] == "storyboard.generate":
                node["configuration"]["provider_id"] = "wavespeed_direct"
            if node["type"] == "animator.generate":
                node["configuration"]["provider_id"] = "kie_ai"
        return WorkflowScheduler(
            workflow,
            project_id=PROJECT_ID,
            lock_root=os.path.join(self.tmp, "locks"),
            output_dir=self.tmp,
            executor_resolver=self._resolver(),
        ).run()

    def test_storyboard_only_template_completes_through_generic_dispatch(self):
        result = self._run_template(storyboard_only_template())
        self.assertEqual(result.status, "succeeded", result.errors)
        node = result.execution_record["nodes"]["n_storyboard"]
        self.assertEqual(node["status"], "succeeded")
        # Manifest written by the real adapter path.
        manifest = safe_json_read(
            os.path.join(self.sb_root, PROJECT_ID, "storyboard.json")
        )
        self.assertEqual(manifest["ready"], manifest["total"])
        self.assertEqual(manifest["errors"], 0)

    def test_full_video_template_completes_through_generic_dispatch(self):
        result = self._run_template(full_video_template())
        self.assertEqual(result.status, "succeeded", result.errors)
        statuses = {
            node_id: node["status"]
            for node_id, node in result.execution_record["nodes"].items()
        }
        self.assertTrue(
            all(status == "succeeded" for status in statuses.values()),
            statuses,
        )
        self.assertEqual(
            result.execution_record["nodes"]["n_storyboard"]["status"], "succeeded"
        )
        self.assertEqual(
            result.execution_record["nodes"]["n_animator"]["status"], "succeeded"
        )
        # Timeline assembly node produced a project payload for the editor.
        assemble = result.execution_record["nodes"]["n_assemble"]
        self.assertEqual(assemble["status"], "succeeded")
        job = safe_json_read(os.path.join(self.an_root, PROJECT_ID, "grabber_job.json"))
        self.assertIn(job["status"], ("done", "completed"))
        self.assertEqual(job.get("provider") or "kie_ai", "kie_ai")

    def test_built_in_templates_still_serialize(self):
        ids = [item["template_id"] for item in serialize_templates()]
        self.assertIn("storyboard_only", ids)
        self.assertIn("full_video", ids)


# -- legacy page routes -----------------------------------------------------


class LegacyPageRouteTests(unittest.TestCase):
    """Storyboard and Animator pages keep their generate/start envelopes."""

    def setUp(self):
        self.tmp = _managed_temp("sts_gate_legacy_")
        self.addCleanup(_rmtree, self.tmp)
        _clear_grabber_jobs()

    def test_storyboard_generate_envelope(self):
        from app import app
        from studio.storyboard import routes as sb_routes

        submitted = []

        def record(instance, request, project_id, options):
            submitted.append({
                "provider": instance.id,
                "request": request,
                "project_id": project_id,
            })
            return JobHandle(
                job_id=project_id, domain="storyboard",
                provider_id=instance.id, project_id=project_id,
            )

        with mock.patch.object(sb_jobs, "STORYBOARD_DIR", self.tmp), \
                mock.patch.object(sb_routes, "_submit", record):
            with app.test_client() as client:
                response = client.post("/api/storyboard/generate", json={
                    "project_id": PROJECT_ID,
                    "provider": "direct",
                    "scenes": [
                        {"scene": 0, "prompt": "a lighthouse"},
                        {"scene": 1, "prompt": "a harbour"},
                    ],
                    "aspect_ratio": "9:16",
                })
        self.assertEqual(response.status_code, 202)
        body = response.get_json()
        self.assertEqual(body["status"], "running")
        self.assertEqual(body["project_id"], PROJECT_ID)
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["provider"], "wavespeed_direct")
        self.assertEqual(submitted[-1]["provider"], "wavespeed_direct")

    def test_animator_grabber_start_envelope(self):
        from app import app
        from studio.animator import animation_routes as anim_routes

        submitted = []

        def record(instance, request, project_id, options):
            submitted.append({
                "provider": instance.id,
                "request": request,
                "project_id": project_id,
            })
            anim_jobs.seed(
                project_id, request, provider_id=instance.id, status="waiting"
            )
            return JobHandle(
                job_id=project_id, domain="animator",
                provider_id=instance.id, project_id=project_id,
            )

        with mock.patch.object(anim_jobs, "ANIMATOR_DIR", self.tmp), \
                mock.patch.object(anim_routes, "_submit", record):
            with app.test_client() as client:
                response = client.post("/api/animator/grabber/start", json={
                    "project_id": PROJECT_ID,
                    "provider": "kie-ai",
                    "aspect_ratio": "9:16",
                    "scenes": [
                        {"scene": 0, "prompt": "a lighthouse"},
                        {"scene": 1, "prompt": "a harbour"},
                    ],
                })
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["project_id"], PROJECT_ID)
        self.assertEqual(body["scene_count"], 2)
        self.assertEqual(body["provider"], "kie_ai")
        self.assertTrue(body.get("grabber_id"))
        self.assertEqual(submitted[-1]["provider"], "kie_ai")


# -- cache fingerprints -----------------------------------------------------


class FingerprintCompatibilityTests(unittest.TestCase):
    def test_provider_id_is_part_of_the_visual_node_fingerprint(self):
        for node_type in ("storyboard.generate", "animator.generate"):
            with self.subTest(node=node_type):
                node = {"id": "n", "type": node_type, "type_version": 2}
                base = fingerprint_components(
                    node, {"provider_id": "wavespeed_direct", "aspect_ratio": "9:16"},
                    {}, {},
                )
                other = fingerprint_components(
                    node, {"provider_id": "gemini_ws", "aspect_ratio": "9:16"},
                    {}, {},
                )
                options = fingerprint_components(
                    node,
                    {
                        "provider_id": "wavespeed_direct",
                        "aspect_ratio": "9:16",
                        "provider_options": {"image_model": "flux"},
                    },
                    {},
                    {},
                )
                self.assertNotEqual(
                    canonical_fingerprint(base), canonical_fingerprint(other)
                )
                self.assertNotEqual(
                    canonical_fingerprint(base), canonical_fingerprint(options)
                )


# -- generic dispatch surface guards ----------------------------------------


class GenericDispatchSurfaceTests(unittest.TestCase):
    """Routes and adapters must not re-introduce provider-ID branches."""

    BRANCH_RE = re.compile(
        r"""if\s+(?:provider(?:_id)?|selected|canonical)\s*==\s*['\"]"""
    )

    def test_storyboard_adapter_has_no_provider_id_branch(self):
        source = inspect.getsource(storyboard_adapter)
        self.assertIsNone(self.BRANCH_RE.search(source), source)
        self.assertIn("run_manifest_job", source)
        self.assertIn("resolve_provider", source)

    def test_animator_adapter_has_no_provider_id_branch(self):
        source = inspect.getsource(animator_adapter)
        self.assertIsNone(self.BRANCH_RE.search(source), source)
        self.assertIn("run_manifest_job", source)
        self.assertIn("resolve_provider", source)

    def test_storyboard_routes_dispatch_generically(self):
        from studio.storyboard import routes as sb_routes

        source = inspect.getsource(sb_routes)
        self.assertIsNone(self.BRANCH_RE.search(source), source)
        self.assertIn("resolve_provider", source)
        self.assertIn("hub.create", source)

    def test_animator_routes_dispatch_generically(self):
        from studio.animator import animation_routes as anim_routes

        source = inspect.getsource(anim_routes)
        self.assertIsNone(self.BRANCH_RE.search(source), source)
        self.assertIn("resolve_provider", source)
        # B8: no direct import of a concrete provider package for generation.
        self.assertNotIn("from .providers.kie_ai import generate_image", source)
        self.assertNotIn("providers.kie_ai import generate_image", source)

    def test_shipped_ids_and_aliases_are_unchanged(self):
        sb = hub.registry("storyboard")
        an = hub.registry("animator")
        self.assertEqual(set(sb.list_ids()), set(STORYBOARD_PROVIDERS))
        self.assertEqual(set(an.list_ids()), set(ANIMATOR_PROVIDERS))
        self.assertEqual(sb.aliases(), STORYBOARD_ALIASES)
        self.assertEqual(an.aliases(), ANIMATOR_ALIASES)
        self.assertEqual(DOMAINS["storyboard"].default_provider, "gemini_ws")
        self.assertEqual(DOMAINS["animator"].default_provider, "grok_automa")


# -- fixture provider through the real adapter (no node edit) ---------------


class FixtureProviderThroughAdapterTests(unittest.TestCase):
    """A folder-only provider runs through storyboard.generate with no code edit."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sts_gate_fix_")
        self.addCleanup(_rmtree, self.tmp)

    def test_fixture_storyboard_provider_via_media_job_service(self):
        from studio.storyboard.providers.contract import StoryboardRequest
        from studio.shared.providers_common.invocation import build_invocation

        root = os.path.join(ROOT_DIR, "tests", "fixture_providers", "storyboard")
        shipped = DOMAINS["storyboard"]
        local = ProviderHub(catalog={
            "storyboard": DomainSpec(
                id="storyboard",
                label=shipped.label,
                package="tests.fixture_providers.storyboard",
                providers_base=root,
                default_provider="fixture_async",
                capability_vocabulary=shipped.capability_vocabulary,
                request_model=shipped.request_model,
                result_model=shipped.result_model,
            )
        })
        local.discover("storyboard")
        provider = local.create("storyboard", "fixture_async")
        out_dir = os.path.join(self.tmp, "out")
        os.makedirs(out_dir, exist_ok=True)
        request = StoryboardRequest.from_scenes(SCENES["scenes"])
        invocation = build_invocation(
            None,
            domain="storyboard",
            provider_id="fixture_async",
            project_id=PROJECT_ID,
            output_dir=out_dir,
            settings={"endpoint_url": "https://fixture.invalid"},
            options={},
        )
        service = MediaJobService(MediaJobStore(), sleeper=lambda _s: None)
        result = service.run(provider, request, invocation)
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(result.units), 2)
        self.assertTrue(result.artifact_refs)


# -- live gate documentation contract ---------------------------------------


class LiveGateDocumentationTests(unittest.TestCase):
    """Live providers stay gated; the README records who is blocked."""

    def test_live_suite_is_skipped_without_sts_live(self):
        source = Path(ROOT_DIR, "tests", "test_live_providers.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('STS_LIVE', source)
        self.assertIn("pytest.mark.live", source)
        self.assertIn("STS_LIVE_STORYBOARD", source)
        # Full Video pins the API-driven animator; grok_automa is not automatable.
        self.assertIn('provider"] = "kie_ai"', source)
        self.assertIn("grok_automa", source)

    def test_live_verification_readme_documents_blocked_providers(self):
        readme = Path(
            ROOT_DIR, "_dev", "loop-engineering", "live-verification", "README.md"
        ).read_text(encoding="utf-8")
        for needle in (
            "WaveSpeed",
            "grok_automa",
            "STS_LIVE",
            "Kie AI",
            "STS_LIVE_STORYBOARD",
        ):
            self.assertIn(needle, readme)


if __name__ == "__main__":
    unittest.main()
