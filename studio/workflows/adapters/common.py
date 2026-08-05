from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from config import OUTPUT_DIR

PROJECT_ID_RE = re.compile(r"^p[pm]_[A-Za-z0-9]{6}$")
CONTROL = {"ok": True}


class AdapterError(RuntimeError):
    """Structured node failure consumed by the workflow scheduler."""

    def __init__(self, code: str, message: str, *, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass(frozen=True)
class AdapterContext:
    project_id: str
    execution_id: str = ""
    node_id: str = ""
    progress: Callable[[str], None] | None = None
    stop_requested: Callable[[], bool] | None = None
    authorize_existing_replace: bool = False
    # Adapters which create a new artifact may ask the scheduler for a path
    # that is invisible to readers until the node succeeds.  Existing
    # adapters remain compatible while they are migrated to staged writes.
    stage_artifact: Callable[[str], str] | None = None


def context_value(context: AdapterContext | Mapping[str, Any], name: str, default=None):
    if isinstance(context, Mapping):
        return context.get(name, default)
    return getattr(context, name, default)


def project_id(context, inputs: Mapping[str, Any] | None = None) -> str:
    value = context_value(context, "project_id", "")
    if not value and inputs:
        candidate = inputs.get("project_id")
        value = candidate.get("project_id") if isinstance(candidate, Mapping) else candidate
    if not isinstance(value, str) or not PROJECT_ID_RE.fullmatch(value):
        raise AdapterError("PROJECT_ID_INVALID", "A strict pp_/pm_ project ID is required")
    return value


def inherited_config(config: Mapping[str, Any] | None, settings: Any, aliases=None) -> dict:
    """Apply incoming settings as defaults; explicit node configuration wins.

    Verified live (step 6.1): schema defaults are empty strings, so an unset
    node field must not mask a configured project setting — empty is not
    explicit. A config value only overrides a non-empty inherited value when
    it is itself non-empty.
    """
    inherited = dict(settings) if isinstance(settings, Mapping) else {}
    aliases = aliases or {}
    for source, target in aliases.items():
        if source in inherited and target not in inherited:
            inherited[target] = inherited[source]
    for key, value in dict(config or {}).items():
        if value in (None, "") and inherited.get(key) not in (None, ""):
            continue
        inherited[key] = value
    return inherited


def artifact_ref(path: str) -> str:
    absolute = os.path.abspath(path)
    root = os.path.abspath(OUTPUT_DIR)
    try:
        if os.path.commonpath([root, absolute]) != root:
            raise ValueError
    except ValueError as exc:
        raise AdapterError("ARTIFACT_UNMANAGED", "Artifact is outside the managed output directory") from exc
    return os.path.relpath(absolute, root).replace("\\", "/")


def with_artifacts(payload: Mapping[str, Any], *paths: str) -> dict:
    result = dict(payload)
    refs = list(result.get("artifact_refs") or [])
    for path in paths:
        if path:
            ref = artifact_ref(path)
            if ref not in refs:
                refs.append(ref)
    result["artifact_refs"] = refs
    return result


def outputs(**ports) -> dict:
    return {"control": CONTROL, **ports}
