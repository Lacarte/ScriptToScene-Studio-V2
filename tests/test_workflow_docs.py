"""Step 6.6 tests: generated node reference cannot drift from the registry."""

import unittest
from pathlib import Path

from studio.workflows.docs import DEFAULT_OUTPUT, generate_node_reference, main
from studio.workflows.registry import CATEGORIES, PORT_TYPES, all_node_types

DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"


class NodeReferenceGenerationTests(unittest.TestCase):
    def setUp(self):
        self.content = generate_node_reference()

    def test_committed_reference_matches_registry_output(self):
        """The committed markdown must be byte-identical to the generator output."""
        self.assertTrue(DEFAULT_OUTPUT.exists(), "docs/workflow-nodes.md is missing — run python -m studio.workflows.docs")
        committed = DEFAULT_OUTPUT.read_text(encoding="utf-8")
        self.assertEqual(
            committed, self.content,
            "docs/workflow-nodes.md is stale — regenerate with: python -m studio.workflows.docs",
        )

    def test_check_mode_agrees_with_drift_assertion(self):
        self.assertEqual(main(["--check"]), 0)

    def test_every_node_type_documented(self):
        for type_key, definition in all_node_types().items():
            with self.subTest(type_key=type_key):
                self.assertIn(f"(`{type_key}`)", self.content)
                self.assertIn(definition["display_name"], self.content)
                self.assertIn(definition["description"], self.content)
                for field in definition.get("config_schema", []):
                    self.assertIn(f"`{field['name']}`", self.content)

    def test_every_port_type_and_category_documented(self):
        for port_type in PORT_TYPES:
            self.assertIn(f"| `{port_type}` |", self.content)
        for key, info in CATEGORIES.items():
            self.assertIn(f"| `{key}` | {info['label']} |", self.content)

    def test_no_internal_executor_fields_leak(self):
        self.assertNotIn("executor", self.content)
        self.assertNotIn("studio.workflows.adapters", self.content)

    def test_generated_header_marks_file_as_machine_written(self):
        self.assertTrue(self.content.startswith("<!-- GENERATED FILE"))
        self.assertIn("python -m studio.workflows.docs", self.content)

    def test_builtin_templates_documented(self):
        for template_id in ("full_video", "narration_only", "storyboard_only", "reexport_existing_project"):
            self.assertIn(f"`{template_id}`", self.content)


class UserGuideTests(unittest.TestCase):
    def test_guide_exists_and_links_generated_reference(self):
        guide = DOCS_DIR / "workflow-guide.md"
        self.assertTrue(guide.exists())
        text = guide.read_text(encoding="utf-8")
        self.assertIn("workflow-nodes.md", text)
        # The newcomer path: template, validate, run, and recovery topics are covered.
        for topic in ("Full Video", "Validate", "Run", "Sample Input", "run mode", "draft"):
            self.assertIn(topic.lower(), text.lower())

    def test_readme_links_workflow_onboarding(self):
        readme = DOCS_DIR.parent / "README.md"
        text = readme.read_text(encoding="utf-8")
        self.assertIn("docs/workflow-guide.md", text)
        self.assertIn("docs/workflow-nodes.md", text)


if __name__ == "__main__":
    unittest.main()
