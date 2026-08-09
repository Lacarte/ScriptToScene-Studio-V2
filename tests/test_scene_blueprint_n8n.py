"""Step 13.4 — AI scene blueprint as the `n8n` scene_blueprint provider."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from studio.build_scene_blueprints.providers.contract import (
    SceneBlueprintRequest,
    SceneBlueprintResultPayload,
)
from studio.build_scene_blueprints.providers.n8n import provider as n8n_mod
from studio.build_scene_blueprints.routes import scenes_bp
from studio.build_scene_blueprints.service import SceneServiceError
from studio.shared.providers_common import fixtures as provider_fixtures
from studio.shared.providers_common import legacy
from studio.shared.providers_common.errors import (
    PROVIDER_REQUEST_INVALID,
    PROVIDER_RESPONSE_MALFORMED,
    PROVIDER_TIMEOUT,
    PROVIDER_TRANSPORT_FAILED,
    ProviderError,
    is_retryable,
)
from studio.shared.providers_common.hub import hub
from studio.shared.providers_common.results import coerce_result, validate_egress


def _segments_from_request(request: dict) -> dict:
    return {
        "segments": list(request.get("segments") or []),
        "metadata": {},
    }


def _configuration_from_request(request: dict) -> dict:
    return {
        "text": request.get("script") or "",
        "style": request.get("style") or "cinematic",
        "style_prompt": request.get("style_notes") or "",
        "story_tone": request.get("tone") or "",
        "aspect_ratio": request.get("aspect_ratio") or "9:16",
        "webhook_url": "https://example.com/webhook/scene-blueprint",
    }


class N8nProviderRegistrationTests(unittest.TestCase):
    def test_provider_is_registered_with_builtin_alias(self):
        hub.discover("scene_blueprint")
        instance = hub.get("scene_blueprint", "n8n")
        self.assertIsNotNone(instance)
        self.assertEqual(instance.id, "n8n")
        self.assertIn("builtin", instance.manifest.aliases)
        self.assertTrue(instance.manifest.capabilities.get("chaptering"))
        self.assertTrue(instance.manifest.capabilities.get("coherence_scoring"))
        self.assertTrue(instance.manifest.capabilities.get("sfx_report"))

        aliased = hub.get("scene_blueprint", "builtin")
        self.assertIsNotNone(aliased)
        self.assertEqual(aliased.id, "n8n")

        created = hub.create("scene_blueprint", "builtin")
        self.assertEqual(type(created).__name__, "N8nSceneBlueprintProvider")
        self.assertTrue(callable(getattr(created, "generate", None)))

    def test_domain_default_is_n8n(self):
        from studio.shared.providers_common.domains import DOMAINS

        self.assertEqual(DOMAINS["scene_blueprint"].default_provider, "n8n")
        self.assertEqual(
            DOMAINS["scene_blueprint"].request_model,
            "studio.build_scene_blueprints.providers.contract:SceneBlueprintRequest",
        )
        self.assertEqual(
            DOMAINS["scene_blueprint"].result_model,
            "studio.build_scene_blueprints.providers.contract:SceneBlueprintResultPayload",
        )

    def test_settings_schema_owns_webhook_url(self):
        instance = hub.get("scene_blueprint", "n8n")
        schema = instance.settings_schema()
        self.assertIn("webhook_url", schema["properties"])
        self.assertEqual(
            instance.manifest.environment.get("webhook_url"), "N8N_WEBHOOK_URL"
        )


class SceneContractTests(unittest.TestCase):
    def test_request_rejects_unknown_keys(self):
        with self.assertRaises(Exception):
            SceneBlueprintRequest.model_validate({"style": "cinematic", "extra": 1})

    def test_request_maps_legacy_configuration_aliases(self):
        req = SceneBlueprintRequest.from_configuration(
            {
                "style_prompt": "custom notes",
                "story_tone": "dark",
                "text": "hello world",
                "style": "cinematic",
            },
            segments=[{"words": "one"}, {"words": "two"}],
        )
        self.assertEqual(req.script, "hello world")
        self.assertEqual(req.style_notes, "custom notes")
        self.assertEqual(req.tone, "dark")
        self.assertEqual(len(req.segments), 2)
        self.assertEqual(req.segments[0].index, 0)

    def test_result_payload_requires_scenes(self):
        with self.assertRaises(Exception):
            SceneBlueprintResultPayload(
                scenes=[],
                style_spec={},
                style_prompt="",
                analysis={},
            )


class N8nGenerateTests(unittest.TestCase):
    def setUp(self):
        self.provider = n8n_mod.create()
        self.raw = provider_fixtures.load_fixture(
            "scene_blueprint", "n8n", "raw_response.json"
        )
        self.request = provider_fixtures.load_fixture(
            "scene_blueprint", "n8n", "request.json"
        )

    def test_fixture_backed_generate_writes_scenes_and_standard_payload(self):
        def fake_webhook(url, payload, *, timeout=180, label="Webhook"):
            self.assertIn("system_prompt", payload)
            self.assertIn("segments", payload)
            return dict(self.raw)

        with tempfile.TemporaryDirectory() as tmp:
            scenes_dir = Path(tmp) / "scenes"
            with patch("studio.build_scene_blueprints.service.SCENES_DIR", str(scenes_dir)):
                with patch(
                    "studio.build_scene_blueprints.service.is_safe_webhook_url",
                    return_value=True,
                ):
                    result = self.provider.generate(
                        _segments_from_request(self.request),
                        _configuration_from_request(self.request),
                        project_id="pm_SAMPLE",
                        webhook_caller=fake_webhook,
                    )

            path = Path(result["path"])
            self.assertTrue(path.is_file())
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["project_id"], "pm_SAMPLE")
            self.assertEqual(len(document["scenes"]), 5)
            self.assertTrue(document["scenes"][0].get("image_prompt"))
            self.assertEqual(document["provider"], "n8n")
            self.assertIn("coherence_score", document)
            self.assertIn("sfx_report", document)
            self.assertIn("scene_blueprints", document)
            self.assertIn("style_spec", document)

            payload = SceneBlueprintResultPayload.from_mapping(document)
            self.assertEqual(len(payload.scenes), 5)
            self.assertEqual(result["provider"], "n8n")

    def test_invoke_returns_standard_envelope(self):
        from studio.shared.providers_common.invocation import (
            CancellationToken,
            ProviderInvocation,
        )

        def fake_webhook(url, payload, *, timeout=180, label="Webhook"):
            return dict(self.raw)

        request = SceneBlueprintRequest.from_configuration(
            _configuration_from_request(self.request),
            segments=self.request["segments"],
            script=self.request["script"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            scenes_dir = output_dir / "scenes"
            with patch("studio.build_scene_blueprints.service.SCENES_DIR", str(scenes_dir)):
                with patch(
                    "studio.build_scene_blueprints.service.is_safe_webhook_url",
                    return_value=True,
                ):
                    with patch("config.OUTPUT_DIR", str(output_dir)):
                        with patch(
                            "studio.shared.providers_common.results.OUTPUT_DIR",
                            str(output_dir),
                        ):
                            original = self.provider.generate

                            def _generate(segments, configuration, *, project_id):
                                return original(
                                    segments,
                                    configuration,
                                    project_id=project_id,
                                    webhook_caller=fake_webhook,
                                )

                            with patch.object(
                                self.provider, "generate", side_effect=_generate
                            ):
                                inv = ProviderInvocation(
                                    domain="scene_blueprint",
                                    provider_id="n8n",
                                    project_id="pm_SAMPLE",
                                    output_dir=str(output_dir),
                                    cancel=CancellationToken(),
                                )
                                result = self.provider.invoke(request, inv)

        payload_data = {
            k: v for k, v in result.payload.items() if k != "document_ref"
        }
        payload = SceneBlueprintResultPayload.model_validate(payload_data)
        self.assertEqual(len(payload.scenes), 5)
        self.assertIn("scenes/", result.artifact_refs[0])


class N8nErrorMappingTests(unittest.TestCase):
    def setUp(self):
        self.provider = n8n_mod.create()
        self.segments = {
            "segments": [
                {"index": 0, "words": "one"},
                {"index": 1, "words": "two"},
            ]
        }
        self.config = {
            "text": "one two",
            "style": "cinematic",
            "webhook_url": "https://example.com/webhook/scene-blueprint",
        }

    def test_empty_scenes_is_response_malformed_and_retryable(self):
        def empty_webhook(url, payload, *, timeout=180, label="Webhook"):
            return {"scenes": []}

        with patch(
            "studio.build_scene_blueprints.service.is_safe_webhook_url", return_value=True
        ):
            with self.assertRaises(ProviderError) as ctx:
                self.provider.generate(
                    self.segments,
                    self.config,
                    project_id="pm_SAMPLE",
                    webhook_caller=empty_webhook,
                )
        err = ctx.exception
        self.assertEqual(err.code, PROVIDER_RESPONSE_MALFORMED)
        self.assertTrue(err.retryable)
        self.assertTrue(is_retryable(err.code))

    def test_unsafe_webhook_is_request_invalid_and_not_retryable(self):
        with patch(
            "studio.build_scene_blueprints.service.is_safe_webhook_url", return_value=False
        ):
            with self.assertRaises(ProviderError) as ctx:
                self.provider.generate(
                    self.segments,
                    {
                        "text": "one two",
                        "style": "cinematic",
                        "webhook_url": "http://169.254.169.254/",
                    },
                    project_id="pm_SAMPLE",
                )
        err = ctx.exception
        self.assertEqual(err.code, PROVIDER_REQUEST_INVALID)
        self.assertFalse(err.retryable)

    def test_timeout_is_retryable(self):
        import requests

        def boom(url, payload, *, timeout=180, label="Webhook"):
            raise requests.Timeout("timed out")

        with patch(
            "studio.build_scene_blueprints.service.is_safe_webhook_url", return_value=True
        ):
            with self.assertRaises(ProviderError) as ctx:
                self.provider.generate(
                    self.segments,
                    self.config,
                    project_id="pm_SAMPLE",
                    webhook_caller=boom,
                )
        self.assertEqual(ctx.exception.code, PROVIDER_TIMEOUT)
        self.assertTrue(ctx.exception.retryable)

    def test_transport_runtime_error_does_not_leak_body(self):
        def boom(url, payload, *, timeout=180, label="Webhook"):
            raise RuntimeError("Scene webhook returned 502: sk-secret-body-fragment")

        with patch(
            "studio.build_scene_blueprints.service.is_safe_webhook_url", return_value=True
        ):
            with self.assertRaises(ProviderError) as ctx:
                self.provider.generate(
                    self.segments,
                    self.config,
                    project_id="pm_SAMPLE",
                    webhook_caller=boom,
                )
        err = ctx.exception
        self.assertEqual(err.code, PROVIDER_TRANSPORT_FAILED)
        self.assertTrue(err.retryable)
        self.assertNotIn("sk-secret", err.message)
        self.assertNotIn("502", err.message)

    def test_service_error_mapping_table_covers_known_codes(self):
        for code, expected in (
            ("SCENES_WEBHOOK_UNSAFE", PROVIDER_REQUEST_INVALID),
            ("SCENES_RESPONSE_MALFORMED", PROVIDER_RESPONSE_MALFORMED),
            ("SCENES_SEGMENTS_EMPTY", PROVIDER_REQUEST_INVALID),
        ):
            mapped = n8n_mod.N8nSceneBlueprintProvider._map_service_error(
                SceneServiceError(code, "internal detail that must not leak")
            )
            self.assertEqual(mapped.code, expected)
            self.assertNotIn("internal detail", mapped.message)


class N8nFixtureTests(unittest.TestCase):
    def test_fixture_matches_legacy_adapter_and_passes_egress(self):
        raw = provider_fixtures.load_fixture(
            "scene_blueprint", "n8n", "raw_response.json"
        )
        expected = provider_fixtures.load_fixture(
            "scene_blueprint", "n8n", "expected_result.json"
        )
        for name in provider_fixtures.FIXTURE_FILES:
            value = provider_fixtures.load_fixture("scene_blueprint", "n8n", name)
            issues = provider_fixtures.validate_sanitation(value)
            self.assertEqual(issues, [], msg=f"{name}: {issues}")

        built = legacy.scenes_document_to_result(
            {
                "scenes": list(raw.get("scenes") or []),
                "analysis": dict(raw.get("analysis") or {}),
                "style_spec": {"id": "cinematic", "label": "Cinematic"},
                "style_prompt": "cinematic realistic",
                "coherence_score": 0.92,
                "coherence_warnings": [],
                "coherence_metrics": {"role_mismatches": 0},
                "sfx_report": {
                    "hint_count": 0,
                    "hint_max": 3,
                    "hint_min": 0,
                    "dropped": 0,
                },
                "total_duration": 12.5,
                "style": "cinematic",
                "scene_blueprints": [],
                "provider": "n8n",
                "generation_time": 2.5,
                "timestamp": "2026-01-01T00:00:00+00:00",
            },
            document_ref="scenes/pm_SAMPLE/scenes.json",
            provider_id="n8n",
            provider_version="1.0.0",
        )
        coerced = coerce_result(
            built,
            domain="scene_blueprint",
            provider_id="n8n",
            provider_version="1.0.0",
        )
        self.assertEqual(coerced.payload, expected["payload"])
        self.assertEqual(coerced.artifact_refs, expected["artifact_refs"])
        validate_egress(coerced.to_dict())


class ScenesAdapterN8nTests(unittest.TestCase):
    def test_scenes_adapter_runs_n8n_without_importing_service(self):
        import inspect

        from studio.workflows.adapters import scenes as scenes_adapter
        from studio.workflows.adapters.common import AdapterContext

        source = inspect.getsource(scenes_adapter)
        self.assertNotIn("studio.build_scene_blueprints.service", source)
        self.assertNotIn("generate_scenes", source)
        self.assertNotIn("_step_scenes", source)
        self.assertNotIn("SceneServiceError", source)

        raw = provider_fixtures.load_fixture(
            "scene_blueprint", "n8n", "raw_response.json"
        )
        request = provider_fixtures.load_fixture(
            "scene_blueprint", "n8n", "request.json"
        )

        def fake_webhook(url, payload, *, timeout=180, label="Webhook"):
            return dict(raw)

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            scenes_dir = output_dir / "scenes"
            with patch("studio.build_scene_blueprints.service.SCENES_DIR", str(scenes_dir)):
                with patch(
                    "studio.workflows.adapters.common.OUTPUT_DIR", str(output_dir)
                ):
                    with patch(
                        "studio.build_scene_blueprints.service.is_safe_webhook_url",
                        return_value=True,
                    ):
                        with patch(
                            "studio.build_scene_blueprints.service.call_webhook",
                            side_effect=fake_webhook,
                        ):
                            outputs = scenes_adapter.blueprint(
                                inputs={
                                    "segments": _segments_from_request(request),
                                    "script": request["script"],
                                },
                                config={
                                    "provider_id": "n8n",
                                    "style": "cinematic",
                                    "story_tone": "mysterious",
                                    "webhook_url": (
                                        "https://example.com/webhook/scene-blueprint"
                                    ),
                                },
                                context=AdapterContext(project_id="pm_SAMPLE"),
                            )
        self.assertIn("scenes", outputs)
        self.assertEqual(len(outputs["scenes"]["scenes"]), 5)
        self.assertEqual(outputs["scenes"]["provider"], "n8n")
        self.assertIn("image_prompts", outputs)
        self.assertEqual(
            outputs["scenes"]["artifact_refs"], ["scenes/pm_SAMPLE/scenes.json"]
        )

    def test_scenes_adapter_resolves_builtin_alias(self):
        from studio.workflows.adapters.common import AdapterContext
        from studio.workflows.adapters.scenes import blueprint as scenes_blueprint

        raw = provider_fixtures.load_fixture(
            "scene_blueprint", "n8n", "raw_response.json"
        )
        request = provider_fixtures.load_fixture(
            "scene_blueprint", "n8n", "request.json"
        )

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            scenes_dir = output_dir / "scenes"
            with patch("studio.build_scene_blueprints.service.SCENES_DIR", str(scenes_dir)):
                with patch(
                    "studio.workflows.adapters.common.OUTPUT_DIR", str(output_dir)
                ):
                    with patch(
                        "studio.build_scene_blueprints.service.is_safe_webhook_url",
                        return_value=True,
                    ):
                        with patch(
                            "studio.build_scene_blueprints.service.call_webhook",
                            return_value=dict(raw),
                        ):
                            outputs = scenes_blueprint(
                                inputs={
                                    "segments": _segments_from_request(request),
                                    "script": request["script"],
                                },
                                config={
                                    "provider_id": "builtin",
                                    "style": "cinematic",
                                    "webhook_url": (
                                        "https://example.com/webhook/scene-blueprint"
                                    ),
                                },
                                context=AdapterContext(project_id="pm_SAMPLE"),
                            )
        self.assertEqual(outputs["scenes"]["provider"], "n8n")


class LegacyScenesRouteEnvelopeTests(unittest.TestCase):
    """Old `/api/scenes` callers keep their established envelope (13.4 done-when)."""

    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(scenes_bp)
        self.client = app.test_client()
        hub.discover("scene_blueprint")

    def test_generate_route_envelope_and_provider_stamp(self):
        raw = provider_fixtures.load_fixture(
            "scene_blueprint", "n8n", "raw_response.json"
        )
        request = provider_fixtures.load_fixture(
            "scene_blueprint", "n8n", "request.json"
        )

        with tempfile.TemporaryDirectory() as tmp:
            scenes_dir = Path(tmp) / "scenes"
            with patch("studio.build_scene_blueprints.service.SCENES_DIR", str(scenes_dir)):
                with patch(
                    "studio.build_scene_blueprints.service.is_safe_webhook_url",
                    return_value=True,
                ):
                    with patch(
                        "studio.build_scene_blueprints.service.call_webhook",
                        return_value=dict(raw),
                    ):
                        resp = self.client.post(
                            "/api/scenes/generate",
                            json={
                                "project_id": "pm_SAMPLE",
                                "script": request["script"],
                                "style": "cinematic",
                                "segments": request["segments"],
                                "webhook_url": (
                                    "https://example.com/webhook/scene-blueprint"
                                ),
                            },
                        )

            self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
            body = resp.get_json()
            for key in (
                "project_id",
                "scenes",
                "style",
                "style_spec",
                "style_prompt",
                "timestamp",
                "generation_time",
            ):
                self.assertIn(key, body)
            self.assertEqual(body["provider"], "n8n")
            self.assertEqual(len(body["scenes"]), 5)
            artifact = scenes_dir / "pm_SAMPLE" / "scenes.json"
            self.assertTrue(artifact.is_file())
            saved = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(saved["provider"], "n8n")

    def test_route_accepts_builtin_alias_and_returns_canonical_provider(self):
        raw = provider_fixtures.load_fixture(
            "scene_blueprint", "n8n", "raw_response.json"
        )
        request = provider_fixtures.load_fixture(
            "scene_blueprint", "n8n", "request.json"
        )
        with tempfile.TemporaryDirectory() as tmp:
            scenes_dir = Path(tmp) / "scenes"
            with patch("studio.build_scene_blueprints.service.SCENES_DIR", str(scenes_dir)):
                with patch(
                    "studio.build_scene_blueprints.service.is_safe_webhook_url",
                    return_value=True,
                ):
                    with patch(
                        "studio.build_scene_blueprints.service.call_webhook",
                        return_value=dict(raw),
                    ):
                        resp = self.client.post(
                            "/api/scenes/generate",
                            json={
                                "project_id": "pm_SAMPLE",
                                "provider_id": "builtin",
                                "script": request["script"],
                                "style": "cinematic",
                                "segments": request["segments"],
                                "webhook_url": (
                                    "https://example.com/webhook/scene-blueprint"
                                ),
                            },
                        )
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        self.assertEqual(resp.get_json()["provider"], "n8n")

    def test_unknown_provider_is_503(self):
        resp = self.client.post(
            "/api/scenes/generate",
            json={
                "provider_id": "does_not_exist",
                "script": "hello",
                "segments": [{"index": 0, "words": "hello"}],
            },
        )
        self.assertEqual(resp.status_code, 503)
        self.assertIn("error", resp.get_json())


if __name__ == "__main__":
    unittest.main()
