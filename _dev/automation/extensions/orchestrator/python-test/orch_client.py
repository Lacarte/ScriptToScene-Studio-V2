"""
STS Orchestrator — WebSocket Client

Reusable client for communicating with the orchestrator extension.
Supports all commands: list_tabs, focus_tab, focus_by_name, screenshot, diagnose, ping.

Usage:
    from orch_client import OrchClient

    orch = OrchClient()                  # auto-discovers port 5050-5059
    tabs = orch.list_tabs()
    orch.focus_by_name("gemini")
    orch.screenshot(name="grok", label="before-test")
    report = orch.diagnose()
    orch.close()
"""

import base64
import json
import os
import time

try:
    import websocket
except ImportError:
    raise ImportError("pip install websocket-client")


_SCREENSHOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diag-output", "screenshots")

PASS = "\033[92m PASS \033[0m"
FAIL = "\033[91m FAIL \033[0m"
INFO = "\033[94m INFO \033[0m"
WARN = "\033[93m WARN \033[0m"
SNAP = "\033[96m SNAP \033[0m"


class OrchClient:
    """WebSocket client for the STS Orchestrator extension."""

    def __init__(self, port=None, timeout=10):
        self.timeout = timeout
        self._req_id = 0
        self.ws = None

        if port:
            url = f"ws://127.0.0.1:{port}/ws/orchestrator"
            self.ws = websocket.create_connection(url, timeout=timeout)
        else:
            # Auto-discover port
            for p in range(5050, 5060):
                try:
                    url = f"ws://127.0.0.1:{p}/ws/orchestrator"
                    self.ws = websocket.create_connection(url, timeout=3)
                    break
                except Exception:
                    continue

        if not self.ws:
            raise ConnectionError("Could not connect to orchestrator WS on ports 5050-5059")

        # Drain hello/initial messages
        self.ws.settimeout(1)
        try:
            while True:
                self.ws.recv()
        except Exception:
            pass
        self.ws.settimeout(timeout)

    def _next_id(self):
        self._req_id += 1
        return f"req_{self._req_id}"

    def _send_cmd(self, command, **kwargs):
        """Send a command and wait for matching response."""
        rid = self._next_id()
        msg = {"command": command, "request_id": rid, **kwargs}
        self.ws.send(json.dumps(msg))
        return self._wait_response(rid)

    def _wait_response(self, request_id, timeout=None):
        """Wait for a response matching the request_id."""
        timeout = timeout or self.timeout
        start = time.time()
        self.ws.settimeout(timeout)
        while time.time() - start < timeout:
            try:
                raw = self.ws.recv()
                msg = json.loads(raw)
                if msg.get("request_id") == request_id:
                    return msg
                # Ignore other messages (pong, status, etc.)
            except websocket.WebSocketTimeoutException:
                break
            except Exception:
                break
        return None

    def ping(self):
        """Check if orchestrator is alive."""
        result = self._send_cmd("ping")
        return result and result.get("type") == "pong"

    def list_tabs(self):
        """Get all open browser tabs."""
        result = self._send_cmd("list_tabs")
        if result and result.get("type") == "tab_list":
            return result.get("tabs", [])
        return []

    def focus_tab(self, tab_id):
        """Focus a specific tab by ID."""
        return self._send_cmd("focus_tab", tab_id=tab_id)

    def focus_by_name(self, name):
        """Focus a tab by name (gemini, grok, studio, or URL substring)."""
        return self._send_cmd("focus_by_name", name=name)

    def screenshot(self, name=None, tab_id=None, label=None, save=True):
        """
        Take a screenshot via the orchestrator.

        Args:
            name: Tab name ("gemini", "grok") or URL substring
            tab_id: Specific tab ID
            label: Label for the screenshot file
            save: Save to disk (default True)

        Returns:
            dict with screenshot data, or saved file path
        """
        kwargs = {"label": label or name or "screenshot"}
        if name:
            kwargs["name"] = name
        elif tab_id:
            kwargs["tab_id"] = tab_id

        result = self._send_cmd("screenshot", **kwargs)

        if not result:
            return None

        if result.get("error"):
            print(f"  [{WARN}] Screenshot failed ({kwargs['label']}): {result['error']}")
            return None

        if save and result.get("screenshot"):
            return self._save_screenshot(result)

        return result

    def _save_screenshot(self, result):
        """Save screenshot data to disk."""
        os.makedirs(_SCREENSHOTS_DIR, exist_ok=True)
        data = result["screenshot"]
        b64 = data.split(",", 1)[1] if "," in data else data
        label = result.get("label", "screenshot").replace(" ", "-").replace("/", "-")[:40]
        ts = time.strftime("%Y%m%d-%H%M%S")
        filename = f"orch_{label}_{ts}.png"
        path = os.path.join(_SCREENSHOTS_DIR, filename)

        with open(path, "wb") as f:
            f.write(base64.b64decode(b64))

        size_kb = os.path.getsize(path) / 1024
        print(f"  [{SNAP}] {label} -> {filename} ({size_kb:.0f} KB)")
        return path

    def diagnose(self):
        """Get full diagnostic report from the orchestrator."""
        return self._send_cmd("diagnose")

    def close(self):
        """Close the WebSocket connection."""
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
