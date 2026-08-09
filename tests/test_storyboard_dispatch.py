"""Step 14.2 — Storyboard providers behind their interface.

Covers the four things the step promises:

  * `/api/storyboard/generate`, `/api/storyboard/grab`, and `storyboard.generate`
    resolve and execute providers generically — no `provider_id == …` branch;
  * the three shipped IDs, their defaults, their settings, and the artifacts
    they produce stay compatible;
  * an unavailable browser extension and an invalid API key are isolated health
    states and per-unit errors, never a whole-job failure with a leaked message;
  * every provider is exercised through a mocked transport.

Plus the audited defect this step exists to repair: the bulk route accepted a
`provider` field and discarded it, because the field was a read-only property
shadowing the posted value.
"""

from __future__ import annotations

import inspect
import json
import os
import tempfile
import unittest
from unittest import mock

from studio.shared.providers_common.hub import hub
from studio.shared.providers_common.invocation import build_invocation
from studio.shared.providers_common.jobs import FAILED, RUNNING, SUCCEEDED, JobHandle
from studio.storyboard import generation as sb_generation
from studio.storyboard import jobs as sb_jobs
from studio.storyboard import routes as sb_routes
from studio.storyboard.providers.base import StoryboardProvider
from studio.storyboard.providers.contract import StoryboardRequest
from studio.workflows.adapters import storyboard as storyboard_adapter

PROJECT_ID = "pm_ABC123"
# Captured before any test patches it, so the exception-boundary test can run
# the real implementation while the rest of the class stubs it out.
REAL_SUBMIT = sb_routes._submit
SHIPPED = ("gemini_ws", "wavespeed_webhook", "wavespeed_direct")
LEGACY_ALIASES = {
    "gemini": "gemini_ws",
    "webhook": "wavespeed_webhook",
    "direct": "wavespeed_direct",
}


def request_for(scenes=None, *, aspect_ratio="9:16", style=""):
    return StoryboardRequest.from_scenes(
        scenes or [{"index": 0, "prompt": "a lighthouse"}],
        aspect_ratio=aspect_ratio,
        style=style,
    )


def invocation_for(provider_id, *, settings=None, options=None):
    return build_invocation(
        None,
        domain="storyboard",
        provider_id=provider_id,
        project_id=PROJECT_ID,
        output_dir=sb_jobs.project_dir(PROJECT_ID),
        settings=settings or {},
        options=options or {},
    )


class InlineThreads:
    """`threading` stand-in so a provider's worker runs inline under test."""

    class Thread:
        def __init__(self, target=None, args=(), kwargs=None, **_ignored):
            self._target, self._args, self._kwargs = target, args, kwargs or {}

        def start(self):
            if self._target is not None:
                self._target(*self._args, **self._kwargs)


