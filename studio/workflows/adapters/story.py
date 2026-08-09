"""Workflow adapter for the existing story generation module."""

from __future__ import annotations

from studio.story.service import StoryServiceError

from .common import (
    AdapterError,
    inherited_config,
    outputs,
    project_id,
    provider_id,
    provider_run_options,
    resolve_provider,
    with_artifacts,
)

DOMAIN = "script"


def generate(inputs, config, context):
    configuration = inherited_config(
        config,
        inputs.get("settings"),
        aliases={"style": "preset_style", "tone": "story_tone"},
    )
    configuration["project_name_id"] = project_id(context, inputs)
    # `provider_id` is absent on every workflow saved before step 12.3, so it
    # resolves to the domain default: today the `builtin` bridge, a passthrough
    # to the same `generate_story` this adapter used to call directly. That is
    # why M4 needs no `type_version` bump (§41.3); 13.2 swaps the bridge for the
    # real `gemini` provider behind this same call.
    selected = provider_id(DOMAIN, configuration)
    provider = resolve_provider(DOMAIN, selected)
    configuration.update(provider_run_options(DOMAIN, selected, configuration))
    try:
        result = provider.generate(
            configuration, project_id=configuration["project_name_id"]
        )
    except StoryServiceError as exc:
        raise AdapterError(exc.code, str(exc)) from exc
    except ValueError as exc:
        raise AdapterError("STORY_CONFIG_INVALID", str(exc)) from exc
    path = result.pop("path")
    return outputs(
        script=result["story_text"],
        story=with_artifacts(result, path),
    )
