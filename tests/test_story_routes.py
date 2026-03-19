import os
import unittest
from unittest.mock import patch

from flask import Flask

from studio.story.routes import story_bp, _resolve_classify_webhook_url


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class StoryRouteTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(story_bp)
        self.client = app.test_client()

    def test_resolve_classify_webhook_derives_from_story_url(self):
        with patch.dict(os.environ, {"N8N_CLASSIFY_WEBHOOK_URL": ""}, clear=False):
            with patch(
                "studio.story.routes.N8N_STORY_WEBHOOK_URL",
                "https://example.com/webhook/story-generator",
            ):
                resolved = _resolve_classify_webhook_url()

        self.assertEqual(
            resolved,
            "https://example.com/webhook/classify-style",
        )

    def test_classify_route_uses_story_webhook_host_override(self):
        fake_response = _FakeResponse(
            {
                "style_id": "cinematic",
                "confidence": 0.91,
                "reason": "Matches the visual tone.",
            }
        )

        with patch("studio.story.routes.http_requests.post", return_value=fake_response) as mock_post:
            response = self.client.post(
                "/api/story/classify-style",
                json={
                    "text": "The city glows with neon rain and cinematic suspense.",
                    "webhook_url": "https://example.com/webhook/story-generator",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            mock_post.call_args.args[0],
            "https://example.com/webhook/classify-style",
        )
        self.assertEqual(response.get_json()["style_id"], "cinematic")


if __name__ == "__main__":
    unittest.main()
