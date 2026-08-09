"""Step 15.2: generic TTS dispatch and voice options.

The step's claim is that nothing between a caller and a TTS provider knows
which provider it is. Four groups assert it:

  * **dispatch** — provider resolution, the voice split (P5) resolved from
    provider metadata rather than from an id comparison, and the preview cache
    keyed per provider;
  * **one reconciled shape** — the metadata dict and the `job_meta` block are
    key-for-key identical whichever provider ran, which the two hand-built
    branches this replaces were not;
  * **the legacy surfaces** — `/api/tts/voices`, `/api/tts/generate`, and
    `/api/tts/stream` answered from the registry and from capabilities;
  * **the zero-touch proof** — a third TTS provider that exists only under
    `tests/` runs through the unmodified `tts.generate` node, and its voices
    reach the node's dropdown, with no registry, adapter, or UI edit.

A saved `engine` configuration is migrated and then executed, so "old workflows
keep running" is asserted end to end rather than at the migration alone.
"""

import json
import os
import shutil
import tempfile
import unittest
from copy import deepcopy
from unittest import mock

from flask import Flask

from config import ROOT_DIR
from studio.shared.providers_common import settings_manager
from studio.shared.providers_common.domains import DOMAINS, DomainSpec
from studio.shared.providers_common.errors import ProviderError
from studio.shared.providers_common.hub import ProviderHub
from studio.shared.providers_common.results import validate_egress
from studio.tts import dispatch
from studio.tts.routes import tts_bp
from studio.workflows import options as options_module
from studio.workflows.adapters.common import AdapterContext

PROJECT_ID = "pm_ABC123"
SECRET = "sk-live-not-a-real-key"

FIXTURE_ROOT = os.path.join(ROOT_DIR, "tests", "fixture_providers")
FIXTURE_ID = "fixture_artifact"


def _rmtree(path):
    shutil.rmtree(path, ignore_errors=True)


class DispatchCase(unittest.TestCase):
    """A sandboxed managed output directory plus isolated provider settings."""

    def setUp(self):
        self.output_dir = tempfile.mkdtemp(prefix="sts_15_2_")
        self.addCleanup(_rmtree, self.output_dir)
        self._patch_paths()

        self.settings = {
            "version": settings_manager.SETTINGS_VERSION,
            "general": {},
            "domains": {
                domain: {"selected_provider": None, "per_provider": {}}
                for domain in DOMAINS
            },
        }
        self._patch(mock.patch.object(
            settings_manager, "load_settings",
            side_effect=lambda: deepcopy(self.settings),
        ))
        self._patch(mock.patch.object(
            settings_manager, "save_settings", side_effect=self._save
        ))
        options_module.clear_option_cache()
        self.addCleanup(options_module.clear_option_cache)

    def _save(self, data):
        self.settings = deepcopy(data)

    def _patch(self, patcher):
        patcher.start()
        self.addCleanup(patcher.stop)

    def _patch_paths(self):
        """Point every module-level output constant at the sandbox."""
        import config
        from studio.shared.providers_common import results
        from studio.workflows.adapters import common as adapter_common

        for module in (config, results, adapter_common):
            self._patch(mock.patch.object(module, "OUTPUT_DIR", self.output_dir))
        tts_dir = os.path.join(self.output_dir, "tts")
        cache_dir = os.path.join(self.output_dir, "tts_cache")
        os.makedirs(cache_dir, exist_ok=True)
        self._patch(mock.patch.object(config, "TTS_DIR", tts_dir))
        self._patch(mock.patch.object(dispatch, "TTS_DIR", tts_dir))
        self._patch(mock.patch.object(dispatch, "TTS_CACHE_DIR", cache_dir))
        import studio.tts.providers.kokoro.provider as kokoro_module

        self._patch(mock.patch("studio.tts.providers.base.TTS_DIR", tts_dir, create=True))
        self.kokoro_module = kokoro_module

    def select(self, provider_id):
        self.settings["domains"]["tts"]["selected_provider"] = provider_id

    def stored(self, provider_id, values):
        self.settings["domains"]["tts"]["per_provider"][provider_id] = dict(values)


# ---------------------------------------------------------------------------
# Provider and voice resolution — the P5 split, closed without a branch
# ---------------------------------------------------------------------------


