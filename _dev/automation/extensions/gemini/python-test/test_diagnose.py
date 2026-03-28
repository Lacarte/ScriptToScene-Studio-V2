"""
Gemini Extension — Remote Diagnostics

Sends a DIAGNOSE command via WebSocket. The extension's background worker
captures a screenshot + internal state from both background and content
script, then sends it all back over WS.

Usage:
    python test_diagnose.py
    python test_diagnose.py --save-dir ./diag-output
"""
import argparse
import base64
import json
import os
import sys
import time

try:
    import websocket
except ImportError:
    sys.exit("pip install websocket-client")

WS_URL = "ws://127.0.0.1:5050/ws/storyboard-gemini-image-grabber"


def run_diagnose(save_dir):
    os.makedirs(save_dir, exist_ok=True)

    print("Connecting to WS...")
    ws = websocket.create_connection(WS_URL, timeout=10)
    ws.send(json.dumps({"type": "EXTENSION_READY", "source": "diagnose-tool"}))

    # Drain any pending messages first
    ws.settimeout(2)
    try:
        while True:
            raw = ws.recv()
            msg = json.loads(raw)
            if msg.get("type") not in ("PING", "PONG"):
                print(f"  (drained: {msg.get('type')})")
    except:
        pass

    # Send DIAGNOSE command — the server will broadcast it to the extension
    print("Sending DIAGNOSE command...")
    ws.send(json.dumps({"type": "DIAGNOSE"}))

    # Wait for the DIAGNOSE_REPORT back
    ws.settimeout(15)
    report = None
    try:
        while True:
            raw = ws.recv()
            msg = json.loads(raw)
            if msg.get("type") == "DIAGNOSE_REPORT":
                report = msg
                break
            elif msg.get("type") == "PING":
                ws.send(json.dumps({"type": "PONG"}))
            else:
                print(f"  (got: {msg.get('type')})")
    except Exception as e:
        print(f"  Timeout waiting for report: {e}")

    ws.close()

    if not report:
        print("\nNo DIAGNOSE_REPORT received.")
        print("Possible causes:")
        print("  - Extension not loaded in Chrome")
        print("  - Background worker not connected to this WS")
        print("  - DIAGNOSE message not reaching extension")
        return

    # Print report
    print("\n" + "=" * 60)
    print("  DIAGNOSE REPORT")
    print("=" * 60)

    bg = report.get("bg", {})
    print(f"\n  Background Worker:")
    print(f"    WS connected:      {bg.get('wsConnected')}")
    print(f"    WS URL:            {bg.get('wsUrl')}")
    print(f"    WS readyState:     {bg.get('wsReadyState')} (0=CONNECTING, 1=OPEN, 2=CLOSING, 3=CLOSED)")
    print(f"    Active ports:      {bg.get('portsActive')}")
    print(f"    Reconnect attempts:{bg.get('reconnectAttempts')}")

    states = report.get("contentStates", [])
    if states:
        for cs in states:
            print(f"\n  Content Script (tab {cs.get('tabId')}):")
            if cs.get("error"):
                print(f"    ERROR: {cs['error']}")
            else:
                s = cs.get("state", {})
                print(f"    active:        {s.get('active')}")
                print(f"    wsConnected:   {s.get('wsConnected')}")
                print(f"    connected:     {s.get('connected')}")
                print(f"    wsUrl:         {s.get('wsUrl')}")
                print(f"    projectId:     {s.get('projectId')}")
                print(f"    scenes:        {s.get('scenesCount')}")
                print(f"    queue:         {s.get('queueLength')}")
                print(f"    typing:        {s.get('typingActive')}")
                print(f"    panel exists:  {s.get('panelExists')}")
                print(f"    connBar:       display={s.get('connBarDisplay')}, class={s.get('connBarClass')}")
                print(f"    connMsg:       '{s.get('connMsgText')}'")
                print(f"    headDot:       class={s.get('headDotClass')}")
    else:
        print("\n  Content Script: NO RESPONSE")

    errors = report.get("errors", [])
    if errors:
        print(f"\n  Errors:")
        for e in errors:
            print(f"    - {e}")

    # Save screenshot
    screenshot = report.get("screenshot")
    if screenshot:
        # Strip data:image/png;base64, prefix
        if "," in screenshot:
            b64 = screenshot.split(",", 1)[1]
        else:
            b64 = screenshot
        ts = time.strftime("%Y%m%d-%H%M%S")
        path = os.path.join(save_dir, f"diag-{ts}.png")
        with open(path, "wb") as f:
            f.write(base64.b64decode(b64))
        size_kb = os.path.getsize(path) / 1024
        print(f"\n  Screenshot saved: {path} ({size_kb:.0f} KB)")
    else:
        print(f"\n  Screenshot: NOT CAPTURED")

    # Save full JSON report
    report_no_screenshot = {k: v for k, v in report.items() if k != "screenshot"}
    json_path = os.path.join(save_dir, f"diag-{time.strftime('%Y%m%d-%H%M%S')}.json")
    with open(json_path, "w") as f:
        json.dump(report_no_screenshot, f, indent=2)
    print(f"  Report saved:     {json_path}")

    print("\n" + "=" * 60)

    # Diagnosis
    print("  DIAGNOSIS:")
    if bg.get("wsConnected") and states and not states[0].get("error"):
        s = states[0].get("state", {})
        if s.get("wsConnected"):
            print("    Background + Content both report connected.")
            if s.get("connMsgText") == "Disconnected":
                print("    BUT conn bar shows Disconnected -> render() bug")
            else:
                print("    All looks good!")
        else:
            print("    Background connected, Content says NOT connected")
            print("    -> sendMessage/onMessage relay is broken")
    elif bg.get("wsConnected") and (not states or states[0].get("error")):
        print("    Background connected but content script not responding")
        print("    -> content script not loaded or crashed")
    elif not bg.get("wsConnected"):
        print("    Background NOT connected to WS")
        print("    -> check service worker console for errors")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--save-dir", default="./_dev/automation/extensions/gemini/python-test/diag-output")
    args = parser.parse_args()
    run_diagnose(args.save_dir)
