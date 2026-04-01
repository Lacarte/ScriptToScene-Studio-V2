"""
Background Tab Image Generation Test
=====================================
Tests whether Gemini image generation completes properly when the tab is NOT
active/focused. Uses the DOM Activity Recorder extension to monitor mutations.

Setup:
  1. Load BOTH extensions in Chrome:
     - STS Gemini Sync
     - DOM Activity Recorder (SAR)
  2. Open Gemini tab → start DOM recorder on XPath:
       /html/body/chat-app/main/side-navigation-v2/bard-sidenav-container/bard-sidenav-content/div[2]/div/div[2]
  3. Start this script
  4. When prompted, switch AWAY from the Gemini tab
  5. Wait for results

What it tests:
  - Does generation start normally?
  - Do STATUS_UPDATE messages keep arriving when tab is background?
  - Does IMAGE_UPLOAD arrive (generation completed)?
  - How long does each phase take?
  - Compare with an active-tab baseline run

Usage:
    python test_background_tab.py                    # Interactive (prompts you to switch tabs)
    python test_background_tab.py --auto             # No prompts, just monitor
    python test_background_tab.py --port 5052        # Custom port
    python test_background_tab.py --scenes 3         # Multiple scenes
"""

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime

try:
    import websocket
except ImportError:
    sys.exit("pip install websocket-client")

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

from screenshot import ScreenshotCapture

# ── Config ──────────────────────────────────────────

PROJECT_ID = "pp_BGTAB_TEST"
DEFAULT_PORT = 5050

PASS  = "\033[92m PASS \033[0m"
FAIL  = "\033[91m FAIL \033[0m"
INFO  = "\033[94m INFO \033[0m"
WARN  = "\033[93m WARN \033[0m"
PHASE = "\033[95mPHASE\033[0m"

TEST_PROMPTS = [
    "Generate a wide cinematic image of a lone astronaut standing on a red desert planet, looking up at two moons in a purple twilight sky, dust particles floating in the air",
    "Generate a wide cinematic image of an ancient library with towering bookshelves, golden light streaming through stained glass windows, dust motes floating in light beams",
    "Generate a wide cinematic image of a cyberpunk street market at night, neon signs reflecting in rain puddles, street vendors with holographic displays",
]


def log(tag, msg):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"  [{ts}] [{tag}] {msg}")


def elapsed_str(start):
    return f"{time.time() - start:.1f}s"


# ── Event Timeline ──────────────────────────────────

class Timeline:
    """Records timestamped events for analysis."""

    def __init__(self):
        self.events = []
        self.start = time.time()

    def add(self, event_type, detail=""):
        t = time.time() - self.start
        self.events.append({"t": round(t, 2), "type": event_type, "detail": detail})

    def summary(self):
        lines = ["\n  ╔══ Event Timeline ══════════════════════════════════"]
        for e in self.events:
            lines.append(f"  ║ {e['t']:>7.2f}s  {e['type']:<20s}  {e['detail']}")
        lines.append("  ╚═══════════════════════════════════════════════════")
        return "\n".join(lines)

    def phase_durations(self):
        """Calculate time between key phases."""
        phases = {}
        by_type = {}
        for e in self.events:
            if e["type"] not in by_type:
                by_type[e["type"]] = e["t"]

        if "job_sent" in by_type and "first_status" in by_type:
            phases["job_sent → first_status"] = round(by_type["first_status"] - by_type["job_sent"], 2)
        if "first_status" in by_type and "image_upload" in by_type:
            phases["first_status → image_upload"] = round(by_type["image_upload"] - by_type["first_status"], 2)
        if "job_sent" in by_type and "job_complete" in by_type:
            phases["job_sent → job_complete (total)"] = round(by_type["job_complete"] - by_type["job_sent"], 2)
        if "tab_switched" in by_type:
            phases["tab_switched_at"] = by_type["tab_switched"]
            if "image_upload" in by_type:
                phases["tab_switch → image_upload"] = round(by_type["image_upload"] - by_type["tab_switched"], 2)

        return phases


# ── WebSocket Listener ──────────────────────────────

