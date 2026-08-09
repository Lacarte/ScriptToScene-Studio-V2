"""Step 12.4: the backend half of adopting the shared provider UI.

The legacy pages stopped owning provider knowledge; three things had to move
into the backend for that to be possible, and this file freezes them:

  - the catalog names each domain's retired `app-config.json` selection key, so
    a page can read through to it and mirror writes back without the mapping
    being written down a second time in JavaScript (contracts.md §24.3 rule 3);
  - a provider's first alias *is* its legacy wire spelling (§40.3, output
    column), which is the rule the browser derives a request's `provider` field
    from;
  - the per-run options a page sends arrive under the provider's own settings
    key names, while the flat legacy keys keep winning (§40.2 O1).

`test_the_option_source_is_scoped_to_its_domain` and the manifest tests are the
zero-touch claim in miniature: what a page renders is what a provider declares.
"""

import json
import unittest
from unittest.mock import patch

from flask import Flask

from studio.animator import animation_bp
from studio.animator.providers.grok_automa.manifest import manifest as grok_manifest
from studio.animator.providers.kie_ai.settings_schema import (
    settings_schema as kie_settings_schema,
)
from studio.providers import catalog as catalog_module
from studio.shared.providers_common.domains import DOMAINS
from studio.shared.providers_common.hub import hub
from studio.storyboard.providers.wavespeed_webhook.settings_schema import (
    settings_schema as webhook_settings_schema,
)
from studio.workflows.options import (
    OptionContextError,
    build_context,
    clear_option_cache,
    resolve_options,
)
from studio.workflows.registry import ASYNC_OPTION_SOURCES


class CatalogLegacyKeyTests(unittest.TestCase):
    """§24.3 — the key name crosses to the browser; the value never does."""

    def test_every_domain_reports_its_legacy_selection_key(self):
        catalog = catalog_module.build_catalog()
        for domain, spec in DOMAINS.items():
            with self.subTest(domain=domain):
                self.assertIn('legacy_selection_key', catalog[domain])
                self.assertEqual(
                    catalog[domain]['legacy_selection_key'],
                    spec.legacy_selection_key,
                )

    def test_a_domain_that_never_had_one_reports_none(self):
        catalog = catalog_module.build_catalog()
        # `script` and `scene_blueprint` are new surface (§40.1): they had no
        # pre-platform selection anywhere, so there is nothing to read through to.
        self.assertIsNone(catalog['script']['legacy_selection_key'])
        self.assertIsNone(catalog['scene_blueprint']['legacy_selection_key'])

    def test_the_catalog_carries_no_settings_values(self):
        payload = json.dumps(catalog_module.build_catalog())
        for key in ('api_key', 'webhook_url', 'sts-tts-provider'):
            self.assertNotIn(f'"{key}":', payload)


class LegacyWireSpellingTests(unittest.TestCase):
    """§40.3 — the browser reads the output column off `aliases[0]`."""

    EMITTED = {
        ('storyboard', 'gemini_ws'): 'gemini',
        ('storyboard', 'wavespeed_webhook'): 'webhook',
        ('storyboard', 'wavespeed_direct'): 'direct',
        ('animator', 'grok_automa'): 'grok',
        ('animator', 'kie_ai'): 'kie-ai',
        ('tts', 'kokoro'): 'kokoro',
        ('tts', 'inworld'): 'inworld',
    }

    def test_the_first_alias_is_the_legacy_string_the_routes_compare(self):
        for (domain, provider_id), expected in self.EMITTED.items():
            with self.subTest(provider=provider_id):
                provider = hub.get(domain, provider_id)
                self.assertIsNotNone(provider)
                aliases = provider.aliases
                self.assertEqual(aliases[0] if aliases else provider.id, expected)


