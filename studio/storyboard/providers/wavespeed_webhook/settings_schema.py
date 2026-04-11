"""WaveSpeed Webhook Settings Schema — Phase 6."""


def settings_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "webhook_url": {
                "type": "string",
                "label": "n8n Webhook URL",
                "description": "n8n webhook URL for WaveSpeed image generation",
                "default": "",
                "ui": {
                    "type": "text",
                },
            },
            "image_model": {
                "type": "string",
                "label": "Image Model",
                "description": "Optional model override (leave empty for default)",
                "default": "",
                "ui": {
                    "type": "text",
                },
            },
        },
        "required": ["webhook_url"],
    }