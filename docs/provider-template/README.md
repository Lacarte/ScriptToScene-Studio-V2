# Provider Templates

Templates for creating new modular providers in ScriptToScene Studio.

## Quick Start

```bash
# Create a new TTS provider
python -m studio.shared.providers_common.scaffold tts my_provider

# Create a storyboard provider
python -m studio.shared.providers_common.scaffold storyboard my_provider --kind extension

# Create an animator provider
python -m studio.shared.providers_common.scaffold animator my_video_provider --kind cloud
```

## Provider Structure

Each provider needs:

### `manifest.py` (required)

```python
from studio.shared.providers_common import ProviderManifest

def manifest() -> ProviderManifest:
    return ProviderManifest(
        id="my_provider",           # Must match folder name
        label="My Provider",        # Display name
        domain="tts",              # tts | storyboard | animator
        kind="cloud",             # local | cloud | extension
        version="1.0.0",
        requires=["api_key"],       # Required settings fields
        capabilities={
            "test_connection": True,
            "single_scene": True,
            "batch": True,
        },
    )
```

### `settings_schema.py` (optional)

```python
def settings_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "api_key": {
                "type": "string",
                "label": "API Key",
                "ui": {"type": "password"},
            },
            "voice": {
                "type": "string",
                "label": "Default Voice",
                "ui": {"type": "dropdown", "options": ["voice1", "voice2"]},
            },
        },
        "required": ["api_key"],
    }
```

### `provider.py` (optional for cloud/local, required for extension)

```python
from studio.tts.providers.base import TTSProvider, TTSResult, Voice

class MyProvider(TTSProvider):
    def synthesize(self, text, settings, voice=None, speed=1.0, on_progress=None) -> TTSResult:
        # Implementation
        pass

    def list_voices(self, settings) -> list[Voice]:
        return []

def validate_settings(settings) -> list[dict]:
    issues = []
    if not settings.get("api_key"):
        issues.append({"field": "api_key", "severity": "error", "message": "API key required"})
    return issues

def health_check(settings) -> dict:
    return {"status": "ok", "message": "Ready"}
```

### `runtime.py` (extension providers only)

```python
def register_runtime(app, sock):
    @sock.route("/ws/my-provider")
    def ws_handler(ws):
        # WebSocket handling
        pass
```

## Provider Kinds

### `local`
- Runs on the local machine (e.g., Kokoro ONNX)
- No network required for synthesis

### `cloud`
- Uses external API (e.g., Inworld, WaveSpeed)
- Requires API key or credentials

### `extension`
- Communicates via WebSocket with browser extension
- Needs `register_runtime(app, sock)` hook

## UI Widget Types

Supported in `settings_schema`:

- `text` - Basic text input
- `password` - Masked text input
- `dropdown` - Select from options
- `slider` - Numeric range
- `toggle` - Boolean switch
- `file_picker` - File selection
- `path_picker` - Folder selection
- `multi_select` - Multiple selection