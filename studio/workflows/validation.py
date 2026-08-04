"""Validation for persisted workflow definitions (Phase 1).

The canvas performs the same fast checks for UX, but this module is the
authoritative trust boundary for anything saved or imported.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from typing import Any

from .registry import DYNAMIC_PORT_TYPES, get_node_type, is_supported
from .sample_data import validate_stub_payload

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_NODES = 200
MAX_EDGES = 500
MAX_NESTING_DEPTH = 20
MAX_VARIABLES_BYTES = 64 * 1024
MAX_EXTENSIONS_BYTES = 64 * 1024

WORKFLOW_ID_RE = re.compile(r"^wf_[A-Z0-9]{6}$")
ELEMENT_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

_TOP_FIELDS = {
    "schema_version", "workflow_id", "name", "description", "nodes", "edges",
    "variables", "viewport", "settings", "created_at", "updated_at", "extensions",
}
_NODE_FIELDS = {
    "id", "type", "type_version", "name", "position", "configuration", "disabled",
    "extensions",
}
_EDGE_FIELDS = {
    "id", "source_node", "source_port", "target_node", "target_port", "edge_type",
    "extensions",
}


def _problem(code: str, message: str, path: str = "", *, severity: str = "error") -> dict:
    item = {"code": code, "message": message, "severity": severity}
    if path:
        item["path"] = path
    return item


def _json_size(value: Any) -> int:
    return len(json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8"))


def _json_shape_error(value: Any) -> str | None:
    """Return the first transport-independent JSON shape violation."""
    stack = [(value, 1)]
    seen: set[int] = set()
    while stack:
        item, depth = stack.pop()
        if isinstance(item, bool) or item is None or isinstance(item, str):
            continue
        if isinstance(item, (int, float)):
            if isinstance(item, float) and not math.isfinite(item):
                return "JSON numbers must be finite"
            continue
        if not isinstance(item, (dict, list)):
            return "Workflow contains a value that is not valid JSON"
        if depth > MAX_NESTING_DEPTH:
            return f"JSON nesting depth exceeds {MAX_NESTING_DEPTH}"
        identity = id(item)
        if identity in seen:
            return "Workflow contains a recursive JSON value"
        seen.add(identity)
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                return "JSON object keys must be strings"
            stack.extend((child, depth + 1) for child in item.values())
        else:
            stack.extend((child, depth + 1) for child in item)
    return None


def _valid_server_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not RFC3339_RE.fullmatch(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _validate_extensions(value: Any, path: str, problems: list[dict]) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        problems.append(_problem("WORKFLOW_INVALID", "extensions must be an object", path))
    elif _json_size(value) > MAX_EXTENSIONS_BYTES:
        problems.append(_problem("WORKFLOW_INVALID", "extensions exceeds 64 KiB", path))


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _port_type(node: dict, port: dict) -> str:
    if port.get("type") != "dynamic":
        return port.get("type", "")
    return (node.get("configuration") or {}).get("port_type", "")


def _field_is_visible(field: dict, configuration: dict) -> bool:
    display = field.get("display_options") or {}
    for reference, values in (display.get("show") or {}).items():
        if configuration.get(reference) not in values:
            return False
    for reference, values in (display.get("hide") or {}).items():
        if configuration.get(reference) in values:
            return False
    return True


def _validate_config(
    node: dict,
    definition: dict,
    path: str,
    problems: list[dict],
    *,
    require_complete: bool,
) -> None:
    config = node.get("configuration")
    if not isinstance(config, dict):
        problems.append(_problem("WORKFLOW_INVALID", "configuration must be an object", f"{path}.configuration"))
        return
    if _json_size(config) > 256 * 1024:
        problems.append(_problem("WORKFLOW_INVALID", "configuration exceeds 256 KiB", f"{path}.configuration"))
        return

    fields = {field["name"]: field for field in definition.get("config_schema", [])}
    for unknown in sorted(set(config) - set(fields)):
        problems.append(_problem("WORKFLOW_INVALID", f"Unknown configuration field: {unknown}", f"{path}.configuration.{unknown}"))

    for name, field in fields.items():
        value = config.get(name, field.get("default"))
        field_path = f"{path}.configuration.{name}"
        if field.get("required") and _field_is_visible(field, config) and (
            value is None or value == ""
        ):
            problems.append(_problem(
                "WORKFLOW_INVALID",
                f"{field.get('label', name)} is required",
                field_path,
                severity="error" if require_complete else "warning",
            ))
            continue
        if value is None:
            continue
        widget = field.get("type")
        if widget in {"string", "textarea"}:
            if not isinstance(value, str):
                problems.append(_problem("WORKFLOW_INVALID", "must be a string", field_path))
                continue
            if len(value) < field.get("min_length", 0) or len(value) > field.get("max_length", 100000):
                problems.append(_problem("WORKFLOW_INVALID", "string length is outside allowed limits", field_path))
            pattern = field.get("pattern")
            if pattern and value and not re.fullmatch(pattern, value):
                problems.append(_problem("WORKFLOW_INVALID", "value has an invalid format", field_path))
        elif widget == "number":
            if not _finite_number(value):
                problems.append(_problem("WORKFLOW_INVALID", "must be a finite number", field_path))
            elif value < field.get("min", -math.inf) or value > field.get("max", math.inf):
                problems.append(_problem("WORKFLOW_INVALID", "number is outside allowed limits", field_path))
        elif widget == "boolean" and not isinstance(value, bool):
            problems.append(_problem("WORKFLOW_INVALID", "must be a boolean", field_path))
        elif widget == "options":
            options = field.get("options")
            if options and value not in options:
                problems.append(_problem("WORKFLOW_INVALID", "value is not an allowed option", field_path))
        elif widget == "json":
            try:
                _json_size(value)
            except (TypeError, ValueError):
                problems.append(_problem("WORKFLOW_INVALID", "must be JSON-serializable", field_path))
        elif widget == "media_asset" and value is not None and not isinstance(value, dict):
            problems.append(_problem("WORKFLOW_INVALID", "must be a managed media reference", field_path))

    # Sample Input payloads are typed data, not free-form JSON: enforce the
    # per-port-type stub contract, including fixture-only file references
    # (contracts.md §2 "Utility/testing nodes", step 2.5).
    if node.get("type") == "stub.input" or (
        node.get("type") == "stub.output" and config.get("pinned") is True
    ):
        port_type = config.get("port_type", "generic_json")
        if port_type in DYNAMIC_PORT_TYPES:
            payload = config.get("payload", fields.get("payload", {}).get("default"))
            for stub_problem in validate_stub_payload(port_type, payload):
                problems.append(_problem(
                    stub_problem["code"],
                    stub_problem["message"],
                    f"{path}.configuration.payload",
                ))


def validate_workflow(document: Any, *, require_identity: bool = True, require_complete: bool = False) -> list[dict]:
    """Return structured errors/warnings for a workflow document."""
    problems: list[dict] = []
    if not isinstance(document, dict):
        return [_problem("WORKFLOW_INVALID", "Workflow must be a JSON object")]
    shape_error = _json_shape_error(document)
    if shape_error:
        return [_problem("WORKFLOW_INVALID", shape_error)]
    try:
        if _json_size(document) > MAX_DOCUMENT_BYTES:
            return [_problem("WORKFLOW_INVALID", "Workflow exceeds the 2 MiB limit")]
    except (TypeError, ValueError):
        return [_problem("WORKFLOW_INVALID", "Workflow is not valid JSON data")]

    for unknown in sorted(set(document) - _TOP_FIELDS):
        problems.append(_problem("WORKFLOW_INVALID", f"Unknown workflow field: {unknown}", unknown))
    if document.get("schema_version") != 1:
        problems.append(_problem("WORKFLOW_INVALID", "schema_version must be 1", "schema_version"))
    workflow_id = document.get("workflow_id")
    if (require_identity or workflow_id is not None) and (
        not isinstance(workflow_id, str) or not WORKFLOW_ID_RE.fullmatch(workflow_id)
    ):
        problems.append(_problem("WORKFLOW_INVALID", "workflow_id must match wf_XXXXXX", "workflow_id"))
    for field in ("created_at", "updated_at"):
        value = document.get(field)
        if (require_identity or value is not None) and not _valid_server_timestamp(value):
            problems.append(_problem("WORKFLOW_INVALID", f"{field} must be an RFC 3339 timestamp", field))
    name = document.get("name")
    if not isinstance(name, str) or not (1 <= len(name.strip()) <= 120):
        problems.append(_problem("WORKFLOW_INVALID", "name must contain 1–120 characters", "name"))
    description = document.get("description", "")
    if not isinstance(description, str) or len(description) > 2000:
        problems.append(_problem("WORKFLOW_INVALID", "description must be at most 2,000 characters", "description"))

    nodes = document.get("nodes")
    edges = document.get("edges")
    if not isinstance(nodes, list):
        problems.append(_problem("WORKFLOW_INVALID", "nodes must be an array", "nodes"))
        nodes = []
    elif len(nodes) > MAX_NODES:
        problems.append(_problem("WORKFLOW_INVALID", f"nodes exceeds the {MAX_NODES} item limit", "nodes"))
    if not isinstance(edges, list):
        problems.append(_problem("WORKFLOW_INVALID", "edges must be an array", "edges"))
        edges = []
    elif len(edges) > MAX_EDGES:
        problems.append(_problem("WORKFLOW_INVALID", f"edges exceeds the {MAX_EDGES} item limit", "edges"))

    node_map: dict[str, tuple[dict, dict]] = {}
    for index, node in enumerate(nodes):
        path = f"nodes[{index}]"
        if not isinstance(node, dict):
            problems.append(_problem("WORKFLOW_INVALID", "node must be an object", path))
            continue
        for unknown in sorted(set(node) - _NODE_FIELDS):
            problems.append(_problem("WORKFLOW_INVALID", f"Unknown node field: {unknown}", f"{path}.{unknown}"))
        node_id = node.get("id")
        if not isinstance(node_id, str) or not ELEMENT_ID_RE.fullmatch(node_id):
            problems.append(_problem("WORKFLOW_INVALID", "node id has an invalid format", f"{path}.id"))
            continue
        if node_id in node_map:
            problems.append(_problem("WORKFLOW_INVALID", f"Duplicate node id: {node_id}", f"{path}.id"))
            continue
        type_key = node.get("type")
        definition = get_node_type(type_key) if isinstance(type_key, str) else None
        if not definition:
            problems.append(_problem("UNKNOWN_NODE_TYPE", f"Unknown node type: {type_key}", f"{path}.type"))
            continue
        if not is_supported(type_key, node.get("type_version")):
            problems.append(_problem("UNSUPPORTED_NODE_VERSION", f"Unsupported version for {type_key}", f"{path}.type_version"))
        node_name = node.get("name")
        if not isinstance(node_name, str) or not (1 <= len(node_name.strip()) <= 120):
            problems.append(_problem("WORKFLOW_INVALID", "node name must contain 1–120 characters", f"{path}.name"))
        position = node.get("position")
        if not isinstance(position, dict) or set(position) != {"x", "y"} or not all(
            _finite_number(position.get(axis)) and -1_000_000 <= position[axis] <= 1_000_000 for axis in ("x", "y")
        ):
            problems.append(_problem("WORKFLOW_INVALID", "position must contain finite x/y coordinates", f"{path}.position"))
        if not isinstance(node.get("disabled"), bool):
            problems.append(_problem("WORKFLOW_INVALID", "disabled must be a boolean", f"{path}.disabled"))
        _validate_extensions(node.get("extensions"), f"{path}.extensions", problems)
        _validate_config(node, definition, path, problems, require_complete=require_complete)
        node_map[node_id] = (node, definition)

    edge_ids: set[str] = set()
    connections: set[tuple[str, str, str, str]] = set()
    occupied: set[tuple[str, str]] = set()
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_map}
    connected_inputs: set[tuple[str, str]] = set()
    for index, edge in enumerate(edges):
        path = f"edges[{index}]"
        if not isinstance(edge, dict):
            problems.append(_problem("WORKFLOW_INVALID", "edge must be an object", path))
            continue
        for unknown in sorted(set(edge) - _EDGE_FIELDS):
            problems.append(_problem("WORKFLOW_INVALID", f"Unknown edge field: {unknown}", f"{path}.{unknown}"))
        edge_id = edge.get("id")
        if not isinstance(edge_id, str) or not ELEMENT_ID_RE.fullmatch(edge_id):
            problems.append(_problem("WORKFLOW_INVALID", "edge id has an invalid format", f"{path}.id"))
        elif edge_id in edge_ids:
            problems.append(_problem("WORKFLOW_INVALID", f"Duplicate edge id: {edge_id}", f"{path}.id"))
        else:
            edge_ids.add(edge_id)
        _validate_extensions(edge.get("extensions"), f"{path}.extensions", problems)
        source_id, target_id = edge.get("source_node"), edge.get("target_node")
        if source_id not in node_map or target_id not in node_map:
            problems.append(_problem("WORKFLOW_INVALID", "edge endpoint does not exist", path))
            continue
        source_node, source_def = node_map[source_id]
        target_node, target_def = node_map[target_id]
        source_port = next((p for p in source_def["outputs"] if p["id"] == edge.get("source_port")), None)
        target_port = next((p for p in target_def["inputs"] if p["id"] == edge.get("target_port")), None)
        if not source_port or not target_port:
            problems.append(_problem("WORKFLOW_INVALID", "edge references an unknown port", path))
            continue
        source_type = _port_type(source_node, source_port)
        target_type = _port_type(target_node, target_port)
        if source_type not in DYNAMIC_PORT_TYPES + ["control"] or target_type not in DYNAMIC_PORT_TYPES + ["control"]:
            problems.append(_problem("PORT_TYPE_MISMATCH", "dynamic port_type is invalid", path))
            continue
        expected_edge_type = "control" if source_type == "control" else "data"
        if source_type != target_type or edge.get("edge_type") != expected_edge_type:
            problems.append(_problem("PORT_TYPE_MISMATCH", f"Cannot connect {source_type} to {target_type}", path))
            continue
        key = (source_id, source_port["id"], target_id, target_port["id"])
        if key in connections:
            problems.append(_problem("WORKFLOW_INVALID", "duplicate connection", path))
            continue
        connections.add(key)
        target_key = (target_id, target_port["id"])
        if not target_port.get("multiple") and target_key in occupied:
            problems.append(_problem("WORKFLOW_INVALID", "single-value input has multiple connections", path))
            continue
        occupied.add(target_key)
        connected_inputs.add(target_key)
        adjacency[source_id].append(target_id)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        if any(visit(target) for target in adjacency.get(node_id, [])):
            return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    if any(visit(node_id) for node_id in node_map if node_id not in visited):
        problems.append(_problem("CYCLE_DETECTED", "Workflow connections must form a DAG", "edges"))

    for node_id, (_, definition) in node_map.items():
        for port in definition.get("inputs", []):
            if port.get("required") and (node_id, port["id"]) not in connected_inputs:
                problems.append(_problem(
                    "MISSING_REQUIRED_INPUT",
                    f"{node_id}.{port['id']} is not connected",
                    f"nodes.{node_id}.inputs.{port['id']}",
                    severity="error" if require_complete else "warning",
                ))

    viewport = document.get("viewport", {"x": 0, "y": 0, "zoom": 1})
    if not isinstance(viewport, dict) or not all(_finite_number(viewport.get(k)) for k in ("x", "y", "zoom")) or not 0.1 <= viewport.get("zoom", 0) <= 1.5:
        problems.append(_problem("WORKFLOW_INVALID", "viewport is invalid", "viewport"))
    variables = document.get("variables", {})
    if not isinstance(variables, dict):
        problems.append(_problem("WORKFLOW_INVALID", "variables must be an object", "variables"))
    elif _json_size(variables) > MAX_VARIABLES_BYTES:
        problems.append(_problem("WORKFLOW_INVALID", "variables exceeds 64 KiB", "variables"))
    elif variables:
        problems.append(_problem("WORKFLOW_INVALID", "variables must remain empty until Phase 5", "variables"))
    _validate_extensions(document.get("extensions"), "extensions", problems)
    settings = document.get("settings", {"on_error": "stop"})
    if not isinstance(settings, dict):
        problems.append(_problem("WORKFLOW_INVALID", "settings must be an object", "settings"))
    else:
        for unknown in sorted(set(settings) - {"on_error", "auto_attach_stubs"}):
            problems.append(_problem("WORKFLOW_INVALID", f"Unknown settings field: {unknown}", f"settings.{unknown}"))
        if settings.get("on_error", "stop") != "stop":
            problems.append(_problem("WORKFLOW_INVALID", "settings.on_error must be stop in Phase 1", "settings.on_error"))
        if not isinstance(settings.get("auto_attach_stubs", True), bool):
            problems.append(_problem("WORKFLOW_INVALID", "settings.auto_attach_stubs must be a boolean", "settings.auto_attach_stubs"))
    return problems


def validation_errors(problems: list[dict]) -> list[dict]:
    return [problem for problem in problems if problem.get("severity") == "error"]
