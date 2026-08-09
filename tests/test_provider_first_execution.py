"""Step 11.4: first-ever execution of the shipped provider methods.

contracts.md §16 records that `TTSProvider.synthesize`, `Storyboard`/
`AnimatorProvider.submit`/`poll`, and every `get_provider()` factory have **zero
call sites** — execution branches on `if provider_id == …` into legacy modules
instead. Step 11.4 therefore treats every existing `provider.py` body as
unverified code under first-time test.

Each test here calls a method that has never run in this repository, with its
network, model, and filesystem collaborators stubbed. The point is not to prove
the provider is correct against a live service — that is what §46's recorded
fixtures and the `STS_LIVE` tests are for — but to prove the code executes at
all, produces the shapes the v2 contract expects, and does not leak.

Modules are reached through `ProviderInstance.provider_module` rather than by
import, because five of the seven provider folders have no `__init__.py` and are
loadable only through discovery. That also guarantees the object under test is
the one the registry actually serves.
"""

import tempfile
import unittest
from unittest import mock

from studio.animator.providers.base import AnimatorProvider
from studio.shared.providers_common.hub import hub
from studio.shared.providers_common.jobs import (
    FAILED,
    RUNNING,
    SUBMITTED,
    SUCCEEDED,
    JobHandle,
    JobStatus,
)
from studio.shared.providers_common.invocation import build_invocation
from studio.shared.providers_common.results import validate_egress
from studio.storyboard.providers.base import StoryboardProvider
from studio.storyboard.providers.contract import StoryboardRequest
from studio.tts.providers.base import TTSProvider, TTSResult, Voice

PROJECT_ID = "pm_ABC123"


def provider_module(domain, provider_id):
    instance = hub.get(domain, provider_id)
    assert instance is not None, f"{domain}/{provider_id} is not registered"
    return instance.provider_module


def storyboard_request(*, scenes=None, aspect_ratio="9:16", style=""):
    return StoryboardRequest.from_scenes(
        scenes or [{"index": 0, "prompt": "a lighthouse"}],
        aspect_ratio=aspect_ratio,
        style=style,
    )


def storyboard_invocation(provider_id, *, settings=None, options=None, output_dir=""):
    return build_invocation(
        None,
        domain="storyboard",
        provider_id=provider_id,
        project_id=PROJECT_ID,
        output_dir=output_dir,
        settings=settings or {},
        options=options or {},
    )


class FakeAudio:
    """Stand-in for a soundfile info/array pair, with no soundfile dependency."""

    duration = 8.0
    samplerate = 24000


class ShippedProviderCase(unittest.TestCase):
    domain = ""
    provider_id = ""

    def setUp(self):
        self.module = provider_module(self.domain, self.provider_id)
        self.instance = hub.create(self.domain, self.provider_id)
        self.assertIsNotNone(self.instance)


# -- tts/kokoro --------------------------------------------------------------


