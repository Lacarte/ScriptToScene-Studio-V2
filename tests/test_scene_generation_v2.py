import unittest

from studio.scenes.planner import (
    build_scene_blueprints,
    build_visual_bible,
    summarize_blueprints,
)
from studio.scenes.prompts import build_scene_system_prompt
from studio.scenes.style_compiler import public_template_payload, resolve_template_bundle
from studio.scenes.templates import TEMPLATES_BY_ID
from studio.scenes.validators import ensure_analysis_payload, finalize_scene_result


class SceneGenerationV2Tests(unittest.TestCase):
    def setUp(self):
        self.segments = [
            {"index": 0, "words": "You notice the pattern for the first time."},
            {"index": 1, "words": "Then it starts appearing everywhere around you."},
            {"index": 2, "words": "That is when the story shifts."},
            {"index": 3, "words": "Now you cannot unsee it."},
            {"index": 4, "words": "What else have you been missing?"},
        ]
        self.script = " ".join(segment["words"] for segment in self.segments)

    def test_public_template_payload_hides_internal_style_spec(self):
        template = TEMPLATES_BY_ID["cinematic"]
        payload = public_template_payload(template)

        self.assertEqual(
            set(payload.keys()),
            {"id", "name", "description", "color", "style_prompt"},
        )
        self.assertNotIn("style_spec", payload)

    def test_scene_planning_prompt_and_result_annotations(self):
        bundle = resolve_template_bundle("cinematic", TEMPLATES_BY_ID, "")
        visual_bible = build_visual_bible(self.script, self.segments, bundle["style_spec"])
        blueprints = build_scene_blueprints(self.segments, visual_bible, bundle["style_spec"])
        summary = summarize_blueprints(blueprints)

        prompt = build_scene_system_prompt(
            bundle["style_spec"],
            visual_bible,
            blueprints,
            plan_summary=summary,
        )

        self.assertIn("VISUAL BIBLE", prompt)
        self.assertIn("SCENE BLUEPRINTS", prompt)

        result = {
            "analysis": {},
            "scenes": [
                {
                    "index": 0,
                    "title": "First Glimpse",
                    "narrative_role": "hook",
                    "type_of_scene": "video",
                    "image_prompt": "wide, lone figure noticing repeated symbols in a corridor, dim hallway, cool lighting, uneasy wonder, dust drifting, slow push-in, cinematic",
                    "text_content": None,
                },
                {
                    "index": 1,
                    "title": "Everywhere",
                    "narrative_role": "buildup",
                    "type_of_scene": "video",
                    "image_prompt": "medium, same figure turning as repeated symbols appear in windows, urban interior, cool lighting, rising tension, reflections shifting, camera drift, cinematic",
                    "text_content": None,
                },
                {
                    "index": 2,
                    "title": "Shift",
                    "narrative_role": "text_accent",
                    "type_of_scene": "text",
                    "image_prompt": "medium, blurred corridor with repeating symbols, same urban interior, cool lighting, ominous mood, cinematic",
                    "text_content": "THE SHIFT",
                },
                {
                    "index": 3,
                    "title": "Unseen",
                    "narrative_role": "peak",
                    "type_of_scene": "video",
                    "image_prompt": "close-up, figure staring at layered reflections, mirrored wall, cold lighting, intense unease, light flicker, breath tremor, cinematic",
                    "text_content": None,
                },
                {
                    "index": 4,
                    "title": "What Else",
                    "narrative_role": "cta",
                    "type_of_scene": "image",
                    "image_prompt": "wide, same figure alone at the end of the corridor, dim institutional interior, cold lighting, lingering doubt, cinematic",
                    "text_content": None,
                },
            ],
        }

        ensure_analysis_payload(result, visual_bible, bundle["style_spec"], bundle["template"])
        finalize_scene_result(result, blueprints, visual_bible)

        self.assertIn("visual_bible", result["analysis"])
        self.assertIn("coherence_score", result)
        self.assertIn("shot_type", result["scenes"][0])
        self.assertIn("anchor_used", result["scenes"][0])


if __name__ == "__main__":
    unittest.main()
