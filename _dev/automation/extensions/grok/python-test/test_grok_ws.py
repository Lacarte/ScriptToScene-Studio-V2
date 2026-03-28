"""
Smoke test for Grok extension WebSocket flow.

Sends a single GRABBER_START job via the assets API and monitors
the WS for status updates and asset upload confirmation.

Usage:
    python test_grok_ws.py
    python test_grok_ws.py --prompt "a red paper airplane soaring through clouds"
    python test_grok_ws.py --scenes 3
    python test_grok_ws.py --mode image --aspect 9:16
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
WS_URL = "ws://127.0.0.1:5050/ws/animator-grok-video-grabber"
PROJECT_ID = "pp_GROK01"

DEFAULT_PROMPTS = [
    "a single red paper airplane soaring through vast empty white space, minimalist, clean lines",
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


def check_grok_extension():
    """Check if Grok extension is connected via WS."""
    try:
        r = requests.get(f"{FLASK_URL}/api/animator/grabber/status/{PROJECT_ID}", timeout=3)
        return True  # endpoint exists
    except Exception:
        return True  # endpoint may 404 but Flask is up


def monitor_ws(results, timeout=180):
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
        if t == "GRABBER_START":
            scenes = msg.get("scenes", [])
            print(f"  [{ts}] GRABBER_START received — {len(scenes)} scene(s)")
            results["job_received"] = True
        elif t == "ANIMATE_JOB":
            print(f"  [{ts}] ANIMATE_JOB: scene {msg.get('sceneIndex')}")
            results["messages"].append(msg)
        else:
            summary = json.dumps(msg, default=str)[:200]
            print(f"  [{ts}] {t}: {summary}")
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

    done.wait(timeout)
    wsapp.close()
    return results


def send_job(prompts, mode="video", aspect_ratio="9:16", duration="6s", quality="480p", image_path=None):
    """Send GRABBER_START via the assets API."""
    import base64
    import os

    # Encode reference image if provided
    image_b64 = None
    if image_path and os.path.isfile(image_path):
        with open(image_path, "rb") as f:
            raw = f.read()
        ext = os.path.splitext(image_path)[1].lstrip(".").lower()
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
        image_b64 = f"data:image/{mime};base64,{base64.b64encode(raw).decode()}"
        size_kb = len(raw) // 1024
        print(f"[IMG] Encoded {os.path.basename(image_path)} ({size_kb} KB)")

    scenes = []
    for i, p in enumerate(prompts):
        entry = {"scene": i + 1, "prompt": p}
        if image_b64:
            entry["image"] = image_b64
        scenes.append(entry)

    payload = {
        "project_id": PROJECT_ID,
        "provider": "grok",
        "aspect_ratio": aspect_ratio,
        "auto_type": True,
        "grok_mode": mode,
        "grok_quality": quality,
        "grok_duration": duration,
        "scenes": scenes,
    }

    print(f"\n[SEND] {len(scenes)} scene(s) to {FLASK_URL}/api/animator/grabber/start")
    print(f"  Mode: {mode} | Aspect: {aspect_ratio} | Duration: {duration} | Quality: {quality}")
    if image_path:
        print(f"  Image: {os.path.basename(image_path)}")
    for s in scenes:
        print(f"  Scene {s['scene']}: {s['prompt'][:80]}...")

    r = requests.post(f"{FLASK_URL}/api/animator/grabber/start", json=payload, timeout=10)
    print(f"[RESP] {r.status_code}: {r.text[:200]}")
    return r.status_code in (200, 201, 202)


def main():
    parser = argparse.ArgumentParser(description="Grok extension smoke test")
    parser.add_argument("--prompt", type=str, help="Custom prompt (single scene)")
    parser.add_argument("--scenes", type=int, default=1, help="Number of default scenes")
    parser.add_argument("--timeout", type=int, default=180, help="Max wait time in seconds")
    parser.add_argument("--aspect", type=str, default="9:16", help="Aspect ratio")
    parser.add_argument("--mode", type=str, default="video", choices=["video", "image"], help="Grok generation mode")
    parser.add_argument("--duration", type=str, default="6s", help="Video duration (e.g. 6s)")
    parser.add_argument("--quality", type=str, default="480p", help="Video quality (e.g. 480p, 720p)")
    parser.add_argument("--image", type=str, help="Path to reference image (sent as storyboard image)")
    args = parser.parse_args()

    print("=" * 50)
    print("  Grok Extension Smoke Test")
    print("=" * 50)

    if not check_flask():
        sys.exit(1)

    # Build prompts
    if args.prompt:
        prompts = [args.prompt]
    else:
        prompts = DEFAULT_PROMPTS[:args.scenes]
        while len(prompts) < args.scenes:
            prompts.append(f"abstract geometric shape #{len(prompts)+1} floating in empty space, minimalist, white background")

    results = {"job_received": False, "messages": []}

    # Start WS monitor in background
    print(f"\n[WS] Connecting to {WS_URL}...")
    monitor_thread = threading.Thread(target=monitor_ws, args=(results, args.timeout), daemon=True)
    monitor_thread.start()
    time.sleep(1)

    # Send job
    if not send_job(prompts, args.mode, args.aspect, args.duration, args.quality, args.image):
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
    uploads = [m for m in results["messages"] if m.get("type") == "ASSET_UPLOAD"]
    statuses = [m for m in results["messages"] if m.get("type") == "STATUS_UPDATE"]
    errors = [m for m in results["messages"] if m.get("type") == "STATUS_UPDATE" and m.get("status") == "error"]
    animate = [m for m in results["messages"] if m.get("type") == "ANIMATE_JOB"]

    print(f"  Job received:     {'Yes' if results['job_received'] else 'No'}")
    print(f"  Status updates:   {len(statuses)}")
    print(f"  Animate jobs:     {len(animate)}")
    print(f"  Assets uploaded:  {len(uploads)}")
    print(f"  Errors:           {len(errors)}")

    if uploads:
        print(f"\n  [OK] Smoke test PASSED")
    elif statuses or animate:
        print(f"\n  [~] Extension responded but no assets uploaded yet")
    else:
        print(f"\n  [!] No response from extension — check if it's loaded in Chromium")


if __name__ == "__main__":
    main()
