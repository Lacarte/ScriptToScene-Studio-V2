"""Step 14.1 — shared asynchronous media-job service.

Deterministic coverage of multi-unit submit/poll/push orchestration:
all-success, partial-success, all-failed, delayed callback, duplicate
callback, restart reconciliation, cancellation, timeout, and retry.

The service is media-neutral: the same tests run against both visual domain
labels so Storyboard and Animator can share it without domain branches.
"""

from __future__ import annotations

import os
import random
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from studio.shared.providers_common.errors import (
    PROVIDER_NOT_FOUND,
    PROVIDER_TIMEOUT,
    PROVIDER_UNIT_FAILED,
    ProviderCancelled,
    ProviderError,
    ProviderErrorPayload,
)
from studio.shared.providers_common.invocation import (
    CancellationToken,
    ProgressReporter,
    ProviderInvocation,
    ProviderLogger,
)
from studio.shared.providers_common.jobs import (
    FIRST_POLL_DELAY_S,
    JOB_CANCELLED,
    MAX_CONSECUTIVE_POLL_FAILURES,
    RUNNING,
    SUBMITTED,
    TIMED_OUT,
    JobHandle,
    JobStatus,
    poll_interval,
)
from studio.shared.providers_common.media_jobs import (
    RECORD_FILENAME,
    MediaJobService,
    MediaJobStore,
    filter_request_units,
    legacy_progress,
    merge_prior_units,
    record_path_for,
    result_from_status,
    units_from_legacy_scenes,
    units_needing_retry,
)
from studio.shared.providers_common.results import (
    PARTIAL,
    SUCCEEDED,
    UNIT_FAILED,
    UNIT_SUCCEEDED,
    UnitResult,
)


PROJECT_ID = "pm_MEDIAJOB1"
DOMAINS = ("storyboard", "animator")


# -- fakes ------------------------------------------------------------------


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += max(0.0, seconds)


class ScriptedProvider:
    """Async provider driven entirely by the test — no wall clock, no I/O.

    Each `poll()` consumes the next scripted status. `push_later` is applied
    by the test via `service.apply_callback` between polls.
    """

    def __init__(
        self,
        *,
        job_id: str = "job-1",
        poll_script: list[JobStatus] | None = None,
        fail_polls: int = 0,
        fail_poll_exc: BaseException | None = None,
    ):
        self.job_id = job_id
        self.poll_script = list(poll_script or [])
        self.fail_polls = fail_polls
        self.fail_poll_exc = fail_poll_exc or RuntimeError("poll transport down")
        self.submit_calls = 0
        self.poll_calls = 0
        self.cancel_calls = 0
        self.last_request = None
        self.last_invocation = None

    def submit(self, request, invocation) -> JobHandle:
        self.submit_calls += 1
        self.last_request = request
        self.last_invocation = invocation
        return JobHandle(
            job_id=self.job_id,
            domain=invocation.domain,
            provider_id=invocation.provider_id,
            project_id=invocation.project_id,
            invocation_id=invocation.invocation_id,
        )

    def poll(self, job_id: str, invocation) -> JobStatus:
        self.poll_calls += 1
        if self.fail_polls > 0:
            self.fail_polls -= 1
            raise self.fail_poll_exc
        if not self.poll_script:
            return JobStatus(job_id=job_id, state=RUNNING, ready=0, total=1)
        return self.poll_script.pop(0)

    def cancel_job(self, job_id: str, invocation) -> None:
        self.cancel_calls += 1


def _unit(index: int, state: str = UNIT_SUCCEEDED, ref: str | None = None) -> UnitResult:
    if state == UNIT_SUCCEEDED:
        return UnitResult(
            unit_index=index,
            state=UNIT_SUCCEEDED,
            artifact_refs=(ref or f"unit-{index}.bin",),
        )
    return UnitResult(
        unit_index=index,
        state=UNIT_FAILED,
        error=ProviderErrorPayload.from_error(
            ProviderError(PROVIDER_UNIT_FAILED, f"unit {index} failed", retryable=True)
        ),
    )