class StoryboardCase(unittest.TestCase):
    """Every test writes its manifest into a private directory."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(_rmtree, self.tmp)
        patch = mock.patch.object(sb_jobs, "STORYBOARD_DIR", self.tmp)
        patch.start()
        self.addCleanup(patch.stop)

    def provider_module(self, provider_id):
        instance = hub.get("storyboard", provider_id)
        self.assertIsNotNone(instance, f"{provider_id} is not registered")
        return instance.provider_module

    def inline_threads(self, provider_id):
        patch = mock.patch.object(
            self.provider_module(provider_id), "threading", InlineThreads
        )
        patch.start()
        self.addCleanup(patch.stop)


def _rmtree(path):
    import shutil

    shutil.rmtree(path, ignore_errors=True)


# -- the request contract ----------------------------------------------------


class StoryboardRequestTests(unittest.TestCase):
    def test_both_historical_scene_spellings_are_accepted(self):
        """The route emitted `scene`, the workflow adapter emitted `index`."""
        from_route = request_for([{"scene": 3, "prompt": "a"}])
        from_adapter = request_for([{"index": 3, "image_prompt": "a"}])
        self.assertEqual(from_route.indices(), [3])
        self.assertEqual(from_adapter.indices(), [3])
        self.assertEqual(from_route.legacy_scenes(), from_adapter.legacy_scenes())

    def test_scenes_without_a_prompt_are_dropped(self):
        request = request_for([
            {"index": 0, "image_prompt": "a"},
            {"index": 1, "image_prompt": "  "},
            {"index": 2},
        ])
        self.assertEqual(request.indices(), [0])

    def test_an_empty_request_is_rejected_rather_than_submitted(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            request_for([{"index": 0, "image_prompt": ""}])

    def test_the_aspect_ratio_defaults_without_silently_overriding(self):
        self.assertEqual(request_for(aspect_ratio="").aspect_ratio, "9:16")
        self.assertEqual(request_for(aspect_ratio="16:9").aspect_ratio, "16:9")

    def test_provider_settings_are_not_request_fields(self):
        """§32.4: `image_model`, `prompt_prefix`, and `auto_type` are settings."""
        fields = set(StoryboardRequest.model_fields)
        self.assertEqual(fields, {"scenes", "aspect_ratio", "style"})


# -- generic dispatch --------------------------------------------------------


class ProviderResolutionTests(unittest.TestCase):
    def test_every_legacy_spelling_resolves_to_its_canonical_provider(self):
        for legacy, canonical in LEGACY_ALIASES.items():
            with self.subTest(legacy=legacy):
                self.assertEqual(sb_routes.resolve_provider(legacy).id, canonical)

    def test_a_canonical_id_resolves_to_itself(self):
        for provider_id in SHIPPED:
            with self.subTest(provider=provider_id):
                self.assertEqual(sb_routes.resolve_provider(provider_id).id, provider_id)

    def test_resolution_takes_the_first_candidate_that_exists(self):
        resolved = sb_routes.resolve_provider("", None, "nope", "webhook", "gemini")
        self.assertEqual(resolved.id, "wavespeed_webhook")

    def test_no_candidate_resolves_to_nothing_rather_than_a_substitute(self):
        self.assertIsNone(sb_routes.resolve_provider("", None, "nope"))


class RouteDispatchTests(StoryboardCase):
    """The routes resolve and submit generically (P24, P25)."""

    def setUp(self):
        super().setUp()
        self.submitted = []

        def record(instance, request, project_id, options):
            self.submitted.append({
                "provider": instance.id,
                "request": request,
                "project_id": project_id,
                "options": options,
            })
            return JobHandle(job_id=project_id, domain="storyboard",
                             provider_id=instance.id, project_id=project_id)

        patch = mock.patch.object(sb_routes, "_submit", record)
        patch.start()
        self.addCleanup(patch.stop)

    def post(self, path, body):
        from app import app

        with app.test_client() as client:
            return client.post(path, json=body)

    def generate_body(self, **extra):
        return {
            "project_id": PROJECT_ID,
            "scenes": [{"scene": 0, "prompt": "a lighthouse"}],
            "aspect_ratio": "9:16",
            **extra,
        }

    def test_the_bulk_route_honours_its_legacy_provider_field(self):
        """The audited gap: the posted `provider` value was discarded.

        `provider` was a `@property` returning `provider_override or "webhook"`,
        so with `extra: allow` the posted value landed in the model's extras and
        was shadowed on every read. Both the Storyboard page and the pipeline
        send this field.
        """
        for legacy, canonical in LEGACY_ALIASES.items():
            with self.subTest(legacy=legacy):
                self.submitted.clear()
                response = self.post(
                    "/api/storyboard/generate", self.generate_body(provider=legacy)
                )
                self.assertEqual(response.status_code, 202)
                self.assertEqual(self.submitted[-1]["provider"], canonical)
                self.assertEqual(response.get_json()["provider"], canonical)

    def test_a_canonical_override_beats_the_legacy_field(self):
        response = self.post(
            "/api/storyboard/generate",
            self.generate_body(provider="gemini", provider_override="wavespeed_direct"),
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.submitted[-1]["provider"], "wavespeed_direct")

    def test_the_saved_selection_is_used_when_the_request_names_nothing(self):
        with mock.patch.object(
            sb_routes, "_selected_provider", return_value="wavespeed_direct"
        ):
            response = self.post("/api/storyboard/generate", self.generate_body())
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.submitted[-1]["provider"], "wavespeed_direct")

    def test_an_unknown_provider_falls_through_to_the_domain_default(self):
        with mock.patch.object(sb_routes, "_selected_provider", return_value=""):
            response = self.post(
                "/api/storyboard/generate", self.generate_body(provider="not-a-provider")
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.submitted[-1]["provider"], "gemini_ws")

    def test_the_bulk_envelope_old_callers_read_is_unchanged(self):
        response = self.post("/api/storyboard/generate", self.generate_body())
        payload = response.get_json()
        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["project_id"], PROJECT_ID)
        self.assertEqual(payload["total"], 1)

    def test_per_run_request_values_reach_the_provider_as_options(self):
        response = self.post(
            "/api/storyboard/generate",
            self.generate_body(
                provider="webhook",
                webhook_url="https://n8n.invalid/hook",
                image_model="flux-dev",
                auto_type=False,
            ),
        )
        self.assertEqual(response.status_code, 202)
        options = self.submitted[-1]["options"]
        self.assertEqual(options["webhook_url"], "https://n8n.invalid/hook")
        self.assertEqual(options["image_model"], "flux-dev")
        self.assertIs(options["auto_type"], False)

    def test_a_provider_that_raises_answers_502_with_a_safe_message(self):
        class Boom:
            def submit(self, request, invocation):
                raise RuntimeError("POST https://n8n.invalid/hook?token=abc123xyz failed")

        # Run the real `_submit` so its exception boundary is what is tested.
        with mock.patch.object(sb_routes, "_submit", REAL_SUBMIT):
            with mock.patch.object(sb_routes.hub, "create", return_value=Boom()):
                response = self.post("/api/storyboard/generate", self.generate_body())

        self.assertEqual(response.status_code, 502)
        body = json.dumps(response.get_json())
        self.assertNotIn("abc123xyz", body)
        self.assertNotIn("n8n.invalid", body)
        self.assertNotIn("Traceback", body)

    def test_a_request_with_no_usable_prompt_is_a_bad_request_not_a_500(self):
        response = self.post(
            "/api/storyboard/generate",
            self.generate_body(scenes=[{"scene": 0, "prompt": "   "}]),
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.submitted)

    def test_the_single_scene_route_dispatches_through_the_same_path(self):
        """`grab` branched on the legacy string `gemini` (P25)."""
        for legacy, canonical in LEGACY_ALIASES.items():
            with self.subTest(legacy=legacy):
                self.submitted.clear()
                response = self.post("/api/storyboard/grab", {
                    "project_id": PROJECT_ID,
                    "scene": 2,
                    "prompt": "a harbour",
                    "provider": legacy,
                })
                self.assertEqual(response.status_code, 202)
                payload = response.get_json()
                self.assertEqual(payload["status"], "generating")
                self.assertEqual(payload["scene"], 2)
                self.assertEqual(payload["provider"], canonical)
                self.assertEqual(self.submitted[-1]["request"].indices(), [2])

    def test_regenerating_one_scene_keeps_the_others_in_the_manifest(self):
        sb_jobs.seed(
            PROJECT_ID,
            request_for([{"index": 0, "prompt": "a"}, {"index": 1, "prompt": "b"}]),
        )
        sb_jobs.mark_scene(
            PROJECT_ID, 0, "ready", local_path="/output/storyboard/x/0/image.jpeg"
        )
        # `_submit` is stubbed, so emulate the seed a real provider performs.
        with mock.patch.object(
            sb_routes, "_submit",
            lambda instance, request, project_id, options: sb_jobs.seed(project_id, request),
        ):
            response = self.post("/api/storyboard/grab", {
                "project_id": PROJECT_ID, "scene": 1, "prompt": "b",
            })
        self.assertEqual(response.status_code, 202)
        scenes = sb_jobs.read(PROJECT_ID)["scene_statuses"]
        self.assertEqual(set(scenes), {"0", "1"})
        self.assertEqual(scenes["0"]["status"], "ready")


class SourceLevelDispatchTests(unittest.TestCase):
    """A branch is what makes the next provider silently do nothing."""

    def test_neither_the_routes_nor_the_adapter_name_a_provider(self):
        for module in (sb_routes, storyboard_adapter):
            source = inspect.getsource(module).lower()
            for provider_id in SHIPPED + tuple(LEGACY_ALIASES):
                with self.subTest(module=module.__name__, provider=provider_id):
                    self.assertNotIn(f'"{provider_id}"', source)
                    self.assertNotIn(f"'{provider_id}'", source)

    def test_the_transport_module_is_reachable_from_the_routes(self):
        """`threading` was referenced in two route bodies but never imported.

        Both non-extension paths raised `NameError` the moment they ran, which
        is every bulk generate and every webhook grab.
        """
        self.assertTrue(hasattr(sb_routes, "threading"))


# -- provider contract tests, mocked transports ------------------------------


class GeminiWsProviderTests(StoryboardCase):
    def setUp(self):
        super().setUp()
        self.provider = hub.create("storyboard", "gemini_ws")
        self.runtime = mock.Mock()
        self.runtime.is_extension_connected.return_value = True
        patch = mock.patch.object(self.provider, "_runtime", return_value=self.runtime)
        patch.start()
        self.addCleanup(patch.stop)

    def message(self):
        return self.runtime.queue_image_job.call_args[0][0]

    def test_it_implements_the_storyboard_interface(self):
        self.assertIsInstance(self.provider, StoryboardProvider)

    def test_submit_seeds_the_manifest_and_queues_the_job(self):
        handle = self.provider.submit(request_for(), invocation_for("gemini_ws"))
        self.assertEqual(handle.job_id, PROJECT_ID)
        self.assertEqual(
            handle.correlation, ("storyboard", "gemini_ws", PROJECT_ID, PROJECT_ID)
        )
        self.assertEqual(self.message()["type"], "IMAGE_JOB")
        self.assertEqual(self.message()["scenes"], [{"scene": 0, "prompt": "a lighthouse"}])
        self.assertIsNotNone(sb_jobs.read(PROJECT_ID))

    def test_it_uses_the_requested_aspect_ratio(self):
        """`add_job` hardcoded `16:9`, so a 9:16 node produced landscape frames."""
        self.provider.submit(request_for(aspect_ratio="9:16"), invocation_for("gemini_ws"))
        self.assertEqual(self.message()["aspectRatio"], "9:16")
        self.provider.submit(request_for(aspect_ratio="16:9"), invocation_for("gemini_ws"))
        self.assertEqual(self.message()["aspectRatio"], "16:9")

    def test_prompt_prefix_and_auto_type_come_from_its_own_settings(self):
        self.provider.submit(
            request_for(),
            invocation_for(
                "gemini_ws",
                settings={"prompt_prefix": "cinematic, ", "auto_type": False},
            ),
        )
        self.assertEqual(self.message()["scenes"][0]["prompt"], "cinematic, a lighthouse")
        self.assertIs(self.message()["autoType"], False)

    def test_a_disconnected_extension_still_queues_the_job(self):
        """Unavailable is a health state, not a submit failure."""
        self.runtime.is_extension_connected.return_value = False
        handle = self.provider.submit(request_for(), invocation_for("gemini_ws"))
        self.assertEqual(handle.provider_id, "gemini_ws")
        self.runtime.queue_image_job.assert_called_once()

    def test_poll_reports_the_manifest_instead_of_a_constant(self):
        """The v1 body always answered `submitted`, blinding the watchdog."""
        invocation = invocation_for("gemini_ws")
        self.provider.submit(
            request_for([{"index": 0, "prompt": "a"}, {"index": 1, "prompt": "b"}]),
            invocation,
        )
        self.assertEqual(self.provider.poll(PROJECT_ID, invocation).state, RUNNING)

        sb_jobs.mark_scene(PROJECT_ID, 0, "ready", local_path="/output/storyboard/x/0/i.jpeg")
        running = self.provider.poll(PROJECT_ID, invocation)
        self.assertEqual((running.state, running.ready, running.total), (RUNNING, 1, 2))

        sb_jobs.mark_scene(PROJECT_ID, 1, "ready", local_path="/output/storyboard/x/1/i.jpeg")
        done = self.provider.poll(PROJECT_ID, invocation)
        self.assertEqual(done.state, SUCCEEDED)
        self.assertEqual(len(done.units), 2)

    def test_a_job_declared_done_with_a_pending_scene_settles_as_partial(self):
        invocation = invocation_for("gemini_ws")
        self.provider.submit(
            request_for([{"index": 0, "prompt": "a"}, {"index": 1, "prompt": "b"}]),
            invocation,
        )
        sb_jobs.mark_scene(PROJECT_ID, 0, "ready", local_path="/output/storyboard/x/0/i.jpeg")
        sb_jobs.mark_done(PROJECT_ID)
        self.assertEqual(self.provider.poll(PROJECT_ID, invocation).state, "partial")

    def test_the_completion_marker_is_never_counted_as_a_scene(self):
        invocation = invocation_for("gemini_ws")
        self.provider.submit(request_for(), invocation)
        sb_jobs.mark_scene(PROJECT_ID, 0, "ready", local_path="/output/storyboard/x/0/i.jpeg")
        sb_jobs.mark_done(PROJECT_ID)
        status = self.provider.poll(PROJECT_ID, invocation)
        self.assertEqual((status.total, status.ready), (1, 1))

    def test_an_absent_extension_is_a_warning_not_a_failure(self):
        from studio.storyboard import gemini_ws

        module = self.provider_module("gemini_ws")
        with mock.patch.object(gemini_ws, "_ws_clients", []):
            unavailable = module.health_check({})
        with mock.patch.object(gemini_ws, "_ws_clients", [object()]):
            available = module.health_check({})
        self.assertEqual(unavailable["status"], "warn")
        self.assertEqual(available["status"], "ok")
        self.assertEqual(available["details"]["clients"], 1)


class WaveSpeedProviderTests(StoryboardCase):
    """Both cloud providers, differing only in the transport they choose."""

    def submit_capturing(self, provider_id, **invocation_kwargs):
        provider = hub.create("storyboard", provider_id)
        self.inline_threads(provider_id)
        captured = {}

        def capture(project_id, request, transport, **kwargs):
            captured.update(project_id=project_id, request=request, transport=transport)

        with mock.patch.object(sb_generation, "run_batch", capture):
            handle = provider.submit(
                request_for(), invocation_for(provider_id, **invocation_kwargs)
            )
        return handle, captured

    def test_the_webhook_provider_posts_to_the_configured_webhook(self):
        handle, captured = self.submit_capturing(
            "wavespeed_webhook", settings={"webhook_url": "https://n8n.invalid/hook"}
        )
        self.assertEqual(handle.provider_id, "wavespeed_webhook")
        with mock.patch.object(
            sb_generation, "call_webhook",
            return_value={"image_url": "https://cdn.test/a.png"},
        ) as call:
            url = captured["transport"]({"scene": 0, "prompt": "x"}, "9:16", PROJECT_ID)
        self.assertEqual(url, "https://cdn.test/a.png")
        self.assertEqual(call.call_args[0][0], "https://n8n.invalid/hook")

    def test_the_direct_provider_always_calls_the_api_directly(self):
        """With no model override the v1 path silently ran the webhook."""
        from studio.storyboard import wavespeed

        _handle, captured = self.submit_capturing("wavespeed_direct")
        with mock.patch.object(
            wavespeed, "generate_image", return_value="https://cdn.test/a.png"
        ) as generate:
            url = captured["transport"]({"scene": 0, "prompt": "x"}, "9:16", PROJECT_ID)
        self.assertEqual(url, "https://cdn.test/a.png")
        generate.assert_called_once()

    def test_a_malformed_webhook_response_is_a_safe_provider_error(self):
        transport = sb_generation.webhook_transport("https://n8n.invalid/hook")
        with mock.patch.object(sb_generation, "call_webhook", return_value={}):
            with self.assertRaises(ValueError):
                transport({"scene": 0, "prompt": "x"}, "9:16", PROJECT_ID)

    def test_an_invalid_key_becomes_an_isolated_non_retryable_unit_error(self):
        error = sb_generation.classify(RuntimeError("401 Unauthorized for /v3/predictions"))
        self.assertEqual(error.code, "PROVIDER_AUTH_FAILED")
        self.assertFalse(error.retryable)

    def test_a_transport_failure_never_leaks_the_original_text(self):
        """`storyboard.json` reaches the `images` port verbatim (§36 L2)."""
        leaky = RuntimeError("POST https://n8n.invalid/hook?token=abc123xyz failed")
        message = sb_generation.classify(leaky).message
        self.assertNotIn("abc123xyz", message)
        self.assertNotIn("n8n.invalid", message)

    def test_one_failed_scene_does_not_lose_the_rest_of_the_batch(self):
        request = request_for([
            {"index": 0, "prompt": "a"}, {"index": 1, "prompt": "b"},
        ])
        sb_jobs.seed(PROJECT_ID, request)

        def transport(scene, _aspect_ratio, _project_id):
            if scene["scene"] == 0:
                raise RuntimeError("401 Unauthorized")
            return "https://cdn.test/b.png"

        with mock.patch.object(sb_generation, "download_image", return_value=True):
            with mock.patch.object(sb_jobs, "generate_thumbnail", return_value=None):
                with mock.patch.object(sb_jobs, "_dimensions", return_value=None):
                    sb_generation.run_batch(PROJECT_ID, request, transport)

        scenes = sb_jobs.read(PROJECT_ID)["scene_statuses"]
        self.assertEqual(scenes["0"]["status"], "error")
        self.assertEqual(scenes["1"]["status"], "ready")
        self.assertNotIn("401", scenes["0"]["error"])

    def test_a_cancelled_batch_stops_before_the_next_scene(self):
        request = request_for([
            {"index": 0, "prompt": "a"}, {"index": 1, "prompt": "b"},
        ])
        sb_jobs.seed(PROJECT_ID, request)
        calls = []

        with mock.patch.object(sb_generation, "download_image", return_value=True):
            with mock.patch.object(sb_jobs, "generate_thumbnail", return_value=None):
                with mock.patch.object(sb_jobs, "_dimensions", return_value=None):
                    sb_generation.run_batch(
                        PROJECT_ID, request,
                        lambda scene, *_: calls.append(scene["scene"]) or "https://c/a.png",
                        is_cancelled=lambda: len(calls) >= 1,
                    )
        self.assertEqual(calls, [0])

    def test_a_missing_key_is_a_warning_rather_than_a_health_failure(self):
        module = self.provider_module("wavespeed_direct")
        with mock.patch.object(module, "WAVESPEED_API_KEY", ""):
            self.assertEqual(module.health_check({})["status"], "warn")
            self.assertEqual(module.validate_settings({})[0]["field"], "api_key")
        self.assertEqual(module.health_check({"api_key": "k"})["status"], "ok")

    def test_a_rejected_webhook_credential_is_reported_as_a_failure(self):
        module = self.provider_module("wavespeed_webhook")
        with mock.patch("requests.get", return_value=mock.Mock(status_code=401)):
            health = module.health_check({"webhook_url": "https://n8n.invalid/hook"})
        self.assertEqual(health["status"], "fail")
        self.assertIn("credentials", health["message"])

    def test_a_health_failure_is_sanitized_before_it_is_served(self):
        instance = hub.get("storyboard", "wavespeed_webhook")
        with mock.patch(
            "requests.get",
            side_effect=RuntimeError("connect failed to /home/user/.n8n/config token=abc123xyz"),
        ):
            health = instance.health_check({"webhook_url": "https://n8n.invalid/hook"})
        self.assertEqual(health.status, "fail")
        self.assertNotIn("/home/user", health.message)
        self.assertNotIn("abc123xyz", health.message)


# -- normalized per-scene metadata -------------------------------------------


class SceneMetadataTests(StoryboardCase):
    """Every provider's frames carry the same metadata (§32.4)."""

    def test_a_produced_frame_records_path_thumbnail_and_size(self):
        sb_jobs.seed(PROJECT_ID, request_for())
        path = sb_jobs.prepare_scene_file(PROJECT_ID, 0, ".png")
        with open(path, "wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\n")

        with mock.patch.object(
            sb_jobs, "generate_thumbnail",
            return_value=f"/api/thumbnails/{PROJECT_ID}/storyboard/0.jpg",
        ):
            with mock.patch.object(sb_jobs, "_dimensions", return_value=(1080, 1920)):
                entry = sb_jobs.record_ready(
                    PROJECT_ID, 0, path, image_url="https://cdn.test/a.png"
                )

        self.assertEqual(entry["local_path"], f"/output/storyboard/{PROJECT_ID}/0/image.png")
        self.assertEqual(entry["thumb_path"], f"/api/thumbnails/{PROJECT_ID}/storyboard/0.jpg")
        self.assertEqual((entry["width"], entry["height"]), (1080, 1920))
        stored = sb_jobs.read(PROJECT_ID)["scene_statuses"]["0"]
        self.assertEqual(stored["status"], "ready")
        self.assertEqual(stored["thumb_path"], entry["thumb_path"])

    def test_the_watermark_pass_runs_before_the_thumbnail_is_cut(self):
        """The extension path generated no thumbnail at all, so a cleaned frame
        and a watermarked thumbnail could disagree."""
        sb_jobs.seed(PROJECT_ID, request_for())
        path = sb_jobs.prepare_scene_file(PROJECT_ID, 0, ".png")
        with open(path, "wb") as handle:
            handle.write(b"\x89PNG\r\n\x1a\n")
        order = []

        with mock.patch.object(
            sb_jobs, "_remove_watermark", side_effect=lambda p: order.append("watermark")
        ):
            with mock.patch.object(
                sb_jobs, "generate_thumbnail",
                side_effect=lambda *a: order.append("thumbnail"),
            ):
                with mock.patch.object(sb_jobs, "_dimensions", return_value=None):
                    sb_jobs.record_ready(PROJECT_ID, 0, path, remove_watermark=True)

        self.assertEqual(order, ["watermark", "thumbnail"])

    def test_regenerating_a_frame_keeps_the_previous_version(self):
        sb_jobs.seed(PROJECT_ID, request_for())
        first = sb_jobs.prepare_scene_file(PROJECT_ID, 0, ".png")
        with open(first, "wb") as handle:
            handle.write(b"one")
        second = sb_jobs.prepare_scene_file(PROJECT_ID, 0, ".png")
        with open(second, "wb") as handle:
            handle.write(b"two")

        directory = sb_jobs.scene_dir(PROJECT_ID, 0)
        self.assertEqual(
            sorted(os.listdir(directory)), ["image.png", "image_v1.png"]
        )

    def test_a_failed_frame_records_a_message_without_the_raw_exception(self):
        sb_jobs.seed(PROJECT_ID, request_for())
        sb_jobs.record_error(PROJECT_ID, 0, "The image service failed")
        entry = sb_jobs.read(PROJECT_ID)["scene_statuses"]["0"]
        self.assertEqual(entry["status"], "error")
        self.assertEqual(entry["error"], "The image service failed")

    def test_the_manifest_keeps_the_shape_the_status_route_reads(self):
        sb_jobs.seed(
            PROJECT_ID,
            request_for([{"index": 0, "prompt": "a"}, {"index": 1, "prompt": "b"}]),
            provider_id="wavespeed_webhook",
        )
        job = sb_jobs.read(PROJECT_ID)
        self.assertEqual(
            set(job) >= {
                "project_id", "status", "total", "ready", "errors",
                "aspect_ratio", "created_at", "completed_at", "scene_statuses",
            },
            True,
        )
        self.assertEqual(job["total"], 2)
        self.assertEqual(set(job["scene_statuses"]), {"0", "1"})

    def test_the_manifest_is_written_atomically(self):
        """Three of the four historical writers used bare `open().write()`."""
        source = inspect.getsource(sb_jobs)
        self.assertIn("safe_json_write", source)
        self.assertNotIn("json.dump(", source)


