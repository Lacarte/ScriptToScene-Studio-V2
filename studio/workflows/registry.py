"""Authoritative node-type registry for the workflow builder.

Single source of truth (contracts.md §2-§3): port IDs, port types, config
schemas, defaults, and capabilities for every node type. The frontend
consumes the presentation-safe form served by GET /api/workflow/node-types;
the execution engine (Phase 3) dispatches through the internal ``executor``
field, which is never serialized.
"""

from copy import deepcopy

REGISTRY_VERSION = 1

# contracts.md §3 — frozen v1 port vocabulary.
PORT_TYPES = [
    "control", "text", "script", "project_id", "project_settings",
    "audio_file", "tts_metadata", "alignment", "segments", "scenes",
    "image_prompts", "storyboard_images", "animation_assets", "captions",
    "music_track", "editor_project", "export_profile", "video_file",
    "generic_json",
]

# Data types a dynamic port (workflow.output, stub.*) may resolve to.
DYNAMIC_PORT_TYPES = [t for t in PORT_TYPES if t != "control"]

# contracts.md §11 — backend-approved async option sources. `caption_presets`
# reconciles §2 (captions.generate: "approved preset id") with the allowlist.
ASYNC_OPTION_SOURCES = [
    "tts_voices", "story_tones", "style_templates",
    "storyboard_providers", "animator_providers", "export_profiles",
    "caption_presets",
]

CATEGORIES = {
    "input":   {"label": "Input",   "color": "#4ECDC4"},
    "audio":   {"label": "Audio",   "color": "#A78BFA"},
    "timing":  {"label": "Timing",  "color": "#60A5FA"},
    "ai":      {"label": "AI",      "color": "#F472B6"},
    "assets":  {"label": "Assets",  "color": "#FBBF24"},
    "video":   {"label": "Video",   "color": "#34D399"},
    "output":  {"label": "Output",  "color": "#F87171"},
    "utility": {"label": "Utility", "color": "#9CA3AF"},
    "testing": {"label": "Testing", "color": "#78716C"},
}

_ASPECT_RATIOS = ["9:16", "16:9", "1:1"]


def _in(port_id, port_type, *, required=False):
    return {"id": port_id, "type": port_type, "required": required, "multiple": False}


def _out(port_id, port_type):
    return {"id": port_id, "type": port_type}


_TRIGGER_IN = _in("trigger", "control")
_CONTROL_OUT = _out("control", "control")


# ---------------------------------------------------------------------------
# Node catalog — port IDs frozen per contracts.md §3.1.
# ---------------------------------------------------------------------------