class ResolutionTests(DispatchCase):
    def test_the_precedence_chain_is_request_then_selection_then_default(self):
        self.select("inworld")
        self.assertEqual(
            dispatch.resolve_provider_id({"tts_provider_override": "kokoro"}),
            ("kokoro", "request"),
        )
        self.assertEqual(dispatch.resolve_provider_id({}), ("inworld", "selection"))
        self.select(None)
        self.assertEqual(
            dispatch.resolve_provider_id({}),
            (DOMAINS["tts"].default_provider, "default"),
        )

    def test_the_historical_override_keys_still_select(self):
        """`provider`, `tts_provider`, and `provider_id` are compatibility inputs."""
        for key in ("provider", "tts_provider", "provider_id"):
            with self.subTest(key=key):
                self.assertEqual(
                    dispatch.resolve_provider_id({key: "inworld"})[0], "inworld"
                )

    def test_an_unregistered_provider_fails_rather_than_substituting(self):
        with self.assertRaises(ProviderError) as caught:
            dispatch.resolve_provider({"provider": "a_provider_from_another_install"})
        self.assertEqual(caught.exception.code, "PROVIDER_NOT_FOUND")

    def voice(self, provider_id, config):
        instance, _reason = dispatch.resolve_provider({"provider": provider_id})
        return dispatch.resolve_voice(instance, config)

    def test_each_provider_takes_the_voice_that_belongs_to_it(self):
        """The live defect P5: the frontend sends both spellings at once.

        Before 15.2 the pipeline chose between them by comparing the provider
        id. The provider's own declared catalog answers now, so a third
        provider gets the same treatment without an edit.
        """
        both = {"voice": "af_heart", "tts_voice": "Ashley"}
        self.assertEqual(self.voice("kokoro", both), "af_heart")
        self.assertEqual(self.voice("inworld", both), "Ashley")

    def test_a_voice_from_another_providers_catalog_falls_back_to_the_default(self):
        """Better a provider's own default than a remote 400 on a foreign id."""
        self.assertEqual(self.voice("inworld", {"voice": "am_fenrir"}), "Ashley")
        self.assertEqual(self.voice("kokoro", {"voice": "Ashley"}), "af_bella")

    def test_a_saved_setting_is_the_last_resort_before_the_schema_default(self):
        instance, _ = dispatch.resolve_provider({"provider": "kokoro"})
        self.assertEqual(
            dispatch.resolve_voice(instance, {}, settings={"voice": "bm_george"}),
            "bm_george",
        )
        self.assertEqual(dispatch.resolve_voice(instance, {}), "af_bella")

    def test_the_preview_cache_key_separates_two_providers(self):
        kokoro = dispatch.cache_key("hello", "af_heart", 1.0, "kokoro")
        inworld = dispatch.cache_key("hello", "af_heart", 1.0, "inworld")
        self.assertNotEqual(kokoro, inworld)


# ---------------------------------------------------------------------------
# The fixture catalog — a third provider, registered by folder alone
# ---------------------------------------------------------------------------


def fixture_spec() -> DomainSpec:
    shipped = DOMAINS["tts"]
    return DomainSpec(
        id="tts",
        label=shipped.label,
        package="tests.fixture_providers.tts",
        providers_base=os.path.join(FIXTURE_ROOT, "tts"),
        default_provider=FIXTURE_ID,
        capability_vocabulary=shipped.capability_vocabulary,
        legacy_selection_key=shipped.legacy_selection_key,
        request_model=shipped.request_model,
        result_model=shipped.result_model,
    )


class SharedCatalogCase(DispatchCase):
    """The shipped TTS catalog with the fixture provider added to it.

    The realistic shape of "someone installed a TTS provider": Kokoro and
    Inworld are still registered and still selectable, and the fixture is
    reached by exactly the same lookups.
    """

    def setUp(self):
        super().setUp()
        from studio.shared.providers_common.hub import hub as shipped

        source = ProviderHub({"tts": fixture_spec()})
        source.discover_all()
        self.addCleanup(source.shutdown)

        shipped.discover("tts")
        registry = shipped.registry("tts")
        # Restore the shipped snapshot without retiring anything: the instances
        # in it are process-wide and other tests hold them.
        self.addCleanup(registry.publish, registry.snapshot)
        discovered = source.get("tts", FIXTURE_ID)
        self.assertIsNotNone(discovered)
        registry.register(
            FIXTURE_ID,
            discovered.module,
            discovered.manifest,
            provider_module=discovered.provider_module,
            schema_module=discovered.schema_module,
        )
        self.hub = shipped


# ---------------------------------------------------------------------------
# One reconciled result, and the zero-touch node run
# ---------------------------------------------------------------------------


