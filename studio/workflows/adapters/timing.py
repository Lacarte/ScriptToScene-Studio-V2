import os
from config import ALIGN_DIR
from studio.pipeline.services import _step_timing
from .common import AdapterError, outputs, project_id, with_artifacts


def align(inputs, config, context):
    pid = project_id(context, inputs)
    audio = inputs["audio"]
    metadata = dict(audio)
    metadata["wav_path"] = audio.get("wav_path") or audio.get("path")
    metadata.setdefault("folder", audio.get("source_folder") or pid)
    metadata.setdefault("filename", os.path.basename(metadata["wav_path"]))
    try:
        result = _step_timing(metadata, {"text": inputs["script"]}, pid)
    except RuntimeError as exc:
        raise AdapterError("ALIGNMENT_EMPTY", str(exc)) from exc
    path = os.path.join(ALIGN_DIR, result["folder"], "alignment.json")
    return outputs(alignment=with_artifacts(result, path))
