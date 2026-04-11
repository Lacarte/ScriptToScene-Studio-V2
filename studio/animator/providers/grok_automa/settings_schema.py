"""Grok Automa Settings Schema — Phase 7."""


def settings_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "label": "Mode",
                "description": "Generation mode",
                "default": "video",
                "ui": {
                    "type": "dropdown",
                    "options": ["video", "image"],
                },
            },
            "quality": {
                "type": "string",
                "label": "Quality",
                "description": "Video quality",
                "default": "480p",
                "ui": {
                    "type": "dropdown",
                    "options": ["480p", "720p", "1080p"],
                },
            },
            "duration": {
                "type": "string",
                "label": "Duration",
                "description": "Video duration",
                "default": "6s",
                "ui": {
                    "type": "dropdown",
                    "options": ["5s", "6s", "10s"],
                },
            },
        },
    }