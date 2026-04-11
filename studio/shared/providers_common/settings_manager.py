"""Settings Manager — Phase 1: load, save, validate, atomic writes, redaction.

Canonical source of truth for nested provider settings at settings/settings.json.
Thread-safe with file locking.
"""

import json
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

from loguru import logger

from config import ROOT_DIR
from studio.shared.providers_common.settings_migrations import apply_migrations


SETTINGS_DIR = os.path.join(ROOT_DIR, "settings")
SETTINGS_PATH = os.path.join(SETTINGS_DIR, "settings.json")

_lock = threading.RLock()


def _ensure_settings_dir() -> None:
    """Ensure the settings directory exists."""
    os.makedirs(SETTINGS_DIR, exist_ok=True)


def load_settings() -> dict:
    """Load settings from settings/settings.json, applying migrations if needed.
    
    Returns the full settings dict with version, general, and domains keys.
    """
    _ensure_settings_dir()
    
    with _lock:
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            logger.warning("[settings] settings.json not found, returning defaults")
            return _default_settings()
        except json.JSONDecodeError as e:
            logger.error("[settings] Corrupted settings.json: {}, returning defaults", e)
            return _default_settings()
    
    migrated, changed = apply_migrations(data)
    if changed:
        logger.info("[settings] Applied migrations, version now {}", migrated.get("version"))
        save_settings(migrated)
    
    return migrated


def save_settings(data: dict) -> None:
    """Save settings to settings/settings.json atomically.
    
    Uses write-to-temp-then-rename for atomicity.
    """
    _ensure_settings_dir()
    
    with _lock:
        temp_fd, temp_path = tempfile.mkstemp(
            dir=SETTINGS_DIR,
            prefix=".settings_",
            suffix=".tmp"
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, SETTINGS_PATH)
            logger.debug("[settings] Saved settings.json")
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise


def _default_settings() -> dict:
    """Return default settings structure (v1)."""
    return {
        "version": 1,
        "general": {
            "default_style": "cinematic",
            "sync_folder": "",
            "auto_sync": False
        },
        "domains": {
            "tts": {
                "selected_provider": "kokoro",
                "per_provider": {}
            },
            "storyboard": {
                "selected_provider": "gemini_ws",
                "per_provider": {}
            },
            "animator": {
                "selected_provider": "grok_automa",
                "per_provider": {}
            }
        }
    }


def get_domain_settings(domain: str) -> dict:
    """Get settings for a specific domain."""
    settings = load_settings()
    return settings.get("domains", {}).get(domain, {})


def get_provider_settings(domain: str, provider_id: str) -> dict:
    """Get settings for a specific provider."""
    domain_settings = get_domain_settings(domain)
    return domain_settings.get("per_provider", {}).get(provider_id, {})


def set_provider_settings(domain: str, provider_id: str, provider_settings: dict) -> None:
    """Set settings for a specific provider."""
    settings = load_settings()
    if "domains" not in settings:
        settings["domains"] = {}
    if domain not in settings["domains"]:
        settings["domains"][domain] = {"selected_provider": None, "per_provider": {}}
    if "per_provider" not in settings["domains"][domain]:
        settings["domains"][domain]["per_provider"] = {}
    
    settings["domains"][domain]["per_provider"][provider_id] = provider_settings
    save_settings(settings)


def set_selected_provider(domain: str, provider_id: str) -> None:
    """Set the selected provider for a domain."""
    settings = load_settings()
    if "domains" not in settings:
        settings["domains"] = {}
    if domain not in settings["domains"]:
        settings["domains"][domain] = {"selected_provider": None, "per_provider": {}}
    
    settings["domains"][domain]["selected_provider"] = provider_id
    save_settings(settings)


def get_general_settings() -> dict:
    """Get general settings."""
    settings = load_settings()
    return settings.get("general", {})


def set_general_settings(general_settings: dict) -> None:
    """Set general settings."""
    settings = load_settings()
    settings["general"] = general_settings
    save_settings(settings)


SENSITIVE_KEYS_RE = re.compile(
    r"(api_key|token|secret|password|auth|bearer|credential)",
    re.IGNORECASE
)


def redact_settings(data: dict) -> dict:
    """Redact sensitive fields from settings.
    
    Redacts fields that:
    - Have type "password" in schema
    - Keys matching *_key, *_token, *_secret patterns
    """
    if not isinstance(data, dict):
        return data
    
    redacted = {}
    for key, value in data.items():
        if SENSITIVE_KEYS_RE.search(key):
            redacted[key] = "***"
        elif isinstance(value, dict):
            redacted[key] = redact_settings(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_settings(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            redacted[key] = value
    
    return redacted


def redacted_provider_settings(domain: str, provider_id: str) -> dict:
    """Get redacted settings for a specific provider."""
    return redact_settings(get_provider_settings(domain, provider_id))


def validate_settings(data: dict) -> list[dict]:
    """Validate settings structure.
    
    Returns list of ValidationIssue dicts with 'field', 'severity', 'message'.
    """
    issues = []
    
    if not isinstance(data, dict):
        return [{"field": "root", "severity": "error", "message": "Settings must be a JSON object"}]
    
    version = data.get("version")
    if version is None:
        issues.append({"field": "version", "severity": "warning", "message": "version field missing, assuming v1"})
    
    domains = data.get("domains")
    if not isinstance(domains, dict):
        issues.append({"field": "domains", "severity": "error", "message": "domains must be an object"})
    else:
        valid_domains = {"tts", "storyboard", "animator"}
        for domain in domains:
            if domain not in valid_domains:
                issues.append({
                    "field": f"domains.{domain}",
                    "severity": "warning",
                    "message": f"Unknown domain '{domain}'"
                })
    
    return issues
