"""Atomic file persistence for workflow definitions."""

from __future__ import annotations

import os
import random
import re
import shutil
import string
from copy import deepcopy
from datetime import datetime

from config import TRASH_DIR, WORKFLOWS_DIR, WORKFLOW_EXECUTIONS_DIR
from studio.io_utils import now_iso, safe_json_read, safe_json_write
from studio.security import safe_join

from .models import summary
from .redaction import redact
from .validation import WORKFLOW_ID_RE, validate_workflow, validation_errors


class WorkflowNotFound(FileNotFoundError):
    pass


class WorkflowConflict(RuntimeError):
    pass


class WorkflowValidationError(ValueError):
    def __init__(self, problems: list[dict]):
        super().__init__("Workflow has validation errors")
        self.problems = problems


EXECUTIONS_DIR = WORKFLOW_EXECUTIONS_DIR
EXECUTION_ID_RE = re.compile(r"^ex_[A-Za-z0-9]{6}$")


def _strict_id(workflow_id: str) -> str:
    if not isinstance(workflow_id, str) or not WORKFLOW_ID_RE.fullmatch(workflow_id):
        raise ValueError("workflow_id must match wf_XXXXXX")
    return workflow_id


def _path(workflow_id: str) -> str:
    return safe_join(WORKFLOWS_DIR, f"{_strict_id(workflow_id)}.json")


def _generate_id() -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(200):
        candidate = "wf_" + "".join(random.SystemRandom().choices(alphabet, k=6))
        if not os.path.exists(_path(candidate)):
            return candidate
    raise RuntimeError("Could not allocate a workflow id")


def _validate_or_raise(document: dict, *, require_complete: bool = False) -> list[dict]:
    problems = validate_workflow(document, require_identity=True, require_complete=require_complete)
    errors = validation_errors(problems)
    if errors:
        raise WorkflowValidationError(problems)
    return problems


def create_workflow(draft: dict) -> dict:
    document = deepcopy(draft)
    document["workflow_id"] = _generate_id()
    timestamp = now_iso()
    document["created_at"] = timestamp
    document["updated_at"] = timestamp
    document.setdefault("description", "")
    document.setdefault("variables", {})
    document.setdefault("viewport", {"x": 0, "y": 0, "zoom": 1})
    document.setdefault("settings", {"on_error": "stop"})
    document.setdefault("extensions", {})
    document = redact(document)
    _validate_or_raise(document)
    safe_json_write(_path(document["workflow_id"]), document, indent=2)
    return document


def load_workflow(workflow_id: str) -> dict:
    path = _path(workflow_id)
    try:
        document = safe_json_read(path)
    except FileNotFoundError as exc:
        raise WorkflowNotFound(workflow_id) from exc
    document = redact(document)
    _validate_or_raise(document)
    return document


def list_workflows(*, limit: int = 100) -> tuple[list[dict], int]:
    os.makedirs(WORKFLOWS_DIR, exist_ok=True)
    items = []
    for filename in os.listdir(WORKFLOWS_DIR):
        if not filename.endswith(".json") or filename.endswith(".json.bak"):
            continue
        workflow_id = filename[:-5]
        if not WORKFLOW_ID_RE.fullmatch(workflow_id):
            continue
        try:
            items.append(summary(load_workflow(workflow_id)))
        except (ValueError, OSError):
            continue
    items.sort(key=lambda item: (item.get("updated_at") or "", item["workflow_id"]), reverse=True)
    return items[:limit], len(items)


def update_workflow(workflow_id: str, draft: dict, *, expected_updated_at: str) -> dict:
    current = load_workflow(workflow_id)
    if not expected_updated_at or current.get("updated_at") != expected_updated_at:
        raise WorkflowConflict(workflow_id)
    document = deepcopy(draft)
    document["workflow_id"] = workflow_id
    document["created_at"] = current["created_at"]
    document["updated_at"] = now_iso()
    document = redact(document)
    _validate_or_raise(document)
    safe_json_write(_path(workflow_id), document, indent=2)
    return document