def _status(
    job_id: str,
    state: str,
    units: list[UnitResult],
    *,
    ready: int | None = None,
) -> JobStatus:
    produced = sum(1 for unit in units if unit.state == UNIT_SUCCEEDED)
    return JobStatus(
        job_id=job_id,
        state=state,
        ready=produced if ready is None else ready,
        total=len(units),
        units=tuple(units),
    )


# -- case base --------------------------------------------------------------


class MediaJobCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.output_dir = self.tmp.name
        self.clock = FakeClock()
        self.slept: list[float] = []

        def sleeper(seconds: float) -> None:
            self.slept.append(seconds)
            self.clock.advance(seconds)

        self.store = MediaJobStore()
        self.rng = random.Random(0)  # jitter is deterministic
        self.service = MediaJobService(
            self.store, clock=self.clock, sleeper=sleeper, rng=self.rng
        )
        self.cancel_flag = {"value": False}

    def tearDown(self):
        self.tmp.cleanup()

    def invocation(
        self,
        domain: str = "storyboard",
        *,
        provider_id: str = "fixture_async",
        deadline_s: float | None = 100.0,
    ) -> ProviderInvocation:
        return ProviderInvocation(
            domain=domain,
            provider_id=provider_id,
            project_id=PROJECT_ID,
            execution_id="ex_1",
            node_id="n_sb",
            invocation_id="inv_media_1",
            output_dir=self.output_dir,
            cancel=CancellationToken(lambda: self.cancel_flag["value"]),
            progress=ProgressReporter(min_interval_s=0.0, clock=self.clock),
            log=ProviderLogger({"domain": domain, "provider_id": provider_id}),
            deadline_s=deadline_s,
            settings={},
            options={"unit_count": 3},
        )


# -- scenarios --------------------------------------------------------------


class AllSuccessTests(MediaJobCase):
    def test_all_success_on_both_domains(self):
        for domain in DOMAINS:
            with self.subTest(domain=domain):
                # Fresh service per domain so sleeps/polls do not bleed across.
                self.store = MediaJobStore()
                self.clock = FakeClock()
                self.slept = []

                def sleeper(seconds: float) -> None:
                    self.slept.append(seconds)
                    self.clock.advance(seconds)

                self.service = MediaJobService(
                    self.store,
                    clock=self.clock,
                    sleeper=sleeper,
                    rng=random.Random(0),
                )
                units = [_unit(0), _unit(1), _unit(2)]
                provider = ScriptedProvider(
                    poll_script=[
                        _status("job-1", RUNNING, units[:1]),
                        _status("job-1", RUNNING, units[:2]),
                        _status("job-1", SUCCEEDED, units),
                    ]
                )
                result = self.service.run(
                    provider,
                    {"units": [{"index": i} for i in range(3)]},
                    self.invocation(domain),
                )
                self.assertEqual(result.status, SUCCEEDED)
                self.assertEqual(result.domain, domain)
                self.assertEqual([u.state for u in result.units], [UNIT_SUCCEEDED] * 3)
                self.assertEqual(provider.submit_calls, 1)
                self.assertGreaterEqual(provider.poll_calls, 3)
                # First sleep is the frozen early poll delay (± jitter).
                self.assertGreater(self.slept[0], 0)
                self.assertLessEqual(
                    self.slept[0], FIRST_POLL_DELAY_S * (1 + 0.11)
                )


