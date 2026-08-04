"""Phase 1.6/1.7 workflow validation, persistence, routes, and templates."""

import math
import os
import tempfile
import unittest

from flask import Flask

from studio.workflows import workflows_bp
from studio.workflows.models import workflow_draft
from studio.workflows import persistence
from studio.workflows.persistence import WorkflowConflict, WorkflowValidationError
from studio.workflows.templates import serialize_templates
from studio.workflows.validation import validate_workflow, validation_errors
from studio.workflows.validation import _field_is_visible


def script_node(node_id="n_script"):
    return {
        "id": node_id,
        "type": "script.input",
        "type_version": 1,
        "name": "Script",
        "position": {"x": 0, "y": 0},
        "configuration": {"text": "A small test script."},
        "disabled": False,
    }


def draft(name="Test workflow"):
    document = workflow_draft(name=name)
    document["nodes"] = [script_node()]
    return document


class WorkflowTestBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sts_workflows_")
        self.old_workflows = persistence.WORKFLOWS_DIR
        self.old_trash = persistence.TRASH_DIR
        persistence.WORKFLOWS_DIR = os.path.join(self.temp.name, "workflows")
        persistence.TRASH_DIR = os.path.join(self.temp.name, "trash")
        os.makedirs(persistence.WORKFLOWS_DIR, exist_ok=True)

    def tearDown(self):
        persistence.WORKFLOWS_DIR = self.old_workflows
        persistence.TRASH_DIR = self.old_trash
        self.temp.cleanup()


class ValidationTests(unittest.TestCase):
    def test_conditional_field_visibility_matches_inspector_rules(self):
        field = {"display_options": {"show": {"enabled": [True]}}}
        self.assertFalse(_field_is_visible(field, {"enabled": False}))
        self.assertTrue(_field_is_visible(field, {"enabled": True}))
        hidden = {"display_options": {"hide": {"mode": ["auto"]}}}
        self.assertFalse(_field_is_visible(hidden, {"mode": "auto"}))
        self.assertTrue(_field_is_visible(hidden, {"mode": "manual"}))

    def test_valid_draft_has_only_missing_input_warnings_when_incomplete(self):
        document = draft()
        problems = validate_workflow(document, require_identity=False)
        self.assertEqual(validation_errors(problems), [])

    def test_rejects_unknown_fields_types_cycles_and_dynamic_mismatch(self):
        document = draft()
        document["surprise"] = True
        document["nodes"].append({
            "id": "n_output", "type": "workflow.output", "type_version": 1,
            "name": "Output", "position": {"x": 200, "y": 0},
            "configuration": {"port_type": "audio_file", "label": ""}, "disabled": False,
        })
        document["edges"] = [
            {"id": "e_bad", "source_node": "n_script", "source_port": "script",
             "target_node": "n_output", "target_port": "value", "edge_type": "data"},
        ]
        codes = {problem["code"] for problem in validation_errors(
            validate_workflow(document, require_identity=False)
        )}
        self.assertIn("WORKFLOW_INVALID", codes)
        self.assertIn("PORT_TYPE_MISMATCH", codes)

    def test_full_video_template_is_complete_and_valid(self):
        templates = serialize_templates()
        self.assertEqual([item["template_id"] for item in templates], ["full_video"])
        problems = validate_workflow(
            templates[0]["workflow"], require_identity=False, require_complete=False
        )
        self.assertEqual(validation_errors(problems), [])
        self.assertTrue(any(problem["severity"] == "warning" for problem in problems))

    def test_rejects_non_finite_numbers_and_excessive_nesting(self):
        non_finite = draft()
        non_finite["viewport"]["x"] = math.nan
        problems = validation_errors(validate_workflow(non_finite, require_identity=False))
        self.assertIn("finite", problems[0]["message"])

        nested = draft()
        value = {}
        nested["extensions"] = value
        for _ in range(20):
            value["child"] = {}
            value = value["child"]
        problems = validation_errors(validate_workflow(nested, require_identity=False))
        self.assertIn("nesting depth", problems[0]["message"])

    def test_rejects_oversized_reserved_data_and_bad_extensions(self):
        oversized = draft()
        oversized["variables"] = {"value": "x" * (64 * 1024)}
        problems = validation_errors(validate_workflow(oversized, require_identity=False))
        self.assertTrue(any(problem.get("path") == "variables" for problem in problems))

        reserved = draft()
        reserved["variables"] = {"future": True}
        problems = validation_errors(validate_workflow(reserved, require_identity=False))
        self.assertTrue(any("Phase 5" in problem["message"] for problem in problems))

        bad_extensions = draft()
        bad_extensions["extensions"] = []
        problems = validation_errors(validate_workflow(bad_extensions, require_identity=False))
        self.assertTrue(any(problem.get("path") == "extensions" for problem in problems))

    def test_persisted_identity_requires_timezone_aware_timestamps(self):
        document = draft()
        document.update({
            "workflow_id": "wf_ABC123",
            "created_at": "2026-08-04T12:00:00",
            "updated_at": "not-a-timestamp",
        })
        problems = validation_errors(validate_workflow(document))
        timestamp_paths = {problem.get("path") for problem in problems}
        self.assertEqual(timestamp_paths & {"created_at", "updated_at"}, {"created_at", "updated_at"})


