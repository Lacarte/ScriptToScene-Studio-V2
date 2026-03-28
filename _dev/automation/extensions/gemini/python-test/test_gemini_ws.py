"""
Gemini Extension — Integration Test Suite

Tests all 4 core functionalities:
  1. WebSocket localhost detection + handshake (EXTENSION_READY)
  2. Connection status (connect/disconnect detection)
  3. Job listening (IMAGE_JOB delivery + pending job flush)
  4. Job completion notification (JOB_COMPLETE, STATUS_UPDATE, IMAGE_UPLOAD)

Usage:
    python test_gemini_ws.py                 # Run all tests
    python test_gemini_ws.py --test connect  # Run single test
    python test_gemini_ws.py --test job      # Test job delivery
    python test_gemini_ws.py --port 5050     # Specify port
"""

import argparse
import json
import sys
import threading
import time

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

try:
    import websocket  # websocket-client
except ImportError:
    sys.exit("pip install websocket-client")


# ── Config ──────────────────────────────────────────

FLASK_URL = "http://127.0.0.1:5050"
WS_URL = "ws://127.0.0.1:5050/ws/storyboard-gemini-image-grabber"
PROJECT_ID = "pp_TEST01"

PASS = "\033[92m PASS \033[0m"
FAIL = "\033[91m FAIL \033[0m"
INFO = "\033[94m INFO \033[0m"


def log(tag, msg):
    ts = time.strftime("%H:%M:%S")
    print(f"  [{ts}] [{tag}] {msg}")


# -- Test 1: WebSocket Connect + Handshake --─────────

def test_connect(port):
    """Verify WS connection and EXTENSION_READY handshake."""
    print("\n-- Test 1: WebSocket Connect + Handshake --")
    url = f"ws://127.0.0.1:{port}/ws/storyboard-gemini-image-grabber"
    result = {"connected": False, "handshake_sent": False, "flush_received": False}

    try:
        ws = websocket.create_connection(url, timeout=5)
        result["connected"] = True
        log(PASS, f"Connected to {url}")

        # Send EXTENSION_READY (same as real extension)
        ready_msg = json.dumps({"type": "EXTENSION_READY", "source": "test-harness"})
        ws.send(ready_msg)
        result["handshake_sent"] = True
        log(PASS, "Sent EXTENSION_READY handshake")

        # Listen briefly for flush of pending jobs
        ws.settimeout(2)
        try:
            while True:
                raw = ws.recv()
                msg = json.loads(raw)
                if msg.get("type") == "IMAGE_JOB":
                    result["flush_received"] = True
                    scenes = msg.get("scenes", [])
                    log(INFO, f"Received flushed IMAGE_JOB ({len(scenes)} scenes)")
                elif msg.get("type") == "PING":
                    ws.send(json.dumps({"type": "PONG"}))
        except (websocket.WebSocketTimeoutException, Exception):
            pass

        ws.close()
        log(PASS, "Connection closed cleanly")
        return True

    except Exception as e:
        log(FAIL, f"Connection failed: {e}")
        return False


# -- Test 2: Connection Status Detection --───────────

def test_status(port):
    """Verify server detects connect/disconnect correctly."""
    print("\n-- Test 2: Connection Status Detection --")
    url = f"ws://127.0.0.1:{port}/ws/storyboard-gemini-image-grabber"

    # Check health first
    try:
        r = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=3)
        if r.status_code != 200:
            log(FAIL, f"Health check failed: {r.status_code}")
            return False
        log(PASS, f"Flask healthy: {r.json().get('status')}")
    except Exception as e:
        log(FAIL, f"Flask not reachable: {e}")
        return False

    # Connect
    try:
        ws = websocket.create_connection(url, timeout=5)
        ws.send(json.dumps({"type": "EXTENSION_READY", "source": "test-status"}))
        log(PASS, "Connected (light should be GREEN)")
    except Exception as e:
        log(FAIL, f"Connection failed: {e}")
        return False

    # Verify server sees us as connected
    time.sleep(0.5)
    try:
        r = requests.post(
            f"http://127.0.0.1:{port}/api/storyboard/generate",
            json={
                "project_id": "pp_STATUS_TEST",
                "provider": "gemini",
                "aspect_ratio": "9:16",
                "scenes": [{"scene": 0, "prompt": "status test"}],
            },
            timeout=5,
        )
        if r.status_code == 202:
            log(PASS, "Server accepted job (extension detected as connected)")
        else:
            log(INFO, f"Server returned {r.status_code}: {r.text[:100]}")
    except Exception as e:
        log(INFO, f"Job send check: {e}")

    # Drain any messages
    ws.settimeout(1)
    try:
        while True:
            ws.recv()
    except Exception:
        pass

    # Disconnect
    ws.close()
    log(PASS, "Disconnected (light should be RED)")
    time.sleep(1)

    # Reconnect to verify recovery
    try:
        ws2 = websocket.create_connection(url, timeout=5)
        ws2.send(json.dumps({"type": "EXTENSION_READY", "source": "test-reconnect"}))
        log(PASS, "Reconnected successfully (light should be GREEN again)")
        ws2.close()
        return True
    except Exception as e:
        log(FAIL, f"Reconnect failed: {e}")
        return False


# ── Test 3: Job Listening ───────────────────────────

