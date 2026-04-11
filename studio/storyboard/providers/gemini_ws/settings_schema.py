"""Gemini WS Settings Schema — Phase 6."""


def settings_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "auto_type": {
                "type": "boolean",
                "label": "Auto-type images",
                "description": "Automatically type images as they arrive from extension",
                "default": False,
                "ui": {
                    "type": "toggle",
                },
            },
        },
    }