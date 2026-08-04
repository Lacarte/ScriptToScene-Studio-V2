import os
from config import SCENES_DIR
from studio.pipeline.services import _step_scenes
from .common import inherited_config, outputs, project_id, with_artifacts


def blueprint(inputs, config, context):
    pid = project_id(context, inputs)
    merged = inherited_config(config, inputs.get("settings"), {"tone": "story_tone"})
    merged["text"] = inputs["script"]
    result = _step_scenes(inputs["segments"], merged, pid)
    payload = with_artifacts(result, os.path.join(SCENES_DIR, pid, "scenes.json"))
    prompts = with_artifacts({"project_id": pid, "image_prompts": [s.get("image_prompt", "") for s in result.get("scenes", [])]}, os.path.join(SCENES_DIR, pid, "scenes.json"))
    return outputs(scenes=payload, image_prompts=prompts)
