"""Asynchronous workflow execution orchestration for the HTTP API."""

from __future__ import annotations

import os
import random
import string
import threading
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from config import OUTPUT_DIR, generate_project_id
from studio.io_utils import JobStore, now_iso

from .adapters.common import PROJECT_ID_RE
from .events import EventBroker, ExecutionEventBuffer, TERMINAL_STATUSES
from .persistence import generate_execution_id, load_execution, save_execution
from .registry import get_node_type
from .scheduler import WorkflowScheduler, dependency_maps, resolve_executor
from .validation import validate_workflow, validation_errors


RUN_MODES = {"full", "node_with_deps", "node_isolated"}


class ExecutionRequestError(ValueError):
    def __init__(self, code: str, message: str, *, details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details


@dataclass
class ActiveExecution:
    scheduler: WorkflowScheduler
    stop_event: threading.Event
    thread: threading.Thread | None = None


def _transient_workflow_id() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "wf_" + "".join(random.SystemRandom().choices(alphabet, k=6))


def prepare_snapshot(document: Mapping[str, Any]) -> dict[str, Any]:
    snapshot = deepcopy(dict(document))
    if "workflow_id" not in snapshot:
        snapshot["workflow_id"] = _transient_workflow_id()
    timestamp = now_iso()
    snapshot.setdefault("created_at", timestamp)
    snapshot.setdefault("updated_at", timestamp)
    problems = validation_errors(validate_workflow(snapshot, require_identity=True, require_complete=True))
    if problems:
        raise ExecutionRequestError(
            "WORKFLOW_INVALID", "Workflow has validation errors", details={"problems": problems}
        )
    return snapshot


def resolve_scope(workflow: Mapping[str, Any], run_mode: str, target_node_ids: list[str]) -> list[str]:
    if run_mode not in RUN_MODES:
        raise ExecutionRequestError("BAD_REQUEST", f"Unsupported run_mode: {run_mode}")
    nodes = {node["id"]: node for node in workflow.get("nodes", [])}
    if run_mode == "full":
        if target_node_ids:
            raise ExecutionRequestError("BAD_REQUEST", "full mode does not accept target_node_ids")
        return list(nodes)
    if len(target_node_ids) != 1 or target_node_ids[0] not in nodes:
        raise ExecutionRequestError("BAD_REQUEST", f"{run_mode} requires exactly one existing target node")

    target = target_node_ids[0]
    dependencies, _ = dependency_maps(workflow)
    if run_mode == "node_with_deps":
        scope: set[str] = set()

        def include(node_id: str) -> None:
            if node_id in scope:
                return
            scope.add(node_id)
            for predecessor in dependencies[node_id]:
                include(predecessor)

        include(target)
        return [node_id for node_id in nodes if node_id in scope]

    # Isolation deliberately ignores normal upstream nodes. Required inputs
    # must instead be supplied by directly connected Sample Input nodes.
    incoming = [edge for edge in workflow.get("edges", []) if edge["target_node"] == target]
    stub_ids = {
        edge["source_node"] for edge in incoming
        if nodes[edge["source_node"]].get("type") == "stub.input"
    }
    definition = get_node_type(nodes[target]["type"])
    for port in definition.get("inputs", []):
        if not port.get("required"):
            continue
        sources = [edge["source_node"] for edge in incoming if edge["target_port"] == port["id"]]
        if not sources or any(source not in stub_ids for source in sources):
            raise ExecutionRequestError(
                "MISSING_REQUIRED_INPUT",
                f"Isolated node {target} requires Sample Input data for port {port['id']}",
            )
    scope = stub_ids | {target}
    return [node_id for node_id in nodes if node_id in scope]


def resolve_project_id(workflow: Mapping[str, Any], requested: str | None) -> str:
    if requested is not None and (not isinstance(requested, str) or not PROJECT_ID_RE.fullmatch(requested)):
        raise ExecutionRequestError("BAD_REQUEST", "project_id must match pp_/pm_XXXXXX")
    existing = [
        (node.get("configuration") or {}).get("project_id")
        for node in workflow.get("nodes", [])
        if node.get("type") == "project.existing" and not node.get("disabled")
    ]
    existing = [value for value in existing if value]
    if len(set(existing)) > 1:
        raise ExecutionRequestError("WORKFLOW_INVALID", "Enabled existing-project nodes disagree")
    if existing and requested and existing[0] != requested:
        raise ExecutionRequestError("WORKFLOW_INVALID", "Requested project_id disagrees with project.existing")
    return requested or (existing[0] if existing else generate_project_id("pm"))


class ExecutionManager:
    def __init__(
        self,
        *,
        output_dir: str = OUTPUT_DIR,
        max_events: int = 1000,
        executor_resolver=resolve_executor,
    ):
        self.output_dir = output_dir
        self.execution_root = os.path.join(output_dir, "workflows", "executions")
        self.active = JobStore()
        self.events = EventBroker(max_events=max_events)
        self.executor_resolver = executor_resolver

    def start(
        self,
        workflow: Mapping[str, Any],
        *,
        run_mode: str,
        target_node_ids: list[str],
        project_id: str | None = None,
    ) -> tuple[str, str]:
        snapshot = prepare_snapshot(workflow)
        scope = resolve_scope(snapshot, run_mode, target_node_ids)
        resolved_project = resolve_project_id(snapshot, project_id)
        execution_id = generate_execution_id(root=self.execution_root)
        stream = self.events.create(execution_id)
        stop_event = threading.Event()
        scheduler = WorkflowScheduler(
            snapshot,
            project_id=resolved_project,
            execution_id=execution_id,
            output_dir=self.output_dir,
            run_mode=run_mode,
            scope_node_ids=scope,
            stop_requested=stop_event.is_set,
            on_event=stream.emit,
            executor_resolver=self.executor_resolver,
        )
        save_execution(scheduler.record, root=self.execution_root, secrets=scheduler.redactor.secrets)
        stream.emit({"type": "execution_status", "node_id": None, "status": "queued"})
        handle = ActiveExecution(scheduler=scheduler, stop_event=stop_event)
        thread = threading.Thread(
            target=self._run,
            args=(handle, stream),
            name=f"workflow-{execution_id}",
            daemon=True,
        )
        handle.thread = thread
        self.active.set(execution_id, handle)
        thread.start()
        return execution_id, resolved_project

    def _run(self, handle: ActiveExecution, stream: ExecutionEventBuffer) -> None:
        try:
            handle.scheduler.run()
        except Exception as exc:  # lock acquisition and scheduler setup boundary
            record = handle.scheduler.record
            status = "cancelled" if handle.stop_event.is_set() else "failed"
            record.status = status
            record.finished_at = now_iso()
            save_execution(record, root=self.execution_root, secrets=handle.scheduler.redactor.secrets)
            stream.emit({
                "type": "execution_finished",
                "node_id": None,
                "status": status,
                "error": {
                    "code": getattr(exc, "code", "NODE_EXECUTION_FAILED"),
                    "message": str(exc),
                },
            })

    def stop(self, execution_id: str) -> str:
        record = load_execution(execution_id, root=self.execution_root)
        if record.get("status") in TERMINAL_STATUSES:
            raise ExecutionRequestError("EXECUTION_TERMINAL", "Execution is already terminal")
        handle = self.active.get(execution_id)
        if handle is None:
            raise ExecutionRequestError("EXECUTION_NOT_ACTIVE", "Execution is not active")
        handle.stop_event.set()
        self.events.create(execution_id).emit({
            "type": "execution_status", "node_id": None, "status": "cancelling"
        })
        return "cancelling"


execution_manager = ExecutionManager()
