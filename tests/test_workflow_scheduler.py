from __future__ import annotations

import os
import threading

import pytest

from studio.workflows.scheduler import (
    ArtifactPromoter,
    ProjectLock,
    ProjectLockedError,
    WorkflowScheduler,
    calculate_scope,
    dependency_maps,
    deterministic_order,
)
from studio.workflows.registry import get_node_type


def _node(node_id, node_type="trigger.manual", *, disabled=False, port_type=None, config=None):
    if config is None:
        config = {} if port_type is None else {"port_type": port_type, "payload": {}}
    return {
        "id": node_id, "type": node_type, "type_version": 1, "name": node_id,
        "position": {"x": 0, "y": 0}, "configuration": config, "disabled": disabled,
    }


def _edge(edge_id, source, source_port, target, target_port, edge_type="control"):
    return {
        "id": edge_id, "source_node": source, "source_port": source_port,
        "target_node": target, "target_port": target_port, "edge_type": edge_type,
    }


def _workflow(nodes, edges):
    return {
        "schema_version": 1, "workflow_id": "wf_ABC123", "name": "Schedule",
        "description": "", "nodes": nodes, "edges": edges, "variables": {},
        "viewport": {"x": 0, "y": 0, "zoom": 1}, "settings": {"on_error": "stop"},
        "created_at": "2026-08-04T12:00:00Z", "updated_at": "2026-08-04T12:00:00Z",
    }


def _resolver(calls, behavior=None):
    behavior = behavior or {}
    def resolve(node):
        def execute(inputs, config, context):
            calls.append((node["id"], inputs))
            defaults = {
                port["id"]: ({"ok": True} if port["id"] == "control" else {})
                for port in get_node_type(node["type"])["outputs"]
            }
            return behavior.get(node["id"], defaults)
        return execute
    return resolve


def test_order_is_deterministic_by_saved_order_then_id(tmp_path):
    workflow = _workflow(
        [_node("root"), _node("later", "project.setup"),
         _node("earlier", "project.setup"), _node("join", "project.setup")],
        [_edge("e1", "root", "control", "later", "trigger"),
         _edge("e2", "root", "control", "earlier", "trigger"),
         _edge("e3", "later", "control", "join", "trigger")],
    )
    assert deterministic_order(workflow) == ["root", "later", "earlier", "join"]
    calls = []
    result = WorkflowScheduler(workflow, project_id="pm_ABC123", lock_root=str(tmp_path / "locks"),
                               output_dir=str(tmp_path), executor_resolver=_resolver(calls)).run()
    assert [node_id for node_id, _ in calls] == result.order
    dependencies, reverse = dependency_maps(workflow)
    assert dependencies["join"] == {"later"}
    assert reverse["root"] == {"later", "earlier"}


def test_multi_input_and_diamond_join_wait_for_every_predecessor(tmp_path):
    nodes = [_node("source"), _node("left", "script.input", config={"text": "hello"}),
             _node("right", "project.setup"), _node("join", "tts.generate")]
    edges = [
        _edge("e1", "source", "control", "left", "trigger"),
        _edge("e2", "source", "control", "right", "trigger"),
        _edge("e3", "left", "script", "join", "script", "data"),
        _edge("e4", "right", "settings", "join", "settings", "data"),
    ]
    workflow = _workflow(nodes, edges)
    calls = []
    behavior = {
        "source": {"control": {"ok": True}},
        "left": {"control": {"ok": True}, "script": "script-value"},
        "right": {"control": {"ok": True}, "settings": {"tone": "test"}},
        "join": {"control": {"ok": True}, "audio": {}, "metadata": {}},
    }
    # Test executors deliberately expose extra ports; the scheduler consumes
    # only those named by graph edges.
    result = WorkflowScheduler(workflow, project_id="pm_ABC123", lock_root=str(tmp_path / "locks"),
                               output_dir=str(tmp_path), executor_resolver=_resolver(calls, behavior)).run()
    assert result.status == "succeeded"
    assert calls[-1] == ("join", {"script": "script-value", "settings": {"tone": "test"}})
    assert result.order == ["source", "left", "right", "join"]


def test_partial_run_scopes_on_branch_and_diamond_graph():
    #       root
    #      /    \
    #   left   right
    #      \    /
    #       join -> tail
    workflow = _workflow(
        [_node("root"), _node("left"), _node("right"), _node("join"), _node("tail")],
        [
            _edge("e1", "root", "control", "left", "trigger"),
            _edge("e2", "root", "control", "right", "trigger"),
            _edge("e3", "left", "control", "join", "trigger"),
            _edge("e4", "right", "control", "join", "trigger"),
            _edge("e5", "join", "control", "tail", "trigger"),
        ],
    )
    assert calculate_scope(workflow, "selected", ["left", "right"]) == ["root", "left", "right"]
    assert calculate_scope(workflow, "from_node", ["left"]) == ["left", "join", "tail"]
    assert calculate_scope(workflow, "retry_failed", ["join"]) == ["join"]
    assert calculate_scope(workflow, "retry_failed_desc", ["left"]) == ["left", "join", "tail"]