def kokoro_engine_stub(module):
    """Stub the ONNX session so Kokoro synthesis is deterministic and offline."""
    engine = mock.Mock()
    engine.create.return_value = (object(), 24000)

    def _write(path, data, rate):
        with open(path, "wb") as handle:
            handle.write(b"RIFF")

    sf = mock.Mock()
    sf.info.return_value = mock.Mock(duration=8.0, samplerate=24000)
    sf.write.side_effect = _write
    return (
        mock.patch.object(module, "_model_files_present", return_value=True),
        mock.patch.object(module, "load_model", return_value=engine),
        mock.patch.object(module, "_phonemize_with_misaki", return_value=("h", True)),
        mock.patch.object(module, "sf", sf),
        mock.patch.object(module, "gc", mock.Mock()),
        mock.patch("studio.tts.audio.pad_audio", side_effect=lambda a, **k: a),
        mock.patch("studio.tts.audio.run_loudnorm"),
    )


def inworld_stub(module):
    def _write(path, data, rate):
        with open(path, "wb") as handle:
            handle.write(b"RIFF")

    sf = mock.Mock()
    sf.read.return_value = (object(), 24000)
    sf.info.return_value = mock.Mock(duration=8.0, samplerate=24000)
    sf.write.side_effect = _write
    client = mock.Mock()
    client.post_json.return_value = {
        "audioContent": "UklGRg==", "usage": {"processedCharactersCount": 11}
    }
    return (
        mock.patch.object(module, "INWORLD_API_KEY", "fixture-key"),
        mock.patch.object(module, "sf", sf),
        mock.patch.object(module, "_client", return_value=client),
        mock.patch("studio.tts.audio.run_loudnorm"),
    )


class ReconciledResultTests(SharedCatalogCase):
    """§32.3 D39: one metadata dict and one `job_meta`, for every provider."""

    def run_step(self, provider_id, **config):
        from studio.pipeline.services import _step_tts

        module = self.hub.get("tts", provider_id).provider_module
        stubs = {
            "kokoro": kokoro_engine_stub,
            "inworld": inworld_stub,
        }.get(provider_id)
        patches = stubs(module) if stubs else ()
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        return _step_tts(
            {"text": "hello there", "tts_provider_override": provider_id, **config},
            PROJECT_ID,
        )

    # Every key the reconciled dict guarantees. Before 15.2 `characters_billed`
    # existed only on one branch and `cache_hit` only on the other, so a
    # consumer had to know which provider had run.
    RECONCILED_KEYS = frozenset({
        "filename", "folder", "prompt", "model", "model_id", "provider", "voice",
        "project_id", "visual_style", "story_tone", "category", "timestamp",
        "inference_time", "rtf", "duration_seconds", "sample_rate", "speed",
        "words", "approx_tokens", "cache_hit", "characters_billed", "wav_path",
        "job_meta",
    })

    def test_every_provider_produces_the_same_reconciled_keys(self):
        for provider in ("kokoro", "inworld", FIXTURE_ID):
            with self.subTest(provider=provider):
                self.assertLessEqual(self.RECONCILED_KEYS, set(self.run_step(provider)))

    def test_a_providers_own_extras_survive_without_dispatch_knowing_them(self):
        """§32.3 — `tts.json` consumers keep the fields their provider writes."""
        self.assertEqual(self.run_step(FIXTURE_ID)["engine"], "fixture")
        self.assertEqual(self.run_step("kokoro")["model"], "kokoro-v1.0")

    def test_every_provider_produces_the_same_job_meta_keys(self):
        expected = {
            "provider_id", "provider_version", "provider_kind", "contract_version",
            "resolved_settings_redacted", "provider_options", "selection_reason",
            "invocation_id", "resolved_at", "settings_version",
        }
        for provider in ("kokoro", "inworld", FIXTURE_ID):
            with self.subTest(provider=provider):
                job_meta = self.run_step(provider)["job_meta"]
                self.assertEqual(set(job_meta), expected)
                self.assertEqual(job_meta["provider_id"], provider)

    def test_the_sidecar_is_written_beside_the_audio_without_the_absolute_path(self):
        result = self.run_step(FIXTURE_ID)
        sidecar = os.path.join(
            self.output_dir, "tts", PROJECT_ID, dispatch.SIDECAR_NAME
        )
        with open(sidecar, encoding="utf-8") as handle:
            written = json.load(handle)
        self.assertNotIn("wav_path", written)
        self.assertEqual(written["provider"], FIXTURE_ID)
        self.assertEqual(validate_egress(written), [])

    def test_a_credential_is_redacted_into_job_meta_and_appears_nowhere_else(self):
        self.stored(FIXTURE_ID, {"api_key": SECRET})
        result = self.run_step(FIXTURE_ID)
        self.assertNotIn(SECRET, json.dumps({k: v for k, v in result.items()}))
        self.assertEqual(
            result["job_meta"]["resolved_settings_redacted"]["api_key"], "***"
        )

    def test_the_second_run_of_one_request_is_served_from_the_cache(self):
        first = self.run_step("kokoro")
        self.assertFalse(first["cache_hit"])
        # The cached copy is a stub RIFF header, so a real decode is stubbed the
        # same way the first synthesis was.
        with mock.patch.object(dispatch, "sf") as sf, \
                mock.patch("studio.tts.audio.run_loudnorm"):
            sf.info.return_value = mock.Mock(duration=8.0, samplerate=24000)
            second = self.run_step("kokoro")
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["inference_time"], 0.0)