class PartialSuccessTests(MediaJobCase):
    def test_partial_succeeds_the_node_with_a_warning(self):
        units = [_unit(0), _unit(1, UNIT_FAILED)]
        provider = ScriptedProvider(
            poll_script=[
                _status("job-1", RUNNING, units[:1]),
                _status("job-1", PARTIAL, units),
            ]
        )
        result = self.service.run(
            provider, {"units": [{"index": 0}, {"index": 1}]}, self.invocation()
        )
        self.assertEqual(result.status, PARTIAL)
        self.assertEqual(result.payload["ready"], 1)
        self.assertTrue(any(w["code"] == "PARTIAL_UNITS" for w in result.warnings))

    def test_require_all_upgrades_partial_to_failure(self):
        units = [_unit(0), _unit(1, UNIT_FAILED)]
        provider = ScriptedProvider(
            poll_script=[_status("job-1", PARTIAL, units)]
        )
        with self.assertRaises(ProviderError) as caught:
            self.service.run(
                provider,
                {"units": [{"index": 0}, {"index": 1}]},
                self.invocation(),
                require_all=True,
            )
        self.assertEqual(caught.exception.code, PROVIDER_UNIT_FAILED)


class AllFailedTests(MediaJobCase):
    def test_all_failed_is_never_success(self):
        units = [_unit(0, UNIT_FAILED), _unit(1, UNIT_FAILED)]
        # Even a buggy provider claiming SUCCEEDED is rejected.
        provider = ScriptedProvider(
            poll_script=[_status("job-1", SUCCEEDED, units, ready=0)]
        )
        with self.assertRaises(ProviderError) as caught:
            self.service.run(
                provider, {"units": [{"index": 0}, {"index": 1}]}, self.invocation()
            )
        self.assertEqual(caught.exception.code, PROVIDER_UNIT_FAILED)
        self.assertIn("All 2 units failed", caught.exception.message)

    def test_all_failed_via_failed_state(self):
        units = [_unit(0, UNIT_FAILED), _unit(1, UNIT_FAILED)]
        provider = ScriptedProvider(
            poll_script=[_status("job-1", "failed", units, ready=0)]
        )
        with self.assertRaises(ProviderError) as caught:
            self.service.run(
                provider, {"units": [{"index": 0}, {"index": 1}]}, self.invocation()
            )
        self.assertEqual(caught.exception.code, PROVIDER_UNIT_FAILED)


class DelayedCallbackTests(MediaJobCase):
    def test_delayed_push_completes_the_job_without_further_polls(self):
        """Push arrives after submit; the wait loop observes terminal status."""
        units = [_unit(0), _unit(1)]
        provider = ScriptedProvider(poll_script=[])  # polls would hang on RUNNING
        inv = self.invocation()
        handle_box: dict = {}

        original_submit = provider.submit

        def submit_and_schedule(request, invocation):
            handle = original_submit(request, invocation)
            handle_box["handle"] = handle
            # Delayed callback: apply terminal status after the first sleep.
            def push():
                self.service.apply_callback(
                    handle.correlation,
                    _status(handle.job_id, SUCCEEDED, units),
                )
            # Run push on the same thread after the service has registered —
            # we hook the sleeper to fire the callback once.
            pushes = {"done": False}
            real_sleeper = self.service._sleeper

            def sleeper(seconds: float):
                real_sleeper(seconds)
                if not pushes["done"] and "handle" in handle_box:
                    pushes["done"] = True
                    push()

            self.service._sleeper = sleeper
            return handle

        provider.submit = submit_and_schedule
        result = self.service.run(
            provider, {"units": [{"index": 0}, {"index": 1}]}, inv, push=True
        )
        self.assertEqual(result.status, SUCCEEDED)
        self.assertEqual(len(result.units), 2)


