"""Step 14.3 — Animator providers behind their interface.

Covers the four things the step promises:

  * `/api/animator/grabber/start` and `animator.generate` resolve and execute
    providers generically — no `provider_id == …` branch;
  * both shipped IDs, their defaults, their settings, and the artifacts they
    produce stay compatible;
  * an unavailable browser extension and an invalid API key are isolated
    health states and per-unit errors, never a whole-job failure with a leaked
    message;
  * every provider is exercised through a mocked transport.

Plus the audited selection gap this step exists to repair: `provider` defaulted
every request to `midjourney`/`grok_automa`, so the authoritative selected-
provider store was never consulted.
"""

from __future__ import annotations

import inspect
import json
import os
import tempfile
import unittest
from unittest import mock

from studio.animator import generation as anim_generation
from studio.animator import jobs as anim_jobs
from studio.animator import animation_routes as anim_routes
from studio.animator.providers.base import AnimatorProvider
from studio.animator.providers.contract import AnimatorRequest
from studio.shared.providers_common.hub import hub
from studio.shared.providers_common.invocation import build_invocation
from studio.shared.providers_common.jobs import FAILED, RUNNING, SUCCEEDED, JobHandle
from studio.workflows.adapters import animator as animator_adapter

PROJECT_ID = "pm_ABC123"
REAL_SUBMIT = anim_routes._submit
SHIPPED = ("grok_automa", "kie_ai")
LEGACY_ALIASES = {
    "grok": "grok_automa",
    "midjourney": "grok_automa",
    "kie-ai": "kie_ai",
}


def request_for(scenes=None, *, aspect_ratio="9:16", mode="video"):
    return AnimatorRequest.from_scenes(
        scenes or [{"index": 0, "prompt": "a lighthouse"}],
        aspect_ratio=aspect_ratio,
        mode=mode,
    )