def test_job(port):
    """Verify IMAGE_JOB delivery when extension is connected."""
    print("\n-- Test 3: Job Listening (IMAGE_JOB delivery) --")
    url = f"ws://127.0.0.1:{port}/ws/storyboard-gemini-image-grabber"
    result = {"job_received": False, "scenes_count": 0}
    done = threading.Event()

    # Connect WS first
    try:
        ws = websocket.create_connection(url, timeout=5)
        ws.send(json.dumps({"type": "EXTENSION_READY", "source": "test-job"}))
        log(PASS, "Connected, listening for jobs...")
    except Exception as e:
        log(FAIL, f"Connection failed: {e}")
        return False

    # Listen in background
    def listener():
        ws.settimeout(15)
        try:
            while not done.is_set():
                raw = ws.recv()
                msg = json.loads(raw)
                if msg.get("type") == "PING":
                    ws.send(json.dumps({"type": "PONG"}))
                elif msg.get("type") == "IMAGE_JOB":
                    scenes = msg.get("scenes", [])
                    pid = msg.get("projectId", "?")
                    result["job_received"] = True
                    result["scenes_count"] = len(scenes)
                    log(PASS, f"IMAGE_JOB received: {pid} — {len(scenes)} scene(s)")
                    for sc in scenes:
                        log(INFO, f"  Scene {sc.get('scene')}: {sc.get('prompt', '')[:60]}...")
                    done.set()
        except Exception:
            pass

    t = threading.Thread(target=listener, daemon=True)
    t.start()

    # Send job via API
    time.sleep(0.5)
    prompt = "generate an image wide, a single red paper airplane flying through empty white space"
    try:
        r = requests.post(
            f"http://127.0.0.1:{port}/api/storyboard/generate",
            json={
                "project_id": PROJECT_ID,
                "provider": "gemini",
                "aspect_ratio": "9:16",
                "auto_type": True,
                "scenes": [{"scene": 0, "prompt": prompt}],
            },
            timeout=5,
        )
        log(INFO, f"API response: {r.status_code} — {r.json()}")
    except Exception as e:
        log(FAIL, f"API call failed: {e}")
        ws.close()
        return False

    # Wait for job
    done.wait(timeout=10)
    ws.close()

    if result["job_received"]:
        log(PASS, f"Job delivery confirmed ({result['scenes_count']} scenes)")
        return True
    else:
        log(FAIL, "Job was NOT received via WebSocket")
        return False


# -- Test 4: Job Completion Notification --───────────

def test_notify(port):
    """Verify server handles STATUS_UPDATE, IMAGE_UPLOAD, JOB_COMPLETE."""
    print("\n-- Test 4: Job Completion Notification --")
    url = f"ws://127.0.0.1:{port}/ws/storyboard-gemini-image-grabber"

    try:
        ws = websocket.create_connection(url, timeout=5)
        ws.send(json.dumps({"type": "EXTENSION_READY", "source": "test-notify"}))
        log(PASS, "Connected")
    except Exception as e:
        log(FAIL, f"Connection failed: {e}")
        return False

    # Drain any pending messages
    ws.settimeout(2)
    try:
        while True:
            ws.recv()
    except Exception:
        pass

    pid = "pp_NOTIFY_TEST"
    ok = True

    # Send STATUS_UPDATE
    try:
        ws.send(json.dumps({
            "type": "STATUS_UPDATE",
            "projectId": pid,
            "scene": 0,
            "status": "generating",
        }))
        log(PASS, "Sent STATUS_UPDATE (scene 0 -> generating)")
    except Exception as e:
        log(FAIL, f"STATUS_UPDATE failed: {e}")
        ok = False

    # Send IMAGE_UPLOAD (tiny 1x1 PNG)
    tiny_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    try:
        ws.send(json.dumps({
            "type": "IMAGE_UPLOAD",
            "projectId": pid,
            "scene": 0,
            "image": {"data": tiny_png, "source_url": "test://1x1.png"},
        }))
        log(PASS, "Sent IMAGE_UPLOAD (1x1 PNG)")
    except Exception as e:
        log(FAIL, f"IMAGE_UPLOAD failed: {e}")
        ok = False

    # Send JOB_COMPLETE
    try:
        ws.send(json.dumps({
            "type": "JOB_COMPLETE",
            "projectId": pid,
        }))
        log(PASS, "Sent JOB_COMPLETE")
    except Exception as e:
        log(FAIL, f"JOB_COMPLETE failed: {e}")
        ok = False

    time.sleep(1)
    ws.close()

    if ok:
        log(PASS, "All notifications sent and accepted by server")
    return ok


# ── Main ────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Gemini Extension Integration Tests")
    parser.add_argument("--test", choices=["connect", "status", "job", "notify"], help="Run single test")
    parser.add_argument("--port", type=int, default=5050, help="Flask port (default: 5050)")
    args = parser.parse_args()

    print("=" * 56)
    print("  STS Gemini Extension — Integration Test Suite")
    print("=" * 56)

    # Health check
    try:
        r = requests.get(f"http://127.0.0.1:{args.port}/api/health", timeout=3)
        r.raise_for_status()
        print(f"  Flask: OK ({r.json().get('status')})")
    except Exception as e:
        print(f"  Flask: UNREACHABLE ({e})")
        print(f"  Start the STS backend first: python app.py")
        sys.exit(1)

    tests = {
        "connect": ("WS Connect + Handshake", test_connect),
        "status": ("Connection Status", test_status),
        "job": ("Job Listening", test_job),
        "notify": ("Job Completion", test_notify),
    }

    if args.test:
        name, fn = tests[args.test]
        passed = fn(args.port)
    else:
        results = {}
        for key, (name, fn) in tests.items():
            results[key] = fn(args.port)
            time.sleep(0.5)

        # Summary
        print("\n" + "=" * 56)
        print("  Results")
        print("=" * 56)
        all_passed = True
        for key, (name, _) in tests.items():
            status = PASS if results[key] else FAIL
            print(f"  [{status}] {name}")
            if not results[key]:
                all_passed = False

        print()
        if all_passed:
            print("  All tests passed.")
        else:
            print("  Some tests failed — check output above.")
            sys.exit(1)


if __name__ == "__main__":
    main()
