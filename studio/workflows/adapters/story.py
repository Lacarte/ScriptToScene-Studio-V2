"""Workflow adapter for the existing story generation module."""

from __future__ import annotations

from studio.story.service import StoryServiceError, generate_story

from .common import AdapterError, inherited_config, outputs, project_id, with_artifacts


def generate(inputs, config, context):
    configuration = inherited_config(
        config,
        inputs.get("settings"),
        aliases={"style": "preset_style", "tone": "story_tone"},
    )
    configuration["project_name_id"] = project_id(context, inputs)
    try:
        result = generate_story(configuration, project_id=configuration["project_name_id"])
    except StoryServiceError as exc:
        raise AdapterError(exc.code, str(exc)) from exc
    except ValueError as exc:
        raise AdapterError("STORY_CONFIG_INVALID", str(exc)) from exc
    path = result.pop("path")
    return outputs(
        script=result["story_text"],
        story=with_artifacts(result, path),
    )
