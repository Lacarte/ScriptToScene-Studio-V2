"""Flask blueprint for workflow registry and definition persistence."""

import json

from flask import Blueprint, Response, jsonify, request

from studio.security import is_loopback_remote
from .models import copy_draft
from .persistence import (
    WorkflowConflict,
    WorkflowNotFound,
    WorkflowValidationError,
    create_workflow,
    delete_workflow,
    import_workflow,
    list_workflows,
    load_workflow,
    update_workflow,
)
from .registry import serialize_registry
from .templates import serialize_templates
from .validation import MAX_DOCUMENT_BYTES, validate_workflow

workflows_bp = Blueprint("workflows", __name__)


def _error(code, message, status, details=None):
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return jsonify(body), status


def _require_loopback():
    if not is_loopback_remote(request.remote_addr):
        return _error("FORBIDDEN", "Workflow endpoints are local-only", 403)
    return None


def _json_body():
    if request.content_length and request.content_length > MAX_DOCUMENT_BYTES:
        return None, _error("REQUEST_TOO_LARGE", "Request exceeds the 2 MiB limit", 413)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, _error("BAD_REQUEST", "Request body must be a JSON object", 400)
    return body, None


def _persistence_error(exc):
    if isinstance(exc, WorkflowNotFound):
        return _error("NOT_FOUND", "Workflow not found", 404)
    if isinstance(exc, WorkflowConflict):
        return _error("WORKFLOW_CONFLICT", "Workflow changed since it was opened", 409)
    if isinstance(exc, WorkflowValidationError):
        return _error(
            "WORKFLOW_INVALID",
            "Workflow has validation errors",
            422,
            {"problems": exc.problems},
        )
    if isinstance(exc, ValueError):
        return _error("BAD_REQUEST", str(exc), 400)
    raise exc


@workflows_bp.route("/api/workflow/node-types", methods=["GET"])
def node_types():
    denied = _require_loopback()
    if denied:
        return denied
    return jsonify(serialize_registry())


@workflows_bp.route("/api/workflow/templates", methods=["GET"])
def workflow_templates():
    denied = _require_loopback()
    if denied:
        return denied
    return jsonify({"templates": serialize_templates()})


@workflows_bp.route("/api/workflow/validate", methods=["POST"])
def workflow_validate():
    """Structured validation for a draft document (contracts §6).

    Always 200 for a well-formed request — graph problems are data, not
    transport errors. `problems` = severity error, `warnings` = severity
    warning (e.g. required inputs still missing on an incomplete draft).
    """
    denied = _require_loopback()
    if denied:
        return denied
    body, failure = _json_body()
    if failure:
        return failure
    document = body.get("workflow")
    findings = validate_workflow(document, require_identity=False, require_complete=False)
    problems = [p for p in findings if p.get("severity") != "warning"]
    warnings = [p for p in findings if p.get("severity") == "warning"]
    return jsonify({"valid": not problems, "problems": problems, "warnings": warnings})


@workflows_bp.route("/api/workflows", methods=["GET"])
def workflows_list():
    denied = _require_loopback()
    if denied:
        return denied
    try:
        limit = int(request.args.get("limit", 100))
    except (TypeError, ValueError):
        return _error("BAD_REQUEST", "limit must be an integer", 400)
    if not 1 <= limit <= 200:
        return _error("BAD_REQUEST", "limit must be between 1 and 200", 400)
    items, total = list_workflows(limit=limit)
    return jsonify({"workflows": items, "total": total})


@workflows_bp.route("/api/workflows", methods=["POST"])
def workflows_create():
    denied = _require_loopback()
    if denied:
        return denied
    body, error = _json_body()
    if error:
        return error
    if not isinstance(body.get("workflow"), dict):
        return _error("BAD_REQUEST", "workflow must be an object", 400)
    try:
        document = create_workflow(copy_draft(body["workflow"]))
    except (ValueError, WorkflowValidationError) as exc:
        return _persistence_error(exc)
    response = jsonify({"workflow": document})
    response.status_code = 201
    response.headers["Location"] = f"/api/workflows/{document['workflow_id']}"
    return response


@workflows_bp.route("/api/workflows/import", methods=["POST"])
def workflows_import():
    denied = _require_loopback()
    if denied:
        return denied
    body, error = _json_body()
    if error:
        return error
    if not isinstance(body.get("workflow"), dict):
        return _error("BAD_REQUEST", "workflow must be an object", 400)
    try:
        document, original_id = import_workflow(
            body["workflow"], on_conflict=body.get("on_conflict", "new_id")
        )
    except (ValueError, WorkflowConflict, WorkflowValidationError) as exc:
        return _persistence_error(exc)
    return jsonify({"workflow": document, "imported_from_id": original_id}), 201


@workflows_bp.route("/api/workflows/<workflow_id>", methods=["GET"])
def workflows_get(workflow_id):
    denied = _require_loopback()
    if denied:
        return denied
    try:
        return jsonify({"workflow": load_workflow(workflow_id)})
    except (ValueError, WorkflowNotFound, WorkflowValidationError) as exc:
        return _persistence_error(exc)


@workflows_bp.route("/api/workflows/<workflow_id>", methods=["PUT"])
def workflows_update(workflow_id):
    denied = _require_loopback()
    if denied:
        return denied
    body, error = _json_body()
    if error:
        return error
    if not isinstance(body.get("workflow"), dict):
        return _error("BAD_REQUEST", "workflow must be an object", 400)
    try:
        document = update_workflow(
            workflow_id,
            body["workflow"],
            expected_updated_at=body.get("expected_updated_at", ""),
        )
    except (ValueError, WorkflowNotFound, WorkflowConflict, WorkflowValidationError) as exc:
        return _persistence_error(exc)
    return jsonify({"workflow": document})


@workflows_bp.route("/api/workflows/<workflow_id>", methods=["DELETE"])
def workflows_delete(workflow_id):
    denied = _require_loopback()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return _error("BAD_REQUEST", "Request body must be a JSON object", 400)
    try:
        delete_workflow(workflow_id, expected_updated_at=body.get("expected_updated_at"))
    except (ValueError, WorkflowNotFound, WorkflowConflict, WorkflowValidationError) as exc:
        return _persistence_error(exc)
    return jsonify({"deleted": True, "workflow_id": workflow_id})


@workflows_bp.route("/api/workflows/<workflow_id>/export", methods=["GET"])
def workflows_export(workflow_id):
    denied = _require_loopback()
    if denied:
        return denied
    try:
        document = load_workflow(workflow_id)
    except (ValueError, WorkflowNotFound, WorkflowValidationError) as exc:
        return _persistence_error(exc)
    payload = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    return Response(
        payload,
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{workflow_id}.json"'},
    )
