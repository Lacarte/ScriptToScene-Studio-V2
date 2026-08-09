import os

from studio.pipeline.services import _step_tts
from .common import (
    inherited_config,
    outputs,
    project_id,
    provider_id,
    provider_run_options,
    with_artifacts,
)

DOMAIN = "tts"


def generate(inputs, config, context):
    pid = project_id(context, inputs)
    merged = inherited_config(config, inputs.get("settings"), {"tone": "story_tone", "style": "visual_style"})
    merged["text"] = inputs["script"]
    # `engine` became `provider_id` in v2 (contracts.md §41.3 M1). The legacy
    # request field the pipeline reads is unchanged, so a migrated workflow
    # produces the same call it made before the rename.
    selected = provider_id(DOMAIN, merged)
    merged["tts_provider_override"] = selected
    merged["tts_provider_options"] = provider_run_options(DOMAIN, selected, merged)
    result = _step_tts(merged, pid)
    metadata = with_artifacts(result, result["wav_path"], os.path.join(os.path.dirname(result["wav_path"]), "tts.json"))
    audio = with_artifacts({"project_id": pid, "path": result["wav_path"], "filename": result["filename"], "duration_seconds": result.get("duration_seconds")}, result["wav_path"])
    return outputs(audio=audio, metadata=metadata)
