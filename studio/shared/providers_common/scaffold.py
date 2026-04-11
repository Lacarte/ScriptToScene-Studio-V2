"""Provider Scaffolding CLI — Phase 9.

Creates new provider folders from templates.

Usage:
    python -m studio.shared.providers_common.scaffold tts my_new_provider
    python -m studio.shared.providers_common.scaffold storyboard image_provider --kind cloud
    python -m studio.shared.providers_common.scaffold animator video_provider --kind extension
"""

import sys
from pathlib import Path

from loguru import logger

from config import ROOT_DIR


# Each template is a Python str.format() template.
# - `{id}` / `{label}` / `{kind}` / `{requires}` / `{name_cap}` are placeholders.
# - Literal `{` and `}` are escaped as `{{` and `}}` (standard format() rules).
_TEMPLATES = {
    "tts": {
        "manifest.py": '''"""{label} TTS Provider Manifest."""

from studio.shared.providers_common import ProviderManifest


def manifest() -> ProviderManifest:
    return ProviderManifest(
        id="{id}",
        label="{label}",
        domain="tts",
        kind="{kind}",
        version="1.0.0",
        requires={requires},
        capabilities={{
            "test_connection": True,
            "streaming": False,
            "model_download": False,
            "single_scene": True,
            "batch": True,
            "voice_list": True,
        }},
    )
''',
        "settings_schema.py": '''"""{label} TTS Settings Schema."""


def settings_schema() -> dict:
    return {{
        "type": "object",
        "properties": {{
            # Add your fields here, e.g.:
            # "api_key": {{
            #     "type": "string",
            #     "label": "API Key",
            #     "ui": {{"type": "password"}},
            # }},
        }},
        "required": [],
    }}
''',
        "provider.py": '''"""{label} TTS Provider."""

from typing import Optional, Callable

from studio.tts.providers.base import TTSProvider, TTSResult, Voice


class {name_cap}Provider(TTSProvider):
    """{label} TTS provider implementation."""

    def synthesize(
        self,
        text: str,
        settings: dict,
        voice: Optional[str] = None,
        speed: float = 1.0,
        on_progress: Optional[Callable] = None,
    ) -> TTSResult:
        raise NotImplementedError("{name_cap}Provider.synthesize not implemented")

    def list_voices(self, settings: dict) -> list[Voice]:
        return []

    def shutdown(self) -> None:
        pass


def validate_settings(settings: dict) -> list[dict]:
    issues = []
    return issues


def health_check(settings: dict) -> dict:
    return {{"status": "warn", "message": "Not implemented yet"}}
''',
    },
    "storyboard": {
        "manifest.py": '''"""{label} Storyboard Provider Manifest."""

from studio.shared.providers_common import ProviderManifest


def manifest() -> ProviderManifest:
    return ProviderManifest(
        id="{id}",
        label="{label}",
        domain="storyboard",
        kind="{kind}",
        version="1.0.0",
        requires={requires},
        capabilities={{
            "test_connection": True,
            "single_scene": True,
            "batch": True,
        }},
    )
''',
        "settings_schema.py": '''"""{label} Storyboard Settings Schema."""


def settings_schema() -> dict:
    return {{
        "type": "object",
        "properties": {{
        }},
        "required": [],
    }}
''',
        "provider.py": '''"""{label} Storyboard Provider."""

from typing import Optional, Callable

from studio.storyboard.providers.base import (
    StoryboardProvider,
    JobHandle,
    JobStatus,
    SceneResult,
)


class {name_cap}Provider(StoryboardProvider):
    """{label} storyboard provider implementation."""

    def submit(
        self,
        project_id: str,
        scenes: list,
        settings: dict,
        on_progress: Optional[Callable] = None,
    ) -> JobHandle:
        raise NotImplementedError("{name_cap}Provider.submit not implemented")

    def poll(self, job_id: str, settings: dict) -> JobStatus:
        return JobStatus(job_id=job_id, status="unknown")

    def shutdown(self) -> None:
        pass


def validate_settings(settings: dict) -> list[dict]:
    return []


def health_check(settings: dict) -> dict:
    return {{"status": "warn", "message": "Not implemented yet"}}
''',
    },
    "animator": {
        "manifest.py": '''"""{label} Animator Provider Manifest."""

from studio.shared.providers_common import ProviderManifest


def manifest() -> ProviderManifest:
    return ProviderManifest(
        id="{id}",
        label="{label}",
        domain="animator",
        kind="{kind}",
        version="1.0.0",
        requires={requires},
        capabilities={{
            "test_connection": True,
            "single_scene": True,
            "batch": True,
        }},
    )
''',
        "settings_schema.py": '''"""{label} Animator Settings Schema."""


def settings_schema() -> dict:
    return {{
        "type": "object",
        "properties": {{
        }},
        "required": [],
    }}
''',
        "provider.py": '''"""{label} Animator Provider."""

from typing import Optional, Callable

from studio.animator.providers.base import (
    AnimatorProvider,
    JobHandle,
    JobStatus,
    SceneResult,
)


class {name_cap}Provider(AnimatorProvider):
    """{label} animator provider implementation."""

    def submit(
        self,
        project_id: str,
        scenes: list,
        settings: dict,
        on_progress: Optional[Callable] = None,
    ) -> JobHandle:
        raise NotImplementedError("{name_cap}Provider.submit not implemented")

    def poll(self, job_id: str, settings: dict) -> JobStatus:
        return JobStatus(job_id=job_id, status="unknown")

    def shutdown(self) -> None:
        pass


def validate_settings(settings: dict) -> list[dict]:
    return []


def health_check(settings: dict) -> dict:
    return {{"status": "warn", "message": "Not implemented yet"}}
''',
    },
}


