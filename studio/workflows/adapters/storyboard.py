import os
import time
from config import STORYBOARD_DIR
from studio.io_utils import now_iso, safe_json_read
from .common import AdapterError, context_value, inherited_config, outputs, project_id, with_artifacts


def _step_storyboard(scenes_result, config, project_id, context):
    """Start providers directly and reconcile status from the managed manifest."""
    from studio.storyboard import routes as service

    scenes = [
        {"scene": scene.get("index", index), "prompt": scene.get("image_prompt", "")}
        for index, scene in enumerate(scenes_result.get("scenes", []))
        if scene.get("image_prompt")
    ]
    if not scenes:
        raise AdapterError("SCENES_EMPTY", "No scenes have image prompts for storyboard")
    provider = config.get("storyboard_provider_override", "wavespeed_webhook")
    manifest = os.path.join(STORYBOARD_DIR, project_id, "storyboard.json")
    if provider == "gemini_ws":
        from studio.storyboard.gemini_ws import add_job
        add_job(project_id, [{"index": s["scene"], "prompt": s["prompt"]} for s in scenes], config.get("auto_type", True))
    else:
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

    deadline = time.monotonic() + 30 * 60
    while time.monotonic() < deadline:
        if os.path.isfile(manifest):
            status = safe_json_read(manifest)
            total = int(status.get("total", len(scenes)))
            ready = int(status.get("ready", 0))
            errors = int(status.get("errors", 0))
            if status.get("status") == "done" or ready + errors >= total:
                return {"total": total, "ready": ready, "errors": errors, "scene_statuses": status.get("scene_statuses", {})}
        stop = context_value(context, "stop_requested")
        if stop and stop():
            raise AdapterError("EXECUTION_CANCELLED", "Storyboard generation was cancelled")
        time.sleep(1)
    raise AdapterError("NODE_TIMEOUT", "Storyboard generation timed out after 30 minutes")


def generate(inputs, config, context):
    pid = project_id(context, inputs)
    merged = inherited_config(config, inputs.get("settings"))
    merged["storyboard_provider_override"] = merged.get("provider", "wavespeed_webhook")
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
