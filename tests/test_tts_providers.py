"""Step 15.1: Kokoro and Inworld on Provider Contract v2.

Three groups, matching the step's "done when":

  * the **generic contract suite** — one parameterized case that both shipped
    providers run: manifest shape, request rejection, envelope shape, artifact
    refs, error catalog membership, and egress cleanliness. A third, fixture
    provider runs the same suite, which is what proves the suite tests the
    contract rather than the two implementations;
  * **TTS-specific voice/audio** behavior that must survive the migration —
    blending, language inference from the voice prefix, misaki phonemization,
    Inworld's per-voice tuning, and the metadata files;
  * **secret and error redaction**, plus the exclusive-execution capability that
    replaces the two hand-held Kokoro locks (contracts.md B5 / K1).

Providers are reached through `ProviderInstance.provider_module` rather than by
import: the folders have no `__init__.py` and load under synthetic names, so this
guarantees the object under test is the one the registry serves (B8).
"""

import contextlib
import os
import shutil
import tempfile
import threading
import unittest
from unittest import mock

import pydantic

from studio.shared.providers_common.concurrency import (
    exclusive_execution,
    exclusive_lock,
    is_exclusive,
)
from studio.shared.providers_common.errors import (
    PROVIDER_CODES,
    PROVIDER_NOT_CONFIGURED,
    PROVIDER_REQUEST_INVALID,
    PROVIDER_RESPONSE_MALFORMED,
    ProviderError,
)
from studio.shared.providers_common.hub import hub
from studio.shared.providers_common.invocation import build_invocation
from studio.shared.providers_common.results import ProviderResult, validate_egress
from studio.tts.providers.base import TTSProvider, TTSResult, Voice
from studio.tts.providers.contract import TTSRequest, TTSResultPayload

PROJECT_ID = "pm_ABC123"
SECRET = "sk-live-not-a-real-key"


def provider_module(domain, provider_id):
    instance = hub.get(domain, provider_id)
    assert instance is not None, f"{domain}/{provider_id} is not registered"
    return instance.provider_module


