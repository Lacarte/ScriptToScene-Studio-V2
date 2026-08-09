"""Legacy-shape adapters onto the v2 envelope — step 11.4.

The baseline this migration must preserve is the observable output of the
current `if provider_id == …` branches, **not** the ABC path: the ABC methods and
the `get_provider()` factories have never executed (contracts.md §16). These
adapters convert today's dict payloads and today's ABC dataclasses into the §31
envelope, so 13.x/14.x/15.x can diff a rewritten domain against the recorded
legacy fixture field-for-field instead of eyeballing it.

Nothing here is on a production path yet — the domain steps switch onto it. What
it does provide now is a mechanical statement of the mapping, tested against
recorded fixtures.
"""

from __future__ import annotations

from typing import Any, Mapping

from studio.shared.providers_common.errors import (
    PROVIDER_UNIT_FAILED,
    ProviderError,
    ProviderErrorPayload,
)
from studio.shared.providers_common.jobs import (
    FAILED,
    JOB_CANCELLED,
    RUNNING,
    SUBMITTED,
    SUCCEEDED,
    JobStatus,
)
from studio.shared.providers_common.results import (
    PARTIAL,
    UNIT_FAILED,
    UNIT_SKIPPED,
    UNIT_SUCCEEDED,
    Provenance,
    ProviderResult,
    UnitResult,
    dedupe_refs,
)


# The persisted manifests store browser URLs (`/output/storyboard/pm_X/0/image.png`);
# an envelope ref is the same value relative to OUTPUT_DIR.
_OUTPUT_URL_PREFIX = "/output/"


def ref_from_output_url(value: Any) -> str:
    """`/output/a/b.png` -> `a/b.png`. Anything else becomes `""`."""
    if not isinstance(value, str) or not value.strip():
        return ""
    normalized = value.replace("\\", "/").strip()
    if normalized.startswith(_OUTPUT_URL_PREFIX):
        return normalized[len(_OUTPUT_URL_PREFIX):]
    return normalized.lstrip("/")


# -- tts (contracts.md §32.3) -----------------------------------------------

# Keys of today's `_step_tts` metadata dict that become first-class payload
# fields. Everything else stays in `metadata`, so `tts.json` consumers are
# unaffected (§32.3).
TTS_PAYLOAD_KEYS = frozenset({
    "duration_seconds", "sample_rate", "voice", "characters_billed",
})
# Never copied into the envelope: `wav_path` is an absolute path (§36 L7) and
# `job_meta` is superseded by `provenance` (§31.3, D39).
TTS_DROPPED_KEYS = frozenset({"wav_path", "job_meta", "artifact_refs"})


def tts_metadata_to_result(
    metadata: Mapping[str, Any],
    *,
    audio_ref: str,
    manifest_ref: str = "",
    provider_id: str = "",
    provider_version: str = "",
) -> ProviderResult:
    """Today's `_step_tts` return -> a §32.3 `TTSResultPayload` envelope."""
    data = dict(metadata or {})
    payload = {
        "audio_ref": audio_ref,
        "duration_seconds": float(data.get("duration_seconds") or 0.0),
        "sample_rate": int(data.get("sample_rate") or 0),
        "format": "wav",
        "voice": str(data.get("voice") or ""),
        "characters_billed": data.get("characters_billed"),
    }
    leftover = {
        key: value
        for key, value in data.items()
        if key not in TTS_PAYLOAD_KEYS and key not in TTS_DROPPED_KEYS
    }
    job_meta = data.get("job_meta") or {}
    return ProviderResult(
        domain="tts",
        provider_id=provider_id or str(data.get("provider") or ""),
        provider_version=provider_version or str(job_meta.get("provider_version") or ""),
        payload=payload,
        artifact_refs=dedupe_refs([audio_ref, manifest_ref]),
        metadata=leftover,
        provenance=_provenance_from_job_meta(job_meta, domain="tts"),
    )


def tts_result_to_payload(result: Any, *, audio_ref: str) -> dict:
    """The ABC `TTSResult` -> a §32.3 payload.

    `audio_path` becomes `audio_ref` (relative, not absolute) and is supplied by
    the caller, because only the caller knows the managed output root.
    """
    return {
        "audio_ref": audio_ref,
        "duration_seconds": float(getattr(result, "duration_seconds", 0.0) or 0.0),
        "sample_rate": int(getattr(result, "sample_rate", 0) or 0),
        "format": str(getattr(result, "format", "wav") or "wav"),
        "voice": str((getattr(result, "metadata", None) or {}).get("voice", "")),
        "characters_billed": (getattr(result, "metadata", None) or {}).get(
            "characters_billed"
        ),
    }