class ZeroTouchNodeTests(SharedCatalogCase):
    """The unmodified `tts.generate` node runs a provider it has never heard of."""

    def run_node(self, configuration):
        from studio.workflows.adapters import tts

        return tts.generate(
            {"script": "hello there"},
            configuration,
            AdapterContext(project_id=PROJECT_ID),
        )

    def test_the_node_runs_the_fixture_provider_with_no_registry_edit(self):
        outputs = self.run_node({"provider_id": FIXTURE_ID, "voice": "fx_bright"})
        self.assertEqual(set(outputs), {"control", "audio", "metadata"})
        self.assertEqual(outputs["metadata"]["provider"], FIXTURE_ID)
        self.assertEqual(outputs["metadata"]["voice"], "fx_bright")
        audio = os.path.join(self.output_dir, outputs["audio"]["artifact_refs"][0])
        self.assertTrue(os.path.isfile(audio))

    def test_a_per_run_option_wins_over_the_saved_setting(self):
        self.stored(FIXTURE_ID, {"sample_rate": 16000})
        outputs = self.run_node({
            "provider_id": FIXTURE_ID,
            "provider_options": {"sample_rate": 48000},
        })
        self.assertEqual(outputs["metadata"]["sample_rate"], 48000)

    def test_a_saved_engine_configuration_migrates_and_then_runs(self):
        """M1 end to end: a v1 document opens *and* executes unchanged."""
        from studio.workflows.migrations import migrate_workflow
        from studio.workflows.models import workflow_draft

        document = workflow_draft(name="Legacy TTS")
        document["nodes"] = [{
            "id": "n_tts", "type": "tts.generate", "type_version": 1,
            "name": "Text to Speech", "position": {"x": 0, "y": 0},
            "configuration": {"engine": FIXTURE_ID, "voice": "fx_calm", "speed": 1.0},
            "disabled": False,
        }]
        migrated = migrate_workflow(document).document["nodes"][0]["configuration"]
        self.assertEqual(migrated["provider_id"], FIXTURE_ID)
        self.assertNotIn("engine", migrated)

        outputs = self.run_node(migrated)
        self.assertEqual(outputs["metadata"]["provider"], FIXTURE_ID)
        self.assertEqual(outputs["metadata"]["voice"], "fx_calm")

    def test_an_uninstalled_provider_fails_the_node_rather_than_substituting(self):
        from studio.workflows.adapters.common import AdapterError

        with self.assertRaises(AdapterError) as caught:
            self.run_node({"provider_id": "a_provider_from_another_install"})
        # The §7 workflow code, the same one every other adapter reports.
        self.assertEqual(caught.exception.code, "PROVIDER_UNAVAILABLE")


