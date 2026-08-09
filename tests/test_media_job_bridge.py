"""Step 14.1 — Storyboard and Animator running on the shared media-job service.

`test_media_jobs.py` covers the service in isolation. This file drives the two
real adapters through it with scripted legacy job stores, which is what proves
the second half of the step: the visual domains *share* the orchestration, and
their public job IDs, manifests, node payloads, and error codes did not move.

Every scenario is parametrized over both domains and asserted with identical
expectations — a domain-specific branch in the shared path would show up as a
divergence between the two parameters rather than as a source-level grep.
"""

from __future__ import annotations

import json
import os
import random

import pytest

from studio.io_utils import safe_json_write
from studio.shared.providers_common.jobs import status_from_scenes
from studio.shared.providers_common.media_jobs import (
    RECORD_FILENAME,
    MediaJobService,
    MediaJobStore,
)
from studio.workflows.adapters import animator as animator_adapter
from studio.workflows.adapters import media_job
from studio.workflows.adapters import storyboard as storyboard_adapter
from studio.workflows.adapters.common import AdapterError

PROJECT_ID = "pm_BRIDGE01"
SCENES = {
    "scenes": [
        {"index": 0, "image_prompt": "a lighthouse"},
        {"index": 1, "image_prompt": "a harbour"},
    ]
}
DOMAINS = ["storyboard", "animator"]


# -- per-domain manifest shapes ---------------------------------------------


def _storyboard_manifest(states, *, job_status="running"):
    """The `storyboard.json` shape, counters included."""
    entries = {}
    for index, state in enumerate(states):
        entry = {"status": state, "image_url": None, "local_path": None}
        if state == "ready":
            entry["local_path"] = f"/output/storyboard/{PROJECT_ID}/{index}/image.jpeg"
        entries[str(index)] = entry
    return {
        "project_id": PROJECT_ID,
        "status": job_status,
        "total": len(states),
        "ready": sum(1 for state in states if state == "ready"),
        "errors": sum(1 for state in states if state == "error"),
        "scene_statuses": entries,
    }


def _animator_manifest(states, *, job_status="waiting"):
    """The `grabber_job.json` shape, which carries no counters at all."""
    entries = {}
    for index, state in enumerate(states):
        entry = {"status": state, "urls": [], "local_files": []}
        if state == "ready":
            entry["local_files"] = [f"/output/animator/{PROJECT_ID}/{index}/clip.mp4"]
        entries[str(index)] = entry
    return {
        "grabber_id": f"workflow_{PROJECT_ID}",
        "project_id": PROJECT_ID,
        "status": job_status,
        "scene_statuses": entries,
    }


MANIFEST = {"storyboard": _storyboard_manifest, "animator": _animator_manifest}
MANIFEST_NAME = {"storyboard": "storyboard.json", "animator": "grabber_job.json"}
FAILURE_CODE = {"storyboard": "STORYBOARD_FAILED", "animator": "ANIMATOR_FAILED"}


# -- harness ----------------------------------------------------------------


class _InlineThread:
    """A `threading.Thread` stand-in that runs its target on `start()`."""

    def __init__(self, target=None, args=(), kwargs=None, **_ignored):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target is not None:
            self._target(*self._args, **self._kwargs)


class InlineThreads:
    """Substitute for the `threading` module inside a provider under test."""

    Thread = _InlineThread


