"""
Screenshot utility for Gemini extension tests.

Captures screenshots via WebSocket SCREENSHOT command to the extension's
background worker. Screenshots are saved to diag-output/screenshots/.

Usage:
    from screenshot import ScreenshotCapture

    cap = ScreenshotCapture(ws)          # pass an open websocket
    cap.take("before-submit")            # captures and saves
    cap.take("after-error")              # label appears in filename
    cap.take("retry-2", on_fail="warn")  # don't crash if capture fails

Filenames: screenshots/{test}_{label}_{timestamp}.png
"""

import base64
import json
import os
import time


# Default output directory (relative to this file)
_DEFAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diag-output", "screenshots")


class ScreenshotCapture:
    """Captures screenshots from the Gemini extension via WebSocket."""

    def __init__(self, ws, save_dir=None, test_name=None, timeout=10):
        """
        Args:
            ws: An open websocket-client WebSocket connection.
            save_dir: Directory to save screenshots. Defaults to diag-output/screenshots/.
            test_name: Prefix for filenames (e.g. "diagnose", "disconnect").
            timeout: Seconds to wait for screenshot response.
        """
        self.ws = ws
        self.save_dir = save_dir or _DEFAULT_DIR
        self.test_name = test_name or "test"
        self.timeout = timeout
        self.count = 0
        os.makedirs(self.save_dir, exist_ok=True)

    def take(self, label="capture", on_fail="warn"):
        """
        Capture a screenshot and save to disk.

        Args:
            label: Descriptive label (used in filename and logs).
            on_fail: "warn" = print warning, "raise" = raise exception, "silent" = ignore.

        Returns:
            str: Path to saved screenshot, or None if failed.
        """
        self.count += 1
        try:
            return self._capture(label)
        except Exception as e:
            msg = f"[SCREENSHOT] Failed ({label}): {e}"
            if on_fail == "raise":
                raise
            elif on_fail == "warn":
                print(f"  \033[93m WARN \033[0m {msg}")
            return None

    def _capture(self, label):
        # Send screenshot request
        self.ws.send(json.dumps({"type": "SCREENSHOT", "label": label}))

        # Wait for SCREENSHOT_RESULT
        old_timeout = self.ws.gettimeout()
        self.ws.settimeout(self.timeout)
        try:
            result = self._wait_for_result()
        finally:
            self.ws.settimeout(old_timeout)

        if not result:
            raise TimeoutError(f"No SCREENSHOT_RESULT received within {self.timeout}s")

        if result.get("error"):
            raise RuntimeError(result["error"])

        screenshot = result.get("screenshot")
        if not screenshot:
            raise RuntimeError("Empty screenshot data")

        # Decode and save
        if "," in screenshot:
            b64 = screenshot.split(",", 1)[1]
        else:
            b64 = screenshot

        ts = time.strftime("%Y%m%d-%H%M%S")
        safe_label = label.replace(" ", "-").replace("/", "-")[:40]
        filename = f"{self.test_name}_{safe_label}_{ts}.png"
        path = os.path.join(self.save_dir, filename)

        with open(path, "wb") as f:
            f.write(base64.b64decode(b64))

        size_kb = os.path.getsize(path) / 1024
        print(f"  \033[96m SNAP \033[0m {label} -> {filename} ({size_kb:.0f} KB)")
        return path

    def _wait_for_result(self):
        """Drain messages until SCREENSHOT_RESULT or timeout."""
        start = time.time()
        while time.time() - start < self.timeout:
            try:
                raw = self.ws.recv()
                msg = json.loads(raw)
                if msg.get("type") == "SCREENSHOT_RESULT":
                    return msg
                elif msg.get("type") == "PING":
                    self.ws.send(json.dumps({"type": "PONG"}))
                # Ignore other messages
            except Exception:
                break
        return None