def ws_listener(ws, timeline, results, done_event):
    """Background thread: listens for all WS messages and records them."""
    first_status_seen = False

    while not done_event.is_set():
        try:
            ws.settimeout(2)
            raw = ws.recv()
            msg = json.loads(raw)
            msg_type = msg.get("type", "?")

            if msg_type == "PING":
                ws.send(json.dumps({"type": "PONG"}))
                continue

            elif msg_type == "STATUS_UPDATE":
                scene = msg.get("scene", "?")
                status = msg.get("status", "?")
                detail = f"scene={scene} status={status}"
                if not first_status_seen:
                    timeline.add("first_status", detail)
                    first_status_seen = True
                timeline.add("status_update", detail)
                log(INFO, f"STATUS_UPDATE: {detail}")
                results["status_updates"].append({"scene": scene, "status": status, "t": time.time()})

            elif msg_type == "IMAGE_UPLOAD":
                scene = msg.get("scene", "?")
                has_data = bool(msg.get("image", {}).get("data"))
                detail = f"scene={scene} has_image={has_data}"
                timeline.add("image_upload", detail)
                log(PASS, f"IMAGE_UPLOAD: {detail}")
                results["images_received"] += 1

            elif msg_type == "JOB_COMPLETE":
                pid = msg.get("projectId", "?")
                timeline.add("job_complete", f"projectId={pid}")
                log(PASS, f"JOB_COMPLETE: {pid}")
                results["job_complete"] = True
                done_event.set()

            elif msg_type == "IMAGE_JOB":
                # Echo of our job or flush of pending — just note it
                scenes = msg.get("scenes", [])
                timeline.add("image_job_echo", f"{len(scenes)} scenes")
                log(INFO, f"IMAGE_JOB received by extension ({len(scenes)} scenes)")

            else:
                timeline.add("ws_message", f"type={msg_type}")
                log(INFO, f"WS message: {msg_type}")

        except websocket.WebSocketTimeoutException:
            continue
        except websocket.WebSocketConnectionClosedException:
            log(WARN, "WebSocket closed")
            timeline.add("ws_closed")
            break
        except Exception as e:
            if not done_event.is_set():
                log(WARN, f"Listener error: {e}")
            break


# ── Main Test ───────────────────────────────────────