def _provenance_from_job_meta(job_meta: Mapping[str, Any], *, domain: str) -> Provenance:
    """`job_meta` (TTS-only today) -> §31.3 provenance (D39)."""
    meta = dict(job_meta or {})
    return Provenance(
        domain=domain,
        provider_id=str(meta.get("provider_id") or ""),
        provider_version=str(meta.get("provider_version") or ""),
        settings_version=int(meta.get("settings_version") or 0),
        resolved_settings_redacted=dict(meta.get("resolved_settings_redacted") or {}),
        options=dict(meta.get("provider_options") or {}),
        finished_at=str(meta.get("resolved_at") or ""),
    )


# -- storyboard (contracts.md §32.4) ----------------------------------------

# `scene_statuses` values use these strings today; `done` appears in the legacy
# status route's readiness count (`storyboard/routes.py:390`).
_STORYBOARD_UNIT_STATE = {
    "ready": UNIT_SUCCEEDED,
    "done": UNIT_SUCCEEDED,
    "error": UNIT_FAILED,
    "pending": UNIT_SKIPPED,
    "generating": UNIT_SKIPPED,
    "downloading": UNIT_SKIPPED,
}


def storyboard_manifest_to_units(manifest: Mapping[str, Any]) -> list[UnitResult]:
    """`storyboard.json` `scene_statuses` -> ordered `UnitResult`s (§31.5).

    Two egress rules are applied here rather than left to the caller: the remote
    `image_url` is dropped (§36 L9) and the raw `str(e)` the route persists
    becomes a `ProviderErrorPayload` (§31.5 rule 6, §36 L3).
    """
    statuses = dict(manifest.get("scene_statuses") or {})
    units: list[UnitResult] = []
    for key in sorted(statuses, key=_as_index):
        if key == "-1":  # the single-scene sentinel the legacy route writes
            continue
        entry = statuses[key] if isinstance(statuses[key], Mapping) else {}
        state = _STORYBOARD_UNIT_STATE.get(str(entry.get("status", "")), UNIT_SKIPPED)
        refs = dedupe_refs([ref_from_output_url(entry.get("local_path"))])
        metadata = {}
        thumb = ref_from_output_url(entry.get("thumb_path"))
        if thumb:
            metadata["thumbnail_ref"] = thumb
        units.append(UnitResult(
            unit_index=_as_index(key),
            state=state,
            artifact_refs=tuple(refs),
            metadata=metadata,
            error=_unit_error(entry, state),
        ))
    return units


# -- animator (contracts.md §32.5) ------------------------------------------

_ANIMATOR_UNIT_STATE = {
    "ready": UNIT_SUCCEEDED,
    "error": UNIT_FAILED,
    "pending": UNIT_SKIPPED,
    "generating": UNIT_SKIPPED,
    "waiting": UNIT_SKIPPED,
}


def animator_manifest_to_units(manifest: Mapping[str, Any]) -> list[UnitResult]:
    """`grabber_job.json` `scene_statuses` -> ordered `UnitResult`s (§31.5).

    The remote `urls` list is provider-specific response data and is dropped;
    the downloaded `local_files` are the output (§32.5, §36 L9).
    """
    statuses = dict(manifest.get("scene_statuses") or {})
    units: list[UnitResult] = []
    for key in sorted(statuses, key=_as_index):
        entry = statuses[key] if isinstance(statuses[key], Mapping) else {}
        state = _ANIMATOR_UNIT_STATE.get(str(entry.get("status", "")), UNIT_SKIPPED)
        refs = dedupe_refs(
            ref_from_output_url(item) for item in (entry.get("local_files") or [])
        )
        units.append(UnitResult(
            unit_index=_as_index(key),
            state=state,
            artifact_refs=tuple(refs),
            # `kind` describes the media that was produced, so a unit that
            # produced none does not claim one.
            metadata=(
                {"kind": "video" if _looks_like_video(refs) else "image"} if refs else {}
            ),
            error=_unit_error(entry, state),
        ))
    return units


