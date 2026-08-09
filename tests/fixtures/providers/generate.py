"""Regenerate the provider-boundary fixtures (contracts.md §46).

Run from the repository root:

    venv/Scripts/python.exe tests/fixtures/providers/generate.py

`request.json` and `raw_response.json` are **recorded by a human** and are never
touched here. This script only derives each `expected_result.json` from the
recorded response through the shared legacy adapters, and rewrites
`manifest.json` with the SHA-256 of every file, so an accidental edit fails a
test rather than silently changing the meaning of every provider test
(§46.4 rule 4).
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))
sys.path.insert(0, ROOT)

from studio.io_utils import safe_json_write  # noqa: E402
from studio.shared.providers_common import fixtures, legacy  # noqa: E402
from studio.shared.providers_common.results import coerce_result  # noqa: E402


def _tts_kokoro(raw):
    return legacy.tts_metadata_to_result(
        raw,
        audio_ref="tts/pm_SAMPLE/voice.wav",
        manifest_ref="tts/pm_SAMPLE/tts.json",
        provider_id="kokoro",
        provider_version="1.0.0",
    )


def _visual(domain, provider_id, manifest_ref, version):
    def build(raw):
        return legacy.visual_manifest_to_result(
            raw,
            domain=domain,
            provider_id=provider_id,
            manifest_ref=manifest_ref,
            provider_version=version,
        )
    return build


BUILDERS = {
    ("tts", "kokoro"): _tts_kokoro,
    ("storyboard", "wavespeed_webhook"): _visual(
        "storyboard", "wavespeed_webhook", "storyboard/pm_SAMPLE/storyboard.json", "1.0.0"
    ),
    ("animator", "kie_ai"): _visual(
        "animator", "kie_ai", "animator/pm_SAMPLE/grabber_job.json", "1.0.0"
    ),
}


def _drop_rotations() -> None:
    """Remove the `.bak` rotations `safe_json_write` leaves in the fixture tree."""
    for root, _dirs, files in os.walk(fixtures.fixture_root()):
        for name in files:
            if name.endswith(".bak"):
                os.unlink(os.path.join(root, name))


def main() -> int:
    for domain, provider_id in fixtures.list_boundaries():
        builder = BUILDERS.get((domain, provider_id))
        if builder is None:
            print(f"skip {domain}/{provider_id}: no builder registered")
            continue
        raw = fixtures.load_fixture(domain, provider_id, "raw_response.json")
        result = coerce_result(
            builder(raw),
            domain=domain,
            provider_id=provider_id,
            provider_version="1.0.0",
        )
        path = os.path.join(
            fixtures.fixture_dir(domain, provider_id), "expected_result.json"
        )
        safe_json_write(path, result.to_dict(), indent=2)
        print(f"wrote {domain}/{provider_id}/expected_result.json")

    print(f"wrote {fixtures.write_manifest()}")
    _drop_rotations()
    problems = fixtures.validate_fixtures()
    for problem in problems:
        print(f"PROBLEM: {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