def run_test(port, num_scenes, auto_mode):
    base_url = f"http://127.0.0.1:{port}"
    ws_url = f"ws://127.0.0.1:{port}/ws/image-gemini"

    print("\n" + "=" * 60)
    print("  Background Tab — Image Generation Test")
    print("=" * 60)

    # ─ Health check
    try:
        r = requests.get(f"{base_url}/api/health", timeout=3)
        r.raise_for_status()
        log(PASS, f"Server healthy: {r.json().get('status')}")
    except Exception as e:
        log(FAIL, f"Server not reachable: {e}")
        print("  Start the STS backend first.")
        return False

    # ─ Connect WS
    try:
        ws = websocket.create_connection(ws_url, timeout=10)
        ws.send(json.dumps({"type": "EXTENSION_READY", "source": "bg-tab-test"}))
        log(PASS, f"WebSocket connected to {ws_url}")
    except Exception as e:
        log(FAIL, f"WS connection failed: {e}")
        return False

    # ─ Drain pending
    ws.settimeout(2)
    try:
        while True:
            raw = ws.recv()
            msg = json.loads(raw)
            log(INFO, f"Drained: {msg.get('type')}")
    except Exception:
        pass

    timeline = Timeline()
    results = {
        "status_updates": [],
        "images_received": 0,
        "job_complete": False,
    }
    done = threading.Event()

    # Screenshot capture for audit trail
    cap = ScreenshotCapture(ws, test_name="bg-tab")

    # ─ Start listener
    listener_thread = threading.Thread(target=ws_listener, args=(ws, timeline, results, done), daemon=True)
    listener_thread.start()

    # ─ Pre-flight instructions
    print()
    print("  ┌─────────────────────────────────────────────────────┐")
    print("  │  INSTRUCTIONS                                       │")
    print("  │                                                      │")
    print("  │  1. Make sure Gemini tab is ACTIVE right now         │")
    print("  │  2. DOM Activity Recorder should be monitoring:      │")
    print("  │     XPath: /html/body/chat-app/main/                 │")
    print("  │       side-navigation-v2/bard-sidenav-container/     │")
    print("  │       bard-sidenav-content/div[2]/div/div[2]         │")
    print("  │  3. Job will be sent in 3 seconds...                 │")
    print("  │  4. Once you see 'generating', SWITCH TABS           │")
    print("  └─────────────────────────────────────────────────────┘")
    print()

    time.sleep(3)

    # ─ Send job
    prompts = TEST_PROMPTS[:num_scenes]
    scenes = [{"scene": i, "prompt": p} for i, p in enumerate(prompts)]

    log(PHASE, f"Sending IMAGE_JOB with {len(scenes)} scene(s)...")
    timeline.add("job_sent", f"{len(scenes)} scenes")
    cap.take("before-job-sent", on_fail="warn")

    try:
        r = requests.post(
            f"{base_url}/api/storyboard/generate",
            json={
                "project_id": PROJECT_ID,
                "provider": "gemini",
                "aspect_ratio": "16:9",
                "auto_type": True,
                "scenes": scenes,
            },
            timeout=10,
        )
        if r.status_code == 202:
            log(PASS, f"Job accepted (202)")
        else:
            log(WARN, f"Server returned {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log(FAIL, f"Job send failed: {e}")
        ws.close()
        return False

    # ─ Wait for first status update, then prompt tab switch
    print()
    log(PHASE, "Waiting for generation to start...")

    switch_prompted = False
    start_time = time.time()

    while not done.is_set():
        # Once we see the first status update, prompt the tab switch
        if not switch_prompted and results["status_updates"]:
            cap.take("generation-started", on_fail="warn")
            print()
            if auto_mode:
                log(PHASE, "Generation started — in auto mode, NOT prompting tab switch")
                log(INFO, "Switch tabs manually whenever you want to test")
                timeline.add("auto_mode", "no tab switch prompt")
            else:
                print("  ╔═══════════════════════════════════════════════════╗")
                print("  ║  >>> SWITCH AWAY FROM GEMINI TAB NOW! <<<        ║")
                print("  ║                                                   ║")
                print("  ║  Click on any other tab or window.                ║")
                print("  ║  Press ENTER here once you've switched.           ║")
                print("  ╚═══════════════════════════════════════════════════╝")
                print()

                # Non-blocking: just mark the event after a small delay
                # (user might not press enter immediately)
                def wait_for_switch():
                    try:
                        input("  Press ENTER after switching tabs > ")
                        timeline.add("tab_switched", "user confirmed")
                        log(PHASE, "Tab switch recorded")
                    except EOFError:
                        timeline.add("tab_switched", "auto")
                switch_thread = threading.Thread(target=wait_for_switch, daemon=True)
                switch_thread.start()

            switch_prompted = True

        # Timeout after 5 minutes
        if time.time() - start_time > 300:
            log(FAIL, "Timeout: 5 minutes elapsed without JOB_COMPLETE")
            timeline.add("timeout", "300s")
            break

        time.sleep(0.5)

    # ─ Final screenshot before closing
    success_pre = results["images_received"] >= num_scenes and results["job_complete"]
    cap.take("completed" if success_pre else "failed", on_fail="warn")

    # ─ Results
    ws.close()

    print()
    print(timeline.summary())

    phases = timeline.phase_durations()
    if phases:
        print("\n  ┌─── Phase Durations ──────────────────────────────────")
        for k, v in phases.items():
            print(f"  │  {k}: {v}s")
        print("  └─────────────────────────────────────────────────────")

    print("\n  ┌─── Results ──────────────────────────────────────────")
    print(f"  │  Status updates received: {len(results['status_updates'])}")
    print(f"  │  Images received:         {results['images_received']}")
    print(f"  │  Job complete:            {results['job_complete']}")
    print(f"  │  Scenes requested:        {num_scenes}")

    success = results["images_received"] >= num_scenes and results["job_complete"]
    if success:
        print(f"  │  [{PASS}] All images generated successfully!")
    elif results["images_received"] > 0:
        print(f"  │  [{WARN}] Partial success: {results['images_received']}/{num_scenes} images")
    else:
        print(f"  │  [{FAIL}] No images received")
    print("  └─────────────────────────────────────────────────────")

    # ─ Save report
    report_dir = os.path.dirname(os.path.abspath(__file__))
    report_file = os.path.join(report_dir, f"bg-tab-report-{datetime.now().strftime('%Y%m%dT%H%M%S')}.json")
    report = {
        "test": "background_tab_image_generation",
        "timestamp": datetime.now().isoformat(),
        "scenes_requested": num_scenes,
        "images_received": results["images_received"],
        "job_complete": results["job_complete"],
        "status_updates": results["status_updates"],
        "timeline": timeline.events,
        "phase_durations": phases,
        "success": success,
    }
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2, default=str)
    log(INFO, f"Report saved: {report_file}")

    print()
    print("  TIP: Check the DOM Activity Recorder report in Gemini tab")
    print("  to see what DOM mutations occurred while the tab was inactive.")
    print("  Export it and compare with the timeline above.")
    print()

    return success


def main():
    parser = argparse.ArgumentParser(description="Background Tab Image Generation Test")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Server port (default: {DEFAULT_PORT})")
    parser.add_argument("--scenes", type=int, default=1, choices=[1, 2, 3], help="Number of scenes (default: 1)")
    parser.add_argument("--auto", action="store_true", help="Auto mode — no tab-switch prompt")
    args = parser.parse_args()

    success = run_test(args.port, args.scenes, args.auto)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
