"""Step 12.4 / 16.1: the backend half of the shared provider UI.

After 16.1 the catalog no longer ships `legacy_selection_key` and the browser
sends canonical provider ids. What remains frozen here:

  - input aliases still resolve (manifests declare them; the hub resolves them);
  - the per-run options a page sends arrive under the provider's own settings
    key names, while the flat legacy keys keep winning (§40.2 O1);
  - option sources and capabilities stay provider-declared (zero-touch).
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


class CatalogLegacyKeyRetirementTests(unittest.TestCase):
    """Step 16.1 — the catalog no longer ships the retired selection keys."""

    def test_no_domain_reports_a_legacy_selection_key(self):
        catalog = catalog_module.build_catalog()
        for domain in DOMAINS:
            with self.subTest(domain=domain):
                self.assertNotIn('legacy_selection_key', catalog[domain])

    def test_the_catalog_carries_no_settings_values_or_retired_keys(self):
        payload = json.dumps(catalog_module.build_catalog())
        # Settings *values* would appear as `"api_key": "..."`; the requires
        # list may still name the key. Retired selection fields must not appear
        # as fields at all.
        for key in ('api_key', 'webhook_url'):
            self.assertNotIn(f'"{key}":', payload)
        for key in ('sts-tts-provider', 'sts-storyboard-provider',
                    'sts-asset-provider', 'legacy_selection_key'):
            self.assertNotIn(f'"{key}"', payload)

    def test_domain_specs_keep_the_key_name_for_the_one_time_migration(self):
        # The v2 settings migration still needs to find the retired keys on an
        # un-migrated machine; DomainSpec is the only place they remain.
        self.assertEqual(DOMAINS['tts'].legacy_selection_key, 'sts-tts-provider')
        self.assertEqual(
            DOMAINS['storyboard'].legacy_selection_key, 'sts-storyboard-provider'
        )
        self.assertEqual(DOMAINS['animator'].legacy_selection_key, 'sts-asset-provider')


class InputAliasTests(unittest.TestCase):
    """§40.3 — aliases remain accepted as input; canonical ids are persisted."""

    ACCEPTED = {
        ('storyboard', 'gemini'): 'gemini_ws',
        ('storyboard', 'webhook'): 'wavespeed_webhook',
        ('storyboard', 'direct'): 'wavespeed_direct',
        ('animator', 'grok'): 'grok_automa',
        ('animator', 'midjourney'): 'grok_automa',
        ('animator', 'kie-ai'): 'kie_ai',
    }

    def test_every_documented_alias_resolves_to_its_canonical_id(self):
        for (domain, alias), canonical in self.ACCEPTED.items():
            with self.subTest(alias=alias):
                provider = hub.get(domain, alias)
                self.assertIsNotNone(provider)
                self.assertEqual(provider.id, canonical)


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
            options, _context = resolve_options(
                'storyboard_image_models',
                {'domain': 'storyboard', 'provider': 'wavespeed_webhook'},
            )
        self.assertEqual(options[1], {'value': 'm1', 'label': 'Model One ($0.03)'})

    def test_the_list_comes_from_the_selected_provider(self):
        """Step 14.2 (P32): the resolver used to import one provider's catalog,
        so every provider was offered that provider's models."""
        models = [{'id': 'm1', 'name': 'Model One'}]
        with patch(
            'studio.storyboard.wavespeed.get_models_for_style', return_value=models
        ):
            webhook, _ = resolve_options(
                'storyboard_image_models',
                {'domain': 'storyboard', 'provider': 'wavespeed_webhook'},
            )
            extension, _ = resolve_options(
                'storyboard_image_models',
                {'domain': 'storyboard', 'provider': 'gemini_ws'},
            )
        self.assertEqual([option['value'] for option in webhook], ['', 'm1'])
        # The extension declares no model catalog, so it offers only "Auto".
        self.assertEqual([option['value'] for option in extension], [''])

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
        import tempfile
        payload = {
            'project_id': 'legacy_adoption_probe',
            'scenes': [{'prompt': 'a castle', 'scene': 0}],
            'provider_override': 'grok_automa',
        }
        payload.update(body)
        # The job record is written under `output/`; this test is about what the
        # extension receives, not about persistence. Point the manifest root at
        # a private directory so a real write never touches the live tree.
        tmp = tempfile.mkdtemp(prefix='sts_legacy_anim_')
        with patch('studio.animator.routes.queue_grabber_start'), \
                patch('studio.animator.jobs.ANIMATOR_DIR', tmp):
            resp = self.client.post('/api/animator/grabber/start', json=payload)
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        from studio.animator import jobs as anim_jobs

        job = anim_jobs.get('legacy_adoption_probe')
        self.assertIsNotNone(job)
        return job['payload']

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
