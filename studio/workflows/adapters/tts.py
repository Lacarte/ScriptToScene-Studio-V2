import os

from studio.pipeline.services import _step_tts
from .common import inherited_config, outputs, project_id, with_artifacts


def generate(inputs, config, context):
    pid = project_id(context, inputs)
    merged = inherited_config(config, inputs.get("settings"), {"tone": "story_tone", "style": "visual_style"})
    merged["text"] = inputs["script"]
    merged["tts_provider_override"] = merged.get("engine", "kokoro")
    merged["tts_provider_options"] = merged.get("provider_options", {})
    result = _step_tts(merged, pid)
    metadata = with_artifacts(result, result["wav_path"], os.path.join(os.path.dirname(result["wav_path"]), "tts.json"))
    audio = with_artifacts({"project_id": pid, "path": result["wav_path"], "filename": result["filename"], "duration_seconds": result.get("duration_seconds")}, result["wav_path"])
    return outputs(audio=audio, metadata=metadata)
