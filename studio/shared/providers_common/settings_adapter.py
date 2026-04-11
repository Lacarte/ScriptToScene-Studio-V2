"""Settings Adapter — DEPRECATED: Phase 9 removal planned.

Translates between:
  - Old flat format: app-config.json['user'] (e.g., sts-tts-voice, sts-auto-type)
  - New nested format: settings/settings.json (domains.{domain}.per_provider.{id})

This adapter is a TEMPORARY compatibility shim. It must be deleted in Phase 9.
Mark your calendars: Phase 9 cleanup.
"""

import warnings
from typing import Any

from loguru import logger

from config import APP_CONFIG_PATH
from studio.io_utils import safe_json_read, safe_json_write


warnings.warn(
    "settings_adapter.py is deprecated and will be removed in Phase 9. "
    "Use settings_manager.py directly for all new code.",
    DeprecationWarning,
    stacklevel=2
)


FLAT_TO_NESTED = {
    "sts-tts-voice": ("tts", "kokoro", "voice"),
    "sts-tts-lang": ("tts", "kokoro", "lang"),
    "sts-tts-speed": ("tts", "kokoro", "speed"),
    "sts-tts-blend": ("tts", "kokoro", "blend"),
    "sts-tts-blendA": ("tts", "kokoro", "blendA"),
    "sts-tts-blendB": ("tts", "kokoro", "blendB"),
    "sts-tts-blendRatio": ("tts", "kokoro", "blendRatio"),
    "sts-tts-blendMethod": ("tts", "kokoro", "blendMethod"),
    "sts-tts-genMode": ("tts", "kokoro", "genMode"),
    "sts-tts-provider": ("tts", "selected_provider", None),
    "sts-tts-voiceOpen": ("tts", "kokoro", "voiceOpen"),
    "sts-auto-type": ("storyboard", "gemini_ws", "auto_type"),
    "sts-sync-folder": ("general", "sync_folder", None),
    "sts-auto-sync": ("general", "auto_sync", None),
    "sts-normalize": ("general", "normalize", None),
    "sts-clean": ("general", "clean", None),
}

GENERAL_NESTED_TO_FLAT = {
    nested_field: flat_key
    for flat_key, (domain, nested_field, field) in FLAT_TO_NESTED.items()
    if domain == "general"
}

SELECTED_PROVIDER_NESTED_TO_FLAT = {
    domain: flat_key
    for flat_key, (domain, nested_field, field) in FLAT_TO_NESTED.items()
    if nested_field == "selected_provider" and field is None
}

PROVIDER_NESTED_TO_FLAT = {
    (domain, provider, field): flat_key
    for flat_key, (domain, provider, field) in FLAT_TO_NESTED.items()
    if field is not None and domain != "general"
}


def flat_to_nested(flat: dict) -> dict:
    """Convert flat app-config['user'] dict to nested settings format."""
    result = {
        "version": 1,
        "general": {},
        "domains": {
            "tts": {"selected_provider": None, "per_provider": {"kokoro": {}, "inworld": {}}},
            "storyboard": {"selected_provider": "gemini_ws", "per_provider": {"gemini_ws": {}}},
            "animator": {"selected_provider": "grok_automa", "per_provider": {"grok_automa": {}}},
        }
    }
    
    for flat_key, value in flat.items():
        if flat_key not in FLAT_TO_NESTED:
            continue
        
        domain, provider_or_field, field = FLAT_TO_NESTED[flat_key]
        
        if domain == "general":
            result["general"][provider_or_field] = value
        elif field is None:
            result["domains"][domain]["selected_provider"] = value
        else:
            provider = provider_or_field
            result["domains"][domain]["per_provider"].setdefault(provider, {})[field] = value
    
    return result


def nested_to_flat(nested: dict) -> dict:
    """Convert nested settings format to flat app-config['user'] dict."""
    result = {}

    general = nested.get("general", {})
    for key, value in general.items():
        flat_key = GENERAL_NESTED_TO_FLAT.get(key)
        if flat_key:
            result[flat_key] = value

    domains = nested.get("domains", {})
    for domain, domain_data in domains.items():
        selected = domain_data.get("selected_provider")
        if selected:
            flat_key = SELECTED_PROVIDER_NESTED_TO_FLAT.get(domain)
            if flat_key:
                result[flat_key] = selected

        per_provider = domain_data.get("per_provider", {})
        for provider, settings in per_provider.items():
            if not isinstance(settings, dict):
                continue
            for field, value in settings.items():
                flat_key = PROVIDER_NESTED_TO_FLAT.get((domain, provider, field))
                if flat_key:
                    result[flat_key] = value

    return result


def read_flat_settings() -> dict:
    """Read flat settings from app-config.json['user']."""
    try:
        cfg = safe_json_read(APP_CONFIG_PATH) or {}
        return cfg.get("user", {})
    except Exception as e:
        logger.warning("[adapter] Failed to read flat settings: {}", e)
        return {}


def write_flat_settings(flat: dict) -> None:
    """Write flat settings to app-config.json['user']."""
    try:
        cfg = safe_json_read(APP_CONFIG_PATH) or {"version": 2, "defaults": {}, "localStorage": []}
        cfg["user"] = flat
        safe_json_write(APP_CONFIG_PATH, cfg, indent=2)
    except Exception as e:
        logger.error("[adapter] Failed to write flat settings: {}", e)
        raise


def get_flat_setting(key: str, default: Any = None) -> Any:
    """Get a single flat setting."""
    flat = read_flat_settings()
    return flat.get(key, default)


def set_flat_setting(key: str, value: Any) -> None:
    """Set a single flat setting."""
    flat = read_flat_settings()
    flat[key] = value
    write_flat_settings(flat)