def _looks_like_video(refs: list[str]) -> bool:
    return any(ref.lower().endswith((".mp4", ".webm", ".mov")) for ref in refs)


def _as_index(key: Any) -> int:
    try:
        return int(key)
    except (TypeError, ValueError):
        return 0


def _unit_error(entry: Mapping[str, Any], state: str) -> ProviderErrorPayload | None:
    """A failed unit must carry an error (§31.5 rule 5), and it must be safe."""
    if state != UNIT_FAILED:
        return None
    # `ProviderError` sanitizes on construction, so the raw `str(e)` the legacy
    # route persisted is stripped of paths and key=value secrets here.
    return ProviderErrorPayload.from_error(ProviderError(
        PROVIDER_UNIT_FAILED,
        str(entry.get("error") or "The provider failed to produce this unit"),
        retryable=True,
    ))


# -- visual-domain envelopes -------------------------------------------------


def visual_manifest_to_result(
    manifest: Mapping[str, Any],
    *,
    domain: str,
    provider_id: str,
    manifest_ref: str,
    provider_version: str = "",
) -> ProviderResult:
    """A storyboard/animator manifest -> the §32.4/§32.5 envelope.

    `payload` carries only the counts and the manifest ref; per-scene detail
    lives in `units[]`, which is what retires `scene_statuses` as a
    provider-facing shape.
    """
    units = (
        storyboard_manifest_to_units(manifest)
        if domain == "storyboard"
        else animator_manifest_to_units(manifest)
    )
    ready = sum(1 for unit in units if unit.state == UNIT_SUCCEEDED)
    errors = sum(1 for unit in units if unit.state == UNIT_FAILED)
    return ProviderResult(
        domain=domain,
        provider_id=provider_id,
        provider_version=provider_version,
        payload={
            "total": len(units),
            "ready": ready,
            "errors": errors,
            "manifest_ref": manifest_ref,
        },
        artifact_refs=dedupe_refs([manifest_ref]),
        units=units,
    )


# -- the ABC job types (contracts.md §33.1) ---------------------------------

# The old `JobStatus.status` held provider-defined strings; these are the values
# the five shipped providers actually emit.
_LEGACY_JOB_STATE = {
    "pending": SUBMITTED,
    "submitted": SUBMITTED,
    "queued": SUBMITTED,
    "processing": RUNNING,
    "running": RUNNING,
    "generating": RUNNING,
    "complete": SUCCEEDED,
    "completed": SUCCEEDED,
    "done": SUCCEEDED,
    "success": SUCCEEDED,
    "partial": PARTIAL,
    "failed": FAILED,
    "error": FAILED,
    "cancelled": JOB_CANCELLED,
    "canceled": JOB_CANCELLED,
}


def job_status_from_legacy(legacy: Any, *, units: tuple[UnitResult, ...] = ()) -> JobStatus:
    """An ABC `JobStatus` -> the one §33.1 `JobStatus`.

    `status` (provider-defined) becomes `state` (closed vocabulary); `progress`
    becomes `fraction`; `result: dict | None` is replaced by `units`, which the
    caller supplies because the old field had no agreed shape; `error: str`
    becomes a `ProviderErrorPayload`. An unrecognized status is `running`, never
    a silent success.
    """
    raw = str(getattr(legacy, "status", "") or "").strip().lower()
    state = _LEGACY_JOB_STATE.get(raw, RUNNING)
    error = getattr(legacy, "error", None)
    return JobStatus(
        job_id=str(getattr(legacy, "job_id", "") or ""),
        state=state,
        ready=sum(1 for unit in units if unit.state == UNIT_SUCCEEDED),
        total=len(units),
        fraction=getattr(legacy, "progress", None),
        message=getattr(legacy, "message", None),
        units=units,
        error=(
            ProviderErrorPayload.from_error(
                ProviderError(PROVIDER_UNIT_FAILED, str(error), retryable=True)
            )
            if error
            else None
        ),
    )


__all__ = [
    "TTS_DROPPED_KEYS",
    "TTS_PAYLOAD_KEYS",
    "animator_manifest_to_units",
    "job_status_from_legacy",
    "ref_from_output_url",
    "storyboard_manifest_to_units",
    "tts_metadata_to_result",
    "tts_result_to_payload",
    "visual_manifest_to_result",
]