class DuplicateCallbackTests(MediaJobCase):
    def test_duplicate_terminal_unit_callback_is_idempotent(self):
        store = self.store
        handle = JobHandle(
            job_id="job-dup",
            domain="storyboard",
            provider_id="fixture_async",
            project_id=PROJECT_ID,
        )
        first_units = (_unit(0),)
        store.register(
            handle,
            JobStatus(job_id="job-dup", state=RUNNING, ready=1, total=2, units=first_units),
        )
        # First push: unit 1 succeeds → partial still running if total=2? mark running.
        ok = store.apply_status(
            handle.correlation,
            JobStatus(
                job_id="job-dup",
                state=RUNNING,
                ready=2,
                total=2,
                units=(_unit(0), _unit(1)),
            ),
            source="push",
        )
        self.assertIsNotNone(ok)
        self.assertEqual(ok.ready, 2)

        # Duplicate push tries to flip unit 0 to failed — must be ignored.
        again = store.apply_status(
            handle.correlation,
            JobStatus(
                job_id="job-dup",
                state=RUNNING,
                ready=1,
                total=2,
                units=(_unit(0, UNIT_FAILED), _unit(1)),
            ),
            source="push",
        )
        self.assertEqual(again.units[0].state, UNIT_SUCCEEDED)
        self.assertEqual(again.ready, 2)

    def test_push_for_unknown_correlation_is_dropped(self):
        applied = self.service.apply_callback(
            ("storyboard", "other", PROJECT_ID, "nope"),
            JobStatus(job_id="nope", state=SUCCEEDED, ready=1, total=1),
        )
        self.assertFalse(applied)


class RestartReconciliationTests(MediaJobCase):
    def test_resume_continues_polling_a_persisted_running_job(self):
        path = record_path_for(self.output_dir)
        handle = JobHandle(
            job_id="job-resume",
            domain="storyboard",
            provider_id="fixture_async",
            project_id=PROJECT_ID,
            invocation_id="inv_old",
        )
        partial = JobStatus(
            job_id="job-resume",
            state=RUNNING,
            ready=1,
            total=2,
            units=(_unit(0),),
        )
        self.store.save(handle, partial, path)
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(Path(path).name, RECORD_FILENAME)

        provider = ScriptedProvider(
            job_id="job-resume",
            poll_script=[
                _status("job-resume", SUCCEEDED, [_unit(0), _unit(1)]),
            ],
        )
        result = self.service.resume(provider, self.invocation(), record_path=path)
        self.assertEqual(result.status, SUCCEEDED)
        self.assertEqual(len(result.units), 2)
        # Resume must not call submit again.
        self.assertEqual(provider.submit_calls, 0)

    def test_resume_with_missing_provider_fails_not_found(self):
        path = record_path_for(self.output_dir)
        handle = JobHandle(
            job_id="job-gone",
            domain="animator",
            provider_id="vanished",
            project_id=PROJECT_ID,
        )
        self.store.save(
            handle,
            JobStatus(job_id="job-gone", state=RUNNING, ready=0, total=3),
            path,
        )
        with self.assertRaises(ProviderError) as caught:
            self.service.resume(
                None,
                self.invocation(domain="animator", provider_id="vanished"),
                record_path=path,
                provider_registered=False,
            )
        self.assertEqual(caught.exception.code, PROVIDER_NOT_FOUND)
        # Record is persisted as failed so a second resume does not hang.
        record = self.store.load(path)
        self.assertEqual(record.status.state, "failed")

    def test_resume_of_already_terminal_job_returns_result(self):
        path = record_path_for(self.output_dir)
        handle = JobHandle(
            job_id="job-done",
            domain="storyboard",
            provider_id="fixture_async",
            project_id=PROJECT_ID,
        )
        done = _status("job-done", SUCCEEDED, [_unit(0), _unit(1)])
        self.store.save(handle, done, path)
        result = self.service.resume(
            ScriptedProvider(job_id="job-done"),
            self.invocation(),
            record_path=path,
        )
        self.assertEqual(result.status, SUCCEEDED)
        self.assertEqual(result.payload["ready"], 2)


