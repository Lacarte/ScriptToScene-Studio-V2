import os
from config import ANIMATOR_DIR
from studio.io_utils import now_iso
from .common import (
    AdapterError,
    inherited_config,
    outputs,
    project_id,
    provider_id,
    provider_option,
    provider_run_options,
    with_artifacts,
)
from .media_job import read_manifest, run_manifest_job

DOMAIN = "animator"


def _step_assets(scenes_result, config, project_id, context):
    """Create the animator job; the shared media-job service owns the wait.

    As with storyboard, 14.1 moved the deadline, poll cadence, cancellation,
    progress reporting, per-scene aggregation, and job persistence into
    `MediaJobService`. The provider-ID branch below moves into the providers
    themselves in 14.3.
    """
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
    manifest = os.path.join(ANIMATOR_DIR, project_id, "grabber_job.json")

    def start():
        service._set_job(project_id, job)
        service._save_job(job)
        if provider == "kie_ai":
            job["status"] = "generating"
            service._kie_ai_generate_all(project_id, job)
            return
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

    def read():
        # The in-memory store stays authoritative while the process lives; the
        # manifest is the restart path. Order preserved from the legacy loop.
        return service._get_job(project_id) or read_manifest(manifest)

    result = run_manifest_job(
        domain=DOMAIN,
        provider=provider,
        project_id=project_id,
        context=context,
        scenes=scenes,
        manifest_path=manifest,
        start=start,
        read=read,
        failure_code="ANIMATOR_FAILED",
        failure_details={"provider": provider},
    )
    # The animator node has never exposed the raw per-scene map on its port,
    # and those entries still carry remote URLs (D38 belongs to 14.3).
    result.pop("scene_statuses", None)
    result["provider"] = provider
    return result


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
