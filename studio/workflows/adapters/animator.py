import os
import time
from config import ANIMATOR_DIR
from studio.io_utils import now_iso, safe_json_read
from studio.shared.providers_common.errors import (
    PROVIDER_TIMEOUT,
    ProviderCancelled,
    ProviderError,
)
from .common import (
    AdapterError,
    context_value,
    inherited_config,
    outputs,
    project_id,
    provider_id,
    provider_option,
    provider_run_options,
    with_artifacts,
)

DOMAIN = "animator"


def _step_assets(scenes_result, config, project_id, context):
    """Create animator jobs directly; provider callbacks update the shared store."""
    from studio.animator import animation_routes as service

    scenes = [
        {"scene": scene.get("index", index), "prompt": scene.get("image_prompt", "")}
        for index, scene in enumerate(scenes_result.get("scenes", []))
        if scene.get("image_prompt")
    ]
    if not scenes:
        raise AdapterError("SCENES_EMPTY", "No scenes have prompts for animation")
    provider = config.get("animator_provider_override", "grok_automa")
    options = config.get("animator_provider_options", {})
    job = {
        "grabber_id": f"workflow_{project_id}", "project_id": project_id,
        "provider": provider, "arguments": config.get("arguments", ""),
        "payload": {"projectId": project_id, "aspect_ratio": config.get("aspect_ratio", "9:16"), "scenes": scenes},
        "scene_statuses": {str(s["scene"]): {"status": "pending", "urls": [], "local_files": []} for s in scenes},
        "status": "waiting", "created_at": now_iso(), "updated_at": now_iso(),
    }
    if provider == "kie_ai":
        from studio.shared.providers_common import settings_manager
        job["_kie_ai_options"] = {
            "aspect_ratio": config.get("aspect_ratio", "9:16"),
            "resolution": options.get("resolution", "1"), "output_format": options.get("output_format", "jpg"),
            # Portable options only: the job manifest is written under output/ and
            # may be archived, so a credential must never reach it (§22.6).
            # `options` already carries these, merged request-wins; re-applying
            # them last keeps Kie AI's inverted precedence exactly as it is
            # today (§40.2 O4 / §47 C4 — the correction belongs to 14.3).
            **settings_manager.portable_provider_settings("animator", "kie_ai"),
        }
    service._set_job(project_id, job)
    service._save_job(job)
    if provider == "kie_ai":
        job["status"] = "generating"
        service._kie_ai_generate_all(project_id, job)
    else:
        from studio.animator.routes import add_job
        # mode/quality/duration moved out of the node config into this
        # provider's own settings (§41.3 M3), so their defaults now come from
        # the schema that declares them rather than from literals here.
        add_job(
            project_id,
            scenes,
            provider_option(DOMAIN, provider, options, "mode"),
            provider_option(DOMAIN, provider, options, "quality"),
            provider_option(DOMAIN, provider, options, "duration"),
        )

    manifest = os.path.join(ANIMATOR_DIR, project_id, "grabber_job.json")
    deadline = time.monotonic() + 2 * 60 * 60
    while time.monotonic() < deadline:
        status = service._get_job(project_id)
        if status is None and os.path.isfile(manifest):
            status = safe_json_read(manifest)
        if status:
            statuses = status.get("scene_statuses", {})
            total = len(statuses)
            ready = sum(1 for item in statuses.values() if item.get("status") == "ready")
            errors = sum(1 for item in statuses.values() if item.get("status") == "error")
            if status.get("status") in ("done", "completed") or ready + errors >= total:
                return {"total": total, "ready": ready, "errors": errors, "provider": provider}
        stop = context_value(context, "stop_requested")
        if stop and stop():
            # See the storyboard adapter: `EXECUTION_CANCELLED` was recognized
            # nowhere and recorded a cancelled node as `failed` (§35.1, D36).
            raise ProviderCancelled(
                "Animator generation was cancelled", domain="animator"
            ).as_adapter_error()
        time.sleep(1)
    raise ProviderError(
        PROVIDER_TIMEOUT,
        "Animator generation timed out after 120 minutes",
        domain="animator",
    ).as_adapter_error()


def generate(inputs, config, context):
    pid = project_id(context, inputs)
    merged = inherited_config(config, inputs.get("settings"))
    selected = provider_id(DOMAIN, merged)
    merged["animator_provider_override"] = selected
    merged["animator_provider_options"] = provider_run_options(DOMAIN, selected, merged)
    result = _step_assets(inputs["scenes"], merged, pid, context)
    # Verified live (step 6.1): a provider that errors every scene still
    # completes the job manifest — zero produced assets must fail the node.
    if not result.get("ready"):
        raise AdapterError(
            "ANIMATOR_FAILED",
            f"All {result.get('total', 0)} animator scenes failed",
            details={"errors": result.get("errors"), "provider": result.get("provider")},
        )
    asset_root = os.path.join(ANIMATOR_DIR, pid)
    result["artifact_refs"] = []
    if os.path.isdir(asset_root):
        result["artifact_refs"] = [
            "animator/" + os.path.relpath(os.path.join(root, name), ANIMATOR_DIR).replace("\\", "/")
            for root, _dirs, files in os.walk(asset_root) for name in files
        ]
    return outputs(assets=with_artifacts({**result, "project_id": pid}, os.path.join(ANIMATOR_DIR, pid, "grabber_job.json")))