class CancellationTests(MediaJobCase):
    def test_cancellation_raises_provider_cancelled_not_failed(self):
        provider = ScriptedProvider(
            poll_script=[
                _status("job-1", RUNNING, [_unit(0)]),
                # never reaches terminal — cancel fires instead
            ]
        )
        inv = self.invocation()
        # Cancel after the first sleep.
        sleeps = {"n": 0}
        real = self.service._sleeper

        def sleeper(seconds: float):
            real(seconds)
            sleeps["n"] += 1
            if sleeps["n"] >= 1:
                self.cancel_flag["value"] = True

        self.service._sleeper = sleeper
        with self.assertRaises(ProviderCancelled):
            self.service.run(
                provider, {"units": [{"index": 0}, {"index": 1}]}, inv
            )
        self.assertEqual(provider.cancel_calls, 1)


class TimeoutTests(MediaJobCase):
    def test_timeout_preserves_partial_units_and_raises_provider_timeout(self):
        units = [_unit(0)]
        provider = ScriptedProvider(
            poll_script=[
                _status("job-1", RUNNING, units),
                # subsequent polls keep running until deadline
                _status("job-1", RUNNING, units),
                _status("job-1", RUNNING, units),
                _status("job-1", RUNNING, units),
                _status("job-1", RUNNING, units),
            ]
        )
        inv = self.invocation(deadline_s=5.0)
        with self.assertRaises(ProviderError) as caught:
            self.service.run(
                provider, {"units": [{"index": 0}, {"index": 1}, {"index": 2}]}, inv
            )
        self.assertEqual(caught.exception.code, PROVIDER_TIMEOUT)
        self.assertEqual(caught.exception.workflow_code, "POLL_TIMEOUT")
        self.assertEqual(caught.exception.details["ready"], 1)
        self.assertEqual(len(caught.exception.details["units"]), 1)

    def test_three_consecutive_poll_failures_fail_the_job(self):
        provider = ScriptedProvider(
            fail_polls=MAX_CONSECUTIVE_POLL_FAILURES,
            poll_script=[],
        )
        with self.assertRaises(ProviderError) as caught:
            self.service.run(
                provider, {"units": [{"index": 0}]}, self.invocation()
            )
        # After 3 strikes the job is failed; result_from_status raises.
        self.assertIn(
            caught.exception.code,
            {PROVIDER_UNIT_FAILED, "PROVIDER_FAILED", PROVIDER_TIMEOUT},
        )


class RetryTests(MediaJobCase):
    def test_retry_reuses_succeeded_units_and_only_resubmits_the_rest(self):
        prior = JobStatus(
            job_id="old",
            state=PARTIAL,
            ready=1,
            total=3,
            units=(_unit(0), _unit(1, UNIT_FAILED), _unit(2, UNIT_FAILED)),
        )
        # Retry provider only produces units 1 and 2.
        provider = ScriptedProvider(
            job_id="job-retry",
            poll_script=[
                _status(
                    "job-retry",
                    SUCCEEDED,
                    [_unit(1, ref="unit-1-retry.bin"), _unit(2, ref="unit-2-retry.bin")],
                )
            ],
        )
        result = self.service.retry(
            provider,
            {"units": [{"index": 0}, {"index": 1}, {"index": 2}]},
            self.invocation(),
            prior,
        )
        self.assertEqual(result.status, SUCCEEDED)
        self.assertEqual([u.unit_index for u in result.units], [0, 1, 2])
        self.assertEqual(result.units[0].artifact_refs, ("unit-0.bin",))
        self.assertEqual(result.units[1].artifact_refs, ("unit-1-retry.bin",))
        # Request was filtered to the failed indices only.
        self.assertEqual(
            [item["index"] for item in provider.last_request["units"]],
            [1, 2],
        )
        self.assertEqual(provider.submit_calls, 1)

    def test_units_needing_retry_helper(self):
        units = (_unit(0), _unit(1, UNIT_FAILED), _unit(2))
        self.assertEqual(units_needing_retry(units), [1])

    def test_filter_request_units_accepts_scenes_key(self):
        request = {
            "scenes": [
                {"scene": 0, "prompt": "a"},
                {"scene": 1, "prompt": "b"},
                {"scene": 2, "prompt": "c"},
            ]
        }
        filtered = filter_request_units(request, [0, 2])
        self.assertEqual([s["scene"] for s in filtered["scenes"]], [0, 2])


