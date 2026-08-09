"""Step 13.4 — Scene Blueprint dispatch and compatibility migration.

Covers:
  * `scenes.blueprint` dispatches only through the hub
  * legacy POST /api/scenes/generate dispatches through the hub
  * P33: document `provider` is the resolved canonical id
  * S7: settings `builtin` → `n8n`, other selections preserved
  * alternate fixture provider runs without node/adapter edits
  * mocked end-to-end Script → Scene Blueprint gate
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from studio.build_scene_blueprints.providers.contract import SceneBlueprintRequest
from studio.shared.providers_common.domains import DOMAINS, DomainSpec
from studio.shared.providers_common.hub import hub
from studio.shared.providers_common.settings_migrations import (
    SETTINGS_VERSION,
    apply_migrations,
    migrate_to_v4,
)
from studio.workflows.adapters import scenes as scenes_adapter
from studio.workflows.adapters import story as story_adapter
from studio.workflows.adapters.common import AdapterContext
from studio.workflows.cache import canonical_fingerprint, fingerprint_components


PROJECT_ID = "pm_ABC123"
CTX = AdapterContext(project_id=PROJECT_ID)


class ScenesAdapterDispatchTests(unittest.TestCase):
    def test_absent_provider_id_defaults_to_n8n(self):
        """M4: pre-12.3 workflows keep the historical AI path without rewrite."""
        seen = {}

        class FakeProvider:
            def generate(self, segments, configuration, *, project_id):
                seen["config"] = dict(configuration)
                seen["project_id"] = project_id
                return {
                    "scenes": [{"index": 0, "image_prompt": "p"}],
                    "provider": "n8n",
                    "path": str(Path(tempfile.gettempdir()) / "scenes.json"),
                }

        with patch.object(scenes_adapter, "resolve_provider", return_value=FakeProvider()):
            with patch.object(scenes_adapter, "provider_run_options", return_value={}):
                with patch.object(
                    scenes_adapter,
                    "with_artifacts",
                    side_effect=lambda payload, *paths: {
                        **payload,
                        "artifact_refs": ["scenes/pm_ABC123/scenes.json"],
                    },
                ):
                    result = scenes_adapter.blueprint(
                        {
                            "segments": {"segments": [{"words": "hi"}]},
                            "script": "hi",
                            "settings": {"style": "cinematic", "tone": "dark"},
                        },
                        {},
                        CTX,
                    )

        self.assertIn("scenes", result)
        self.assertEqual(seen["project_id"], PROJECT_ID)
        self.assertEqual(seen["config"]["provider_id"], "n8n")
        self.assertEqual(seen["config"]["style"], "cinematic")
        self.assertEqual(seen["config"]["story_tone"], "dark")

    def test_adapter_source_never_imports_concrete_service(self):
        import inspect

        source = inspect.getsource(scenes_adapter)
        self.assertNotIn("studio.build_scene_blueprints.service", source)
        self.assertNotIn("_step_scenes", source)
        self.assertNotIn("generate_scenes", source)

    def test_fingerprint_includes_provider_id_and_options(self):
        node = {
            "id": "n_scenes",
            "type": "scenes.blueprint",
            "type_version": 1,
        }
        base = {"style": "cinematic"}
        a = fingerprint_components(
            node, {**base, "provider_id": "n8n"}, {}, {}
        )
        b = fingerprint_components(
            node,
            {
                **base,
                "provider_id": "n8n",
                "provider_options": {"webhook_url": "https://example.com/hook"},
            },
            {},
            {},
        )
        absent = fingerprint_components(node, base, {}, {})
        self.assertNotEqual(canonical_fingerprint(a), canonical_fingerprint(b))
        self.assertNotEqual(canonical_fingerprint(a), canonical_fingerprint(absent))


class SettingsS7MigrationTests(unittest.TestCase):
    def test_builtin_scene_selection_upgrades_to_n8n(self):
        data = {
            "version": 3,
            "general": {},
            "domains": {
                "scene_blueprint": {
                    "selected_provider": "builtin",
                    "per_provider": {},
                },
                "script": {"selected_provider": "gemini", "per_provider": {}},
            },
        }
        migrated, changed = apply_migrations(json.loads(json.dumps(data)), {})
        self.assertTrue(changed)
        self.assertEqual(migrated["version"], SETTINGS_VERSION)
        self.assertEqual(
            migrated["domains"]["scene_blueprint"]["selected_provider"], "n8n"
        )
        self.assertEqual(migrated["domains"]["script"]["selected_provider"], "gemini")

    def test_explicit_non_builtin_selection_is_preserved(self):
        data = {
            "version": 3,
            "general": {},
            "domains": {
                "scene_blueprint": {
                    "selected_provider": "fixture_scenes",
                    "per_provider": {},
                },
            },
        }
        migrated, _ = apply_migrations(json.loads(json.dumps(data)), {})
        self.assertEqual(
            migrated["domains"]["scene_blueprint"]["selected_provider"],
            "fixture_scenes",
        )

    def test_migrate_to_v4_is_idempotent_on_n8n(self):
        data = {
            "version": 3,
            "domains": {
                "scene_blueprint": {
                    "selected_provider": "n8n",
                    "per_provider": {},
                },
            },
        }
        once = migrate_to_v4(json.loads(json.dumps(data)), {})
        twice = migrate_to_v4(json.loads(json.dumps(once)), {})
        self.assertEqual(once, twice)
        self.assertEqual(
            once["domains"]["scene_blueprint"]["selected_provider"], "n8n"
        )

    def test_settings_version_is_at_least_four(self):
        self.assertGreaterEqual(SETTINGS_VERSION, 4)


class FixtureProviderNoNodeEditTests(unittest.TestCase):
    """An alternate scene_blueprint provider runs without node/adapter edits."""

    def test_fixture_provider_runs_through_scenes_adapter(self):
        from studio.shared.providers_common.hub import ProviderHub

        root = Path(__file__).resolve().parent / "fixture_providers" / "scene_blueprint"
        self.assertTrue(root.is_dir())

        # Build a private hub view by temporarily rebinding discovery for
        # scene_blueprint to the fixture package (same technique as 12.5).
        original = DOMAINS["scene_blueprint"]
        fixture_spec = DomainSpec(
            id=original.id,
            label=original.label,
            package=original.package,
            providers_base=str(root),
            default_provider="fixture_scenes",
            capability_vocabulary=original.capability_vocabulary,
            request_model=original.request_model,
            result_model=original.result_model,
        )
        local_hub = ProviderHub(catalog={"scene_blueprint": fixture_spec})
        local_hub.discover("scene_blueprint")
        self.assertIsNotNone(local_hub.get("scene_blueprint", "fixture_scenes"))

        provider = local_hub.create("scene_blueprint", "fixture_scenes")
        with tempfile.TemporaryDirectory() as tmp:
            with patch("config.OUTPUT_DIR", tmp):
                result = provider.generate(
                    {
                        "segments": [
                            {"index": 0, "words": "Hello fixture world."},
                            {"index": 1, "words": "Second beat."},
                        ]
                    },
                    {"style": "cinematic", "label_prefix": "Gate"},
                    project_id="pm_ABC123",
                )
            self.assertEqual(result["provider"], "fixture_scenes")
            self.assertEqual(len(result["scenes"]), 2)
            self.assertTrue(result["scenes"][0]["image_prompt"])
            self.assertTrue(Path(result["path"]).is_file())

            # Same adapter code path: resolve_provider + generate.
            with patch.object(
                scenes_adapter, "resolve_provider", return_value=provider
            ):
                with patch.object(
                    scenes_adapter, "provider_run_options", return_value={"label_prefix": "Gate"}
                ):
                    with patch.object(
                        scenes_adapter,
                        "with_artifacts",
                        side_effect=lambda payload, *paths: {
                            **payload,
                            "artifact_refs": ["scenes/pm_ABC123/scenes.json"],
                        },
                    ):
                        with patch("config.OUTPUT_DIR", tmp):
                            # Re-run through adapter with a fresh generate.
                            outputs = scenes_adapter.blueprint(
                                {
                                    "segments": {
                                        "segments": [
                                            {"index": 0, "words": "Hello fixture world."},
                                        ]
                                    },
                                    "script": "Hello fixture world.",
                                },
                                {"provider_id": "fixture_scenes", "style": "cinematic"},
                                CTX,
                            )
        self.assertIn("scenes", outputs)
        self.assertIn("image_prompts", outputs)


class ScriptToSceneBlueprintGateTests(unittest.TestCase):
    """Mocked end-to-end Script → Scene Blueprint gate (Phase 13 done-when)."""

    def test_script_then_scene_blueprint_mocked(self):
        from studio.shared.providers_common import fixtures as provider_fixtures

        raw_story = provider_fixtures.load_fixture(
            "script", "gemini", "raw_response.json"
        )["story_text"]
        raw_scenes = provider_fixtures.load_fixture(
            "scene_blueprint", "n8n", "raw_response.json"
        )
        scene_request = provider_fixtures.load_fixture(
            "scene_blueprint", "n8n", "request.json"
        )

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            stories = output_dir / "stories"
            history = output_dir / "story_history"
            scenes_dir = output_dir / "scenes"

            with patch("studio.story.service.STORIES_DIR", str(stories)):
                with patch("studio.story.history._HISTORY_DIR", str(history)):
                    with patch(
                        "studio.workflows.adapters.common.OUTPUT_DIR", str(output_dir)
                    ):
                        with patch(
                            "studio.story.service.is_safe_webhook_url", return_value=True
                        ):
                            with patch(
                                "studio.story.service.call_webhook",
                                return_value={"story_text": raw_story},
                            ):
                                story_out = story_adapter.generate(
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
                                    context=CTX,
                                )

            script_text = story_out["script"]
            self.assertTrue(script_text)
            self.assertIn("story", story_out)

            with patch(
                "studio.build_scene_blueprints.service.SCENES_DIR", str(scenes_dir)
            ):
                with patch(
                    "studio.workflows.adapters.common.OUTPUT_DIR", str(output_dir)
                ):
                    with patch(
                        "studio.build_scene_blueprints.service.is_safe_webhook_url",
                        return_value=True,
                    ):
                        with patch(
                            "studio.build_scene_blueprints.service.call_webhook",
                            return_value=dict(raw_scenes),
                        ):
                            scene_out = scenes_adapter.blueprint(
                                inputs={
                                    "segments": {
                                        "segments": scene_request["segments"],
                                    },
                                    "script": script_text,
                                },
                                config={
                                    "provider_id": "n8n",
                                    "style": "cinematic",
                                    "webhook_url": (
                                        "https://example.com/webhook/scene-blueprint"
                                    ),
                                },
                                context=CTX,
                            )

            self.assertEqual(len(scene_out["scenes"]["scenes"]), 5)
            self.assertEqual(scene_out["scenes"]["provider"], "n8n")
            self.assertTrue(
                (scenes_dir / PROJECT_ID / "scenes.json").is_file()
            )
            self.assertTrue((stories / PROJECT_ID / "story.json").is_file())


if __name__ == "__main__":
    unittest.main()
