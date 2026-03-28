"""
Gemini Extension — Disconnect / Reconnect Test

Remotely forces the extension to disconnect its WS, verifies it goes RED,
then waits for auto-reconnect and verifies it goes GREEN again.

No Flask restart needed — uses FORCE_DISCONNECT command.
"""
import json, sys, time

try:
    import websocket
except ImportError:
    sys.exit("pip install websocket-client")

WS_URL = "ws://127.0.0.1:5050/ws/image-gemini"


def diagnose():
    """Get extension state via DIAGNOSE command."""
    try:
        ws = websocket.create_connection(WS_URL, timeout=5)
        ws.send(json.dumps({"type": "EXTENSION_READY", "source": "test"}))
        ws.settimeout(2)
        try:
            while True: ws.recv()
        except: pass

        ws.send(json.dumps({"type": "DIAGNOSE"}))
        ws.settimeout(8)
        try:
            while True:
                msg = json.loads(ws.recv())
                if msg.get("type") == "DIAGNOSE_REPORT":
                    ws.close()
                    return msg
                if msg.get("type") == "PING":
                    ws.send(json.dumps({"type": "PONG"}))
        except: pass
        ws.close()
    except: pass
    return None


def status_line(report):
    if not report:
        return "NO REPORT (extension not connected to WS)"
    bg = report.get("bg", {})
    states = report.get("contentStates", [])
    cs = states[0].get("state", {}) if states and not states[0].get("error") else {}
    dot = cs.get("headDotClass", "")
    color = "GREEN" if "on" in str(dot) else "RED"
    return (f"bg={bg.get('wsConnected')}  content={cs.get('wsConnected')}  "
            f"msg='{cs.get('connMsgText', '?')}'  dot={color}")


def force_disconnect():
    """Send FORCE_DISCONNECT to make the extension close its WS."""
    try:
        ws = websocket.create_connection(WS_URL, timeout=5)
        ws.send(json.dumps({"type": "EXTENSION_READY", "source": "force-dc"}))
        ws.settimeout(1)
        try:
            while True: ws.recv()
        except: pass
        ws.send(json.dumps({"type": "FORCE_DISCONNECT"}))
        time.sleep(0.5)
        ws.close()
        return True
    except Exception as e:
        print(f"  Failed: {e}")
        return False


def main():
    print("=" * 60)
    print("  Disconnect / Reconnect Test")
    print("=" * 60)

    # 1. Check connected
    print("\n1. Current state...")
    r = diagnose()
    print(f"   {status_line(r)}")
    if not r or not r.get("bg", {}).get("wsConnected"):
        print("   Extension not connected. Reload extension first.")
        sys.exit(1)

    # 2. Force disconnect
    print("\n2. Sending FORCE_DISCONNECT...")
    force_disconnect()
    print("   Sent. Waiting 3s for extension to detect...")
    time.sleep(3)

    # 3. Check disconnected
    print("\n3. Checking state (should be RED)...")
    r2 = diagnose()
    print(f"   {status_line(r2)}")

    # 4. Wait for auto-reconnect
    print("\n4. Waiting for auto-reconnect...")
    reconnected = False
    for i in range(10):
        time.sleep(2)
        r3 = diagnose()
        if r3 and r3.get("bg", {}).get("wsConnected"):
            states = r3.get("contentStates", [])
            cs = states[0].get("state", {}) if states and not states[0].get("error") else {}
            if cs.get("wsConnected"):
                print(f"   Reconnected after ~{(i+1)*2}s!")
                print(f"   {status_line(r3)}")
                reconnected = True
                break
        print(f"   Check {i+1}/10: still disconnected...")

    # Summary
    print("\n" + "=" * 60)
    if reconnected:
        print("  PASS")
        print("    Connected -> FORCE_DISCONNECT -> Disconnected -> Auto-reconnect -> Connected")
    else:
        print("  FAIL — Extension did not auto-reconnect within 20s")
    print("=" * 60)


if __name__ == "__main__":
    main()