def invocation_for(provider_id, *, settings=None, options=None):
    return build_invocation(
        None,
        domain="animator",
        provider_id=provider_id,
        project_id=PROJECT_ID,
        output_dir=anim_jobs.project_dir(PROJECT_ID),
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


class AnimatorCase(unittest.TestCase):
    """Every test writes its manifest into a private directory."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(_rmtree, self.tmp)
        patch = mock.patch.object(anim_jobs, "ANIMATOR_DIR", self.tmp)
        patch.start()
        self.addCleanup(patch.stop)
        # Clear any leftover in-memory jobs between tests.
        for key, _value in list(anim_jobs.grabber_jobs.items()):
            anim_jobs.grabber_jobs.pop(key)

    def provider_module(self, provider_id):
        instance = hub.get("animator", provider_id)
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


class AnimatorRequestTests(unittest.TestCase):
    def test_both_historical_scene_spellings_are_accepted(self):
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

    def test_mode_defaults_to_video_and_rejects_unknown_values(self):
        self.assertEqual(request_for(mode="").mode, "video")
        self.assertEqual(request_for(mode="image").mode, "image")
        self.assertEqual(request_for(mode="slideshow").mode, "video")

    def test_provider_settings_are_not_request_fields(self):
        """§32.5: quality/duration/auto_type/resolution are settings."""
        fields = set(AnimatorRequest.model_fields)
        self.assertEqual(fields, {"scenes", "aspect_ratio", "mode"})


# -- generic dispatch --------------------------------------------------------


class ProviderResolutionTests(unittest.TestCase):
    def test_every_legacy_spelling_resolves_to_its_canonical_provider(self):
        for legacy, canonical in LEGACY_ALIASES.items():
            with self.subTest(legacy=legacy):
                self.assertEqual(anim_routes.resolve_provider(legacy).id, canonical)

    def test_a_canonical_id_resolves_to_itself(self):
        for provider_id in SHIPPED:
            with self.subTest(provider=provider_id):
                self.assertEqual(
                    anim_routes.resolve_provider(provider_id).id, provider_id
                )

    def test_resolution_takes_the_first_candidate_that_exists(self):
        resolved = anim_routes.resolve_provider("", None, "nope", "kie-ai", "grok")
        self.assertEqual(resolved.id, "kie_ai")

    def test_no_candidate_resolves_to_nothing_rather_than_a_substitute(self):
        self.assertIsNone(anim_routes.resolve_provider("", None, "nope"))


class RouteDispatchTests(AnimatorCase):
    """The routes resolve and submit generically (P13–P16, P18–P20)."""

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
            anim_jobs.seed(project_id, request, provider_id=instance.id)
            return JobHandle(
                job_id=project_id, domain="animator",
                provider_id=instance.id, project_id=project_id,
            )

        patch = mock.patch.object(anim_routes, "_submit", record)
        patch.start()
        self.addCleanup(patch.stop)

    def post(self, path, body):
        from app import app

        with app.test_client() as client:
            return client.post(path, json=body)

    def start_body(self, **extra):
        return {
            "project_id": PROJECT_ID,
            "scenes": [{"scene": 0, "prompt": "a lighthouse"}],
            "aspect_ratio": "9:16",
            **extra,
        }

    def test_the_legacy_provider_field_is_honoured(self):
        for legacy, canonical in LEGACY_ALIASES.items():
            with self.subTest(legacy=legacy):
                self.submitted.clear()
                response = self.post(
                    "/api/animator/grabber/start", self.start_body(provider=legacy)
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.submitted[-1]["provider"], canonical)
                self.assertEqual(response.get_json()["provider"], canonical)

    def test_a_canonical_override_beats_the_legacy_field(self):
        response = self.post(
            "/api/animator/grabber/start",
            self.start_body(provider="grok", provider_override="kie_ai"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.submitted[-1]["provider"], "kie_ai")

    def test_the_saved_selection_is_used_when_the_request_names_nothing(self):
        """The audited gap: an absent provider used to hard-default to grok_automa."""
        with mock.patch.object(
            anim_routes, "_selected_provider", return_value="kie_ai"
        ):
            response = self.post("/api/animator/grabber/start", self.start_body())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.submitted[-1]["provider"], "kie_ai")

    def test_an_unknown_provider_falls_through_to_the_domain_default(self):
        with mock.patch.object(anim_routes, "_selected_provider", return_value=""):
            response = self.post(
                "/api/animator/grabber/start",
                self.start_body(provider="not-a-provider"),
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.submitted[-1]["provider"], "grok_automa")

    def test_the_start_envelope_old_callers_read_is_unchanged(self):
        response = self.post("/api/animator/grabber/start", self.start_body())
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["project_id"], PROJECT_ID)
        self.assertEqual(payload["scene_count"], 1)
        self.assertIn("grabber_id", payload)
        self.assertIn("provider", payload)

    def test_per_run_request_values_reach_the_provider_as_options(self):
        response = self.post(
            "/api/animator/grabber/start",
            self.start_body(
                provider="grok_automa",
                provider_options={
                    "mode": "image", "quality": "720p",
                    "duration": "10s", "auto_type": True,
                },
            ),
        )
        self.assertEqual(response.status_code, 200)
        options = self.submitted[-1]["options"]
        self.assertEqual(options["mode"], "image")
        self.assertEqual(options["quality"], "720p")
        self.assertEqual(options["duration"], "10s")
        self.assertIs(options["auto_type"], True)

    def test_flat_grok_keys_still_win_over_provider_options(self):
        response = self.post(
            "/api/animator/grabber/start",
            self.start_body(
                provider="grok_automa",
                grok_mode="video",
                provider_options={"mode": "image"},
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.submitted[-1]["options"]["mode"], "video")

    def test_a_provider_that_raises_answers_502_with_a_safe_message(self):
        class Boom:
            def submit(self, request, invocation):
                raise RuntimeError(
                    "POST https://kie.invalid/jobs?token=abc123xyz failed"
                )

        with mock.patch.object(anim_routes, "_submit", REAL_SUBMIT):
            with mock.patch.object(anim_routes.hub, "create", return_value=Boom()):
                response = self.post(
                    "/api/animator/grabber/start",
                    self.start_body(provider_override="kie_ai"),
                )

        self.assertEqual(response.status_code, 502)
        body = json.dumps(response.get_json())
        self.assertNotIn("abc123xyz", body)
        self.assertNotIn("kie.invalid", body)
        self.assertNotIn("Traceback", body)

    def test_a_request_with_no_usable_prompt_is_a_bad_request_not_a_500(self):
        response = self.post(
            "/api/animator/grabber/start",
            self.start_body(scenes=[{"scene": 0, "prompt": "   "}]),
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.submitted)


class SourceLevelDispatchTests(unittest.TestCase):
    """A branch is what makes the next provider silently do nothing."""

    def test_neither_the_routes_nor_the_adapter_name_a_provider(self):
        for module in (anim_routes, animator_adapter):
            source = inspect.getsource(module).lower()
            for provider_id in SHIPPED + tuple(LEGACY_ALIASES):
                with self.subTest(module=module.__name__, provider=provider_id):
                    self.assertNotIn(f'"{provider_id}"', source)
                    self.assertNotIn(f"'{provider_id}'", source)

    def test_the_direct_kie_import_is_gone(self):
        """B8 / contracts.md §8: always registry.get, never import."""
        source = inspect.getsource(anim_routes)
        self.assertNotIn("from .providers.kie_ai", source)
        self.assertNotIn("generate_image as kie_ai", source)
        self.assertNotIn("_kie_ai_generate_all", source)


# -- provider contract tests, mocked transports ------------------------------


class GrokAutomaProviderTests(AnimatorCase):
    def setUp(self):
        super().setUp()
        self.provider = hub.create("animator", "grok_automa")
        self.runtime = mock.Mock()
        self.runtime.is_extension_connected.return_value = True
        patch = mock.patch.object(self.provider, "_runtime", return_value=self.runtime)
        patch.start()
        self.addCleanup(patch.stop)

    def message(self):
        return self.runtime.queue_grabber_start.call_args[0][0]

    def test_it_implements_the_animator_interface(self):
        self.assertIsInstance(self.provider, AnimatorProvider)

    def test_submit_seeds_the_manifest_and_queues_the_job(self):
        handle = self.provider.submit(request_for(), invocation_for("grok_automa"))
        self.assertEqual(handle.job_id, PROJECT_ID)
        self.assertEqual(self.message()["type"], "GRABBER_START")
        self.assertEqual(
            self.message()["scenes"][0]["prompt"], "a lighthouse"
        )
        self.assertIsNotNone(anim_jobs.read(PROJECT_ID))

    def test_mode_quality_duration_come_from_its_own_settings(self):
        self.provider.submit(
            request_for(mode="image"),
            invocation_for(
                "grok_automa",
                settings={
                    "mode": "image", "quality": "720p",
                    "duration": "10s", "auto_type": True,
                },
            ),
        )
        self.assertEqual(self.message()["grokMode"], "image")
        self.assertEqual(self.message()["grokDuration"], "10s")
        self.assertIs(self.message()["autoType"], True)
        job = anim_jobs.read(PROJECT_ID)
        self.assertEqual(job["payload"]["grok_mode"], "image")
        self.assertEqual(job["payload"]["grok_quality"], "720p")

    def test_a_disconnected_extension_still_queues_the_job(self):
        self.runtime.is_extension_connected.return_value = False
        handle = self.provider.submit(request_for(), invocation_for("grok_automa"))
        self.assertEqual(handle.provider_id, "grok_automa")
        self.runtime.queue_grabber_start.assert_called_once()

    def test_poll_reports_the_manifest(self):
        invocation = invocation_for("grok_automa")
        self.provider.submit(
            request_for([{"index": 0, "prompt": "a"}, {"index": 1, "prompt": "b"}]),
            invocation,
        )
        self.assertEqual(self.provider.poll(PROJECT_ID, invocation).state, RUNNING)

        anim_jobs.mark_scene(
            PROJECT_ID, 0, "ready",
            local_files=[f"/output/animator/{PROJECT_ID}/0/clip.mp4"],
        )
        running = self.provider.poll(PROJECT_ID, invocation)
        self.assertEqual((running.state, running.ready, running.total), (RUNNING, 1, 2))

        anim_jobs.mark_scene(
            PROJECT_ID, 1, "ready",
            local_files=[f"/output/animator/{PROJECT_ID}/1/clip.mp4"],
        )
        done = self.provider.poll(PROJECT_ID, invocation)
        self.assertEqual(done.state, SUCCEEDED)

    def test_a_job_declared_done_with_a_pending_scene_settles_as_partial(self):
        invocation = invocation_for("grok_automa")
        self.provider.submit(
            request_for([{"index": 0, "prompt": "a"}, {"index": 1, "prompt": "b"}]),
            invocation,
        )
        anim_jobs.mark_scene(
            PROJECT_ID, 0, "ready",
            local_files=[f"/output/animator/{PROJECT_ID}/0/clip.mp4"],
        )
        anim_jobs.mark_done(PROJECT_ID)
        self.assertEqual(self.provider.poll(PROJECT_ID, invocation).state, "partial")

    def test_an_absent_extension_is_a_warning_not_a_failure(self):
        from studio.animator import routes as animator_routes

        module = self.provider_module("grok_automa")
        with mock.patch.object(animator_routes, "_ws_clients", []):
            unavailable = module.health_check({})
        with mock.patch.object(animator_routes, "_ws_clients", [object()]):
            available = module.health_check({})
        self.assertEqual(unavailable["status"], "warn")
        self.assertEqual(available["status"], "ok")


class KieAIProviderTests(AnimatorCase):
    def setUp(self):
        super().setUp()
        self.provider = hub.create("animator", "kie_ai")
        self.inline_threads("kie_ai")

    def test_it_implements_the_animator_interface(self):
        self.assertIsInstance(self.provider, AnimatorProvider)

    def test_submit_starts_a_batch_with_request_options_winning(self):
        captured = {}

        def capture(project_id, request, transport, **kwargs):
            captured.update(
                project_id=project_id, request=request,
                transport=transport, options=kwargs.get("options"),
            )

        with mock.patch.object(anim_generation, "run_batch", capture):
            handle = self.provider.submit(
                request_for(),
                invocation_for(
                    "kie_ai",
                    settings={"resolution": "2", "model": "saved-model", "api_key": "k"},
                    options={"resolution": "1", "model": "request-model"},
                ),
            )
        self.assertEqual(handle.provider_id, "kie_ai")
        self.assertEqual(captured["options"]["resolution"], "1")
        self.assertEqual(captured["options"]["model"], "request-model")
        self.assertNotIn("api_key", captured["options"])
        job = anim_jobs.read(PROJECT_ID)
        self.assertEqual(job["status"], "generating")
        self.assertNotIn("_kie_ai_options", job)

    def test_submit_without_a_key_never_starts_a_thread(self):
        module = self.provider_module("kie_ai")
        with mock.patch.object(module, "KIE_AI_API_KEY", ""), \
             mock.patch.object(module.threading, "Thread") as thread:
            with self.assertRaises(ValueError):
                self.provider.submit(request_for(), invocation_for("kie_ai"))
        self.assertFalse(thread.called)

    def test_batch_records_success_and_failure_with_safe_messages(self):
        calls = {"n": 0}

        def transport(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"url": "https://cdn.invalid/a.png", "all_urls": [
                    "https://cdn.invalid/a.png"
                ]}
            raise RuntimeError("kie failed at C:\\jobs\\kie.json token=secret")

        with mock.patch.object(
            anim_generation, "organize_grabber_assets",
            return_value=[f"/output/animator/{PROJECT_ID}/0/0.png"],
        ):
            self.provider.submit(
                request_for([
                    {"index": 0, "prompt": "a"},
                    {"index": 1, "prompt": "b"},
                ]),
                invocation_for("kie_ai", settings={"api_key": "fixture-key"}),
            )
            # Re-run the batch inline with the stub transport.
            anim_generation.run_batch(
                PROJECT_ID,
                request_for([
                    {"index": 0, "prompt": "a"},
                    {"index": 1, "prompt": "b"},
                ]),
                transport,
                options={"aspect_ratio": "9:16", "resolution": "1",
                         "output_format": "jpg", "model": "m"},
            )

        job = anim_jobs.read(PROJECT_ID)
        self.assertEqual(job["scene_statuses"]["0"]["status"], "ready")
        self.assertEqual(job["scene_statuses"]["1"]["status"], "error")
        error = job["scene_statuses"]["1"].get("error", "")
        self.assertNotIn("C:\\jobs", error)
        self.assertNotIn("secret", error)

    def test_poll_reports_the_manifest(self):
        invocation = invocation_for("kie_ai", settings={"api_key": "k"})
        with mock.patch.object(anim_generation, "run_batch", lambda *a, **k: None):
            self.provider.submit(
                request_for([{"index": 0, "prompt": "a"}, {"index": 1, "prompt": "b"}]),
                invocation,
            )
        anim_jobs.mark_scene(
            PROJECT_ID, 0, "ready",
            local_files=[f"/output/animator/{PROJECT_ID}/0/0.png"],
        )
        status = self.provider.poll(PROJECT_ID, invocation)
        self.assertEqual(status.state, RUNNING)
        self.assertEqual((status.ready, status.total), (1, 2))

    def test_an_invalid_key_classifies_as_auth_failed(self):
        err = anim_generation.classify(RuntimeError("401 unauthorized"))
        self.assertEqual(err.code, "PROVIDER_AUTH_FAILED")


class AdapterDispatchTests(AnimatorCase):
    def test_the_adapter_resolves_and_waits_without_a_provider_branch(self):
        """`animator.generate` constructs the provider and uses the media-job service."""
        submitted = []

        class FakeProvider:
            def submit(self, request, invocation):
                submitted.append((request, invocation))
                anim_jobs.seed(
                    invocation.project_id, request, provider_id="kie_ai",
                    status="done",
                )
                for scene in request.scenes:
                    anim_jobs.mark_scene(
                        invocation.project_id, scene.index, "ready",
                        local_files=[
                            f"/output/animator/{invocation.project_id}/{scene.index}/0.png"
                        ],
                    )
                anim_jobs.mark_done(invocation.project_id)
                return JobHandle(
                    job_id=invocation.project_id, domain="animator",
                    provider_id="kie_ai", project_id=invocation.project_id,
                )

            def poll(self, job_id, invocation):
                return anim_jobs.status(invocation.project_id or job_id, job_id)

            def cancel_job(self, job_id, invocation):
                return None

        class Ctx:
            project_id = PROJECT_ID
            execution_id = "ex_test"
            node_id = "n_anim"
            stage_artifact = None

            @staticmethod
            def stop_requested():
                return False

            @staticmethod
            def progress(message):
                pass

        with mock.patch.object(
            animator_adapter, "resolve_provider", return_value=FakeProvider()
        ), mock.patch.object(
            animator_adapter, "ANIMATOR_DIR", self.tmp
        ), mock.patch.object(
            animator_adapter, "_resolved_settings", return_value={}
        ):
            result = animator_adapter._step_assets(
                {"scenes": [
                    {"index": 0, "image_prompt": "a"},
                    {"index": 1, "image_prompt": "b"},
                ]},
                {"animator_provider_override": "kie_ai"},
                PROJECT_ID,
                Ctx(),
            )
        self.assertEqual(result["ready"], 2)
        self.assertEqual(result["provider"], "kie_ai")
        self.assertNotIn("scene_statuses", result)
        self.assertEqual(len(submitted), 1)

    def test_a_fixture_provider_executes_with_no_route_or_node_edit(self):
        """Done-when: a fixture Animator provider runs without UI/node changes."""
        from studio.shared.providers_common.domains import DOMAINS, DomainSpec
        from studio.shared.providers_common.hub import ProviderHub
        from studio.shared.providers_common.jobs import SUCCEEDED as JOB_SUCCEEDED
        from config import ROOT_DIR

        fixture_base = os.path.join(
            ROOT_DIR, "tests", "fixture_providers", "animator"
        )
        shipped = DOMAINS["animator"]
        spec = DomainSpec(
            id="animator",
            label=shipped.label,
            package="tests.fixture_providers.animator",
            providers_base=fixture_base,
            default_provider="fixture_async",
            capability_vocabulary=shipped.capability_vocabulary,
            request_model=shipped.request_model,
            result_model=shipped.result_model,
        )
        test_hub = ProviderHub(catalog={"animator": spec})
        test_hub.discover("animator")
        provider = test_hub.create("animator", "fixture_async")
        self.assertIsNotNone(provider)

        request = request_for([
            {"index": 0, "prompt": "a"},
            {"index": 1, "prompt": "b"},
        ])
        out_dir = os.path.join(self.tmp, "fixture-out")
        os.makedirs(out_dir, exist_ok=True)
        invocation = build_invocation(
            None,
            domain="animator",
            provider_id="fixture_async",
            project_id=PROJECT_ID,
            output_dir=out_dir,
            settings={"endpoint_url": "https://fixture.invalid"},
            options={},
        )
        # The same contract surface the node uses after generic dispatch —
        # no route, node, or UI edit required for a new provider package.
        handle = provider.submit(request, invocation)
        status = provider.poll(handle.job_id, invocation)
        status = provider.poll(handle.job_id, invocation)
        self.assertEqual(status.state, JOB_SUCCEEDED)
        self.assertEqual(len(status.units), 2)


if __name__ == "__main__":
    unittest.main()