def _name_cap(provider_id: str) -> str:
    """Convert snake_case provider id to CamelCase class name."""
    return "".join(part.capitalize() or "_" for part in provider_id.split("_"))


def create_provider(
    domain: str,
    provider_id: str,
    kind: str = "cloud",
    label: str = None,
) -> Path:
    """Create a new provider from template.

    Args:
        domain: tts, storyboard, or animator
        provider_id: ID for the provider (must be snake_case, matches folder name)
        kind: local, cloud, or extension
        label: Display label (defaults to provider_id title-cased)

    Returns:
        Path to the created provider directory.
    """
    if domain not in _TEMPLATES:
        raise ValueError(f"Domain must be one of: {list(_TEMPLATES.keys())}")

    if kind not in ("local", "cloud", "extension"):
        raise ValueError("kind must be one of: local, cloud, extension")

    if not provider_id.replace("_", "").isalnum():
        raise ValueError(f"provider_id must be snake_case alphanumeric, got: {provider_id!r}")

    if label is None:
        label = provider_id.replace("_", " ").title()

    providers_dir = Path(ROOT_DIR) / "studio" / domain / "providers" / provider_id

    if providers_dir.exists():
        raise FileExistsError(f"Provider already exists: {providers_dir}")

    requires = ["api_key"] if kind == "cloud" else []

    providers_dir.mkdir(parents=True)
    logger.info("Created provider directory: {}", providers_dir)

    for filename, template in _TEMPLATES[domain].items():
        content = template.format(
            id=provider_id,
            label=label,
            kind=kind,
            requires=repr(requires),
            name_cap=_name_cap(provider_id),
        )
        file_path = providers_dir / filename
        file_path.write_text(content, encoding="utf-8", newline="\n")
        logger.info("Created: {}", file_path)

    logger.success("Created {} provider '{}' at {}", domain, label, providers_dir)
    logger.info("Restart the app to discover the new provider.")
    return providers_dir


def main():
    """CLI entry point."""
    argv = sys.argv[1:]
    if len(argv) < 2 or "--help" in argv or "-h" in argv:
        print(__doc__)
        print("\nArguments:")
        print("  domain        tts | storyboard | animator")
        print("  provider_id   snake_case provider identifier")
        print("\nOptions:")
        print("  --kind KIND   local | cloud (default) | extension")
        print("  --label TEXT  Display label (default: provider_id title-cased)")
        sys.exit(0 if "--help" in argv or "-h" in argv else 1)

    domain = argv[0].lower()
    provider_id = argv[1].lower()

    kind = "cloud"
    label = None
    if "--kind" in argv:
        idx = argv.index("--kind")
        if idx + 1 < len(argv):
            kind = argv[idx + 1].lower()
    if "--label" in argv:
        idx = argv.index("--label")
        if idx + 1 < len(argv):
            label = argv[idx + 1]

    try:
        create_provider(domain, provider_id, kind, label)
    except Exception as e:
        logger.error("{}: {}", type(e).__name__, e)
        sys.exit(1)


if __name__ == "__main__":
    main()
