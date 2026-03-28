"""
Grok Extension — Remote Diagnostics

Sends DIAGNOSE via the animator WS. Reports background + content state.
"""
import json, sys, time

try:
    import websocket
except ImportError:
    sys.exit("pip install websocket-client")

WS_URL = "ws://127.0.0.1:5050/ws/animator-grok-video-grabber"


def run():
    print("Connecting to WS...")
    ws = websocket.create_connection(WS_URL, timeout=5)
    ws.send(json.dumps({"type": "EXTENSION_READY", "source": "diagnose-tool"}))

    ws.settimeout(2)
    try:
        while True: ws.recv()
    except: pass

    print("Sending DIAGNOSE...")
    ws.send(json.dumps({"type": "DIAGNOSE"}))

    ws.settimeout(10)
    report = None
    try:
        while True:
            msg = json.loads(ws.recv())
            if msg.get("type") == "DIAGNOSE_REPORT":
                report = msg
                break
            if msg.get("type") == "PING":
                ws.send(json.dumps({"type": "PONG"}))
    except Exception as e:
        print(f"  Timeout: {e}")

    ws.close()

    if not report:
        print("\nNo report. Extension background not connected.")
        return

    print("\n" + "=" * 60)
    print("  GROK DIAGNOSE REPORT")
    print("=" * 60)

    bg = report.get("bg", {})
    print(f"\n  Background Worker:")
    print(f"    WS connected:      {bg.get('wsConnected')}")
    print(f"    WS readyState:     {bg.get('wsReadyState')}")
    print(f"    Active ports:      {bg.get('portsActive')}")
    print(f"    Reconnect attempts:{bg.get('reconnectAttempts')}")

    for cs in report.get("contentStates", []):
        print(f"\n  Content Script (tab {cs.get('tabId')}):")
        if cs.get("error"):
            print(f"    ERROR: {cs['error']}")
        else:
            s = cs.get("state", {})
            print(f"    wsConnected:   {s.get('wsConnected')}")
            print(f"    connected:     {s.get('connected')}")
            print(f"    projectId:     {s.get('projectId')}")
            print(f"    queue:         {s.get('queueLength')}")
            print(f"    connMsg:       '{s.get('connMsgText')}'")
            print(f"    headDot:       {s.get('headDotClass')}")

    print("\n" + "=" * 60)
    bg_ok = bg.get("wsConnected")
    states = report.get("contentStates", [])
    cs = states[0].get("state", {}) if states and not states[0].get("error") else {}
    cs_ok = cs.get("wsConnected")
    if bg_ok and cs_ok:
        print("  ALL GOOD - both connected")
    elif bg_ok and not cs_ok:
        print("  Background connected, content NOT - messaging issue")
    elif not bg_ok:
        print("  Background NOT connected - check service worker")
    print("=" * 60)


if __name__ == "__main__":
    run()
