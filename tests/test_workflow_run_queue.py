"""Step 7.1: persisted, per-project workflow run queue."""

from __future__ import annotations

import threading
import time

from flask import Flask

import studio.workflows.routes as workflow_routes
from studio.workflows import workflows_bp
from studio.workflows.execution import ExecutionManager
from studio.workflows.persistence import load_execution, load_queue_record


def _workflow():
    return {
        "schema_version": 1,
        "name": "Queue test",
        "description": "",
        "nodes": [{
            "id": "work",
            "type": "trigger.manual",
            "type_version": 1,
            "name": "work",
            "position": {"x": 0, "y": 0},
            "configuration": {},
            "disabled": False,
        }],
        "edges": [],
        "variables": {},
        "viewport": {"x": 0, "y": 0, "zoom": 1},
        "settings": {"on_error": "stop"},
        "extensions": {},
    }


def _wait_for(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition was not reached")


def test_same_project_serializes_while_different_projects_run_concurrently(tmp_path):
    release = threading.Event()
    state_lock = threading.Lock()
    active_by_project = {}
    maximum_by_project = {}
    started_by_project = {}

    def resolver(_node):
        def execute(_inputs, _config, context):
            with state_lock:
                project = context.project_id
                active_by_project[project] = active_by_project.get(project, 0) + 1
                maximum_by_project[project] = max(
                    maximum_by_project.get(project, 0), active_by_project[project]
                )
                started_by_project[project] = started_by_project.get(project, 0) + 1
            release.wait(timeout=3)
            with state_lock:
                active_by_project[project] -= 1
            return {"control": {"ok": True}}
        return execute

    manager = ExecutionManager(output_dir=str(tmp_path), executor_resolver=resolver)
    first, _ = manager.start(
        _workflow(), run_mode="full", target_node_ids=[], project_id="pm_ABC123"
    )
    second, _ = manager.start(
        _workflow(), run_mode="full", target_node_ids=[], project_id="pm_ABC123"
    )
    other, _ = manager.start(
        _workflow(), run_mode="full", target_node_ids=[], project_id="pm_DEF456"
    )

    _wait_for(lambda: started_by_project.get("pm_ABC123") == 1)
    _wait_for(lambda: started_by_project.get("pm_DEF456") == 1)
    assert load_queue_record(second, root=manager.queue_root)["status"] == "pending"
    assert load_queue_record(first, root=manager.queue_root)["status"] == "running"
    assert load_queue_record(other, root=manager.queue_root)["status"] == "running"

    release.set()
    manager.active.get(second).thread.join(timeout=5)
    manager.active.get(other).thread.join(timeout=5)
    assert maximum_by_project == {"pm_ABC123": 1, "pm_DEF456": 1}
    assert started_by_project == {"pm_ABC123": 2, "pm_DEF456": 1}
    assert load_queue_record(second, root=manager.queue_root)["status"] == "done"


def test_pending_run_can_be_cancelled_and_never_executes(tmp_path):
    first_started = threading.Event()
    release = threading.Event()
    calls = []

    def resolver(_node):
        def execute(_inputs, _config, context):
            calls.append(context.execution_id)
            first_started.set()
            release.wait(timeout=3)
            return {"control": {"ok": True}}
        return execute

    manager = ExecutionManager(output_dir=str(tmp_path), executor_resolver=resolver)
    first, _ = manager.start(
        _workflow(), run_mode="full", target_node_ids=[], project_id="pm_ABC123"
    )
    assert first_started.wait(timeout=2)
    pending, _ = manager.start(
        _workflow(), run_mode="full", target_node_ids=[], project_id="pm_ABC123"
    )

    assert manager.cancel_pending(pending) == "cancelled"
    assert load_queue_record(pending, root=manager.queue_root)["status"] == "cancelled"
    assert load_execution(pending, root=manager.execution_root)["status"] == "cancelled"
    release.set()
    manager.active.get(first).thread.join(timeout=5)
    assert calls == [first]


def test_queue_record_persists_source_and_requested_mode(tmp_path):
    manager = ExecutionManager(output_dir=str(tmp_path))
    execution_id, _ = manager.start(
        _workflow(), run_mode="full", target_node_ids=[], source="webhook"
    )
    manager.active.get(execution_id).thread.join(timeout=5)
    item = load_queue_record(execution_id, root=manager.queue_root)
    assert item["source"] == "webhook"
    assert item["requested_run_mode"] == "full"
    assert item["status"] == "done"
    assert item["requested_at"]
    assert item["started_at"]
    assert item["finished_at"]


def test_queue_endpoints_list_and_cancel_pending(tmp_path, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def resolver(_node):
        def execute(_inputs, _config, _context):
            started.set()
            release.wait(timeout=3)
            return {"control": {"ok": True}}
        return execute

    manager = ExecutionManager(output_dir=str(tmp_path), executor_resolver=resolver)
    monkeypatch.setattr(workflow_routes, "execution_manager", manager)
    app = Flask(__name__)
    app.register_blueprint(workflows_bp)
    http = app.test_client()

    first, _ = manager.start(
        _workflow(), run_mode="full", target_node_ids=[], project_id="pm_ABC123"
    )
    assert started.wait(timeout=2)
    pending, _ = manager.start(
        _workflow(), run_mode="full", target_node_ids=[], project_id="pm_ABC123"
    )
    workflow_id = manager.active.get(pending).queue_record.workflow_id

    response = http.get("/api/workflow/queue", query_string={"workflow_id": workflow_id})
    assert response.status_code == 200
    assert response.get_json()["queue"][0]["status"] == "pending"
    response = http.post(f"/api/workflow/queue/{pending}/cancel", json={})
    assert response.status_code == 202
    assert response.get_json()["status"] == "cancelled"

    release.set()
    manager.active.get(first).thread.join(timeout=5)
