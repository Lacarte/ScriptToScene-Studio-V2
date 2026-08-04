"""Small constructors for the persisted workflow document shape."""

from __future__ import annotations

from copy import deepcopy


def workflow_draft(*, name: str = "Untitled workflow", description: str = "") -> dict:
    return {
        "schema_version": 1,
        "name": name,
        "description": description,
        "nodes": [],
        "edges": [],
        "variables": {},
        "viewport": {"x": 0, "y": 0, "zoom": 1},
        "settings": {"on_error": "stop"},
        "extensions": {},
    }


def summary(document: dict) -> dict:
    return {
        "workflow_id": document["workflow_id"],
        "name": document["name"],
        "description": document.get("description", ""),
        "node_count": len(document.get("nodes", [])),
        "edge_count": len(document.get("edges", [])),
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }


def copy_draft(document: dict, *, name: str | None = None) -> dict:
    draft = deepcopy(document)
    for field in ("workflow_id", "created_at", "updated_at"):
        draft.pop(field, None)
    if name is not None:
        draft["name"] = name
    return draft