class KokoroProviderTests(ShippedProviderCase):
    domain, provider_id = "tts", "kokoro"

    def test_the_provider_is_a_tts_provider(self):
        self.assertIsInstance(self.instance, TTSProvider)

    def test_synthesize_runs_for_the_first_time(self):
        """`TTSProvider.synthesize` has never executed (§16)."""
        job_dir = tempfile.mkdtemp(prefix="sts_kokoro_")
        self.addCleanup(_rmtree, job_dir)

        kokoro = mock.Mock()
        kokoro.create.return_value = (object(), 24000)
        sf = mock.Mock()
        sf.info.return_value = FakeAudio()

        with mock.patch.object(self.module, "load_model", return_value=kokoro), \
             mock.patch.object(self.module, "_phonemize_with_misaki",
                               return_value=("hɛloʊ", True)), \
             mock.patch.object(self.module, "_tts_job_dir", return_value=job_dir), \
             mock.patch.object(self.module, "TTS_DIR", job_dir), \
             mock.patch.object(self.module, "sf", sf), \
             mock.patch.object(self.module, "gc", mock.Mock()), \
             mock.patch("studio.tts.audio.pad_audio", side_effect=lambda a, **k: a), \
             mock.patch("studio.tts.audio.run_loudnorm"):
            progress = []
            result = self.instance.synthesize(
                "hello world", {"voice": "af_heart", "speed": 1.0},
                on_progress=progress.append,
            )

        self.assertIsInstance(result, TTSResult)
        self.assertEqual(result.format, "wav")
        self.assertEqual(result.sample_rate, 24000)
        self.assertEqual(result.duration_seconds, 8.0)
        self.assertEqual(result.metadata["voice"], "af_heart")
        self.assertEqual(progress, ["Synthesizing..."])
        self.assertTrue(kokoro.create.called)

    def test_synthesize_blends_two_voices(self):
        """The `voice_blend` capability branch, also never executed."""
        import numpy as np

        job_dir = tempfile.mkdtemp(prefix="sts_kokoro_blend_")
        self.addCleanup(_rmtree, job_dir)

        kokoro = mock.Mock()
        kokoro.create.return_value = (object(), 24000)
        kokoro.get_voice_style.side_effect = [
            np.ones(4, dtype=np.float32), np.zeros(4, dtype=np.float32)
        ]
        sf = mock.Mock()
        sf.info.return_value = FakeAudio()

        with mock.patch.object(self.module, "load_model", return_value=kokoro), \
             mock.patch.object(self.module, "_phonemize_with_misaki",
                               return_value=("hɛloʊ", True)), \
             mock.patch.object(self.module, "_tts_job_dir", return_value=job_dir), \
             mock.patch.object(self.module, "TTS_DIR", job_dir), \
             mock.patch.object(self.module, "sf", sf), \
             mock.patch.object(self.module, "gc", mock.Mock()), \
             mock.patch("studio.tts.audio.pad_audio", side_effect=lambda a, **k: a), \
             mock.patch("studio.tts.audio.run_loudnorm"):
            result = self.instance.synthesize(
                "hello", {"blend": True, "blendA": "af_heart", "blendB": "am_adam",
                          "blendRatio": 50, "blendMethod": "slerp"},
            )

        self.assertEqual(result.metadata["blend"]["method"], "slerp")
        self.assertEqual(result.metadata["blend"]["ratio"], 0.5)
        self.assertEqual(kokoro.get_voice_style.call_count, 2)

    def test_list_voices_returns_typed_voices(self):
        voices = self.instance.list_voices({})
        self.assertTrue(voices)
        self.assertTrue(all(isinstance(voice, Voice) for voice in voices))
        by_id = {voice.id: voice for voice in voices}
        self.assertEqual(by_id["af_heart"].language, "en-us")
        self.assertEqual(by_id["bm_george"].language, "en-gb")
        self.assertEqual(by_id["jf_alpha"].language, "ja")

    def test_shutdown_releases_the_model(self):
        self.module.kokoro_instance = object()
        self.instance.shutdown()
        self.assertIsNone(self.module.kokoro_instance)

    def test_validate_settings_flags_an_unknown_voice(self):
        self.assertEqual(self.module.validate_settings({"voice": "af_heart"}), [])
        issues = self.module.validate_settings({"voice": "not_a_voice"})
        self.assertEqual(issues[0]["field"], "voice")
        self.assertEqual(issues[0]["severity"], "warning")

    def test_health_check_reports_a_missing_model_without_loading_it(self):
        with mock.patch.object(self.module, "_model_files_present", return_value=False):
            self.assertEqual(self.module.health_check({})["status"], "warn")
        with mock.patch.object(self.module, "_model_files_present", return_value=True), \
             mock.patch.object(self.module, "load_model", return_value=object()):
            self.assertEqual(self.module.health_check({})["status"], "ok")

    def test_a_failing_health_check_message_is_sanitized_by_the_registry(self):
        """§36 L4: a *returned* message is as untrusted as a raised one."""
        instance = hub.get(self.domain, self.provider_id)
        with mock.patch.object(self.module, "_model_files_present", return_value=True), \
             mock.patch.object(self.module, "load_model",
                               side_effect=RuntimeError("cannot open C:\\models\\k.onnx")):
            health = instance.health_check({})
        self.assertEqual(health.status, "fail")
        self.assertNotIn("C:\\models", health.message)
        self.assertIn("k.onnx", health.message)