def delete_workflow(workflow_id: str, *, expected_updated_at: str | None = None) -> None:
    current = load_workflow(workflow_id)
    if expected_updated_at and current.get("updated_at") != expected_updated_at:
        raise WorkflowConflict(workflow_id)
    source = _path(workflow_id)
    trash_root = safe_join(TRASH_DIR, "workflows")
    os.makedirs(trash_root, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = safe_join(trash_root, f"{workflow_id}_{stamp}.json")
    shutil.move(source, destination)
    backup = source + ".bak"
    if os.path.isfile(backup):
        shutil.move(backup, destination + ".bak")


def import_workflow(document: dict, *, on_conflict: str = "new_id") -> tuple[dict, str | None]:
    original_id = document.get("workflow_id") if isinstance(document, dict) else None
    if on_conflict not in {"new_id", "reject"}:
        raise ValueError("on_conflict must be new_id or reject")
    if original_id is not None and (
        not isinstance(original_id, str) or not WORKFLOW_ID_RE.fullmatch(original_id)
    ):
        raise WorkflowValidationError([{
            "code": "WORKFLOW_INVALID",
            "message": "Imported workflow_id must match wf_XXXXXX",
            "severity": "error",
            "path": "workflow_id",
        }])
    if on_conflict == "reject" and isinstance(original_id, str) and WORKFLOW_ID_RE.fullmatch(original_id):
        if os.path.exists(_path(original_id)):
            raise WorkflowConflict(original_id)
    draft = deepcopy(document)
    for field in ("workflow_id", "created_at", "updated_at"):
        draft.pop(field, None)
    return create_workflow(draft), original_id


def _strict_execution_id(execution_id: str) -> str:
    if not isinstance(execution_id, str) or not EXECUTION_ID_RE.fullmatch(execution_id):
        raise ValueError("execution_id must match ex_XXXXXX")
    return execution_id


def execution_path(execution_id: str, *, root: str | None = None) -> str:
    return safe_join(root or EXECUTIONS_DIR, f"{_strict_execution_id(execution_id)}.json")


def generate_execution_id(*, root: str | None = None) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(200):
        candidate = "ex_" + "".join(random.SystemRandom().choices(alphabet, k=6))
        if not os.path.exists(execution_path(candidate, root=root)):
            return candidate
    raise RuntimeError("Could not allocate an execution id")


def save_execution(record, *, root: str | None = None, secrets=()) -> dict:
    """Atomically persist a redacted execution record and return that exact shape."""
    document = record.to_dict() if hasattr(record, "to_dict") else deepcopy(record)
    document = redact(document, secrets=secrets)
    _strict_execution_id(document.get("execution_id"))
    safe_json_write(execution_path(document["execution_id"], root=root), document, indent=2)
    return document


def load_execution(execution_id: str, *, root: str | None = None) -> dict:
    return safe_json_read(execution_path(execution_id, root=root))


def list_executions(workflow_id: str, *, limit: int = 100, root: str | None = None) -> tuple[list[dict], int]:
    if not isinstance(workflow_id, str) or not WORKFLOW_ID_RE.fullmatch(workflow_id):
        raise ValueError("workflow_id must match wf_XXXXXX")
    directory = root or EXECUTIONS_DIR
    os.makedirs(directory, exist_ok=True)
    items = []
    for filename in os.listdir(directory):
        execution_id = filename[:-5] if filename.endswith(".json") else ""
        if not EXECUTION_ID_RE.fullmatch(execution_id):
            continue
        try:
            record = load_execution(execution_id, root=directory)
        except (OSError, ValueError):
            continue
        if record.get("workflow_id") != workflow_id:
            continue
        items.append({
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "project_id": record.get("project_id"),
            "run_mode": record.get("run_mode"),
            "status": record.get("status"),
            "started_at": record.get("started_at"),
            "finished_at": record.get("finished_at"),
        })
    items.sort(key=lambda item: (item.get("started_at") or "", item["execution_id"]), reverse=True)
    return items[:limit], len(items)
