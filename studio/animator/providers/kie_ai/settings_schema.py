"""Kie AI Settings Schema — Phase 7."""


def settings_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "label": "Kie AI API Key",
                "description": "Kie AI API key",
                "default": "",
                "ui": {
                    "type": "password",
                },
            },
            "model": {
                "type": "string",
                "label": "Model",
                "description": "Model ID (e.g., 'google/nano-banana')",
                "default": "google/nano-banana",
                "ui": {
                    "type": "text",
                },
            },
            "resolution": {
                "type": "string",
                "label": "Resolution",
                "description": "Resolution setting",
                "default": "1",
                "ui": {
                    "type": "dropdown",
                    "options": ["1", "2", "3", "4"],
                },
            },
        },
        "required": [],
    }