class Harness:
    """Drive one visual adapter against a scripted legacy job store.

    The script advances inside the fake sleeper, which is exactly when the real
    store makes progress: the service is waiting out its poll interval.
    """

    def __init__(self, domain, tmp_path, monkeypatch, *, stop=False, deadline=None):
        self.domain = domain
        self.states = []
        self.index = 0
        self.starts = 0
        self.progress = []
        self.stop = stop
        self.now = 0.0
        self.root = tmp_path / domain
        self.dir = self.root / PROJECT_ID
        self.manifest = str(self.dir / MANIFEST_NAME[domain])
        self._monkeypatch = monkeypatch
        self._deadline = deadline
        self._install()

    # -- scripting ----------------------------------------------------------

    def script(self, *states):
        """`states` is a list of per-scene status lists, one per observation."""
        self.states = list(states)
        self.index = 0
        return self

    def current(self):
        return self.states[min(self.index, len(self.states) - 1)]

    def _advance(self):
        previous = self.index
        self.index = min(self.index + 1, len(self.states) - 1)
        # A store that has nothing new to say rewrites nothing; the timeout
        # cases otherwise spend the whole deadline re-serializing one state.
        if self.index != previous:
            self._publish()

    def _publish(self):
        raise NotImplementedError

    # -- wiring -------------------------------------------------------------

    def _clock(self):
        return self.now

    def _sleeper(self, seconds):
        self.now += max(0.0, seconds)
        self._advance()

    def _install(self):
        store = MediaJobStore()
        service = MediaJobService(
            store,
            clock=self._clock,
            sleeper=self._sleeper,
            rng=random.Random(0),
        )
        self._monkeypatch.setattr(media_job, "MediaJobService", lambda: service)
        self._install_domain()

    def _install_domain(self):
        raise NotImplementedError

    def context(self):
        harness = self

        class Ctx:
            project_id = PROJECT_ID
            execution_id = "ex_bridge"
            node_id = "n_visual"
            stage_artifact = None

            @staticmethod
            def stop_requested():
                return harness.stop

            @staticmethod
            def progress(message):
                harness.progress.append(message)

        return Ctx()

    def run(self, config=None):
        raise NotImplementedError

    @property
    def record_path(self):
        return str(self.dir / RECORD_FILENAME)


class StoryboardHarness(Harness):
    """Step 14.2 moved the storyboard seam: the adapter now hands the real
    provider to the service, so the script is installed under the provider's
    transport rather than under a route helper."""

    def _install_domain(self):
        from studio.shared.providers_common.hub import hub
        from studio.storyboard import generation, jobs as sb_jobs

        self._monkeypatch.setattr(storyboard_adapter, "STORYBOARD_DIR", str(self.root))
        self._monkeypatch.setattr(sb_jobs, "STORYBOARD_DIR", str(self.root))
        self._monkeypatch.setattr(sb_jobs, "seed", lambda *a, **k: {})
        self._monkeypatch.setattr(sb_jobs, "save_scene_prompts", lambda *a, **k: None)
        # `run_batch` is what the WaveSpeed providers hand to their worker
        # thread. Running it inline keeps the scripted store deterministic.
        self._monkeypatch.setattr(
            generation, "run_batch", lambda *a, **k: self._started()
        )
        module = hub.get("storyboard", "wavespeed_webhook").provider_module
        self._monkeypatch.setattr(module, "threading", InlineThreads)

    def _started(self):
        self.starts += 1
        self._publish()

    def _publish(self):
        if not self.states:
            return
        states = self.current()
        done = all(state in ("ready", "error") for state in states)
        safe_json_write(
            self.manifest,
            MANIFEST["storyboard"](states, job_status="done" if done else "running"),
        )

    def run(self, config=None):
        merged = {"storyboard_provider_override": "wavespeed_webhook"}
        merged.update(config or {})
        return storyboard_adapter._step_storyboard(
            SCENES, merged, PROJECT_ID, self.context()
        )