def tts_invocation(provider_id, *, settings=None, options=None, output_dir=""):
    return build_invocation(
        None,
        domain="tts",
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


def _rmtree(path):
    shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------------------------
# The domain request / result contract (§32.3)
# ---------------------------------------------------------------------------


class TTSContractModelTests(unittest.TestCase):
    def test_text_is_required(self):
        with self.assertRaises(pydantic.ValidationError):
            TTSRequest(text="   ")

    def test_unknown_request_keys_are_rejected(self):
        """§32 — a silently ignored request field changes output silently."""
        with self.assertRaises(pydantic.ValidationError):
            TTSRequest(text="hi", engine="kokoro")

    def test_speed_is_bounded(self):
        for bad in (0.1, 9.0):
            with self.subTest(speed=bad):
                with self.assertRaises(pydantic.ValidationError):
                    TTSRequest(text="hi", speed=bad)
        self.assertEqual(TTSRequest(text="hi", speed=None).speed, 1.0)

    def test_output_basename_cannot_escape_its_directory(self):
        for bad in ("../voice", "a/b", "..", "voice\\x"):
            with self.subTest(basename=bad):
                with self.assertRaises(pydantic.ValidationError):
                    TTSRequest(text="hi", output_basename=bad)

    def test_one_voice_field_accepts_either_historical_spelling(self):
        """The `voice` / `tts_voice` split (P5) collapses at the boundary."""
        self.assertEqual(TTSRequest.from_config({"text": "hi", "voice": "af_heart"}).voice, "af_heart")
        self.assertEqual(TTSRequest.from_config({"text": "hi", "tts_voice": "Carter"}).voice, "Carter")
        both = TTSRequest.from_config({"text": "hi", "voice": "af_heart", "tts_voice": "Carter"})
        self.assertEqual(both.voice, "af_heart")

    def test_result_payload_requires_positive_audio(self):
        with self.assertRaises(pydantic.ValidationError):
            TTSResultPayload(audio_ref="tts/p/voice.wav", duration_seconds=0, sample_rate=24000)
        payload = TTSResultPayload(
            audio_ref="tts\\p\\voice.wav", duration_seconds=8.0, sample_rate=24000
        )
        self.assertEqual(payload.audio_ref, "tts/p/voice.wav")

    def test_the_domain_declares_both_models(self):
        from studio.shared.providers_common.domains import get_domain

        spec = get_domain("tts")
        self.assertEqual(spec.request_model, "studio.tts.providers.contract:TTSRequest")
        self.assertEqual(spec.result_model, "studio.tts.providers.contract:TTSResultPayload")


# ---------------------------------------------------------------------------
# The generic contract suite — every TTS provider runs it
# ---------------------------------------------------------------------------


class FixtureTTSProvider(TTSProvider):
    """A third provider, so the suite below tests the contract, not the shipped two."""

    provider_id = "fixture_tts"

    def __init__(self):
        self.calls = []

    def synthesize(self, text, settings, voice=None, speed=1.0, on_progress=None):
        job_dir = settings["output_dir"]
        basename = settings.get("output_basename", "voice")
        os.makedirs(job_dir, exist_ok=True)
        wav_path = os.path.join(job_dir, basename + ".wav")
        with open(wav_path, "wb") as handle:
            handle.write(b"RIFF")
        self.calls.append({"text": text, "voice": voice, "speed": speed})
        if on_progress:
            on_progress("fixture synthesizing")
        return TTSResult(
            audio_path=wav_path,
            duration_seconds=len(text) / 12.0,
            sample_rate=22050,
            metadata={"voice": voice or "fixture", "prompt": text, "words": len(text.split())},
        )

    def list_voices(self, settings):
        return [Voice(id="fixture", name="Fixture", language="en-us")]


class TTSProviderContractSuite:
    """Assertions every TTS provider must satisfy. Mixed into one case per provider."""

    provider_id = ""

    def make_provider(self):
        raise NotImplementedError

    def synthesizing(self, **kwargs):
        """Context manager stubbing this provider's audio backend."""
        raise NotImplementedError

    def setUp(self):
        self.output_root = tempfile.mkdtemp(prefix="sts_tts_out_")
        self.addCleanup(_rmtree, self.output_root)
        self.provider = self.make_provider()
        # `job_dir()` resolves against the real TTS_DIR and a ref is relative to
        # the managed root (§31.2, corrected in 15.2); point both at the sandbox.
        for target, value in (
            ("config.TTS_DIR", os.path.join(self.output_root, "tts")),
            ("studio.shared.providers_common.results.OUTPUT_DIR", self.output_root),
        ):
            patcher = mock.patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def invoke(self, request=None, **kwargs):
        invocation = tts_invocation(
            self.provider_id,
            output_dir=os.path.join(self.output_root, "tts", PROJECT_ID),
            **kwargs,
        )
        request = request or TTSRequest(text="hello world", voice=self.voice)
        with self.synthesizing():
            return self.provider.invoke(request, invocation)

    # -- the contract ------------------------------------------------------

    def test_the_manifest_is_v2_and_declares_its_capabilities(self):
        instance = hub.get("tts", self.provider_id)
        self.assertEqual(instance.manifest.contract_version, 2)
        self.assertEqual(instance.manifest.domain, "tts")
        self.assertEqual(instance.manifest.id, self.provider_id)
        self.assertTrue(instance.capabilities.get("voice_list"))

    def test_invoke_returns_the_standard_envelope(self):
        result = self.invoke()
        self.assertIsInstance(result, ProviderResult)
        payload = TTSResultPayload.model_validate(result.payload)
        self.assertGreater(payload.duration_seconds, 0)
        self.assertGreater(payload.sample_rate, 0)
        self.assertEqual(payload.format, "wav")

    def test_the_audio_ref_is_relative_managed_and_an_artifact(self):
        result = self.invoke()
        ref = result.payload["audio_ref"]
        self.assertFalse(os.path.isabs(ref))
        self.assertNotIn("\\", ref)
        self.assertTrue(ref.startswith(f"tts/{PROJECT_ID}/"), ref)
        self.assertIn(ref, result.artifact_refs)
        self.assertTrue(os.path.exists(os.path.join(self.output_root, ref)))

    def test_the_declared_artifacts_all_exist(self):
        """The boundary's `PROVIDER_ARTIFACT_MISSING` check must pass (§34.2)."""
        result = self.invoke()
        for ref in result.artifact_refs:
            self.assertTrue(
                os.path.exists(os.path.join(self.output_root, ref)),
                f"declared but absent: {ref}",
            )

    def test_the_result_carries_no_secret_and_no_absolute_path(self):
        result = self.invoke(settings={"api_key": SECRET})
        leaks = validate_egress(
            {"payload": dict(result.payload), "metadata": dict(result.metadata)}
        )
        self.assertEqual(leaks, [], leaks)
        blob = repr(result.payload) + repr(result.metadata)
        self.assertNotIn(SECRET, blob)
        self.assertNotIn(self.output_root, blob)

    def test_metadata_keeps_the_tts_json_extras_and_drops_payload_keys(self):
        result = self.invoke()
        self.assertIn("prompt", result.metadata)
        self.assertNotIn("audio_ref", result.metadata)
        self.assertNotIn("duration_seconds", result.metadata)
        self.assertNotIn("wav_path", result.metadata)

    def test_a_malformed_request_is_rejected_before_the_provider_runs(self):
        with self.assertRaises(pydantic.ValidationError):
            TTSRequest(text="")

    def test_progress_reaches_the_reporter(self):
        events = []
        invocation = build_invocation(
            None,
            domain="tts",
            provider_id=self.provider_id,
            project_id=PROJECT_ID,
            output_dir=self.output_root,
        )
        invocation.progress._sink = events.append
        with self.synthesizing():
            self.provider.invoke(TTSRequest(text="hello", voice=self.voice), invocation)
        invocation.progress.flush()
        self.assertTrue(any(event.state == "succeeded" for event in events))

    def test_a_cancelled_invocation_never_synthesizes(self):
        from studio.shared.providers_common.errors import ProviderCancelled
        from studio.shared.providers_common.invocation import CancellationToken

        invocation = tts_invocation(self.provider_id, output_dir=self.output_root)
        object.__setattr__(invocation, "cancel", CancellationToken(lambda: True))
        with self.assertRaises(ProviderCancelled):
            self.provider.invoke(TTSRequest(text="hello", voice=self.voice), invocation)

    def test_an_invalid_project_id_is_a_request_error(self):
        invocation = tts_invocation(self.provider_id, output_dir=self.output_root)
        object.__setattr__(invocation, "project_id", "../escape")
        with self.assertRaises(ProviderError) as caught:
            self.provider.invoke(TTSRequest(text="hi"), invocation)
        self.assertEqual(caught.exception.code, PROVIDER_REQUEST_INVALID)


class FixtureProviderContractTests(TTSProviderContractSuite, unittest.TestCase):
    """The suite against a provider written only from the contract."""

    provider_id = "fixture_tts"
    voice = "fixture"

    def make_provider(self):
        return FixtureTTSProvider()

    def synthesizing(self):
        # Nothing to stub: the fixture provider has no audio backend.
        return contextlib.nullcontext()

    def test_the_manifest_is_v2_and_declares_its_capabilities(self):
        self.skipTest("the fixture provider is not registered; it tests the base contract")


class KokoroContractTests(TTSProviderContractSuite, unittest.TestCase):
    provider_id = "kokoro"
    voice = "af_heart"

    def make_provider(self):
        self.module = provider_module("tts", "kokoro")
        return hub.create("tts", "kokoro")

    def synthesizing(self, duration=8.0):
        engine = mock.Mock()
        engine.create.return_value = (object(), 24000)

        def _write(path, data, rate):
            with open(path, "wb") as handle:
                handle.write(b"RIFF")

        sf = mock.Mock()
        sf.info.return_value = FakeAudio()
        sf.write.side_effect = _write

        return _stack(
            mock.patch.object(self.module, "_model_files_present", return_value=True),
            mock.patch.object(self.module, "load_model", return_value=engine),
            mock.patch.object(self.module, "_phonemize_with_misaki", return_value=("hɛloʊ", True)),
            mock.patch.object(self.module, "sf", sf),
            mock.patch.object(self.module, "gc", mock.Mock()),
            mock.patch("studio.tts.audio.pad_audio", side_effect=lambda a, **k: a),
            mock.patch("studio.tts.audio.run_loudnorm"),
        )


class InworldContractTests(TTSProviderContractSuite, unittest.TestCase):
    provider_id = "inworld"
    voice = "Ashley"

    def make_provider(self):
        self.module = provider_module("tts", "inworld")
        return hub.create("tts", "inworld")

    def synthesizing(self):
        def _write(path, data, rate):
            with open(path, "wb") as handle:
                handle.write(b"RIFF")

        sf = mock.Mock()
        sf.read.return_value = (object(), 24000)
        sf.info.return_value = FakeAudio()
        sf.write.side_effect = _write

        return _stack(
            mock.patch.object(self.module, "INWORLD_API_KEY", "fixture-key"),
            mock.patch.object(self.module, "sf", sf),
            mock.patch.object(
                self.module,
                "_client",
                return_value=_stub_client(
                    {"audioContent": "UklGRg==", "usage": {"processedCharactersCount": 11}}
                ),
            ),
        )


def _stub_client(post_body=None, get_body=None, error=None):
    client = mock.Mock()
    if error is not None:
        client.post_json.side_effect = error
        client.get_json.side_effect = error
    else:
        client.post_json.return_value = post_body or {}
        client.get_json.return_value = get_body or {}
    return client


class _stack:
    """Enter several patchers as one context manager."""

    def __init__(self, *patchers):
        self._patchers = patchers

    def __enter__(self):
        self._entered = [patcher.__enter__() for patcher in self._patchers]
        return self._entered

    def __exit__(self, *exc):
        for patcher in reversed(self._patchers):
            patcher.__exit__(*exc)
        return False


# ---------------------------------------------------------------------------
# TTS-specific voice and audio behavior
# ---------------------------------------------------------------------------


class KokoroVoiceAudioTests(unittest.TestCase):
    """Behavior that must survive the migration unchanged."""

    def setUp(self):
        self.module = provider_module("tts", "kokoro")
        self.provider = hub.create("tts", "kokoro")
        self.job_dir = tempfile.mkdtemp(prefix="sts_kokoro_")
        self.addCleanup(_rmtree, self.job_dir)

    def _synthesize(self, text="hello world", settings=None, **kwargs):
        engine = mock.Mock()
        engine.create.return_value = (object(), 24000)
        engine.get_voice_style.side_effect = _unit_embeddings()

        def _write(path, data, rate):
            with open(path, "wb") as handle:
                handle.write(b"RIFF")

        sf = mock.Mock()
        sf.info.return_value = FakeAudio()
        sf.write.side_effect = _write

        # The sidecar name is the caller's since 15.2; `invoke()` fills it from
        # the request, and a direct `synthesize()` says so itself.
        merged = {
            "output_dir": self.job_dir,
            "output_basename": "voice",
            "output_sidecar": "tts.json",
        }
        merged.update(settings or {})
        with _stack(
            mock.patch.object(self.module, "_model_files_present", return_value=True),
            mock.patch.object(self.module, "load_model", return_value=engine),
            mock.patch.object(self.module, "sf", sf),
            mock.patch.object(self.module, "gc", mock.Mock()),
            mock.patch("studio.tts.audio.pad_audio", side_effect=lambda a, **k: a),
            mock.patch("studio.tts.audio.run_loudnorm"),
        ):
            result = self.provider.synthesize(text, merged, **kwargs)
        return result, engine

    def test_language_is_inferred_from_the_voice_prefix(self):
        for voice, lang in (
            ("af_heart", "en-us"), ("bm_george", "en-gb"),
            ("jf_alpha", "ja"), ("zm_yunxi", "cmn"), ("ff_siwis", "fr-fr"),
        ):
            with self.subTest(voice=voice):
                self.assertEqual(self.module._voice_to_lang(voice), lang)

    def test_misaki_phonemizes_english_only(self):
        g2p = mock.Mock(return_value=("hɛloʊ", None))
        with mock.patch.object(self.module, "_get_misaki_g2p", return_value=g2p):
            self.assertEqual(
                self.module._phonemize_with_misaki("hello", "en-us"), ("hɛloʊ", True)
            )
            # Other languages use kokoro's built-in G2P, untouched.
            self.assertEqual(
                self.module._phonemize_with_misaki("こんにちは", "ja"), ("こんにちは", False)
            )

    def test_misaki_absence_falls_back_to_espeak(self):
        with mock.patch.object(self.module, "_get_misaki_g2p", return_value=None):
            self.assertEqual(
                self.module._phonemize_with_misaki("hello", "en-us"), ("hello", False)
            )

    def test_blending_records_its_recipe_and_passes_an_embedding(self):
        result, engine = self._synthesize(
            settings={
                "blend": True, "blendA": "af_heart", "blendB": "am_adam",
                "blendRatio": 50, "blendMethod": "slerp",
            },
        )
        self.assertEqual(result.metadata["blend"]["method"], "slerp")
        self.assertEqual(result.metadata["blend"]["ratio"], 0.5)
        self.assertEqual(engine.get_voice_style.call_count, 2)
        # The blended style, not a voice name, reaches the model.
        self.assertIsInstance(engine.create.call_args.kwargs["voice"], tuple)

    def test_slerp_and_lerp_agree_at_the_endpoints(self):
        import numpy as np

        a = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        b = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)
        for blend in (self.module._slerp, self.module._lerp):
            with self.subTest(blend=blend.__name__):
                np.testing.assert_allclose(blend(a, b, 0.0), a, atol=1e-6)
                np.testing.assert_allclose(blend(a, b, 1.0), b, atol=1e-6)

    def test_an_unavailable_blend_voice_is_a_request_error(self):
        engine = mock.Mock()
        engine.get_voice_style.side_effect = KeyError("no_such_voice")
        with _stack(
            mock.patch.object(self.module, "_model_files_present", return_value=True),
            mock.patch.object(self.module, "load_model", return_value=engine),
        ):
            with self.assertRaises(ProviderError) as caught:
                self.provider.synthesize(
                    "hi",
                    {"output_dir": self.job_dir, "blend": True, "blendA": "nope", "blendB": "x"},
                )
        self.assertEqual(caught.exception.code, PROVIDER_REQUEST_INVALID)
        self.assertFalse(caught.exception.retryable)

    def test_the_metadata_file_keeps_its_historical_keys(self):
        import json

        result, _ = self._synthesize()
        with open(os.path.join(self.job_dir, "tts.json"), encoding="utf-8") as handle:
            written = json.load(handle)
        for key in (
            "filename", "folder", "prompt", "model", "model_id", "voice",
            "timestamp", "inference_time", "rtf", "duration_seconds",
            "sample_rate", "speed",
        ):
            self.assertIn(key, written, key)
        self.assertEqual(written["model"], "kokoro-v1.0")
        self.assertEqual(result.sample_rate, 24000)

    def test_a_missing_model_is_reported_as_unconfigured_not_as_a_crash(self):
        with mock.patch.object(self.module, "_model_files_present", return_value=False):
            with self.assertRaises(ProviderError) as caught:
                self.provider.synthesize("hi", {"output_dir": self.job_dir})
        self.assertEqual(caught.exception.code, PROVIDER_NOT_CONFIGURED)
        self.assertFalse(caught.exception.retryable)

    def test_list_voices_is_typed_and_language_tagged(self):
        voices = self.provider.list_voices({})
        self.assertTrue(voices)
        self.assertTrue(all(isinstance(voice, Voice) for voice in voices))
        by_id = {voice.id: voice for voice in voices}
        self.assertEqual(by_id["af_heart"].language, "en-us")
        self.assertEqual(by_id["bm_george"].language, "en-gb")

    def test_validate_settings_flags_an_unknown_voice(self):
        self.assertEqual(self.module.validate_settings({"voice": "af_heart"}), [])
        issues = self.module.validate_settings({"voice": "not_a_voice"})
        self.assertEqual(issues[0]["field"], "voice")
        self.assertEqual(issues[0]["severity"], "warning")

    def test_health_check_reports_a_missing_model_without_loading_it(self):
        with mock.patch.object(self.module, "_model_files_present", return_value=False):
            self.assertEqual(self.module.health_check({})["status"], "warn")
        with _stack(
            mock.patch.object(self.module, "_model_files_present", return_value=True),
            mock.patch.object(self.module, "load_model", return_value=object()),
        ):
            self.assertEqual(self.module.health_check({})["status"], "ok")

    def test_shutdown_releases_the_model(self):
        self.module.kokoro_instance = object()
        self.provider.shutdown()
        self.assertIsNone(self.module.kokoro_instance)


