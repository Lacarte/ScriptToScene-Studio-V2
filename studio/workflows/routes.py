"""Flask blueprint for the workflow builder API.

Step 1.2 scope: node-type catalog only. Workflow CRUD (1.6), validation
(2.2), and execution (Phase 3) extend this blueprint. Contracts: all
endpoints are local-app endpoints (loopback-only) and errors use the
single `{error: {code, message, details}}` envelope.
"""

from flask import Blueprint, jsonify, request

from studio.security import is_loopback_remote
from .registry import serialize_registry

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


@workflows_bp.route("/api/workflow/node-types", methods=["GET"])
def node_types():
    denied = _require_loopback()
    if denied:
        return denied
    return jsonify(serialize_registry())