# -- the workflow node -------------------------------------------------------


class AdapterDispatchTests(StoryboardCase):
    def test_the_adapter_hands_the_real_provider_to_the_shared_service(self):
        seen = {}

        def run(**kwargs):
            seen.update(kwargs)
            return {"total": 1, "ready": 1, "errors": 0, "scene_statuses": {}}

        with mock.patch.object(storyboard_adapter, "run_manifest_job", run):
            storyboard_adapter._step_storyboard(
                {"scenes": [{"index": 0, "image_prompt": "a lighthouse"}]},
                {"storyboard_provider_override": "wavespeed_webhook"},
                PROJECT_ID,
                None,
            )

        self.assertEqual(seen["provider"], "wavespeed_webhook")
        self.assertIsInstance(seen["request"], StoryboardRequest)
        self.assertIsNotNone(seen["job_provider"])
        self.assertTrue(hasattr(seen["job_provider"], "submit"))
        self.assertTrue(hasattr(seen["job_provider"], "poll"))

    def test_a_legacy_alias_in_the_node_config_resolves_to_the_canonical_id(self):
        seen = {}

        def run(**kwargs):
            seen.update(kwargs)
            return {"total": 1, "ready": 1, "errors": 0, "scene_statuses": {}}

        with mock.patch.object(storyboard_adapter, "run_manifest_job", run):
            storyboard_adapter._step_storyboard(
                {"scenes": [{"index": 0, "image_prompt": "a"}]},
                {"storyboard_provider_override": "gemini"},
                PROJECT_ID,
                None,
            )
        self.assertEqual(seen["provider"], "gemini_ws")

    def test_scenes_without_prompts_fail_before_any_provider_is_built(self):
        from studio.workflows.adapters.common import AdapterError

        with self.assertRaises(AdapterError) as raised:
            storyboard_adapter._step_storyboard(
                {"scenes": [{"index": 0}]}, {}, PROJECT_ID, None
            )
        self.assertEqual(raised.exception.code, "SCENES_EMPTY")