class InworldCloudOptionTests(unittest.TestCase):
    def setUp(self):
        self.module = provider_module("tts", "inworld")
        self.provider = hub.create("tts", "inworld")
        self.job_dir = tempfile.mkdtemp(prefix="sts_inworld_")
        self.addCleanup(_rmtree, self.job_dir)

    def _synthesize(self, settings=None, **kwargs):
        client = _stub_client(
            {"audioContent": "UklGRg==", "usage": {"processedCharactersCount": 11}}
        )

        def _write(path, data, rate):
            with open(path, "wb") as handle:
                handle.write(b"RIFF")

        sf = mock.Mock()
        sf.read.return_value = (object(), 24000)
        sf.info.return_value = FakeAudio()
        sf.write.side_effect = _write

        merged = {"api_key": "fixture-key", "output_dir": self.job_dir,
                  "output_basename": "voice"}
        merged.update(settings or {})
        with _stack(
            mock.patch.object(self.module, "sf", sf),
            mock.patch.object(self.module, "_client", return_value=client),
        ):
            result = self.provider.synthesize("hello world", merged, **kwargs)
        return result, client

    def test_the_cloud_options_reach_the_payload(self):
        result, client = self._synthesize(
            settings={"model": "inworld-tts-1.5-max"}, voice="Carter"
        )
        payload = client.post_json.call_args[0][1]
        self.assertEqual(payload["voiceId"], "Carter")
        self.assertEqual(payload["modelId"], "inworld-tts-1.5-max")
        self.assertEqual(payload["temperature"], 1.1)
        self.assertEqual(payload["audioConfig"]["speakingRate"], 1.15)
        self.assertEqual(result.metadata["characters_billed"], 11)

    def test_bella_keeps_its_own_tuning(self):
        _, client = self._synthesize(voice="Ashley-bella")
        payload = client.post_json.call_args[0][1]
        self.assertEqual(payload["temperature"], 1.11)
        self.assertEqual(payload["audioConfig"]["speakingRate"], 1.0)

    def test_a_generation_post_is_never_transport_retried(self):
        """D40 — a retried POST would bill and render the same text twice."""
        _, client = self._synthesize()
        self.assertEqual(client.post_json.call_count, 1)

    def test_a_missing_key_fails_before_any_request(self):
        with mock.patch.object(self.module, "INWORLD_API_KEY", ""):
            with mock.patch.object(self.module, "_client") as client:
                with self.assertRaises(ProviderError) as caught:
                    self.provider.synthesize("hello", {})
        self.assertEqual(caught.exception.code, PROVIDER_NOT_CONFIGURED)
        self.assertFalse(client.called)

    def test_an_empty_audio_response_is_malformed_not_a_crash(self):
        with mock.patch.object(self.module, "_client", return_value=_stub_client({})):
            with self.assertRaises(ProviderError) as caught:
                self.provider.synthesize(
                    "hello", {"api_key": "fixture-key", "output_dir": self.job_dir}
                )
        self.assertEqual(caught.exception.code, PROVIDER_RESPONSE_MALFORMED)

    def test_list_voices_is_empty_without_a_key_and_typed_with_one(self):
        with mock.patch.object(self.module, "INWORLD_API_KEY", ""):
            self.assertEqual(self.provider.list_voices({}), [])

        with _stack(
            mock.patch.object(self.module, "_voices_cache", None),
            mock.patch.object(
                self.module,
                "_client",
                return_value=_stub_client(
                    get_body={"voices": [{"voiceId": "Ashley", "displayName": "Ashley"}]}
                ),
            ),
        ):
            voices = self.provider.list_voices({"api_key": "fixture-key"})
        self.assertEqual([voice.id for voice in voices], ["Ashley"])

    def test_list_voices_falls_back_to_the_cache_on_failure(self):
        failure = ProviderError(PROVIDER_RESPONSE_MALFORMED, "boom")
        with _stack(
            mock.patch.object(self.module, "_voices_cache", None),
            mock.patch.object(self.module, "_client", return_value=_stub_client(error=failure)),
        ):
            self.assertEqual(self.provider.list_voices({"api_key": "fixture-key"}), [])

    def test_validate_settings_requires_a_key(self):
        with mock.patch.object(self.module, "INWORLD_API_KEY", ""):
            issues = self.module.validate_settings({})
        self.assertEqual(issues[0]["severity"], "error")
        self.assertEqual(issues[0]["field"], "api_key")

    def test_health_check_reports_reachability(self):
        with mock.patch.object(self.module, "INWORLD_API_KEY", ""):
            self.assertEqual(self.module.health_check({})["status"], "warn")
        with mock.patch.object(self.module, "_client", return_value=_stub_client(get_body={})):
            self.assertEqual(
                self.module.health_check({"api_key": "fixture-key"})["status"], "ok"
            )