class VoiceOptionTests(SharedCatalogCase):
    """The canvas dropdown defect this step names, and its fix."""

    def values(self, provider_id):
        options, context = options_module.resolve_options(
            "tts_voices", {"provider": provider_id}
        )
        self.assertEqual(context["provider"], provider_id)
        return [option["value"] for option in options]

    def test_the_dropdown_follows_the_nodes_provider(self):
        self.assertIn("af_heart", self.values("kokoro"))
        self.assertNotIn("af_heart", self.values(FIXTURE_ID))
        self.assertEqual(self.values(FIXTURE_ID), ["fx_calm", "fx_bright"])

    def test_a_remote_catalog_reaches_the_dropdown_through_list_voices(self):
        """The half a settings-schema lookup could never answer.

        A cloud provider's voices live behind its API; `_live_voice_options`
        asks the provider, which is why `GET /api/tts/voices?provider=…` and
        the canvas now offer the same list.
        """
        from studio.tts.providers.base import Voice

        module = self.hub.get("tts", "inworld").provider_module
        with mock.patch.object(module, "INWORLD_API_KEY", "fixture-key"), \
                mock.patch.object(module, "_voices_cache", None), \
                mock.patch.object(
                    module, "_client",
                    return_value=mock.Mock(get_json=mock.Mock(return_value={
                        "voices": [{"voiceId": "Remote", "displayName": "Remote One"}]
                    })),
                ):
            self.assertEqual(self.values("inworld"), ["Remote"])

    def test_a_provider_that_cannot_answer_falls_back_to_its_declared_list(self):
        module = self.hub.get("tts", "inworld").provider_module
        with mock.patch.object(module, "INWORLD_API_KEY", ""):
            self.assertIn("Ashley", self.values("inworld"))

    def test_the_registry_tells_the_client_which_context_to_send(self):
        """Without this the editor cannot scope a dropdown at all (§23.1)."""
        from studio.workflows.registry import serialize_registry

        schema = serialize_registry()["node_types"]["tts.generate"]["config_schema"]
        fields = {field["name"]: field for field in schema}
        self.assertEqual(fields["voice"]["options_context"], ["domain", "provider"])
        # A source that accepts no context must not advertise one.
        self.assertNotIn("options_context", fields["provider_id"])


# ---------------------------------------------------------------------------
# The legacy TTS routes, answered from the registry
# ---------------------------------------------------------------------------


class LegacyRouteTests(SharedCatalogCase):
    def setUp(self):
        super().setUp()
        app = Flask(__name__)
        app.register_blueprint(tts_bp)
        self.client = app.test_client()

    def test_the_voice_list_is_served_for_any_provider_in_one_shape(self):
        for provider, expected in (("kokoro", "af_bella"), (FIXTURE_ID, "fx_calm")):
            with self.subTest(provider=provider):
                body = self.client.get(f"/api/tts/voices?provider={provider}").get_json()
                self.assertIn(expected, [voice["id"] for voice in body])
                self.assertTrue(all({"id", "label"} <= set(v) for v in body))

    def test_an_omitted_provider_follows_the_selection(self):
        self.select(FIXTURE_ID)
        body = self.client.get("/api/tts/voices").get_json()
        self.assertEqual([voice["id"] for voice in body], ["fx_calm", "fx_bright"])

    def test_generate_produces_the_reconciled_metadata_for_any_provider(self):
        resp = self.client.post("/api/tts/generate", json={
            "prompt": "hello there", "provider": FIXTURE_ID, "voice": "fx_bright",
        })
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        body = resp.get_json()
        self.assertEqual(body["provider"], FIXTURE_ID)
        self.assertEqual(body["voice"], "fx_bright")
        # An absolute path never leaves the boundary (§36 L7).
        self.assertNotIn("wav_path", body)
        self.assertIn("job_meta", body)
        # The history page reads `{folder}/{folder}.json`.
        sidecar = os.path.join(
            self.output_dir, "tts", body["folder"], f"{body['folder']}.json"
        )
        self.assertTrue(os.path.isfile(sidecar))

    def test_streaming_is_refused_by_capability_rather_than_by_provider_id(self):
        resp = self.client.post("/api/tts/stream", json={
            "prompt": "hello", "provider": FIXTURE_ID,
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn("does not support streaming", resp.get_json()["error"])

    def test_the_streaming_provider_is_the_one_that_declares_the_capability(self):
        self.assertTrue(self.hub.get("tts", "kokoro").capabilities["streaming"])
        self.assertFalse(
            self.hub.get("tts", "inworld").capabilities.get("streaming", False)
        )

    def test_the_cache_check_answers_per_provider(self):
        payload = {"prompt": "hello", "voice": "fx_calm", "speed": 1.0}
        self.select(FIXTURE_ID)
        first = self.client.post("/api/tts/cache/check", json=payload).get_json()
        self.select("kokoro")
        second = self.client.post("/api/tts/cache/check", json=payload).get_json()
        self.assertFalse(first["cached"])
        self.assertFalse(second["cached"])


if __name__ == "__main__":
    unittest.main()