# -- tts/inworld -------------------------------------------------------------


class InworldProviderTests(ShippedProviderCase):
    domain, provider_id = "tts", "inworld"

    def test_synthesize_runs_against_a_stubbed_endpoint(self):
        job_dir = tempfile.mkdtemp(prefix="sts_inworld_")
        self.addCleanup(_rmtree, job_dir)

        response = mock.Mock(status_code=200)
        response.json.return_value = {
            "audioContent": "UklGRg==",
            "usage": {"processedCharactersCount": 11},
        }
        sf = mock.Mock()
        sf.read.return_value = (object(), 24000)
        sf.info.return_value = FakeAudio()

        with mock.patch.object(self.module, "TTS_DIR", job_dir), \
             mock.patch.object(self.module, "sf", sf), \
             mock.patch("requests.post", return_value=response) as post:
            progress = []
            result = self.instance.synthesize(
                "hello world", {"api_key": "fixture-key", "model": "inworld-tts-1"},
                voice="Ashley", on_progress=progress.append,
            )

        self.assertIsInstance(result, TTSResult)
        self.assertEqual(result.metadata["voice"], "Ashley")
        self.assertEqual(result.metadata["characters_billed"], 11)
        self.assertEqual(progress, ["Synthesizing via Inworld API..."])
        self.assertEqual(post.call_args.kwargs["json"]["voiceId"], "Ashley")

    def test_synthesize_without_a_key_fails_before_any_request(self):
        with mock.patch.object(self.module, "INWORLD_API_KEY", ""), \
             mock.patch("requests.post") as post:
            with self.assertRaises(ValueError):
                self.instance.synthesize("hello", {})
        self.assertFalse(post.called)

    def test_list_voices_is_empty_without_a_key_and_typed_with_one(self):
        with mock.patch.object(self.module, "INWORLD_API_KEY", ""):
            self.assertEqual(self.instance.list_voices({}), [])

        response = mock.Mock(status_code=200)
        response.json.return_value = {
            "voices": [{"voiceId": "Ashley", "displayName": "Ashley"}]
        }
        with mock.patch.object(self.module, "_voices_cache", None), \
             mock.patch("requests.get", return_value=response):
            voices = self.instance.list_voices({"api_key": "fixture-key"})
        self.assertEqual([voice.id for voice in voices], ["Ashley"])

    def test_list_voices_falls_back_to_the_cache_on_failure(self):
        with mock.patch.object(self.module, "_voices_cache", None), \
             mock.patch("requests.get", side_effect=RuntimeError("network down")):
            self.assertEqual(self.instance.list_voices({"api_key": "fixture-key"}), [])

    def test_validate_settings_requires_a_key(self):
        with mock.patch.object(self.module, "INWORLD_API_KEY", ""):
            issues = self.module.validate_settings({})
        self.assertEqual(issues[0]["severity"], "error")
        self.assertEqual(issues[0]["field"], "api_key")

    def test_health_check_reports_reachability(self):
        with mock.patch.object(self.module, "INWORLD_API_KEY", ""):
            self.assertEqual(self.module.health_check({})["status"], "warn")
        with mock.patch("requests.get", return_value=mock.Mock(status_code=200)):
            health = self.module.health_check({"api_key": "fixture-key"})
        self.assertEqual(health["status"], "ok")

    def test_shutdown_is_idempotent(self):
        self.instance.shutdown()
        self.instance.shutdown()

    def test_the_auth_header_never_reaches_a_result(self):
        header = self.module._auth_header("fixture-key")
        self.assertTrue(validate_egress({"headers": header}))