# -- a fourth provider, with no node, adapter, or route edit -----------------


class FixtureProviderTests(StoryboardCase):
    """A provider the shipped code has never heard of runs end to end."""

    def local_hub(self):
        from pathlib import Path

        from studio.shared.providers_common.domains import DOMAINS, DomainSpec
        from studio.shared.providers_common.hub import ProviderHub

        root = Path(__file__).resolve().parent / "fixture_providers" / "storyboard"
        self.assertTrue(root.is_dir())
        original = DOMAINS["storyboard"]
        spec = DomainSpec(
            id=original.id,
            label=original.label,
            package=original.package,
            providers_base=str(root),
            default_provider="fixture_async",
            capability_vocabulary=original.capability_vocabulary,
            legacy_selection_key=original.legacy_selection_key,
            request_model=original.request_model,
            result_model=original.result_model,
        )
        local = ProviderHub(catalog={"storyboard": spec})
        local.discover("storyboard")
        return local

    def test_a_fixture_provider_satisfies_the_same_interface(self):
        local = self.local_hub()
        instance = local.get("storyboard", "fixture_async")
        self.assertIsNotNone(instance)
        provider = local.create("storyboard", "fixture_async")
        for method in ("submit", "poll", "cancel_job"):
            self.assertTrue(callable(getattr(provider, method)))

    def test_it_runs_through_the_shared_service_with_no_adapter_edit(self):
        from studio.shared.providers_common import results
        from studio.shared.providers_common.media_jobs import MediaJobService, MediaJobStore

        local = self.local_hub()
        provider = local.create("storyboard", "fixture_async")
        invocation = invocation_for("fixture_async", options={"unit_count": 2})
        os.makedirs(invocation.output_dir, exist_ok=True)

        service = MediaJobService(MediaJobStore(), sleeper=lambda _seconds: None)
        with mock.patch.object(results, "OUTPUT_DIR", self.tmp):
            result = service.run(
                provider, {"units": [{"index": 0}, {"index": 1}]}, invocation
            )

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(result.units), 2)
        self.assertTrue(result.artifact_refs)


