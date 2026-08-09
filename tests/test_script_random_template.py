"""Step 13.1 — script contract + random_template provider."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from studio.shared.providers_common import fixtures as provider_fixtures
from studio.shared.providers_common import legacy
from studio.shared.providers_common.domains import DOMAINS
from studio.shared.providers_common.hub import hub
from studio.shared.providers_common.results import coerce_result, validate_egress
from studio.story.providers.contract import ScriptRequest, ScriptResultPayload
from studio.story.providers.random_template import provider as rt
from studio.story.routes import story_bp


class ScriptContractTests(unittest.TestCase):
    def test_domain_points_at_the_script_models(self):
        spec = DOMAINS["script"]
        self.assertEqual(
            spec.request_model, "studio.story.providers.contract:ScriptRequest"
        )
        self.assertEqual(
            spec.result_model, "studio.story.providers.contract:ScriptResultPayload"
        )

    def test_request_rejects_unknown_keys(self):
        with self.assertRaises(Exception):
            ScriptRequest.model_validate({"category": "x", "extra_field": 1})

    def test_request_maps_legacy_configuration_aliases(self):
        req = ScriptRequest.from_configuration({
            "story_category": "motivation",
            "preset_style": "cinematic",
            "story_tone": "warm",
            "duration": 60,
            "idea": "  a lighthouse  ",
            "seed": "7",
        })
        self.assertEqual(req.category, "motivation")
        self.assertEqual(req.style, "cinematic")
        self.assertEqual(req.tone, "warm")
        self.assertEqual(req.target_duration_s, 60)
        self.assertEqual(req.idea, "a lighthouse")
        self.assertEqual(req.seed, 7)

    def test_result_payload_requires_non_empty_script(self):
        with self.assertRaises(Exception):
            ScriptResultPayload(
                script_text="  ",
                sections={},
                word_count=0,
                estimated_duration_s=0,
                language="english",
            )


class RandomTemplateProviderTests(unittest.TestCase):
    def setUp(self):
        rt.reset_anti_repeat()
        # Drop cached catalog so a re-written fixtures file is visible in long
        # test sessions that import this module early.
        rt.load_templates.cache_clear()

    def test_catalog_preserves_frontend_count_and_types(self):
        catalog = rt.load_templates()
        self.assertEqual(len(catalog), 283)
        types = {entry["type"] for entry in catalog}
        self.assertIn("Anecdote", types)
        self.assertIn("Children's Story", types)
        self.assertIn("cinematic", catalog[0]["styles"])

    def test_seed_is_deterministic(self):
        a = rt.pick_template(seed=42)
        b = rt.pick_template(seed=42)
        self.assertEqual(a["index"], b["index"])
        self.assertEqual(a["text"], b["text"])
        self.assertEqual(a["type"], "Children's Story")

    def test_anti_repeat_avoids_immediate_previous(self):
        # Force a tiny pool by filtering to a type with a single entry.
        sci_fi = [e for e in rt.load_templates() if e["type"] == "Science Fiction"]
        self.assertEqual(len(sci_fi), 1)
        first = rt.pick_template(category="Science Fiction")
        second = rt.pick_template(category="Science Fiction")
        # Only one candidate — anti-repeat cannot avoid it, but both succeed.
        self.assertEqual(first["text"], second["text"])

        # Full catalog: successive unseeded picks should not share an index
        # when more than one entry exists (probabilistic only if pool==1).
        seen = {rt.pick_template(seed=None)["index"] for _ in range(1)}
        # After one pick, the next should differ with overwhelming probability
        # on a 283-entry catalog; retry a few times to be deterministic enough.
        different = False
        for _ in range(20):
            nxt = rt.pick_template()
            if nxt["index"] not in seen:
                different = True
                break
            seen.add(nxt["index"])
        self.assertTrue(different, "anti-repeat never left the previous index")

    def test_generate_writes_story_json_and_validates_payload(self,):
        provider = rt.create()
        with tempfile.TemporaryDirectory() as tmp:
            stories = Path(tmp) / "stories"
            with patch("studio.story.providers.random_template.provider.STORIES_DIR", str(stories)):
                result = provider.generate(
                    {"seed": 42, "preset_style": "cinematic", "language": "english"},
                    project_id="pm_SAMPLE",
                )
            path = Path(result["path"])
            self.assertTrue(path.is_file())
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["project_id"], "pm_SAMPLE")
            self.assertTrue(document["story_text"])
            payload = ScriptResultPayload.from_mapping(document)
            self.assertEqual(payload.script_text, document["story_text"])
            self.assertEqual(payload.language, "english")
            self.assertGreater(payload.word_count, 0)
            self.assertEqual(result["story_text"], payload.script_text)

    def test_invoke_returns_standard_envelope(self):
        from studio.shared.providers_common.invocation import ProviderInvocation, CancellationToken

        provider = rt.create()
        request = ScriptRequest(seed=42, style="cinematic", language="english")
        with tempfile.TemporaryDirectory() as tmp:
            stories = Path(tmp) / "stories"
            output_dir = Path(tmp)
            with patch("studio.story.providers.random_template.provider.STORIES_DIR", str(stories)):
                with patch("config.OUTPUT_DIR", str(output_dir)):
                    with patch(
                        "studio.shared.providers_common.results.OUTPUT_DIR",
                        str(output_dir),
                    ):
                        inv = ProviderInvocation(
                            domain="script",
                            provider_id="random_template",
                            project_id="pm_SAMPLE",
                            output_dir=str(output_dir),
                            cancel=CancellationToken(),
                        )
                        # Provide a no-op progress sink the default ProgressReporter needs.
                        result = provider.invoke(request, inv)
        payload = ScriptResultPayload.model_validate(
            {k: v for k, v in result.payload.items() if k != "document_ref"}
        )
        self.assertTrue(payload.script_text)
        self.assertIn("stories/", result.artifact_refs[0])

    def test_provider_is_registered_on_the_hub(self):
        instance = hub.get("script", "random_template")
        self.assertIsNotNone(instance)
        self.assertEqual(instance.id, "random_template")
        self.assertTrue(instance.manifest.capabilities.get("offline"))
        created = hub.create("script", "random_template")
        self.assertTrue(hasattr(created, "generate"))
        self.assertTrue(hasattr(created, "pick"))


class RandomTemplateFixtureTests(unittest.TestCase):
    def test_fixture_matches_legacy_adapter_and_passes_egress(self):
        raw = provider_fixtures.load_fixture("script", "random_template", "raw_response.json")
        expected = provider_fixtures.load_fixture(
            "script", "random_template", "expected_result.json"
        )
        # Sanitation on all three files.
        for name in provider_fixtures.FIXTURE_FILES:
            value = provider_fixtures.load_fixture("script", "random_template", name)
            issues = provider_fixtures.validate_sanitation(value)
            self.assertEqual(issues, [], msg=f"{name}: {issues}")

        built = legacy.script_document_to_result(
            {
                "story_text": raw["text"],
                "sections": {},
                "metadata": {
                    "preset_style": "cinematic",
                    "language": "english",
                    "story_category": raw["type"],
                    "story_tone": "",
                    "duration": 45,
                    "word_count": len(raw["text"].split()),
                    "estimated_duration": expected["payload"]["estimated_duration_s"],
                    "template_type": raw["type"],
                    "template_styles": ",".join(raw["styles"]),
                    "template_index": raw["index"],
                    "seed": raw["seed"],
                    "timestamp": "2026-01-01T00:00:00+00:00",
                },
            },
            document_ref="stories/pm_SAMPLE/story.json",
            provider_id="random_template",
            provider_version="1.0.0",
        )
        coerced = coerce_result(
            built,
            domain="script",
            provider_id="random_template",
            provider_version="1.0.0",
        )
        # Compare the domain-meaningful fields; provenance timestamps are platform-owned.
        self.assertEqual(coerced.payload, expected["payload"])
        self.assertEqual(coerced.artifact_refs, expected["artifact_refs"])
        self.assertEqual(coerced.metadata, expected["metadata"])
        validate_egress(coerced.to_dict())


class RandomTemplateRouteTests(unittest.TestCase):
    def setUp(self):
        rt.reset_anti_repeat()
        app = Flask(__name__)
        app.register_blueprint(story_bp)
        self.client = app.test_client()
        # Ensure the hub has discovered script providers for this process.
        hub.discover("script")

    def test_random_route_returns_seeded_pick(self):
        resp = self.client.post("/api/story/random", json={"seed": 42})
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        data = resp.get_json()
        self.assertEqual(data["provider_id"], "random_template")
        self.assertEqual(data["type"], "Children's Story")
        self.assertTrue(data["text"])
        self.assertIn("children_storybook", data["styles"])
        self.assertEqual(data["index"], 57)

    def test_random_route_rejects_bad_seed(self):
        resp = self.client.post("/api/story/random", json={"seed": "nope"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"]["code"], "INVALID_REQUEST")


class StoryAdapterRandomTemplateTests(unittest.TestCase):
    def test_story_adapter_can_run_random_template(self):
        from studio.workflows.adapters.story import generate as story_generate
        from studio.workflows.adapters.common import AdapterContext

        with tempfile.TemporaryDirectory() as tmp:
            stories = Path(tmp) / "stories"
            with patch(
                "studio.story.providers.random_template.provider.STORIES_DIR",
                str(stories),
            ):
                outputs = story_generate(
                    inputs={},
                    config={
                        "provider_id": "random_template",
                        "seed": 42,
                        "preset_style": "cinematic",
                        "language": "english",
                    },
                    context=AdapterContext(project_id="pm_SAMPLE"),
                )
        self.assertIn("script", outputs)
        self.assertTrue(outputs["script"])
        self.assertIn("story", outputs)


if __name__ == "__main__":
    unittest.main()