class PersistenceTests(WorkflowTestBase):
    def test_create_load_update_list_and_soft_delete(self):
        created = persistence.create_workflow(draft())
        self.assertRegex(created["workflow_id"], r"^wf_[A-Z0-9]{6}$")
        loaded = persistence.load_workflow(created["workflow_id"])
        self.assertEqual(loaded, created)

        changed = dict(loaded)
        changed["name"] = "Renamed"
        updated = persistence.update_workflow(
            created["workflow_id"], changed, expected_updated_at=created["updated_at"]
        )
        self.assertEqual(updated["name"], "Renamed")
        items, total = persistence.list_workflows()
        self.assertEqual(total, 1)
        self.assertEqual(items[0]["workflow_id"], created["workflow_id"])

        persistence.delete_workflow(
            created["workflow_id"], expected_updated_at=updated["updated_at"]
        )
        self.assertFalse(os.path.exists(os.path.join(
            persistence.WORKFLOWS_DIR, f"{created['workflow_id']}.json"
        )))
        trash = os.path.join(persistence.TRASH_DIR, "workflows")
        self.assertEqual(len(os.listdir(trash)), 2)  # JSON + atomic-write backup.

    def test_conflict_and_invalid_id_are_rejected(self):
        created = persistence.create_workflow(draft())
        with self.assertRaises(WorkflowConflict):
            persistence.update_workflow(
                created["workflow_id"], created, expected_updated_at="stale"
            )
        with self.assertRaises(ValueError):
            persistence.load_workflow("../../escape")

    def test_invalid_document_is_not_written(self):
        bad = draft()
        bad["nodes"][0]["configuration"]["text"] = 123
        with self.assertRaises(WorkflowValidationError):
            persistence.create_workflow(bad)
        self.assertEqual(os.listdir(persistence.WORKFLOWS_DIR), [])

    def test_import_allocates_a_new_id(self):
        created = persistence.create_workflow(draft())
        imported, original_id = persistence.import_workflow(created)
        self.assertEqual(original_id, created["workflow_id"])
        self.assertNotEqual(imported["workflow_id"], created["workflow_id"])

    def test_import_rejects_a_malformed_source_id(self):
        document = draft()
        document["workflow_id"] = "../../escape"
        with self.assertRaises(WorkflowValidationError):
            persistence.import_workflow(document)


class RouteTests(WorkflowTestBase):
    def setUp(self):
        super().setUp()
        app = Flask(__name__)
        app.register_blueprint(workflows_bp)
        self.client = app.test_client()

    def test_crud_import_export_and_templates(self):
        response = self.client.post("/api/workflows", json={"workflow": draft()})
        self.assertEqual(response.status_code, 201)
        workflow = response.get_json()["workflow"]
        workflow_id = workflow["workflow_id"]

        self.assertEqual(self.client.get("/api/workflows").status_code, 200)
        self.assertEqual(self.client.get(f"/api/workflows/{workflow_id}").status_code, 200)
        exported = self.client.get(f"/api/workflows/{workflow_id}/export")
        self.assertEqual(exported.status_code, 200)
        self.assertIn("attachment", exported.headers["Content-Disposition"])
        self.assertEqual(self.client.get("/api/workflow/templates").status_code, 200)

        workflow["name"] = "Updated"
        updated = self.client.put(f"/api/workflows/{workflow_id}", json={
            "workflow": workflow,
            "expected_updated_at": workflow["updated_at"],
        })
        self.assertEqual(updated.status_code, 200)
        workflow = updated.get_json()["workflow"]

        imported = self.client.post("/api/workflows/import", json={"workflow": workflow})
        self.assertEqual(imported.status_code, 201)
        self.assertNotEqual(imported.get_json()["workflow"]["workflow_id"], workflow_id)

        deleted = self.client.delete(f"/api/workflows/{workflow_id}", json={
            "expected_updated_at": workflow["updated_at"],
        })
        self.assertEqual(deleted.status_code, 200)

    def test_validation_conflict_and_loopback_errors_use_envelope(self):
        bad = draft()
        bad["nodes"][0]["type"] = "unknown.node"
        response = self.client.post("/api/workflows", json={"workflow": bad})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.get_json()["error"]["code"], "WORKFLOW_INVALID")

        denied = self.client.get(
            "/api/workflows", environ_overrides={"REMOTE_ADDR": "10.1.2.3"}
        )
        self.assertEqual(denied.status_code, 403)
        self.assertIn("error", denied.get_json())


if __name__ == "__main__":
    unittest.main()