# ---------------------------------------------------------------------------
# Redaction and exclusive execution
# ---------------------------------------------------------------------------


class RedactionTests(unittest.TestCase):
    def setUp(self):
        self.module = provider_module("tts", "inworld")

    def test_the_auth_header_never_passes_the_egress_boundary(self):
        self.assertTrue(validate_egress({"headers": self.module._auth_header(SECRET)}))

    def test_a_transport_failure_carries_a_catalog_code_and_no_response_body(self):
        """The old path raised `HTTPError(f"… — {resp.text[:200]}")` (§34.4)."""
        from studio.shared.providers_common.transports.direct_api import classify_http_error
        import requests as http_requests

        response = mock.Mock(status_code=401, text=f"denied for {SECRET}")
        error = classify_http_error(
            http_requests.HTTPError(response=response),
            domain="tts",
            provider_id="inworld",
            response=response,
        )
        self.assertIn(error.code, PROVIDER_CODES)
        payload = error.to_payload()
        self.assertNotIn(SECRET, repr(payload))
        self.assertNotIn("denied", repr(payload))
        self.assertFalse(payload["retryable"])

    def test_a_failing_health_check_message_is_sanitized_by_the_registry(self):
        """§36 L4: a *returned* message is as untrusted as a raised one."""
        module = provider_module("tts", "kokoro")
        instance = hub.get("tts", "kokoro")
        with _stack(
            mock.patch.object(module, "_model_files_present", return_value=True),
            mock.patch.object(
                module, "load_model", side_effect=RuntimeError("cannot open C:\\models\\k.onnx")
            ),
        ):
            health = instance.health_check({})
        self.assertEqual(health.status, "fail")
        self.assertNotIn("C:\\models", health.message)

    def test_provider_settings_are_redacted_in_provenance(self):
        from studio.shared.providers_common import settings_manager

        redacted = settings_manager.redact_settings({"api_key": SECRET, "voice": "Ashley"})
        self.assertNotIn(SECRET, repr(redacted))
        self.assertEqual(redacted["voice"], "Ashley")