_NODE_TYPES = {
    "trigger.manual": {
        "type_version": 1,
        "display_name": "Manual Trigger",
        "description": "Emits one control token when the run starts.",
        "category": "input",
        "icon": "play",
        "inputs": [],
        "outputs": [_CONTROL_OUT],
        "config_schema": [],
        "capabilities": {"retry": False, "cancel": False},
        "executor": "studio.workflows.adapters.control:manual_trigger",
    },
    "project.setup": {
        "type_version": 1,
        "display_name": "Project Setup",
        "description": "Project identity, branding, and creative defaults shared by downstream nodes.",
        "category": "input",
        "icon": "briefcase",
        "inputs": [_TRIGGER_IN],
        "outputs": [_CONTROL_OUT, _out("settings", "project_settings")],
        "config_schema": [
            {"name": "project_name", "label": "Project name", "type": "string", "default": "", "max_length": 120},
            {"name": "channel_name", "label": "Channel name", "type": "string", "default": "", "max_length": 120},
            {"name": "logo_enabled", "label": "Show logo on video", "type": "boolean", "default": False},
            {"name": "logo", "label": "Logo image", "type": "media_asset",
             "accept": ["png", "jpg", "jpeg", "webp"], "default": None,
             "display_options": {"show": {"logo_enabled": [True]}}},
            {"name": "logo_position", "label": "Logo position", "type": "options", "default": "top_right",
             "options": ["top_left", "top_right", "bottom_left", "bottom_right", "center"],
             "display_options": {"show": {"logo_enabled": [True]}}},
            {"name": "logo_size", "label": "Logo size (% of width)", "type": "number",
             "default": 10, "min": 2, "max": 40, "step": 1,
             "display_options": {"show": {"logo_enabled": [True]}}},
            {"name": "logo_opacity", "label": "Logo opacity", "type": "number",
             "default": 0.9, "min": 0.05, "max": 1.0, "step": 0.05,
             "display_options": {"show": {"logo_enabled": [True]}}},
            {"name": "logo_margin", "label": "Logo margin (px)", "type": "number",
             "default": 32, "min": 0, "max": 200, "step": 1,
             "display_options": {"show": {"logo_enabled": [True]}}},
            {"name": "tone", "label": "Story tone", "type": "options",
             "options_source": "story_tones", "default": ""},
            {"name": "style", "label": "Visual style", "type": "options",
             "options_source": "style_templates", "default": "cinematic"},
            {"name": "aspect_ratio", "label": "Aspect ratio", "type": "options",
             "options": _ASPECT_RATIOS, "default": "9:16"},
        ],
        "capabilities": {"retry": False, "cancel": False},
        "executor": "studio.workflows.adapters.project:setup",
    },
    "script.input": {
        "type_version": 1,
        "display_name": "Script Input",
        "description": "The narration script that drives the production.",
        "category": "input",
        "icon": "file-text",
        "inputs": [_TRIGGER_IN],
        "outputs": [_CONTROL_OUT, _out("script", "script")],
        "config_schema": [
            {"name": "text", "label": "Script", "type": "textarea", "default": "",
             "required": True, "min_length": 1, "max_length": 10000},
        ],
        "capabilities": {"retry": False, "cancel": False},
        "executor": "studio.workflows.adapters.project:script_input",
    },
    "project.existing": {
        "type_version": 1,
        "display_name": "Existing Project",
        "description": "Select an existing project (WIP preferred over initial) without rewriting it.",
        "category": "input",
        "icon": "folder-open",
        "inputs": [_TRIGGER_IN],
        "outputs": [_CONTROL_OUT, _out("project_id", "project_id"), _out("project", "editor_project")],
        "config_schema": [
            {"name": "project_id", "label": "Project ID", "type": "string", "default": "",
             "required": True, "pattern": "^p[pm]_[A-Za-z0-9]{6}$"},
        ],
        "capabilities": {"retry": False, "cancel": False},
        "executor": "studio.workflows.adapters.project:existing",
    },
    "tts.generate": {
        "type_version": 1,
        "display_name": "Text to Speech",
        "description": "Generate narration audio from the script.",
        "category": "audio",
        "icon": "mic",
        "inputs": [_TRIGGER_IN, _in("script", "script", required=True), _in("settings", "project_settings")],
        "outputs": [_CONTROL_OUT, _out("audio", "audio_file"), _out("metadata", "tts_metadata")],
        "config_schema": [
            {"name": "engine", "label": "Engine", "type": "options",
             "options": ["kokoro", "inworld"], "default": "kokoro"},
            {"name": "voice", "label": "Voice", "type": "options",
             "options_source": "tts_voices", "default": "af_heart"},
            {"name": "speed", "label": "Speed", "type": "number",
             "default": 1.0, "min": 0.5, "max": 2.0, "step": 0.1},
            {"name": "provider_options", "label": "Provider options", "type": "json", "default": {}},
        ],
        "capabilities": {"retry": True, "cancel": False},
        "executor": "studio.workflows.adapters.tts:generate",
    },
    "timing.align": {
        "type_version": 1,
        "display_name": "Force Alignment",
        "description": "Word-level timestamps for the narration (stable-whisper tiny.en).",
        "category": "timing",
        "icon": "clock",
        "inputs": [_TRIGGER_IN, _in("audio", "audio_file", required=True), _in("script", "script", required=True)],
        "outputs": [_CONTROL_OUT, _out("alignment", "alignment")],
        "config_schema": [],
        "capabilities": {"retry": True, "cancel": False},
        "executor": "studio.workflows.adapters.timing:align",
    },
    "segment.run": {
        "type_version": 1,
        "display_name": "Segmenter",
        "description": "Split the alignment into scene-sized segments.",
        "category": "timing",
        "icon": "scissors",
        "inputs": [_TRIGGER_IN, _in("alignment", "alignment", required=True)],
        "outputs": [_CONTROL_OUT, _out("segments", "segments")],
        "config_schema": [
            {"name": "segment_config", "label": "Segmenter overrides", "type": "json", "default": {}},
        ],
        "capabilities": {"retry": False, "cancel": False},
        "executor": "studio.workflows.adapters.segmenter:run",
    },
    "scenes.blueprint": {
        "type_version": 1,
        "display_name": "Scene Blueprint",
        "description": "AI scene descriptions and image prompts for each segment.",
        "category": "ai",
        "icon": "film",
        "inputs": [_TRIGGER_IN, _in("segments", "segments", required=True),
                   _in("script", "script", required=True), _in("settings", "project_settings")],
        "outputs": [_CONTROL_OUT, _out("scenes", "scenes"), _out("image_prompts", "image_prompts")],
        "config_schema": [
            {"name": "webhook_url", "label": "Webhook URL", "type": "string", "default": ""},
            {"name": "style", "label": "Visual style", "type": "options",
             "options_source": "style_templates", "default": "cinematic"},
            {"name": "style_prompt", "label": "Custom style notes", "type": "textarea", "default": ""},
            {"name": "story_tone", "label": "Story tone", "type": "options",
             "options_source": "story_tones", "default": ""},
        ],
        "capabilities": {"retry": True, "cancel": False},
        "executor": "studio.workflows.adapters.scenes:blueprint",
    },
    "storyboard.generate": {
        "type_version": 1,
        "display_name": "Storyboard",
        "description": "Reference images per scene (never timeline media — see contracts D4).",
        "category": "assets",
        "icon": "grid",
        "inputs": [_TRIGGER_IN, _in("scenes", "scenes", required=True), _in("settings", "project_settings")],
        "outputs": [_CONTROL_OUT, _out("images", "storyboard_images")],
        "config_schema": [
            {"name": "provider", "label": "Provider", "type": "options",
             "options_source": "storyboard_providers", "default": "wavespeed_webhook"},
            {"name": "aspect_ratio", "label": "Aspect ratio", "type": "options",
             "options": _ASPECT_RATIOS, "default": "9:16"},
            {"name": "style", "label": "Visual style", "type": "options",
             "options_source": "style_templates", "default": "cinematic"},
            {"name": "image_model", "label": "Image model", "type": "string", "default": ""},
            {"name": "prompt_prefix", "label": "Prompt prefix", "type": "string", "default": "",
             "display_options": {"show": {"provider": ["gemini_ws"]}}},
            {"name": "auto_type", "label": "Auto-type prompts", "type": "boolean", "default": True,
             "display_options": {"show": {"provider": ["gemini_ws"]}}},
        ],
        "capabilities": {"retry": True, "cancel": False},
        "executor": "studio.workflows.adapters.storyboard:generate",
    },
    "animator.generate": {
        "type_version": 1,
        "display_name": "Animator",
        "description": "Timeline media (video/image) per scene via the asset grabber.",
        "category": "assets",
        "icon": "image",
        "inputs": [_TRIGGER_IN, _in("scenes", "scenes", required=True),
                   _in("storyboard", "storyboard_images"), _in("settings", "project_settings")],
        "outputs": [_CONTROL_OUT, _out("assets", "animation_assets")],
        "config_schema": [
            {"name": "provider", "label": "Provider", "type": "options",
             "options_source": "animator_providers", "default": "grok_automa"},
            {"name": "aspect_ratio", "label": "Aspect ratio", "type": "options",
             "options": _ASPECT_RATIOS, "default": "9:16"},
            {"name": "mode", "label": "Asset mode", "type": "options",
             "options": ["video", "image"], "default": "video"},
            {"name": "quality", "label": "Quality", "type": "options",
             "options": ["360p", "480p", "720p"], "default": "480p",
             "display_options": {"show": {"provider": ["grok_automa"]}}},
            {"name": "duration", "label": "Clip duration", "type": "options",
             "options": ["6s"], "default": "6s",
             "display_options": {"show": {"provider": ["grok_automa"]}}},
            {"name": "arguments", "label": "Extra arguments", "type": "string", "default": ""},
            {"name": "auto_type", "label": "Auto-type prompts", "type": "boolean", "default": True,
             "display_options": {"show": {"provider": ["grok_automa"]}}},
        ],
        "capabilities": {"retry": True, "cancel": False},
        "executor": "studio.workflows.adapters.animator:generate",
    },
    "captions.generate": {
        "type_version": 1,
        "display_name": "Caption Generator",
        "description": "Word-level captions grouped from the alignment.",
        "category": "video",
        "icon": "type",
        "inputs": [_TRIGGER_IN, _in("alignment", "alignment", required=True)],
        "outputs": [_CONTROL_OUT, _out("captions", "captions")],
        "config_schema": [
            {"name": "preset_id", "label": "Caption preset", "type": "options",
             "options_source": "caption_presets", "default": "bold_popup"},
            {"name": "words_per_group", "label": "Words per caption", "type": "number",
             "default": 3, "min": 1, "max": 10, "step": 1},
            {"name": "enabled", "label": "Enabled", "type": "boolean", "default": True},
        ],
        "capabilities": {"retry": False, "cancel": False},
        "executor": "studio.workflows.adapters.captions:generate",
    },
    "music.select": {
        "type_version": 1,
        "display_name": "Background Music",
        "description": "Pick a background track by tone, at random, or explicitly.",
        "category": "audio",
        "icon": "music",
        "inputs": [_TRIGGER_IN, _in("settings", "project_settings"), _in("project_id", "project_id")],
        "outputs": [_CONTROL_OUT, _out("track", "music_track")],
        "config_schema": [
            {"name": "mode", "label": "Selection mode", "type": "options",
             "options": ["tone", "random", "specific"], "default": "tone"},
            {"name": "story_tone", "label": "Story tone", "type": "options",
             "options_source": "story_tones", "default": "",
             "display_options": {"show": {"mode": ["tone"]}}},
            {"name": "track_ref", "label": "Track", "type": "string", "default": "",
             "display_options": {"show": {"mode": ["specific"]}}},
            {"name": "volume", "label": "Volume", "type": "number",
             "default": 0.15, "min": 0.0, "max": 1.0, "step": 0.05},
            {"name": "fade_in", "label": "Fade in (s)", "type": "number",
             "default": 2.0, "min": 0.0, "max": 10.0, "step": 0.5},
            {"name": "fade_out", "label": "Fade out (s)", "type": "number",
             "default": 3.0, "min": 0.0, "max": 10.0, "step": 0.5},
            {"name": "loop", "label": "Loop", "type": "boolean", "default": True},
            {"name": "ducking_enabled", "label": "Duck under voice", "type": "boolean", "default": True},
            {"name": "ducking_level", "label": "Ducking level", "type": "number",
             "default": 0.20, "min": 0.0, "max": 1.0, "step": 0.05},
        ],
        "capabilities": {"retry": False, "cancel": False},
        "executor": "studio.workflows.adapters.music:select",
    },
    "assemble.project": {
        "type_version": 1,
        "display_name": "Assemble Project",
        "description": "Merge audio, scenes, and assets into an editor project.",
        "category": "video",
        "icon": "layers",
        "inputs": [_TRIGGER_IN, _in("assets", "animation_assets", required=True),
                   _in("metadata", "tts_metadata", required=True), _in("scenes", "scenes", required=True),
                   _in("captions", "captions"), _in("music", "music_track"),
                   _in("settings", "project_settings")],
        "outputs": [_CONTROL_OUT, _out("project", "editor_project")],
        "config_schema": [],
        "capabilities": {"retry": False, "cancel": False},
        "executor": "studio.workflows.adapters.editor:assemble",
    },
    "timeline.project": {
        "type_version": 1,
        "display_name": "Timeline Project",
        "description": "Persist the assembled project for the timeline editor.",
        "category": "output",
        "icon": "sliders",
        "inputs": [_TRIGGER_IN, _in("project", "editor_project", required=True)],
        "outputs": [_CONTROL_OUT, _out("project", "editor_project"), _out("project_id", "project_id")],
        "config_schema": [],
        "capabilities": {"retry": False, "cancel": False},
        "executor": "studio.workflows.adapters.editor:timeline_project",
    },
    "export.video": {
        "type_version": 1,
        "display_name": "Video Export",
        "description": "Render the final video with FFmpeg.",
        "category": "output",
        "icon": "download",
        "inputs": [_TRIGGER_IN, _in("project", "editor_project", required=True),
                   _in("settings", "project_settings")],
        "outputs": [_CONTROL_OUT, _out("video", "video_file")],
        "config_schema": [
            {"name": "profile", "label": "Export profile", "type": "options",
             "options_source": "export_profiles", "default": "yt_shorts"},
            {"name": "captions", "label": "Bake captions", "type": "boolean", "default": True},
            {"name": "grain", "label": "Grain overlay", "type": "boolean", "default": False},
        ],
        "capabilities": {"retry": True, "cancel": True},
        "executor": "studio.workflows.adapters.export:video",
    },
    "workflow.output": {
        "type_version": 1,
        "display_name": "Workflow Output",
        "description": "Record a value as a result of this workflow.",
        "category": "utility",
        "icon": "flag",
        "inputs": [_TRIGGER_IN, {"id": "value", "type": "dynamic", "required": True, "multiple": False}],
        "outputs": [],
        "config_schema": [
            {"name": "port_type", "label": "Value type", "type": "options",
             "options": DYNAMIC_PORT_TYPES, "default": "generic_json", "required": True},
            {"name": "label", "label": "Label", "type": "string", "default": "", "max_length": 120},
        ],
        "capabilities": {"retry": False, "cancel": False},
        "executor": "studio.workflows.adapters.control:workflow_output",
    },
    "stub.input": {
        "type_version": 1,
        "display_name": "Sample Input",
        "description": "Editable sample data feeding an unconnected input (testing).",
        "category": "testing",
        "icon": "flask",
        "inputs": [],
        "outputs": [{"id": "value", "type": "dynamic"}],
        "config_schema": [
            {"name": "port_type", "label": "Data type", "type": "options",
             "options": DYNAMIC_PORT_TYPES, "default": "generic_json", "required": True},
            {"name": "payload", "label": "Sample payload", "type": "json", "default": {}},
        ],
        "capabilities": {"retry": False, "cancel": False},
        "executor": "studio.workflows.adapters.stubs:sample_input",
    },
    "stub.output": {
        "type_version": 1,
        "display_name": "Result Viewer",
        "description": "Captures a node's output for inspection (testing; pinning in Phase 4).",
        "category": "testing",
        "icon": "eye",
        "inputs": [{"id": "value", "type": "dynamic", "required": True, "multiple": False}],
        "outputs": [{"id": "value", "type": "dynamic"}],
        "config_schema": [
            {"name": "port_type", "label": "Data type", "type": "options",
             "options": DYNAMIC_PORT_TYPES, "default": "generic_json", "required": True},
            {"name": "pinned", "label": "Pin edited result", "type": "boolean", "default": False},
            {"name": "payload", "label": "Pinned payload", "type": "json", "default": {},
             "display_options": {"show": {"pinned": [True]}}},
        ],
        "capabilities": {"retry": False, "cancel": False},
        "executor": "studio.workflows.adapters.stubs:result_viewer",
    },
}

# Fields internal to the backend, stripped from the served form.
_INTERNAL_FIELDS = ("executor",)


def get_node_type(type_key):
    """Return the full internal definition for a node type, or None."""
    node = _NODE_TYPES.get(type_key)
    return deepcopy(node) if node is not None else None


def all_node_types():
    return deepcopy(_NODE_TYPES)


def is_supported(type_key, type_version):
    node = _NODE_TYPES.get(type_key)
    return bool(node) and node["type_version"] == type_version


def serialize_registry():
    """Presentation-safe registry payload for GET /api/workflow/node-types."""
    node_types = {}
    for key, definition in _NODE_TYPES.items():
        public = deepcopy({k: v for k, v in definition.items() if k not in _INTERNAL_FIELDS})
        public["type"] = key
        node_types[key] = public
    return {
        "registry_version": REGISTRY_VERSION,
        "port_types": list(PORT_TYPES),
        "categories": deepcopy(CATEGORIES),
        "node_types": node_types,
    }