class StoryboardImageModelOptionsTests(unittest.TestCase):
    """§22.4 — the image-model list moved to the provider that consumes it."""

    def setUp(self):
        clear_option_cache()
        self.addCleanup(clear_option_cache)

    def test_the_source_is_allowlisted_and_scoped(self):
        spec = ASYNC_OPTION_SOURCES['storyboard_image_models']
        self.assertEqual(spec.domain, 'storyboard')

    def test_the_provider_reads_the_list_through_its_own_schema(self):
        image_model = webhook_settings_schema()['properties']['image_model']
        self.assertEqual(
            image_model['ui']['options_source'], 'storyboard_image_models'
        )
        # §22.4: the two are mutually exclusive.
        self.assertNotIn('options', image_model['ui'])

    def test_it_always_offers_the_auto_choice(self):
        options, _context = resolve_options('storyboard_image_models')
        self.assertEqual(options[0]['value'], '')

    def test_a_priced_model_is_labelled_with_its_price(self):
        models = [{'id': 'm1', 'name': 'Model One', 'price': '0.03'}]
        with patch(
            'studio.storyboard.wavespeed.get_models_for_style', return_value=models
        ):
            options, _context = resolve_options('storyboard_image_models')
        self.assertEqual(options[1], {'value': 'm1', 'label': 'Model One ($0.03)'})

    def test_the_option_source_is_scoped_to_its_domain(self):
        with self.assertRaises(OptionContextError):
            build_context('storyboard_image_models', {'domain': 'animator'})

    def test_it_accepts_the_context_its_own_renderer_sends(self):
        # 12.4 shipped this source with an empty context tuple while
        # `ProviderSettingsForm` sends `{domain, provider}` to *every*
        # `ui.options_source`, so on the Storyboard page the dropdown answered
        # OPTION_CONTEXT_INVALID and rendered empty. Step 12.5 widened the
        # tuple and made the invariant mechanical.
        context = build_context(
            'storyboard_image_models',
            {'domain': 'storyboard', 'provider': 'wavespeed_webhook'},
        )
        self.assertEqual(context.provider, 'wavespeed_webhook')

    def test_an_unknown_parameter_is_rejected_rather_than_ignored(self):
        with self.assertRaises(OptionContextError):
            build_context('storyboard_image_models', {'style': 'anything'})


class AnimatorProviderMetadataTests(unittest.TestCase):
    """The literals the Assets page used to hold now live in the manifests."""

    def test_the_extension_provider_declares_the_page_it_needs_open(self):
        declared = grok_manifest()
        self.assertTrue(declared.open_url.startswith('https://'))

    def test_it_declares_the_capability_the_page_branches_on(self):
        # §20.4: a declarative boolean is the replacement for `=== 'grok'`.
        self.assertIs(grok_manifest().capabilities.get('image_to_video'), True)

    def test_the_cloud_provider_declares_its_own_model_and_format_choices(self):
        properties = kie_settings_schema()['properties']
        self.assertEqual(properties['model']['ui']['type'], 'dropdown')
        self.assertTrue(properties['model']['ui']['options'])
        # The page shipped `png`; moving the field must not change the default.
        self.assertEqual(properties['output_format']['default'], 'png')


class GrabberPerRunOptionTests(unittest.TestCase):
    """§40.2 O1 — generic per-run options, with the flat keys still winning."""

    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(animation_bp)
        self.client = app.test_client()

    def _start(self, body):
        payload = {
            'project_id': 'legacy_adoption_probe',
            'scenes': [{'prompt': 'a castle', 'scene': 0}],
            'provider_override': 'grok_automa',
        }
        payload.update(body)
        # The job record is written under `output/`; this test is about what the
        # extension receives, not about persistence.
        with patch('studio.animator.routes.queue_grabber_start'), \
                patch('studio.animator.animation_routes._save_job'):
            resp = self.client.post('/api/animator/grabber/start', json=payload)
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        from studio.animator.animation_routes import grabber_jobs

        return grabber_jobs.get('legacy_adoption_probe')['payload']

    def test_options_arrive_under_the_provider_settings_key_names(self):
        payload = self._start({
            'provider_options': {'mode': 'image', 'quality': '720p', 'duration': '10s',
                                 'auto_type': True},
        })
        self.assertEqual(payload['grok_mode'], 'image')
        self.assertEqual(payload['grok_quality'], '720p')
        self.assertEqual(payload['grok_duration'], '10s')
        self.assertIs(payload['auto_type'], True)

    def test_a_client_still_sending_the_flat_keys_is_unaffected(self):
        payload = self._start({
            'grok_mode': 'video',
            'provider_options': {'mode': 'image'},
        })
        # The endpoint contract is unchanged: an un-migrated caller wins.
        self.assertEqual(payload['grok_mode'], 'video')

    def test_the_shipped_defaults_survive_a_request_with_no_options(self):
        payload = self._start({})
        self.assertEqual(payload['grok_mode'], 'video')
        self.assertEqual(payload['grok_quality'], '480p')
        self.assertEqual(payload['grok_duration'], '6s')
        self.assertIs(payload['auto_type'], False)


if __name__ == '__main__':
    unittest.main()