class SharedAcrossDomainsTests(MediaJobCase):
    def test_service_has_no_domain_specific_branches(self):
        """Source-level guard: media_jobs.py must not special-case a domain."""
        source = Path(
            __file__
        ).resolve().parents[1] / "studio" / "shared" / "providers_common" / "media_jobs.py"
        text = source.read_text(encoding="utf-8")
        # Cadence lookups go through poll_interval(domain); no if domain == …
        self.assertNotIn('if domain == "storyboard"', text)
        self.assertNotIn("if domain == 'storyboard'", text)
        self.assertNotIn('if domain == "animator"', text)
        self.assertNotIn("if domain == 'animator'", text)

    def test_poll_cadence_differs_only_via_frozen_table(self):
        self.assertEqual(poll_interval("storyboard"), poll_interval("animator"))
        self.assertEqual(poll_interval("storyboard", push=True), 60.0)

    def test_legacy_scene_statuses_map_for_both_domains(self):
        storyboard = {
            "0": {"status": "ready", "local_path": "storyboard/p/0.png"},
            "1": {"status": "error", "error": "boom"},
            "2": {"status": "pending"},
        }
        animator = {
            "0": {"status": "ready", "local_files": ["animator/p/0.mp4"]},
            "1": {"status": "error", "error": "nope"},
        }
        sb_units = units_from_legacy_scenes(storyboard)
        an_units = units_from_legacy_scenes(animator)
        self.assertEqual([u.state for u in sb_units], [UNIT_SUCCEEDED, UNIT_FAILED])
        self.assertEqual([u.state for u in an_units], [UNIT_SUCCEEDED, UNIT_FAILED])
        self.assertEqual(legacy_progress(_status("j", RUNNING, list(sb_units))), {"ready": 1, "total": 2})

    def test_public_job_id_is_whatever_the_provider_returned(self):
        """Service must not invent a different identity (legacy uses project_id)."""
        provider = ScriptedProvider(
            job_id=PROJECT_ID,  # public id == project_id, as today's stores do
            poll_script=[_status(PROJECT_ID, SUCCEEDED, [_unit(0)])],
        )
        result = self.service.run(
            provider, {"units": [{"index": 0}]}, self.invocation()
        )
        self.assertEqual(result.job.job_id, PROJECT_ID)


class ResultFromStatusTests(MediaJobCase):
    def test_succeeded_with_zero_produced_units_cannot_pass(self):
        status = JobStatus(
            job_id="a",
            state=SUCCEEDED,
            ready=0,
            total=2,
            units=(_unit(0, UNIT_FAILED), _unit(1, UNIT_FAILED)),
        )
        with self.assertRaises(ProviderError) as caught:
            result_from_status(status, self.invocation())
        self.assertEqual(caught.exception.code, PROVIDER_UNIT_FAILED)

    def test_merge_prior_units_keeps_succeeded(self):
        prior = (_unit(0), _unit(1, UNIT_FAILED))
        fresh = (_unit(1, ref="new.bin"),)
        merged = merge_prior_units(prior, fresh)
        self.assertEqual(merged[0].artifact_refs, ("unit-0.bin",))
        self.assertEqual(merged[1].artifact_refs, ("new.bin",))


class PersistenceTests(MediaJobCase):
    def test_run_writes_and_clears_live_registry(self):
        provider = ScriptedProvider(
            poll_script=[_status("job-1", SUCCEEDED, [_unit(0)])]
        )
        path = record_path_for(self.output_dir)
        self.service.run(
            provider, {"units": [{"index": 0}]}, self.invocation(), record_path=path
        )
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(self.store.snapshot(), [])
        record = self.store.load(path)
        self.assertEqual(record.status.state, SUCCEEDED)
        self.assertEqual(record.handle.project_id, PROJECT_ID)


if __name__ == "__main__":
    unittest.main()