# -- compatibility -----------------------------------------------------------


class CompatibilityTests(unittest.TestCase):
    def test_the_three_shipped_ids_and_their_aliases_are_unchanged(self):
        registry = hub.registry("storyboard")
        self.assertEqual(set(registry.list_ids()), set(SHIPPED))
        self.assertEqual(registry.aliases(), LEGACY_ALIASES)

    def test_the_domain_default_is_unchanged(self):
        from studio.shared.providers_common.domains import DOMAINS

        self.assertEqual(DOMAINS["storyboard"].default_provider, "gemini_ws")

    def test_every_shipped_provider_declares_contract_v2(self):
        for provider_id in SHIPPED:
            with self.subTest(provider=provider_id):
                instance = hub.get("storyboard", provider_id)
                self.assertEqual(instance.contract_version, 2)
                self.assertTrue(instance.capabilities.get("async_job"))

    def test_the_settings_keys_operators_have_saved_still_exist(self):
        expected = {
            "gemini_ws": {"auto_type", "prompt_prefix"},
            "wavespeed_webhook": {"webhook_url", "image_model"},
            "wavespeed_direct": {"api_key", "image_model"},
        }
        for provider_id, keys in expected.items():
            with self.subTest(provider=provider_id):
                schema = hub.get("storyboard", provider_id).settings_schema()
                self.assertEqual(set(schema["properties"]) >= keys, True)

    def test_the_extension_provider_publishes_the_url_the_pipeline_opened(self):
        instance = hub.get("storyboard", "gemini_ws")
        self.assertEqual(instance.manifest.open_url, "https://gemini.google.com/app")

    def test_the_pipeline_reads_that_url_from_the_manifest(self):
        from studio.pipeline.routes import _provider_open_url

        self.assertEqual(
            _provider_open_url("storyboard", "gemini"), "https://gemini.google.com/app"
        )
        self.assertIsNone(_provider_open_url("storyboard", "wavespeed_webhook"))
        self.assertIsNone(_provider_open_url("storyboard", ""))

    def test_the_pipeline_no_longer_translates_ids_to_legacy_names(self):
        from studio.pipeline import services

        source = inspect.getsource(services)
        self.assertNotIn("id_to_legacy = {\"gemini_ws\"", source)


if __name__ == "__main__":
    unittest.main()