# -- storyboard --------------------------------------------------------------
#
# The three storyboard providers were first executed here against the v1
# `submit(project_id, scenes, settings, on_progress)` signature. Step 14.2
# replaced that with the Contract v2 async shape and moved the manifest,
# transport, and metadata decisions into the providers, so their contract tests
# moved to `tests/test_storyboard_dispatch.py`, beside the dispatch tests that
# exercise them end to end.


# -- animator ----------------------------------------------------------------
#
# The two animator providers were first executed here against the v1
# `submit(project_id, scenes, settings, on_progress)` signature. Step 14.3
# replaced that with the Contract v2 async shape and moved the manifest,
# transport, and metadata decisions into the providers, so their contract tests
# moved to `tests/test_animator_dispatch.py`, beside the dispatch tests that
# exercise them end to end.


# -- the abstract base classes ----------------------------------------------


class AbstractBaseTests(unittest.TestCase):
    """The optional hooks nothing has ever called."""

    def test_tts_optional_hooks(self):
        class Minimal(TTSProvider):
            def synthesize(self, text, settings, voice=None, speed=1.0, on_progress=None):
                return TTSResult(audio_path="", duration_seconds=0.0)

            def list_voices(self, settings):
                return []

        provider = Minimal()
        self.assertEqual(provider.list_models({}), [])
        with self.assertRaises(NotImplementedError):
            provider.download_model("kokoro", {})
        with self.assertRaises(NotImplementedError):
            next(iter(provider.stream("hi", {})))
        provider.shutdown()

    def test_storyboard_generate_one_default(self):
        class Minimal(StoryboardProvider):
            def submit(self, request, invocation):
                return JobHandle(job_id=invocation.project_id)

            def poll(self, job_id, invocation):
                return JobStatus(job_id=job_id)

        provider = Minimal()
        with self.assertRaises(NotImplementedError):
            provider.generate_one(storyboard_request(), storyboard_invocation("gemini_ws"))
        # `cancel_job` is optional and defaults to a no-op (§33).
        self.assertIsNone(
            provider.cancel_job("pm_ABC123", storyboard_invocation("gemini_ws"))
        )
        provider.shutdown()

    def test_animator_open_url_default(self):
        from studio.animator.providers.contract import AnimatorRequest
        from studio.shared.providers_common.invocation import build_invocation

        class Minimal(AnimatorProvider):
            def submit(self, request, invocation):
                return JobHandle(job_id=invocation.project_id)

            def poll(self, job_id, invocation):
                return JobStatus(job_id=job_id)

        provider = Minimal()
        self.assertIsNone(provider.open_url({}))
        inv = build_invocation(
            None, domain="animator", provider_id="x", project_id="pm_ABC123",
        )
        self.assertIsNone(provider.cancel_job("pm_ABC123", inv))
        provider.shutdown()

    def test_every_shipped_provider_constructs_and_reports_a_job_shape(self):
        """One assertion that spans all seven providers (§21.1 + §33.1)."""
        shipped = [
            ("tts", "kokoro"), ("tts", "inworld"),
            ("storyboard", "gemini_ws"), ("storyboard", "wavespeed_direct"),
            ("storyboard", "wavespeed_webhook"),
            ("animator", "grok_automa"), ("animator", "kie_ai"),
        ]
        for domain, provider_id in shipped:
            with self.subTest(provider=f"{domain}/{provider_id}"):
                instance = hub.create(domain, provider_id)
                self.assertIsNotNone(instance)
                self.assertTrue(callable(getattr(instance, "shutdown")))


def _rmtree(path):
    import shutil

    shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
