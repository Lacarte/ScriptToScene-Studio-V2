"""Backend-approved async option sources (step 2.3, contracts §11).

Every `options_source` identifier in the registry resolves through this
allowlist — schema-provided URLs are never fetched. Resolvers import
their data sources lazily so importing this module stays cheap.
"""

from loguru import logger

from .registry import ASYNC_OPTION_SOURCES

EXPORT_PROFILES = ["yt_shorts", "tiktok", "reels", "yt_landscape", "square"]


def _opt(value, label=None):
    return {"value": value, "label": label or value}


def _tts_voices():
    from studio.tts.routes import VOICES
    return [_opt(voice) for voice in VOICES]


def _story_tones():
    from studio.music.selector import TONE_MUSIC_MAP
    return [_opt("", "—")] + [_opt(tone) for tone in sorted(TONE_MUSIC_MAP)]


def _style_templates():
    from studio.build_scene_blueprints.templates import TEMPLATES_BY_ID
    options = []
    for template_id in sorted(TEMPLATES_BY_ID):
        template = TEMPLATES_BY_ID[template_id] or {}
        options.append(_opt(template_id, template.get("name") or template_id))
    return options


def _provider_options(domain):
    if domain == "storyboard":
        from studio.storyboard.providers import registry
    else:
        from studio.animator.providers import registry
    options = []
    for provider in registry.list_providers():
        manifest = getattr(provider, "manifest", None)
        provider_id = getattr(manifest, "id", None) or getattr(provider, "id", None)
        label = getattr(manifest, "label", None) or provider_id
        if provider_id:
            options.append(_opt(provider_id, label))
    return options


def _caption_presets():
    from studio.captions.routes import CAPTION_PRESETS
    options = []
    for preset_id, preset in CAPTION_PRESETS.items():
        label = preset_id
        if isinstance(preset, dict):
            label = preset.get("name") or preset.get("label") or preset_id
        options.append(_opt(preset_id, label))
    return options


_RESOLVERS = {
    "tts_voices": _tts_voices,
    "story_tones": _story_tones,
    "style_templates": _style_templates,
    "storyboard_providers": lambda: _provider_options("storyboard"),
    "animator_providers": lambda: _provider_options("animator"),
    "export_profiles": lambda: [_opt(p) for p in EXPORT_PROFILES],
    "caption_presets": _caption_presets,
}

# The registry allowlist and the resolver table must never drift.
assert set(_RESOLVERS) == set(ASYNC_OPTION_SOURCES), (
    "options resolvers out of sync with ASYNC_OPTION_SOURCES"
)


def resolve_options(source: str):
    """Return [{value, label}] for an allowlisted source, or None if unknown.

    Raises RuntimeError when a known source fails to load (surfaced as
    PROVIDER_UNAVAILABLE by the route).
    """
    resolver = _RESOLVERS.get(source)
    if resolver is None:
        return None
    try:
        return resolver()
    except Exception as exc:  # data source unavailable — never a 500
        logger.warning("option source {} failed: {}", source, exc)
        raise RuntimeError(f"Option source {source} is unavailable") from exc
