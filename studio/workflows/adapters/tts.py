"""Workflow adapter for the Text to Speech node (`tts.generate`).

Dispatches generically through the `tts` provider hub (step 15.2). The adapter
resolves which provider the node runs on and hands the request to
`studio.tts.dispatch` via `_step_tts`; it knows nothing about voices, models,
streaming, or audio formats, so a TTS provider that ships tomorrow runs on this
node with no edit here and none in the registry.
"""

from __future__ import annotations

import os

from studio.pipeline.services import _step_tts
from studio.shared.providers_common.errors import ProviderError

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
    try:
        result = _step_tts(merged, pid, context)
    except ProviderError as exc:
        raise exc.as_adapter_error() from exc
    metadata = with_artifacts(result, result["wav_path"], os.path.join(os.path.dirname(result["wav_path"]), "tts.json"))
    audio = with_artifacts({"project_id": pid, "path": result["wav_path"], "filename": result["filename"], "duration_seconds": result.get("duration_seconds")}, result["wav_path"])
    return outputs(audio=audio, metadata=metadata)