class ExclusiveExecutionTests(unittest.TestCase):
    """Exclusivity is derived from the manifest, not hardcoded by a caller."""

    def test_kokoro_declares_exclusive_execution_and_inworld_does_not(self):
        self.assertTrue(is_exclusive(hub.get("tts", "kokoro").capabilities))
        self.assertFalse(is_exclusive(hub.get("tts", "inworld").capabilities))

    def test_the_capability_is_in_the_shared_vocabulary(self):
        from studio.shared.providers_common.domains import DOMAINS

        for domain, spec in DOMAINS.items():
            with self.subTest(domain=domain):
                self.assertIn("exclusive_execution", spec.capability_vocabulary)

    def test_one_lock_object_serves_every_caller(self):
        """B5 / K1 — the defect was two lock objects for one ONNX session."""
        self.assertIs(exclusive_lock("tts", "kokoro"), exclusive_lock("tts", "kokoro"))
        self.assertIsNot(exclusive_lock("tts", "kokoro"), exclusive_lock("tts", "inworld"))

    def test_the_routes_module_and_the_provider_share_the_engine(self):
        """B5 — the route no longer owns a second model cache or voice catalog."""
        from studio.tts import routes
        from studio.tts.providers import kokoro_engine

        engine = kokoro_engine()
        self.assertIs(routes._voices(), engine.VOICES)
        self.assertIs(routes._models(), engine.MODELS)
        self.assertIs(routes.VOICES, engine.VOICES)
        self.assertIs(routes.kokoro_instance, engine.kokoro_instance)
        self.assertIs(routes.generation_inference_lock, exclusive_lock("tts", "kokoro"))

        sentinel = object()
        with mock.patch.object(engine, "load_model", return_value=sentinel):
            self.assertIs(routes.load_model(), sentinel)

    def test_the_route_module_defines_no_engine_state_of_its_own(self):
        from studio.tts import routes

        for name in ("kokoro_lock", "_misaki_g2p", "VOICES", "MODELS"):
            with self.subTest(name=name):
                self.assertNotIn(name, vars(routes))

    def test_a_declared_provider_serializes_concurrent_invocations(self):
        overlap = []
        active = threading.Semaphore(1)

        def work():
            with exclusive_execution("tts", "kokoro"):
                overlap.append(active.acquire(blocking=False))
                active.release()

        threads = [threading.Thread(target=work) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(overlap, [True] * 4)

    def test_a_provider_without_the_capability_is_not_serialized(self):
        lock = exclusive_lock("tts", "inworld")
        with exclusive_execution("tts", "inworld"):
            # Not held: a non-exclusive provider must not pay for a lock.
            self.assertTrue(lock.acquire(blocking=False))
            lock.release()

    def test_an_unknown_provider_is_treated_as_non_exclusive(self):
        with exclusive_execution("tts", "not_a_provider"):
            pass


def _unit_embeddings():
    import numpy as np

    return [np.ones(4, dtype=np.float32), np.zeros(4, dtype=np.float32)]


if __name__ == "__main__":
    unittest.main()
