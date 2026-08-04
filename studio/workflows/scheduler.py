"""Deterministic, sequential workflow scheduling and project serialization.

The scheduler deliberately contains no Flask state.  It consumes a validated
workflow snapshot and invokes registry adapters directly, which makes ordering
and readiness independently testable.
"""

from __future__ import annotations

import heapq
import importlib
import json
import os
import shutil
import tempfile
import threading
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from config import OUTPUT_DIR
from studio.io_utils import now_iso
from studio.security import safe_join

from .adapters import AdapterContext, AdapterError
from .adapters.common import PROJECT_ID_RE
from .registry import get_node_type
from .models import ExecutionLog, ExecutionRecord, NodeExecutionRecord
from .persistence import generate_execution_id, save_execution
from .redaction import Redactor
from .validation import validate_workflow, validation_errors


class SchedulerError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


class ProjectLockedError(SchedulerError):
    def __init__(self, project_id: str):
        super().__init__(
            "PROJECT_LOCKED",
            f"Project {project_id} already has an active execution",
            details={"project_id": project_id},
        )


class CancellationRequested(SchedulerError):
    def __init__(self):
        super().__init__("CANCELLED", "Execution was cancelled")


class ProjectLock(AbstractContextManager):
    """Non-blocking in-process and cross-process lock for one project."""

    _guard = threading.Lock()
    _held: set[str] = set()

    def __init__(self, project_id: str, *, lock_root: str | None = None, execution_id: str = ""):
        if not isinstance(project_id, str) or not PROJECT_ID_RE.fullmatch(project_id):
            raise SchedulerError("PROJECT_ID_INVALID", "A strict pp_/pm_ project ID is required")
        self.project_id = project_id
        self.execution_id = execution_id
        self.lock_root = lock_root or os.path.join(OUTPUT_DIR, "workflows", "locks")
        self.path = safe_join(self.lock_root, f"{project_id}.lock")
        self._lock_key = os.path.normcase(os.path.abspath(self.path))
        self._acquired = False

    def acquire(self) -> "ProjectLock":
        os.makedirs(self.lock_root, exist_ok=True)
        with self._guard:
            if self._lock_key in self._held:
                raise ProjectLockedError(self.project_id)
            self._held.add(self._lock_key)
        try:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            fd = os.open(self.path, flags, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({
                    "project_id": self.project_id,
                    "execution_id": self.execution_id,
                    "pid": os.getpid(),
                }, handle)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError as exc:
            with self._guard:
                self._held.discard(self._lock_key)
            raise ProjectLockedError(self.project_id) from exc
        except BaseException:
            with self._guard:
                self._held.discard(self._lock_key)
            raise
        self._acquired = True
        return self

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        finally:
            with self._guard:
                self._held.discard(self._lock_key)
            self._acquired = False

    def __enter__(self) -> "ProjectLock":
        return self.acquire()

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self.release()
        return False


class ArtifactPromoter:
    """Give adapters staged paths and atomically publish them after success."""

    def __init__(self, *, output_dir: str = OUTPUT_DIR, execution_id: str = "execution"):
        self.output_dir = os.path.abspath(output_dir)
        staging_root = os.path.join(self.output_dir, "workflows", ".staging")
        os.makedirs(staging_root, exist_ok=True)
        self.staging_dir = tempfile.mkdtemp(prefix=f"{execution_id}_", dir=staging_root)
        self._pending: list[tuple[str, str]] = []

    def stage_path(self, destination: str) -> str:
        destination = self._destination(destination)
        suffix = os.path.splitext(destination)[1]
        fd, staged = tempfile.mkstemp(prefix="artifact_", suffix=suffix, dir=self.staging_dir)
        os.close(fd)
        os.unlink(staged)  # callers commonly require a path which does not exist
        self._pending.append((staged, destination))
        return staged

    def _destination(self, destination: str) -> str:
        candidate = destination if os.path.isabs(destination) else safe_join(self.output_dir, destination)
        candidate = os.path.abspath(candidate)
        try:
            inside = os.path.commonpath([self.output_dir, candidate]) == self.output_dir
        except ValueError:
            inside = False
        if not inside:
            raise SchedulerError("ARTIFACT_UNMANAGED", "Artifact destination is outside the managed output directory")
        return candidate

    def promote(self) -> None:
        for staged, destination in self._pending:
            if not os.path.isfile(staged):
                raise SchedulerError("ARTIFACT_MISSING", f"Staged artifact was not created: {staged}")
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            # Copy into the destination directory first.  os.replace then
            # publishes on the destination filesystem in one atomic step.
            fd, local_stage = tempfile.mkstemp(prefix=".promote_", dir=os.path.dirname(destination))
            os.close(fd)
            try:
                shutil.copy2(staged, local_stage)
                os.replace(local_stage, destination)
            finally:
                try:
                    os.unlink(local_stage)
                except FileNotFoundError:
                    pass
        self._pending.clear()

    def cleanup(self) -> None:
        shutil.rmtree(self.staging_dir, ignore_errors=True)


@dataclass
class ScheduleResult:
    status: str
    order: list[str]
    node_statuses: dict[str, str]
    outputs: dict[str, dict[str, Any]]
    errors: dict[str, dict[str, Any]] = field(default_factory=dict)
    execution_record: dict[str, Any] | None = None


def _summarize(value: Any, *, depth: int = 0) -> Any:
    """Create a bounded diagnostic summary instead of persisting payload bodies."""
    if depth >= 4:
        return {"type": type(value).__name__}
    if isinstance(value, str):
        return {"chars": len(value)}
    if isinstance(value, bytes):
        return {"bytes": len(value)}
    if isinstance(value, Mapping):
        summary = {str(key): _summarize(child, depth=depth + 1) for key, child in list(value.items())[:30]}
        if len(value) > 30:
            summary["_truncated_keys"] = len(value) - 30
        return summary
    if isinstance(value, (list, tuple)):
        result = {"count": len(value)}
        if value:
            result["items"] = [_summarize(child, depth=depth + 1) for child in value[:3]]
        return result
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return {"type": type(value).__name__}


def _artifact_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, Mapping):
        candidates = value.get("artifact_refs")
        if isinstance(candidates, list):
            refs.extend(item for item in candidates if isinstance(item, str))
        for child in value.values():
            refs.extend(_artifact_refs(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            refs.extend(_artifact_refs(child))
    return list(dict.fromkeys(refs))


@dataclass(frozen=True)
class WorkflowGraph:
    nodes: dict[str, dict]
    incoming: dict[str, list[dict]]
    dependents: dict[str, list[str]]
    saved_order: dict[str, int]


def build_graph(workflow: Mapping[str, Any]) -> WorkflowGraph:
    nodes = {node["id"]: node for node in workflow.get("nodes", [])}
    incoming = {node_id: [] for node_id in nodes}
    dependents = {node_id: [] for node_id in nodes}
    for edge in workflow.get("edges", []):
        incoming[edge["target_node"]].append(edge)
        dependents[edge["source_node"]].append(edge["target_node"])
    return WorkflowGraph(
        nodes=nodes,
        incoming=incoming,
        dependents=dependents,
        saved_order={node["id"]: index for index, node in enumerate(workflow.get("nodes", []))},
    )


def deterministic_order(workflow: Mapping[str, Any]) -> list[str]:
    """Return stable topological order (saved node order, then node ID)."""
    graph = build_graph(workflow)
    remaining = {node_id: len(edges) for node_id, edges in graph.incoming.items()}
    ready = [(graph.saved_order[node_id], node_id) for node_id, count in remaining.items() if count == 0]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        _, node_id = heapq.heappop(ready)
        order.append(node_id)
        for target in graph.dependents[node_id]:
            remaining[target] -= 1
            if remaining[target] == 0:
                heapq.heappush(ready, (graph.saved_order[target], target))
    if len(order) != len(graph.nodes):
        raise SchedulerError("CYCLE_DETECTED", "Workflow connections must form a DAG")
    return order


def dependency_maps(workflow: Mapping[str, Any]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Return predecessor and reverse/dependent maps for scope calculations."""
    graph = build_graph(workflow)
    dependencies = {
        node_id: {edge["source_node"] for edge in edges}
        for node_id, edges in graph.incoming.items()
    }
    reverse_dependencies = {
        node_id: set(targets) for node_id, targets in graph.dependents.items()
    }
    return dependencies, reverse_dependencies


RUN_MODES = {
    "full",
    "node_with_deps",
    "node_isolated",
    "selected",
    "from_node",
    "retry_failed",
    "retry_failed_desc",
}


def calculate_scope(
    workflow: Mapping[str, Any],
    run_mode: str,
    target_node_ids: list[str],
) -> list[str]:
    """Calculate a stable execution subgraph for every topology-based run mode.

    Isolation has input-port semantics in addition to graph topology and is
    completed by ``execution.resolve_scope`` after this function validates its
    target.  Returned IDs always follow saved node order, never traversal order.
    """
    if run_mode not in RUN_MODES:
        raise ValueError(f"Unsupported run_mode: {run_mode}")
    saved_ids = [node["id"] for node in workflow.get("nodes", [])]
    known_ids = set(saved_ids)
    if not isinstance(target_node_ids, list):
        raise ValueError("target_node_ids must be an array of node IDs")
    if len(set(target_node_ids)) != len(target_node_ids):
        raise ValueError("target_node_ids must not contain duplicates")
    unknown = [node_id for node_id in target_node_ids if node_id not in known_ids]
    if unknown:
        raise ValueError(f"Unknown target node: {unknown[0]}")

    if run_mode == "full":
        if target_node_ids:
            raise ValueError("full mode does not accept target_node_ids")
        return saved_ids

    if run_mode == "selected":
        if not target_node_ids:
            raise ValueError("selected requires at least one existing target node")
        seeds = set(target_node_ids)
        direction = "dependencies"
    else:
        if len(target_node_ids) != 1:
            raise ValueError(f"{run_mode} requires exactly one existing target node")
        seeds = {target_node_ids[0]}
        if run_mode in {"node_with_deps"}:
            direction = "dependencies"
        elif run_mode in {"from_node", "retry_failed_desc"}:
            direction = "descendants"
        else:
            # node_isolated and retry_failed contain only their target at the
            # topology layer. Isolation may add directly-connected stubs.
            return [node_id for node_id in saved_ids if node_id in seeds]

    dependencies, descendants = dependency_maps(workflow)
    adjacency = dependencies if direction == "dependencies" else descendants
    scope = set(seeds)
    pending = list(seeds)
    while pending:
        node_id = pending.pop()
        for related_id in adjacency[node_id]:
            if related_id not in scope:
                scope.add(related_id)
                pending.append(related_id)
    return [node_id for node_id in saved_ids if node_id in scope]


def resolve_executor(node: Mapping[str, Any]) -> Callable:
    definition = get_node_type(node.get("type"))
    spec = definition.get("executor") if definition else None
    if not spec or ":" not in spec:
        raise SchedulerError("NODE_EXECUTOR_MISSING", f"No executor is registered for {node.get('type')}")
    module_name, function_name = spec.split(":", 1)
    function = getattr(importlib.import_module(module_name), function_name, None)
    if not callable(function):
        raise SchedulerError("NODE_EXECUTOR_MISSING", f"Executor {spec} is not callable")
    return function


class WorkflowScheduler:
    def __init__(
        self,
        workflow: Mapping[str, Any],
        *,
        project_id: str,
        execution_id: str = "",
        executor_resolver: Callable[[Mapping[str, Any]], Callable] = resolve_executor,
        lock_root: str | None = None,
        output_dir: str = OUTPUT_DIR,
        on_status: Callable[[str, str], None] | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        run_mode: str = "full",
        scope_node_ids: list[str] | None = None,
        stop_requested: Callable[[], bool] | None = None,
    ):
        problems = validation_errors(validate_workflow(dict(workflow), require_complete=True))
        if problems:
            raise SchedulerError("WORKFLOW_INVALID", "Workflow has validation errors", details={"problems": problems})
        if not isinstance(project_id, str) or not PROJECT_ID_RE.fullmatch(project_id):
            raise SchedulerError("PROJECT_ID_INVALID", "A strict pp_/pm_ project ID is required")
        self.workflow = dict(workflow)
        self.project_id = project_id
        execution_root = os.path.join(output_dir, "workflows", "executions")
        self.execution_id = execution_id or generate_execution_id(root=execution_root)
        self.executor_resolver = executor_resolver
        self.lock_root = lock_root
        self.output_dir = output_dir
        self.on_status = on_status
        self.on_event = on_event
        self.run_mode = run_mode
        self.scope_node_ids = list(scope_node_ids or [node["id"] for node in workflow.get("nodes", [])])
        self.stop_requested = stop_requested or (lambda: False)
        self.execution_root = execution_root
        self.redactor = Redactor(workflow)
        self.record = ExecutionRecord(
            execution_id=self.execution_id,
            workflow_id=str(workflow.get("workflow_id", "")),
            workflow_snapshot=self.redactor(workflow),
            project_id=project_id,
            run_mode=run_mode,
            scope_node_ids=self.scope_node_ids,
            started_at=now_iso(),
            nodes={node["id"]: NodeExecutionRecord() for node in workflow.get("nodes", [])},
        )

    def run(self) -> ScheduleResult:
        scope = set(self.scope_node_ids)
        scoped_workflow = {
            **self.workflow,
            "nodes": [node for node in self.workflow.get("nodes", []) if node["id"] in scope],
            "edges": [
                edge for edge in self.workflow.get("edges", [])
                if edge["source_node"] in scope and edge["target_node"] in scope
            ],
        }
        graph = build_graph(scoped_workflow)
        order = deterministic_order(scoped_workflow)
        statuses = {node_id: "idle" for node_id in graph.nodes}
        node_outputs: dict[str, dict[str, Any]] = {}
        errors: dict[str, dict[str, Any]] = {}
        executed: list[str] = []
        self._persist()
        self._emit({"type": "execution_status", "node_id": None, "status": "running"})

        with ProjectLock(self.project_id, lock_root=self.lock_root, execution_id=self.execution_id):
            stopped = False
            cancelled = False
            for node_id in order:
                node = graph.nodes[node_id]
                if self.stop_requested():
                    cancelled = True
                predecessor_statuses = [statuses[edge["source_node"]] for edge in graph.incoming[node_id]]
                if cancelled:
                    self.record.nodes[node_id].duration_ms = 0
                    self._status(statuses, node_id, "cancelled")
                    executed.append(node_id)
                    continue
                if stopped or node.get("disabled") or any(status != "succeeded" for status in predecessor_statuses):
                    self.record.nodes[node_id].duration_ms = 0
                    self._status(statuses, node_id, "skipped")
                    executed.append(node_id)
                    continue

                inputs = self._resolve_inputs(node_id, graph, node_outputs)
                node_record = self.record.nodes[node_id]
                node_record.from_sample_data = (
                    node.get("type") == "stub.input"
                    or any(
                        self.record.nodes[edge["source_node"]].from_sample_data
                        for edge in graph.incoming[node_id]
                    )
                )
                node_record.resolved_inputs_summary = self.redactor(_summarize(inputs))
                node_record.attempts += 1
                self._status(statuses, node_id, "running")
                started = time.perf_counter()
                promoter = ArtifactPromoter(output_dir=self.output_dir, execution_id=self.execution_id or node_id)
                context = AdapterContext(
                    project_id=self.project_id,
                    execution_id=self.execution_id,
                    node_id=node_id,
                    stage_artifact=promoter.stage_path,
                    stop_requested=self.stop_requested,
                )
                try:
                    result = self.executor_resolver(node)(inputs, self._configuration(node), context)
                    if self.stop_requested():
                        raise CancellationRequested()
                    if not isinstance(result, Mapping):
                        raise SchedulerError("NODE_OUTPUT_INVALID", f"Node {node_id} returned a non-object output")
                    result = dict(result)
                    self._validate_outputs(node, result)
                    promoter.promote()
                    node_outputs[node_id] = result
                    node_record.outputs_summary = self.redactor(_summarize(result))
                    node_record.artifact_refs = self.redactor(_artifact_refs(result))
                    node_record.duration_ms = max(0, round((time.perf_counter() - started) * 1000))
                    self._status(statuses, node_id, "succeeded")
                except CancellationRequested:
                    cancelled = True
                    node_record.error = {"code": "CANCELLED", "message": "Execution was cancelled"}
                    node_record.duration_ms = max(0, round((time.perf_counter() - started) * 1000))
                    self._status(statuses, node_id, "cancelled")
                except (AdapterError, SchedulerError) as exc:
                    code = getattr(exc, "code", "NODE_EXECUTION_FAILED")
                    if code == "CANCELLED":
                        cancelled = True
                        node_record.error = {"code": "CANCELLED", "message": "Execution was cancelled"}
                        node_record.duration_ms = max(0, round((time.perf_counter() - started) * 1000))
                        self._status(statuses, node_id, "cancelled")
                        executed.append(node_id)
                        continue
                    errors[node_id] = self.redactor(
                        {"code": code, "message": str(exc), "details": getattr(exc, "details", None)}
                    )
                    node_record.error = errors[node_id]
                    node_record.logs.append(self.redactor(ExecutionLog(
                        ts=now_iso(), level="error", message=str(exc)
                    ).__dict__))
                    self._emit({"type": "node_error", "execution_id": self.execution_id,
                                "node_id": node_id, "error": errors[node_id]})
                    node_record.duration_ms = max(0, round((time.perf_counter() - started) * 1000))
                    self._status(statuses, node_id, "failed")
                    stopped = True
                except Exception as exc:  # adapters are a plugin boundary
                    errors[node_id] = self.redactor(
                        {"code": "NODE_EXECUTION_FAILED", "message": str(exc), "details": None}
                    )
                    node_record.error = errors[node_id]
                    node_record.logs.append(self.redactor(ExecutionLog(
                        ts=now_iso(), level="error", message=str(exc)
                    ).__dict__))
                    self._emit({"type": "node_error", "execution_id": self.execution_id,
                                "node_id": node_id, "error": errors[node_id]})
                    node_record.duration_ms = max(0, round((time.perf_counter() - started) * 1000))
                    self._status(statuses, node_id, "failed")
                    stopped = True
                finally:
                    promoter.cleanup()
                executed.append(node_id)

        overall = "cancelled" if cancelled or self.stop_requested() else ("failed" if errors else "succeeded")
        self.record.status = overall
        self.record.finished_at = now_iso()
        persisted = self._persist()
        self._emit({"type": "execution_finished", "node_id": None, "status": overall})
        return ScheduleResult(overall, executed, statuses, node_outputs, errors, persisted)

    def _status(self, statuses: dict[str, str], node_id: str, status: str) -> None:
        statuses[node_id] = status
        node_record = self.record.nodes[node_id]
        node_record.status = status
        node_record.logs.append(self.redactor(ExecutionLog(
            ts=now_iso(), level="info", message=f"Node status changed to {status}"
        ).__dict__))
        self._persist()
        if self.on_status:
            self.on_status(node_id, status)
        self._emit({
            "type": "node_status",
            "execution_id": self.execution_id,
            "node_id": node_id,
            "status": status,
            "attempt": node_record.attempts,
            "duration_ms": node_record.duration_ms or 0,
            "from_sample_data": node_record.from_sample_data,
        })

    def _persist(self) -> dict[str, Any]:
        return save_execution(self.record, root=self.execution_root, secrets=self.redactor.secrets)

    def _emit(self, event: dict[str, Any]) -> None:
        if self.on_event:
            self.on_event(self.redactor(event))

    @staticmethod
    def _configuration(node: Mapping[str, Any]) -> dict[str, Any]:
        definition = get_node_type(node["type"])
        config = {
            field["name"]: field["default"]
            for field in definition.get("config_schema", [])
            if "default" in field
        }
        config.update(node.get("configuration") or {})
        return config

    @staticmethod
    def _resolve_inputs(node_id: str, graph: WorkflowGraph, outputs: Mapping[str, Mapping[str, Any]]) -> dict:
        resolved: dict[str, Any] = {}
        for edge in graph.incoming[node_id]:
            value = outputs[edge["source_node"]][edge["source_port"]]
            target_port = edge["target_port"]
            definition = get_node_type(graph.nodes[node_id]["type"])
            port = next(item for item in definition["inputs"] if item["id"] == target_port)
            if port.get("multiple"):
                resolved.setdefault(target_port, []).append(value)
            else:
                resolved[target_port] = value
        return resolved

    @staticmethod
    def _validate_outputs(node: Mapping[str, Any], outputs: Mapping[str, Any]) -> None:
        definition = get_node_type(node["type"])
        for port in definition.get("outputs", []):
            if port["id"] not in outputs:
                raise SchedulerError(
                    "NODE_OUTPUT_MISSING",
                    f"Node {node['id']} did not produce output port {port['id']}",
                )


# Short alias for callers which prefer the plan's noun.
Scheduler = WorkflowScheduler