@pytest.mark.parametrize(
    ("mode", "targets", "message"),
    [
        ("selected", [], "at least one"),
        ("selected", ["root", "root"], "duplicates"),
        ("from_node", ["missing"], "Unknown target"),
        ("retry_failed", ["root", "left"], "exactly one"),
        ("not_a_mode", [], "Unsupported"),
    ],
)
def test_partial_run_scope_rejects_invalid_requests(mode, targets, message):
    workflow = _workflow([_node("root"), _node("left")], [])
    with pytest.raises(ValueError, match=message):
        calculate_scope(workflow, mode, targets)


def test_disabled_node_and_its_dependent_are_skipped_but_other_branch_runs(tmp_path):
    workflow = _workflow(
        [_node("root"), _node("off", "project.setup", disabled=True),
         _node("blocked", "project.setup"), _node("independent")],
        [_edge("e1", "root", "control", "off", "trigger"),
         _edge("e2", "off", "control", "blocked", "trigger")],
    )
    calls = []
    result = WorkflowScheduler(workflow, project_id="pm_ABC123", lock_root=str(tmp_path / "locks"),
                               output_dir=str(tmp_path), executor_resolver=_resolver(calls)).run()
    assert result.node_statuses == {
        "root": "succeeded", "off": "skipped", "blocked": "skipped", "independent": "succeeded",
    }
    assert [node_id for node_id, _ in calls] == ["root", "independent"]


def test_v1_stop_policy_skips_every_node_after_failure(tmp_path):
    workflow = _workflow([_node("bad"), _node("otherwise")], [])
    calls = []

    def resolver(node):
        def execute(inputs, config, context):
            calls.append(node["id"])
            if node["id"] == "bad":
                raise RuntimeError("boom")
            return {"control": {"ok": True}}
        return execute

    result = WorkflowScheduler(workflow, project_id="pm_ABC123", lock_root=str(tmp_path / "locks"),
                               output_dir=str(tmp_path), executor_resolver=resolver).run()
    assert result.status == "failed"
    assert result.node_statuses == {"bad": "failed", "otherwise": "skipped"}
    assert calls == ["bad"]


def test_project_lock_contention_is_non_blocking_and_releases(tmp_path):
    root = str(tmp_path / "locks")
    with ProjectLock("pm_ABC123", lock_root=root, execution_id="ex_FIRST1"):
        with pytest.raises(ProjectLockedError) as error:
            ProjectLock("pm_ABC123", lock_root=root, execution_id="ex_SECOND").acquire()
        assert error.value.code == "PROJECT_LOCKED"
        # Different projects never contend.
        with ProjectLock("pm_DEF456", lock_root=root):
            pass
    with ProjectLock("pm_ABC123", lock_root=root):
        pass


def test_concurrent_project_lock_has_exactly_one_winner(tmp_path):
    root = str(tmp_path / "locks")
    barrier = threading.Barrier(2)
    outcomes = []

    def attempt():
        barrier.wait()
        try:
            with ProjectLock("pm_ABC123", lock_root=root):
                outcomes.append("acquired")
                barrier.wait()
        except ProjectLockedError:
            outcomes.append("locked")
            barrier.wait()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["acquired", "locked"]


def test_artifact_is_only_visible_after_atomic_promotion(tmp_path):
    promoter = ArtifactPromoter(output_dir=str(tmp_path), execution_id="ex_TEST12")
    destination = tmp_path / "projects" / "pm_ABC123" / "result.txt"
    staged = promoter.stage_path(str(destination))
    with open(staged, "w", encoding="utf-8") as handle:
        handle.write("complete")
    assert not destination.exists()
    promoter.promote()
    assert destination.read_text(encoding="utf-8") == "complete"
    promoter.cleanup()
    assert not os.path.exists(promoter.staging_dir)


def test_scheduler_promotes_staged_artifact_only_after_adapter_success(tmp_path):
    workflow = _workflow([_node("root")], [])
    destination = tmp_path / "projects" / "pm_ABC123" / "result.txt"

    def resolver(node):
        def execute(inputs, config, context):
            staged = context.stage_artifact(str(destination))
            with open(staged, "w", encoding="utf-8") as handle:
                handle.write("published")
            assert not destination.exists()
            return {"control": {"ok": True}}
        return execute

    result = WorkflowScheduler(workflow, project_id="pm_ABC123", lock_root=str(tmp_path / "locks"),
                               output_dir=str(tmp_path), executor_resolver=resolver).run()
    assert result.status == "succeeded"
    assert destination.read_text(encoding="utf-8") == "published"
