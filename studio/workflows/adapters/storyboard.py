import os
from config import STORYBOARD_DIR
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
from .media_job import run_manifest_job

DOMAIN = "storyboard"


def _step_storyboard(scenes_result, config, project_id, context):
    """Start the selected provider; the shared media-job service owns the wait.

    The deadline, poll cadence, cancellation, progress reporting, per-scene
    aggregation, and job persistence all moved into `MediaJobService` in 14.1 —
    this adapter only knows how to *start* a storyboard job. Cancellation still
    surfaces as `CANCELLED` and a deadline as `POLL_TIMEOUT` (§35.1, D35/D36);
    the provider-ID branch below moves into the providers themselves in 14.2.
    """
    from studio.storyboard import routes as service

    scenes = [
        {"scene": scene.get("index", index), "prompt": scene.get("image_prompt", "")}
        for index, scene in enumerate(scenes_result.get("scenes", []))
        if scene.get("image_prompt")
    ]
    if not scenes:
        raise AdapterError("SCENES_EMPTY", "No scenes have image prompts for storyboard")
    provider = config.get("storyboard_provider_override", "wavespeed_webhook")
    options = config.get("storyboard_provider_options") or {}
    manifest = os.path.join(STORYBOARD_DIR, project_id, "storyboard.json")

    def start():
        if provider == "gemini_ws":
            from studio.storyboard.gemini_ws import add_job
            # `auto_type` moved out of the node config into this provider's own
            # settings (§41.3 M2), so its default now comes from the schema that
            # declares it rather than from a literal here.
            add_job(
                project_id,
                [{"index": s["scene"], "prompt": s["prompt"]} for s in scenes],
                provider_option(DOMAIN, provider, options, "auto_type"),
            )
            return
        job = {
            "project_id": project_id, "status": "running", "total": len(scenes),
            "ready": 0, "errors": 0, "aspect_ratio": config.get("aspect_ratio", "9:16"),
            "created_at": now_iso(), "completed_at": None,
            "scene_statuses": {str(s["scene"]): {"status": "pending", "image_url": None, "local_path": None} for s in scenes},
        }
        service._jobs.set(project_id, job)
        service._save_storyboard_json(project_id, job)
        service._generate_storyboard(
            project_id, scenes, config.get("aspect_ratio", "9:16"), None,
            config.get("style"), config.get("image_model") or None,
        )

    return run_manifest_job(
        domain=DOMAIN,
        provider=provider,
        project_id=project_id,
        context=context,
        scenes=scenes,
        manifest_path=manifest,
        start=start,
        failure_code="STORYBOARD_FAILED",
    )


def generate(inputs, config, context):
    pid = project_id(context, inputs)
    merged = inherited_config(config, inputs.get("settings"))
    selected = provider_id(DOMAIN, merged)
    merged["storyboard_provider_override"] = selected
    merged["storyboard_provider_options"] = provider_run_options(DOMAIN, selected, merged)
    result = _step_storyboard(inputs["scenes"], merged, pid, context)
    # Verified live (step 6.1): provider failures (e.g. a rejected WaveSpeed
    # key) complete the manifest with only errors — that is a node failure,
    # not a success with zero images.
    if not result.get("ready"):
        raise AdapterError(
            "STORYBOARD_FAILED",
            f"All {result.get('total', 0)} storyboard scenes failed",
            details={"errors": result.get("errors")},
        )
    result["artifact_refs"] = [
        str(item.get("local_path")).replace("\\", "/").removeprefix("/output/")
        for item in result.get("scene_statuses", {}).values()
        if isinstance(item, dict) and item.get("local_path")
    ]
    return outputs(images=with_artifacts({**result, "project_id": pid}, os.path.join(STORYBOARD_DIR, pid, "storyboard.json")))