class AnimatorHarness(Harness):
    """Step 14.3 moved the animator seam: the adapter hands the real provider
    to the service, so the script is installed under the provider's transport
    rather than under a route helper."""

    def _install_domain(self):
        from studio.animator import jobs as anim_jobs
        from studio.animator import routes as animator_routes
        from studio.shared.providers_common.hub import hub

        self._monkeypatch.setattr(animator_adapter, "ANIMATOR_DIR", str(self.root))
        self._monkeypatch.setattr(anim_jobs, "ANIMATOR_DIR", str(self.root))
        # Seed becomes a no-op; the scripted statuses on disk are authoritative.
        self._monkeypatch.setattr(anim_jobs, "seed", lambda *a, **k: self._started() or {})
        self._monkeypatch.setattr(
            animator_routes, "queue_grabber_start", lambda *a, **k: None
        )
        self._monkeypatch.setattr(
            animator_routes, "is_extension_connected", lambda: True
        )
        # poll reads through jobs.status → jobs.read; point read at the script.
        self._monkeypatch.setattr(anim_jobs, "read", lambda *a, **k: self._live())
        # Ensure the provider module is constructible without side effects.
        module = hub.get("animator", "grok_automa").provider_module
        self._monkeypatch.setattr(module, "STORYBOARD_DIR", str(self.root))

    def _started(self):
        self.starts += 1
        self._publish()

    def _live(self):
        if not self.states or self.starts == 0:
            return None
        states = self.current()
        done = all(state in ("ready", "error") for state in states)
        return MANIFEST["animator"](states, job_status="done" if done else "waiting")

    def _publish(self):
        live = self._live()
        if live is not None:
            safe_json_write(self.manifest, live)

    def run(self, config=None):
        merged = {"animator_provider_override": "grok_automa"}
        merged.update(config or {})
        return animator_adapter._step_assets(
            SCENES, merged, PROJECT_ID, self.context()
        )


HARNESS = {"storyboard": StoryboardHarness, "animator": AnimatorHarness}


@pytest.fixture
def harness(request, tmp_path, monkeypatch):
    def build(domain, **kwargs):
        return HARNESS[domain](domain, tmp_path, monkeypatch, **kwargs)

    return build


# -- shared scenarios, identical expectations for both domains --------------


@pytest.mark.parametrize("domain", DOMAINS)
def test_all_scenes_ready_reports_success_for_both_domains(harness, domain):
    job = harness(domain).script(["pending", "pending"], ["ready", "pending"], ["ready", "ready"])
    result = job.run()
    assert result["total"] == 2
    assert result["ready"] == 2
    assert result["errors"] == 0
    assert job.starts == 1


@pytest.mark.parametrize("domain", DOMAINS)
def test_partial_success_keeps_the_produced_scenes(harness, domain):
    job = harness(domain).script(["pending", "pending"], ["ready", "error"])
    result = job.run()
    assert (result["total"], result["ready"], result["errors"]) == (2, 1, 1)


@pytest.mark.parametrize("domain", DOMAINS)
def test_all_scenes_failed_can_never_be_reported_as_success(harness, domain):
    job = harness(domain).script(["pending", "pending"], ["error", "error"])
    with pytest.raises(AdapterError) as raised:
        job.run()
    assert raised.value.code == FAILURE_CODE[domain]
    assert raised.value.details["errors"] == 2


@pytest.mark.parametrize("domain", DOMAINS)
def test_cancellation_raises_cancelled_not_a_failure(harness, domain):
    job = harness(domain, stop=True).script(["pending", "pending"])
    with pytest.raises(AdapterError) as raised:
        job.run()
    assert raised.value.code == "CANCELLED"


@pytest.mark.parametrize("domain", DOMAINS)
def test_a_stuck_job_times_out_with_poll_timeout(harness, domain):
    # The store never moves past pending, so the frozen domain deadline is the
    # only thing that ends the wait.
    job = harness(domain).script(["pending", "pending"])
    with pytest.raises(AdapterError) as raised:
        job.run()
    assert raised.value.code == "POLL_TIMEOUT"


@pytest.mark.parametrize("domain", DOMAINS)
def test_a_store_that_declares_itself_done_settles_instead_of_waiting(harness, domain):
    """`gemini_ws._mark_job_done` writes `status: "done"` over pending scenes."""
    job = harness(domain)
    job.script(["pending", "pending"], ["ready", "pending"])
    # Force the "declared done, one scene never arrived" shape.
    job._publish = lambda: safe_json_write(
        job.manifest, MANIFEST[domain](job.current(), job_status="done")
    )
    if domain == "animator":
        from studio.animator import jobs as anim_jobs

        job._monkeypatch.setattr(
            anim_jobs,
            "read",
            lambda *a, **k: MANIFEST[domain](job.current(), job_status="done")
            if job.starts
            else None,
        )
    result = job.run()
    assert result["ready"] == 1
    assert result["total"] == 2


