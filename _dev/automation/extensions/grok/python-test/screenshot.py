"""
Screenshot utility for Grok extension tests.
Identical API to the Gemini screenshot.py — captures via WS SCREENSHOT command.
"""

import base64
import json
import os
import time

_DEFAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diag-output", "screenshots")


class ScreenshotCapture:
    def __init__(self, ws, save_dir=None, test_name=None, timeout=10):
        self.ws = ws
        self.save_dir = save_dir or _DEFAULT_DIR
        self.test_name = test_name or "test"
        self.timeout = timeout
        self.count = 0
        os.makedirs(self.save_dir, exist_ok=True)

    def take(self, label="capture", on_fail="warn"):
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
        self.ws.send(json.dumps({"type": "SCREENSHOT", "label": label}))
        old_timeout = self.ws.gettimeout()
        self.ws.settimeout(self.timeout)
        try:
            result = self._wait_for_result()
        finally:
            self.ws.settimeout(old_timeout)

        if not result:
            raise TimeoutError(f"No SCREENSHOT_RESULT within {self.timeout}s")
        if result.get("error"):
            raise RuntimeError(result["error"])

        screenshot = result.get("screenshot")
        if not screenshot:
            raise RuntimeError("Empty screenshot data")

        b64 = screenshot.split(",", 1)[1] if "," in screenshot else screenshot
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
        start = time.time()
        while time.time() - start < self.timeout:
            try:
                raw = self.ws.recv()
                msg = json.loads(raw)
                if msg.get("type") == "SCREENSHOT_RESULT":
                    return msg
                elif msg.get("type") == "PING":
                    self.ws.send(json.dumps({"type": "PONG"}))
            except Exception:
                break
        return None
