"""
Smoke test for Gemini extension WebSocket flow.

Sends a single IMAGE_JOB via the storyboard API and monitors
the WS for status updates and image upload confirmation.

Usage:
    python test_gemini_ws.py
    python test_gemini_ws.py --prompt "generate a red circle on white background"
    python test_gemini_ws.py --scenes 3
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

FLASK_URL = "http://127.0.0.1:5050"
WS_URL = "ws://127.0.0.1:5050/ws/image-gemini"
PROJECT_ID = "pp_TEST01"

DEFAULT_PROMPTS = [
    "generate an image wide, a single red paper airplane flying through a vast empty white space, minimalist composition, clean lines",
]


def check_flask():
    try:
        r = requests.get(f"{FLASK_URL}/api/health", timeout=3)
        r.raise_for_status()
        print(f"[OK] Flask healthy: {r.json().get('status')}")
        return True
    except Exception as e:
        print(f"[FAIL] Flask not reachable: {e}")
        return False


def monitor_ws(results, timeout=120):
    """Connect to WS and listen for status updates."""
    done = threading.Event()

    def on_message(wsapp, raw):
        msg = json.loads(raw)
        t = msg.get("type", "")
        if t == "PING":
            wsapp.send(json.dumps({"type": "PONG"}))
            return
        if t == "PONG":
            return
        ts = time.strftime("%H:%M:%S")
        if t == "IMAGE_JOB":
            scenes = msg.get("scenes", [])
            print(f"  [{ts}] IMAGE_JOB received by monitor — {len(scenes)} scene(s)")
            results["job_received"] = True
        else:
            print(f"  [{ts}] {t}: {json.dumps(msg, default=str)[:200]}")
            results["messages"].append(msg)

    def on_open(wsapp):
        print(f"[OK] WS monitor connected")
        wsapp.send(json.dumps({"type": "EXTENSION_READY", "source": "test-monitor"}))

    def on_error(wsapp, err):
        print(f"[WS ERROR] {err}")

    def on_close(wsapp, code, reason):
        print(f"[WS] Closed ({code})")
        done.set()

    wsapp = websocket.WebSocketApp(
        WS_URL,
        on_message=on_message,
        on_open=on_open,
        on_error=on_error,
        on_close=on_close,
    )

    t = threading.Thread(target=wsapp.run_forever, daemon=True)
    t.start()

    # Wait for completion or timeout
    done.wait(timeout)
    wsapp.close()
    return results


def send_job(prompts, aspect_ratio="9:16"):
    """Send IMAGE_JOB via the storyboard API."""
    scenes = [{"scene": i + 1, "prompt": p} for i, p in enumerate(prompts)]
    payload = {
        "project_id": PROJECT_ID,
        "provider": "gemini",
        "aspect_ratio": aspect_ratio,
        "auto_type": True,
        "scenes": scenes,
    }

    print(f"\n[SEND] {len(scenes)} scene(s) to {FLASK_URL}/api/storyboard/generate")
    for i, s in enumerate(scenes):
        print(f"  Scene {s['scene']}: {s['prompt'][:80]}...")

    r = requests.post(f"{FLASK_URL}/api/storyboard/generate", json=payload, timeout=10)
    print(f"[RESP] {r.status_code}: {r.json()}")
    return r.status_code == 202


def main():
    parser = argparse.ArgumentParser(description="Gemini extension smoke test")
    parser.add_argument("--prompt", type=str, help="Custom prompt (single scene)")
    parser.add_argument("--scenes", type=int, default=1, help="Number of default scenes")
    parser.add_argument("--timeout", type=int, default=120, help="Max wait time in seconds")
    parser.add_argument("--aspect", type=str, default="9:16", help="Aspect ratio")
    args = parser.parse_args()

    print("=" * 50)
    print("  Gemini Extension Smoke Test")
    print("=" * 50)

    if not check_flask():
        sys.exit(1)

    # Build prompts
    if args.prompt:
        prompts = [args.prompt]
    else:
        prompts = DEFAULT_PROMPTS[:args.scenes]
        # Pad if more scenes requested
        while len(prompts) < args.scenes:
            prompts.append(f"generate an image, abstract geometric shape #{len(prompts)+1}, minimalist, white background")

    results = {"job_received": False, "messages": []}

    # Start WS monitor in background
    print(f"\n[WS] Connecting to {WS_URL}...")
    monitor_thread = threading.Thread(target=monitor_ws, args=(results, args.timeout), daemon=True)
    monitor_thread.start()
    time.sleep(1)

    # Send job
    if not send_job(prompts, args.aspect):
        print("[FAIL] API returned error")
        sys.exit(1)

    print(f"\n[WAIT] Monitoring for {args.timeout}s (Ctrl+C to stop)...")
    try:
        monitor_thread.join(args.timeout)
    except KeyboardInterrupt:
        print("\n[STOP] Interrupted by user")

    # Summary
    print("\n" + "=" * 50)
    print("  Results")
    print("=" * 50)
    uploads = [m for m in results["messages"] if m.get("type") == "IMAGE_UPLOAD"]
    statuses = [m for m in results["messages"] if m.get("type") == "STATUS_UPDATE"]
    errors = [m for m in results["messages"] if m.get("type") == "STATUS_UPDATE" and m.get("status") == "error"]

    print(f"  Job received:    {'Yes' if results['job_received'] else 'No'}")
    print(f"  Status updates:  {len(statuses)}")
    print(f"  Images uploaded: {len(uploads)}")
    print(f"  Errors:          {len(errors)}")

    if uploads:
        print(f"\n  [OK] Smoke test PASSED")
    elif statuses:
        print(f"\n  [~] Extension responded but no image uploaded yet")
    else:
        print(f"\n  [!] No response from extension — check if it's loaded in Chromium")


if __name__ == "__main__":
    main()
