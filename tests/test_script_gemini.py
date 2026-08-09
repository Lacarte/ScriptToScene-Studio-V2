"""Step 13.2 — AI story generator as the `gemini` script provider."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

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
from studio.story.providers.contract import ScriptRequest, ScriptResultPayload
from studio.story.providers.gemini import provider as gemini_mod
from studio.story.routes import story_bp
from studio.story.service import StoryServiceError


class GeminiProviderRegistrationTests(unittest.TestCase):
    def test_provider_is_registered_with_builtin_alias(self):
        hub.discover("script")
        instance = hub.get("script", "gemini")
        self.assertIsNotNone(instance)
        self.assertEqual(instance.id, "gemini")
        self.assertIn("builtin", instance.manifest.aliases)
        self.assertTrue(instance.manifest.capabilities.get("structured_sections"))

        # Permanent input alias from the 12.3 bridge (contracts.md §40.3).
        aliased = hub.get("script", "builtin")
        self.assertIsNotNone(aliased)
        self.assertEqual(aliased.id, "gemini")

        created = hub.create("script", "builtin")
        # Discovery loads provider modules under a private name, so compare by
        # class name rather than `isinstance` against a second import of the file.
        self.assertEqual(type(created).__name__, "GeminiScriptProvider")
        self.assertTrue(callable(getattr(created, "generate", None)))

    def test_domain_default_is_gemini(self):
        from studio.shared.providers_common.domains import DOMAINS

        self.assertEqual(DOMAINS["script"].default_provider, "gemini")

    def test_settings_schema_owns_webhook_url(self):
        instance = hub.get("script", "gemini")
        schema = instance.settings_schema()
        self.assertIn("webhook_url", schema["properties"])
        self.assertEqual(instance.manifest.environment.get("webhook_url"), "N8N_STORY_WEBHOOK_URL")


class GeminiGenerateTests(unittest.TestCase):
    def setUp(self):
        self.provider = gemini_mod.create()
        self.raw_story = provider_fixtures.load_fixture(
            "script", "gemini", "raw_response.json"
        )["story_text"]
        self.request = provider_fixtures.load_fixture("script", "gemini", "request.json")

    def _configuration(self) -> dict:
        return {
            "idea": self.request["idea"],
            "story_category": self.request["category"],
            "preset_style": self.request["style"],
            "story_tone": self.request["tone"],
            "language": self.request["language"],
            "duration": self.request["target_duration_s"],
            "webhook_url": "https://example.com/webhook/story-generator",
        }

    def test_fixture_backed_generate_writes_story_and_standard_payload(self):
        def fake_webhook(url, payload, *, timeout=120, label="Webhook"):
            self.assertIn("system_prompt", payload)
            self.assertIn("user_prompt", payload)
            return {"story_text": self.raw_story}

        with tempfile.TemporaryDirectory() as tmp:
            stories = Path(tmp) / "stories"
            history = Path(tmp) / "story_history"
            with patch("studio.story.service.STORIES_DIR", str(stories)):
                with patch("studio.story.history._HISTORY_DIR", str(history)):
                    with patch(
                        "studio.story.service.is_safe_webhook_url", return_value=True
                    ):
                        result = self.provider.generate(
                            self._configuration(),
                            project_id="pm_SAMPLE",
                            webhook_caller=fake_webhook,
                        )

            path = Path(result["path"])
            self.assertTrue(path.is_file())
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["project_id"], "pm_SAMPLE")
            self.assertTrue(document["story_text"])
            self.assertEqual(
                set(document["sections"]), {"hook", "build", "climax", "cta"}
            )
            self.assertTrue(document["sections"]["hook"])
            # P33 / step 13.3: metadata carries the resolved canonical provider id.
            self.assertEqual(document["metadata"]["provider"], "gemini")
            self.assertEqual(
                document["metadata"]["story_category"], self.request["category"]
            )

            payload = ScriptResultPayload.from_mapping(document)
            self.assertEqual(payload.script_text, document["story_text"])
            self.assertEqual(payload.language, "english")
            self.assertGreater(payload.word_count, 0)
            self.assertEqual(result["story_text"], payload.script_text)

            # Diversity history is a provider-internal side effect, not an artifact.
            history_files = list(history.glob("*.json")) if history.is_dir() else []
            self.assertTrue(history_files, "append_history should have written a file")

    def test_invoke_returns_standard_envelope(self):
        from studio.shared.providers_common.invocation import (
            CancellationToken,
            ProviderInvocation,
        )

        def fake_webhook(url, payload, *, timeout=120, label="Webhook"):
            return {"story_text": self.raw_story}

        request = ScriptRequest.from_configuration(self._configuration())
        with tempfile.TemporaryDirectory() as tmp:
            stories = Path(tmp) / "stories"
            output_dir = Path(tmp)
            history = Path(tmp) / "story_history"
            with patch("studio.story.service.STORIES_DIR", str(stories)):
                with patch("studio.story.history._HISTORY_DIR", str(history)):
                    with patch(
                        "studio.story.service.is_safe_webhook_url", return_value=True
                    ):
                        with patch("config.OUTPUT_DIR", str(output_dir)):
                            with patch(
                                "studio.shared.providers_common.results.OUTPUT_DIR",
                                str(output_dir),
                            ):
                                # Default invoke bridges through generate(); inject
                                # the fixture webhook without reimplementing it.
                                original = self.provider.generate

                                def _generate(configuration, *, project_id):
                                    return original(
                                        configuration,
                                        project_id=project_id,
                                        webhook_caller=fake_webhook,
                                    )

                                with patch.object(
                                    self.provider, "generate", side_effect=_generate
                                ):
                                    inv = ProviderInvocation(
                                        domain="script",
                                        provider_id="gemini",
                                        project_id="pm_SAMPLE",
                                        output_dir=str(output_dir),
                                        cancel=CancellationToken(),
                                    )
                                    result = self.provider.invoke(request, inv)

        payload = ScriptResultPayload.model_validate(
            {k: v for k, v in result.payload.items() if k != "document_ref"}
        )
        self.assertTrue(payload.script_text)
        self.assertEqual(set(payload.sections), {"hook", "build", "climax", "cta"})
        self.assertIn("stories/", result.artifact_refs[0])


class GeminiErrorMappingTests(unittest.TestCase):
    def setUp(self):
        self.provider = gemini_mod.create()

    def test_missing_story_text_is_response_malformed_and_retryable(self):
        def empty_webhook(url, payload, *, timeout=120, label="Webhook"):
            return {"story_text": ""}

        with patch("studio.story.service.is_safe_webhook_url", return_value=True):
            with self.assertRaises(ProviderError) as ctx:
                self.provider.generate(
                    {
                        "story_category": "horror",
                        "preset_style": "cinematic",
                        "webhook_url": "https://example.com/webhook/story-generator",
                    },
                    project_id="pm_SAMPLE",
                    webhook_caller=empty_webhook,
                )
        err = ctx.exception
        self.assertEqual(err.code, PROVIDER_RESPONSE_MALFORMED)
        self.assertTrue(err.retryable)
        self.assertTrue(is_retryable(err.code))
        self.assertNotIn("sk-", err.message)

    def test_unsafe_webhook_is_request_invalid_and_not_retryable(self):
        with patch("studio.story.service.is_safe_webhook_url", return_value=False):
            with self.assertRaises(ProviderError) as ctx:
                self.provider.generate(
                    {
                        "story_category": "horror",
                        "preset_style": "cinematic",
                        "webhook_url": "http://169.254.169.254/",
                    },
                    project_id="pm_SAMPLE",
                )
        err = ctx.exception
        self.assertEqual(err.code, PROVIDER_REQUEST_INVALID)
        self.assertFalse(err.retryable)

    def test_timeout_is_retryable(self):
        import requests

        def boom(url, payload, *, timeout=120, label="Webhook"):
            raise requests.Timeout("timed out")

        with patch("studio.story.service.is_safe_webhook_url", return_value=True):
            with self.assertRaises(ProviderError) as ctx:
                self.provider.generate(
                    {
                        "story_category": "horror",
                        "preset_style": "cinematic",
                        "webhook_url": "https://example.com/webhook/story-generator",
                    },
                    project_id="pm_SAMPLE",
                    webhook_caller=boom,
                )
        self.assertEqual(ctx.exception.code, PROVIDER_TIMEOUT)
        self.assertTrue(ctx.exception.retryable)

    def test_transport_runtime_error_does_not_leak_body(self):
        def boom(url, payload, *, timeout=120, label="Webhook"):
            raise RuntimeError("Story webhook returned 502: sk-secret-body-fragment")

        with patch("studio.story.service.is_safe_webhook_url", return_value=True):
            with self.assertRaises(ProviderError) as ctx:
                self.provider.generate(
                    {
                        "story_category": "horror",
                        "preset_style": "cinematic",
                        "webhook_url": "https://example.com/webhook/story-generator",
                    },
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
            ("STORY_WEBHOOK_UNSAFE", PROVIDER_REQUEST_INVALID),
            ("STORY_TEXT_MISSING", PROVIDER_RESPONSE_MALFORMED),
        ):
            mapped = gemini_mod.GeminiScriptProvider._map_service_error(
                StoryServiceError(code, "internal detail that must not leak")
            )
            self.assertEqual(mapped.code, expected)
            self.assertNotIn("internal detail", mapped.message)


class GeminiFixtureTests(unittest.TestCase):
    def test_fixture_matches_legacy_adapter_and_passes_egress(self):
        raw = provider_fixtures.load_fixture("script", "gemini", "raw_response.json")
        expected = provider_fixtures.load_fixture(
            "script", "gemini", "expected_result.json"
        )
        for name in provider_fixtures.FIXTURE_FILES:
            value = provider_fixtures.load_fixture("script", "gemini", name)
            issues = provider_fixtures.validate_sanitation(value)
            self.assertEqual(issues, [], msg=f"{name}: {issues}")

        from studio.story.engine import parse_story_sections
        from studio.story.prompts import WORDS_PER_SECOND

        parsed = parse_story_sections(raw["story_text"])
        built = legacy.script_document_to_result(
            {
                "story_text": parsed["story_text"],
                "sections": parsed["sections"],
                "metadata": {
                    "preset_style": "neural_glow",
                    "language": "english",
                    "story_category": "horror",
                    "story_tone": "suspenseful",
                    "duration": 50,
                    "word_count": parsed["word_count"],
                    "estimated_duration": round(
                        parsed["word_count"] / WORDS_PER_SECOND
                    ),
                    "provider": "gemini",
                    "generation_time": 1.25,
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "concept_family": "recurring dreams that bleed into waking life",
                },
            },
            document_ref="stories/pm_SAMPLE/story.json",
            provider_id="gemini",
            provider_version="1.0.0",
        )
        coerced = coerce_result(
            built,
            domain="script",
            provider_id="gemini",
            provider_version="1.0.0",
        )
        self.assertEqual(coerced.payload, expected["payload"])
        self.assertEqual(coerced.artifact_refs, expected["artifact_refs"])
        self.assertEqual(coerced.metadata, expected["metadata"])
        validate_egress(coerced.to_dict())


class StoryAdapterGeminiTests(unittest.TestCase):
    def test_story_adapter_runs_gemini_without_importing_service(self):
        import inspect

        from studio.workflows.adapters import story as story_adapter
        from studio.workflows.adapters.common import AdapterContext

        source = inspect.getsource(story_adapter)
        self.assertNotIn("studio.story.service", source)
        self.assertNotIn("generate_story", source)
        self.assertNotIn("StoryServiceError", source)

        raw_story = provider_fixtures.load_fixture(
            "script", "gemini", "raw_response.json"
        )["story_text"]

        def fake_webhook(url, payload, *, timeout=120, label="Webhook"):
            return {"story_text": raw_story}

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            stories = output_dir / "stories"
            history = output_dir / "story_history"
            with patch("studio.story.service.STORIES_DIR", str(stories)):
                with patch("studio.story.history._HISTORY_DIR", str(history)):
                    with patch(
                        "studio.workflows.adapters.common.OUTPUT_DIR", str(output_dir)
                    ):
                        with patch(
                            "studio.story.service.is_safe_webhook_url",
                            return_value=True,
                        ):
                            with patch(
                                "studio.story.service.call_webhook",
                                side_effect=fake_webhook,
                            ):
                                outputs = story_adapter.generate(
                                    inputs={},
                                    config={
                                        "provider_id": "gemini",
                                        "preset_style": "cinematic",
                                        "story_category": "horror",
                                        "language": "english",
                                        "duration": 50,
                                        "webhook_url": (
                                            "https://example.com/webhook/story-generator"
                                        ),
                                    },
                                    context=AdapterContext(project_id="pm_SAMPLE"),
                                )
        self.assertIn("script", outputs)
        self.assertTrue(outputs["script"])
        self.assertIn("Hook:", outputs["script"])
        self.assertIn("story", outputs)
        self.assertEqual(
            outputs["story"]["artifact_refs"], ["stories/pm_SAMPLE/story.json"]
        )

    def test_story_adapter_resolves_builtin_alias(self):
        from studio.workflows.adapters.story import generate as story_generate
        from studio.workflows.adapters.common import AdapterContext

        raw_story = provider_fixtures.load_fixture(
            "script", "gemini", "raw_response.json"
        )["story_text"]

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            stories = output_dir / "stories"
            history = output_dir / "story_history"
            with patch("studio.story.service.STORIES_DIR", str(stories)):
                with patch("studio.story.history._HISTORY_DIR", str(history)):
                    with patch(
                        "studio.workflows.adapters.common.OUTPUT_DIR", str(output_dir)
                    ):
                        with patch(
                            "studio.story.service.is_safe_webhook_url",
                            return_value=True,
                        ):
                            with patch(
                                "studio.story.service.call_webhook",
                                return_value={"story_text": raw_story},
                            ):
                                outputs = story_generate(
                                    inputs={},
                                    config={
                                        "provider_id": "builtin",
                                        "preset_style": "cinematic",
                                        "story_category": "horror",
                                        "language": "english",
                                        "webhook_url": (
                                            "https://example.com/webhook/story-generator"
                                        ),
                                    },
                                    context=AdapterContext(project_id="pm_SAMPLE"),
                                )
        self.assertTrue(outputs["script"])


class LegacyStoryRouteEnvelopeTests(unittest.TestCase):
    """Old `/api/story` callers keep their established envelope (13.2 done-when)."""

    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(story_bp)
        self.client = app.test_client()

    def test_generate_route_envelope_unchanged(self):
        raw_story = provider_fixtures.load_fixture(
            "script", "gemini", "raw_response.json"
        )["story_text"]

        with tempfile.TemporaryDirectory() as tmp:
            stories = Path(tmp) / "stories"
            history = Path(tmp) / "story_history"
            # Route now dispatches through the hub (step 13.3); patch the
            # concrete AI service's transport rather than a route-local helper.
            with patch("studio.story.service.STORIES_DIR", str(stories)):
                with patch("studio.story.history._HISTORY_DIR", str(history)):
                    with patch(
                        "studio.story.service.is_safe_webhook_url", return_value=True
                    ):
                        with patch(
                            "studio.story.service.call_webhook",
                            return_value={"story_text": raw_story},
                        ):
                            resp = self.client.post(
                                "/api/story/generate",
                                json={
                                    "preset_style": "cinematic",
                                    "story_category": "horror",
                                    "duration": 50,
                                    "language": "english",
                                    "webhook_url": (
                                        "https://example.com/webhook/story-generator"
                                    ),
                                },
                            )
            self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
            data = resp.get_json()
            for key in (
                "success",
                "project_id",
                "story_text",
                "sections",
                "duration",
                "estimated_duration",
                "language",
                "story_category",
                "preset_style",
                "provider",
                "word_count",
                "generation_time",
                "timestamp",
            ):
                self.assertIn(key, data)
            self.assertTrue(data["success"])
            self.assertEqual(data["provider"], "gemini")
            self.assertEqual(set(data["sections"]), {"hook", "build", "climax", "cta"})


if __name__ == "__main__":
    unittest.main()
