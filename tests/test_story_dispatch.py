"""Step 13.3 — Generic Story Generator dispatch and compatibility migration.

Covers:
  * `story.generate` declares the previously-latent `story` port (§14.7)
  * the same adapter runs gemini and random_template with no code edit
  * legacy POST /api/story/generate dispatches through the hub
  * P33: metadata/envelope `provider` is the resolved canonical id
  * S6: settings `builtin` → `gemini`, other selections preserved
  * cache fingerprints include provider_id and provider_options
  * the story port is reachable by expressions (no EXPRESSION_OUTPUT_MISSING)
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from studio.shared.providers_common.domains import DOMAINS
from studio.shared.providers_common.hub import hub
from studio.shared.providers_common.settings_migrations import (
    SETTINGS_VERSION,
    apply_migrations,
    migrate_to_v3,
)
from studio.story.routes import story_bp
from studio.workflows.adapters import story as story_adapter
from studio.workflows.adapters.common import AdapterContext
from studio.workflows.cache import canonical_fingerprint, fingerprint_components
from studio.workflows.expressions import resolve_configuration, validate_expressions
from studio.workflows.registry import get_node_type


PROJECT_ID = "pm_ABC123"
CTX = AdapterContext(project_id=PROJECT_ID)


def _story_workflow(*, target_expression: str) -> dict:
    return {
        "schema_version": 1,
        "workflow_id": "wf_ABC123",
        "name": "Story port probe",
        "description": "",
        "nodes": [
            {
                "id": "n_story",
                "type": "story.generate",
                "type_version": 1,
                "name": "Story",
                "position": {"x": 0, "y": 0},
                "configuration": {
                    "story_category": "motivation",
                    "duration": 45,
                    "language": "english",
                },
                "disabled": False,
            },
            {
                "id": "n_target",
                "type": "utility.set_value",
                "type_version": 1,
                "name": "Target",
                "position": {"x": 200, "y": 0},
                "configuration": {"value": target_expression},
                "disabled": False,
            },
        ],
        "edges": [
            {
                "id": "e1",
                "source_node": "n_story",
                "source_port": "control",
                "target_node": "n_target",
                "target_port": "trigger",
                "edge_type": "control",
            }
        ],
        "variables": {},
        "viewport": {"x": 0, "y": 0, "zoom": 1},
        "settings": {"on_error": "stop"},
        "created_at": "2026-08-04T12:00:00Z",
        "updated_at": "2026-08-04T12:00:00Z",
    }


class StoryPortDeclarationTests(unittest.TestCase):
    def test_story_port_is_declared_as_generic_json(self):
        node_type = get_node_type("story.generate")
        outputs = {port["id"]: port["type"] for port in node_type["outputs"]}
        self.assertEqual(outputs["script"], "script")
        self.assertEqual(outputs["story"], "generic_json")

    def test_story_port_is_expression_reachable(self):
        """Regression for §14.7: undeclared port → EXPRESSION_OUTPUT_MISSING."""
        workflow = _story_workflow(
            target_expression="{{ nodes.n_story.outputs.story }}"
        )
        problems = validate_expressions(workflow)
        self.assertEqual(
            [p for p in problems if p.get("code") == "EXPRESSION_OUTPUT_MISSING"],
            [],
            problems,
        )
        node_outputs = {
            "n_story": {
                "control": {"ok": True},
                "script": "Hook text",
                "story": {
                    "story_text": "Hook text",
                    "artifact_refs": ["stories/pm_ABC123/story.json"],
                },
            }
        }
        resolved = resolve_configuration(
            {"doc": "{{ nodes.n_story.outputs.story }}"},
            node_outputs=node_outputs,
            variables={},
            project_id=PROJECT_ID,
        )
        self.assertEqual(
            resolved["doc"]["artifact_refs"],
            ["stories/pm_ABC123/story.json"],
        )

    def test_undeclared_port_still_rejected(self):
        workflow = _story_workflow(
            target_expression="{{ nodes.n_story.outputs.not_a_port }}"
        )
        problems = validate_expressions(workflow)
        self.assertTrue(
            any(p.get("code") == "EXPRESSION_OUTPUT_MISSING" for p in problems),
            problems,
        )


class StoryAdapterDispatchTests(unittest.TestCase):
    def test_absent_provider_id_defaults_to_gemini(self):
        """M4: pre-12.3 workflows keep the historical AI path without rewrite."""
        seen = {}

        class FakeProvider:
            def generate(self, configuration, *, project_id):
                seen["config"] = dict(configuration)
                seen["project_id"] = project_id
                return {
                    "story_text": "Hook: Default path",
                    "sections": {"hook": "Default path"},
                    "metadata": {"provider": "gemini"},
                    "path": str(Path(tempfile.gettempdir()) / "story.json"),
                }

        with patch.object(story_adapter, "resolve_provider", return_value=FakeProvider()):
            with patch.object(story_adapter, "provider_run_options", return_value={}):
                with patch.object(
                    story_adapter,
                    "with_artifacts",
                    side_effect=lambda payload, *paths: {
                        **payload,
                        "artifact_refs": ["stories/pm_ABC123/story.json"],
                    },
                ):
                    # Touch a real file so with_artifacts is fully mocked above.
                    result = story_adapter.generate(
                        {"settings": {"style": "cinematic", "tone": "dramatic"}},
                        {
                            "story_category": "motivation",
                            "duration": 45,
                            "language": "english",
                        },
                        CTX,
                    )

        self.assertEqual(result["script"], "Hook: Default path")
        self.assertIn("story", result)
        self.assertEqual(seen["project_id"], PROJECT_ID)
        # Adapter stamps the canonical id onto the configuration it hands the
        # provider, without rewriting the caller's saved configuration.
        self.assertEqual(seen["config"]["provider_id"], "gemini")
        self.assertEqual(seen["config"]["preset_style"], "cinematic")
        self.assertEqual(seen["config"]["story_tone"], "dramatic")

    def test_random_template_and_gemini_share_the_adapter(self):
        calls = []

        class Fake:
            def __init__(self, label):
                self.label = label

            def generate(self, configuration, *, project_id):
                calls.append((self.label, configuration.get("provider_id"), project_id))
                return {
                    "story_text": f"{self.label} text",
                    "sections": {},
                    "metadata": {"provider": self.label},
                    "path": str(Path(tempfile.gettempdir()) / f"{self.label}.json"),
                }

        def resolve(domain, selected):
            self.assertEqual(domain, "script")
            return Fake(selected if selected != "builtin" else "gemini")

        with patch.object(story_adapter, "resolve_provider", side_effect=resolve):
            with patch.object(story_adapter, "provider_run_options", return_value={}):
                with patch.object(
                    story_adapter,
                    "with_artifacts",
                    side_effect=lambda payload, *paths: {**payload, "artifact_refs": []},
                ):
                    out_gemini = story_adapter.generate(
                        {}, {"provider_id": "gemini"}, CTX
                    )
                    out_random = story_adapter.generate(
                        {}, {"provider_id": "random_template", "seed": 1}, CTX
                    )
                    out_alias = story_adapter.generate(
                        {}, {"provider_id": "builtin"}, CTX
                    )

        self.assertEqual(out_gemini["script"], "gemini text")
        self.assertEqual(out_random["script"], "random_template text")
        self.assertEqual(out_alias["script"], "gemini text")
        self.assertEqual(
            [c[0] for c in calls],
            ["gemini", "random_template", "gemini"],
        )

    def test_adapter_source_never_imports_concrete_ai_service(self):
        import inspect

        source = inspect.getsource(story_adapter)
        self.assertNotIn("studio.story.service", source)
        self.assertNotIn("generate_story", source)
        self.assertNotIn("StoryServiceError", source)


class LegacyGenerateRouteTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(story_bp)
        self.client = app.test_client()
        hub.discover("script")

    def test_route_dispatches_default_to_gemini_and_stamps_provider(self):
        raw = (
            "Hook: Ever had a dream?\n\n"
            "Build: Keep going.\n\n"
            "Climax: The twist.\n\n"
            "CTA: Share this."
        )

        def fake_webhook(url, payload, *, timeout=120, label="Webhook"):
            return {"story_text": raw}

        with tempfile.TemporaryDirectory() as tmp:
            stories = Path(tmp) / "stories"
            history = Path(tmp) / "story_history"
            with patch("studio.story.service.STORIES_DIR", str(stories)):
                with patch("studio.story.history._HISTORY_DIR", str(history)):
                    with patch(
                        "studio.story.service.is_safe_webhook_url", return_value=True
                    ):
                        with patch(
                            "studio.story.service.call_webhook",
                            side_effect=fake_webhook,
                        ):
                            resp = self.client.post(
                                "/api/story/generate",
                                json={
                                    "preset_style": "cinematic",
                                    "story_category": "horror",
                                    "language": "english",
                                    "duration": 50,
                                    "webhook_url": (
                                        "https://example.com/webhook/story-generator"
                                    ),
                                },
                            )

            self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
            body = resp.get_json()
            self.assertTrue(body["success"])
            self.assertEqual(body["provider"], "gemini")
            self.assertIn("Hook:", body["story_text"])
            self.assertIn("hook", body["sections"])
            # Frozen top-level envelope keys (§43).
            for key in (
                "project_id",
                "duration",
                "estimated_duration",
                "language",
                "story_category",
                "story_tone",
                "preset_style",
                "word_count",
                "generation_time",
                "timestamp",
                "concept_family",
            ):
                self.assertIn(key, body)

            # Artifact carries the same resolved identity (P33).
            artifact = stories / body["project_id"] / "story.json"
            self.assertTrue(artifact.is_file())
            saved = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(saved["metadata"]["provider"], "gemini")

    def test_route_accepts_builtin_alias_and_returns_canonical_provider(self):
        raw = "Hook: A.\n\nBuild: B.\n\nClimax: C.\n\nCTA: D."
        with tempfile.TemporaryDirectory() as tmp:
            stories = Path(tmp) / "stories"
            history = Path(tmp) / "story_history"
            with patch("studio.story.service.STORIES_DIR", str(stories)):
                with patch("studio.story.history._HISTORY_DIR", str(history)):
                    with patch(
                        "studio.story.service.is_safe_webhook_url", return_value=True
                    ):
                        with patch(
                            "studio.story.service.call_webhook",
                            return_value={"story_text": raw},
                        ):
                            resp = self.client.post(
                                "/api/story/generate",
                                json={
                                    "provider_id": "builtin",
                                    "preset_style": "cinematic",
                                    "story_category": "horror",
                                    "webhook_url": (
                                        "https://example.com/webhook/story-generator"
                                    ),
                                },
                            )
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        self.assertEqual(resp.get_json()["provider"], "gemini")

    def test_route_runs_random_template_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            stories = Path(tmp) / "stories"
            # Hub loads provider packages under a private module name, so patch
            # that module's STORIES_DIR rather than the importable package path.
            provider_module = hub.get("script", "random_template").provider_module
            with patch.object(provider_module, "STORIES_DIR", str(stories)):
                resp = self.client.post(
                    "/api/story/generate",
                    json={
                        "provider_id": "random_template",
                        "preset_style": "cinematic",
                        "story_category": "motivation",
                        "seed": 7,
                    },
                )
            self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
            body = resp.get_json()
            self.assertEqual(body["provider"], "random_template")
            self.assertTrue(body["story_text"])
            self.assertTrue((stories / body["project_id"] / "story.json").is_file())

    def test_unknown_provider_is_503(self):
        resp = self.client.post(
            "/api/story/generate",
            json={
                "provider_id": "does_not_exist",
                "preset_style": "cinematic",
                "story_category": "horror",
            },
        )
        self.assertEqual(resp.status_code, 503)
        self.assertIn("error", resp.get_json())


class SettingsS6MigrationTests(unittest.TestCase):
    def test_builtin_script_selection_upgrades_to_gemini(self):
        data = {
            "version": 2,
            "general": {},
            "domains": {
                "script": {"selected_provider": "builtin", "per_provider": {}},
                "tts": {"selected_provider": "kokoro", "per_provider": {}},
            },
        }
        migrated, changed = apply_migrations(json.loads(json.dumps(data)), {})
        self.assertTrue(changed)
        self.assertEqual(migrated["version"], SETTINGS_VERSION)
        self.assertEqual(migrated["domains"]["script"]["selected_provider"], "gemini")
        # Unrelated domains are untouched.
        self.assertEqual(migrated["domains"]["tts"]["selected_provider"], "kokoro")

    def test_explicit_random_template_selection_is_preserved(self):
        data = {
            "version": 2,
            "general": {},
            "domains": {
                "script": {
                    "selected_provider": "random_template",
                    "per_provider": {},
                },
            },
        }
        migrated, _ = apply_migrations(json.loads(json.dumps(data)), {})
        self.assertEqual(
            migrated["domains"]["script"]["selected_provider"], "random_template"
        )

    def test_migrate_to_v3_is_idempotent_on_gemini(self):
        data = {
            "version": 2,
            "domains": {
                "script": {"selected_provider": "gemini", "per_provider": {}},
            },
        }
        once = migrate_to_v3(json.loads(json.dumps(data)), {})
        twice = migrate_to_v3(json.loads(json.dumps(once)), {})
        self.assertEqual(once, twice)
        self.assertEqual(once["domains"]["script"]["selected_provider"], "gemini")

    def test_settings_version_is_at_least_three(self):
        self.assertGreaterEqual(SETTINGS_VERSION, 3)
        self.assertEqual(DOMAINS["script"].default_provider, "gemini")


class FingerprintProviderTests(unittest.TestCase):
    def test_provider_id_and_options_affect_fingerprint(self):
        node = {
            "id": "n_story",
            "type": "story.generate",
            "type_version": 1,
        }
        base = {
            "story_category": "motivation",
            "duration": 45,
            "language": "english",
        }
        gemini = fingerprint_components(
            node, {**base, "provider_id": "gemini"}, {}, {}
        )
        random = fingerprint_components(
            node, {**base, "provider_id": "random_template"}, {}, {}
        )
        options = fingerprint_components(
            node,
            {
                **base,
                "provider_id": "gemini",
                "provider_options": {"webhook_url": "https://example.com/a"},
            },
            {},
            {},
        )
        options_b = fingerprint_components(
            node,
            {
                **base,
                "provider_id": "gemini",
                "provider_options": {"webhook_url": "https://example.com/b"},
            },
            {},
            {},
        )
        # Absent provider_id (M4) is a distinct fingerprint from an explicit one.
        absent = fingerprint_components(node, base, {}, {})

        self.assertNotEqual(
            canonical_fingerprint(gemini), canonical_fingerprint(random)
        )
        self.assertNotEqual(
            canonical_fingerprint(options), canonical_fingerprint(options_b)
        )
        self.assertNotEqual(
            canonical_fingerprint(gemini), canonical_fingerprint(absent)
        )


class ServiceProviderStampTests(unittest.TestCase):
    def test_service_stamps_resolved_provider_not_hardcoded_only(self):
        from studio.story import service as story_service

        def webhook(url, payload, **kwargs):
            return {
                "story_text": (
                    "Hook: One.\n\nBuild: Two.\n\nClimax: Three.\n\nCTA: Four."
                )
            }

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(story_service, "STORIES_DIR", tmp):
                with patch.object(story_service, "append_history", lambda **kw: None):
                    with patch.object(
                        story_service, "is_safe_webhook_url", return_value=True
                    ):
                        result = story_service.generate_story(
                            {
                                "preset_style": "cinematic",
                                "story_category": "horror",
                                "duration": 45,
                                "language": "english",
                                "webhook_url": (
                                    "https://example.com/webhook/story-generator"
                                ),
                            },
                            project_id=PROJECT_ID,
                            provider_id="gemini",
                            webhook_caller=webhook,
                        )
        self.assertEqual(result["metadata"]["provider"], "gemini")


if __name__ == "__main__":
    unittest.main()
