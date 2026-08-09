"""Provider compatibility surface — the one residual boundary (step 16.1).

Provider *input* aliases live on each package's manifest (`aliases=[]`) and are
resolved by the registry hub (id first, then alias). That is the only place a
shipped provider identity is translated for dispatch.

This module holds the two things that are *not* provider-declared:

  1. ``LEGACY_SELECTION_ALIASES`` — the retired ``app-config.json`` selection
     store wrote legacy wire spellings (``gemini``, ``grok``, ``kie-ai``, …).
     The one-time settings migration (v2) rewrites those into canonical ids
     before they enter ``settings.json``. After that migration has run, the
     table is never consulted at runtime.

  2. ``LEGACY_SELECTION_KEYS`` — the three key names that store used to own.
     The catalog no longer ships them, the frontend no longer defaults or
     mirrors them, and a load/write of ``app-config.json`` drops them.

Everything else — pipeline request fields, workflow node configs, extension
activate targets — speaks **canonical provider ids**. Aliases remain accepted
as *input* through the hub so un-migrated clients keep working.
"""

from __future__ import annotations

from typing import Mapping, MutableMapping


# Retired ``app-config.json`` selection values → canonical registry ids.
# Kept for the v2 settings migration only (§24.3). Not used at dispatch time.
LEGACY_SELECTION_ALIASES: dict[str, str] = {
    "gemini": "gemini_ws",
    "grok": "grok_automa",
    "kie-ai": "kie_ai",
    "webhook": "wavespeed_webhook",
    "direct": "wavespeed_direct",
}

# The three keys the retired store used. DomainSpecs keep the same strings so
# the v2 migration can still find them on an un-migrated machine; nothing else
# may read or write them after step 16.1.
LEGACY_SELECTION_KEYS: frozenset[str] = frozenset({
    "sts-tts-provider",
    "sts-storyboard-provider",
    "sts-asset-provider",
})


def normalize_selection_alias(value: str, *, domain: str | None = None) -> str:
    """Map a retired selection string onto a canonical provider id.

    ``builtin`` is domain-aware: under ``script`` it becomes ``gemini``; under
    ``scene_blueprint`` it becomes ``n8n``; elsewhere it is left alone so an
    unknown domain cannot silently pick the wrong package.
    """
    raw = (value or "").strip()
    if not raw:
        return raw
    if raw == "builtin":
        if domain == "script":
            return "gemini"
        if domain == "scene_blueprint":
            return "n8n"
        return raw
    return LEGACY_SELECTION_ALIASES.get(raw, raw)


def strip_legacy_selection_keys(user: MutableMapping | Mapping) -> dict:
    """Return a copy of an ``app-config.json['user']`` blob without the three keys.

    Used on every read-through of the retired store so a stale key cannot re-
    enter the browser defaults, and on write so the file itself converges.
    """
    if not isinstance(user, Mapping):
        return {}
    return {k: v for k, v in user.items() if k not in LEGACY_SELECTION_KEYS}


__all__ = [
    "LEGACY_SELECTION_ALIASES",
    "LEGACY_SELECTION_KEYS",
    "normalize_selection_alias",
    "strip_legacy_selection_keys",
]