@pytest.mark.parametrize("domain", DOMAINS)
def test_the_job_record_is_persisted_next_to_the_domain_manifest(harness, domain):
    """D33: job persistence/rehydration now exists for *both* visual domains."""
    job = harness(domain).script(["pending", "pending"], ["ready", "ready"])
    job.run()

    assert os.path.isfile(job.record_path)
    with open(job.record_path, encoding="utf-8") as handle:
        record = json.load(handle)
    # The public job ID is still the project ID; the legacy manifest is intact.
    assert record["handle"]["job_id"] == PROJECT_ID
    assert record["handle"]["domain"] == domain
    assert record["status"]["ready"] == 2
    assert os.path.isfile(job.manifest)
    assert os.path.basename(job.manifest) == MANIFEST_NAME[domain]


@pytest.mark.parametrize("domain", DOMAINS)
def test_persisted_refs_are_managed_and_never_absolute(harness, domain):
    job = harness(domain).script(["pending", "pending"], ["ready", "ready"])
    job.run()
    with open(job.record_path, encoding="utf-8") as handle:
        record = json.load(handle)
    refs = [ref for unit in record["status"]["units"] for ref in unit["artifact_refs"]]
    assert refs, "successful units must record their artifacts"
    for ref in refs:
        assert not ref.startswith("/")
        assert not ref.startswith("output/")
        assert ref.startswith(f"{domain}/{PROJECT_ID}/")


@pytest.mark.parametrize("domain", DOMAINS)
def test_progress_is_reported_where_the_legacy_loops_reported_none(harness, domain):
    job = harness(domain).script(["pending", "pending"], ["ready", "ready"])
    job.run()
    assert job.progress, "the shared service must emit execution progress"
    assert job.progress[0] == "submitted"


@pytest.mark.parametrize("domain", DOMAINS)
def test_an_empty_scene_list_still_fails_before_any_job_is_started(harness, domain):
    job = harness(domain).script(["pending", "pending"])
    with pytest.raises(AdapterError) as raised:
        if domain == "storyboard":
            storyboard_adapter._step_storyboard(
                {"scenes": [{"index": 0}]}, {}, PROJECT_ID, job.context()
            )
        else:
            animator_adapter._step_assets(
                {"scenes": [{"index": 0}]}, {}, PROJECT_ID, job.context()
            )
    assert raised.value.code == "SCENES_EMPTY"
    assert job.starts == 0


# -- the storyboard-only sentinel, fixed in the shared helper ---------------


def test_the_job_level_sentinel_is_not_counted_as_a_scene():
    """`gemini_ws` writes a `-1` marker into the per-scene map; it is no unit."""
    scenes = {
        "0": {"status": "ready"},
        "1": {"status": "error"},
        "-1": {"status": "done"},
    }
    status = status_from_scenes("pm_X", scenes)
    assert status.total == 2
    assert status.ready == 1
    assert status.state == "partial"


def test_the_sentinel_alone_is_not_a_finished_job():
    status = status_from_scenes("pm_X", {"0": {"status": "pending"}, "-1": {"status": "done"}})
    assert status.total == 1
    assert not status.terminal


# -- the node payload the ports have always carried -------------------------


def test_storyboard_still_returns_its_scene_statuses(harness):
    job = harness("storyboard").script(["pending", "pending"], ["ready", "ready"])
    result = job.run()
    assert set(result["scene_statuses"]) == {"0", "1"}


def test_animator_still_omits_scene_statuses_and_names_its_provider(harness):
    job = harness("animator").script(["pending", "pending"], ["ready", "ready"])
    result = job.run()
    assert "scene_statuses" not in result
    assert result["provider"] == "grok_automa"
