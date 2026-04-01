"""
Grok Extension — Quick WebSocket Connection Test

Verifies basic WS connectivity and EXTENSION_READY handshake.
"""
import json, sys, time

try:
    import websocket
except ImportError:
    sys.exit("pip install websocket-client")

WS_URL = "ws://127.0.0.1:5050/ws/animator-grok-video-grabber"


def main():
    print("1. Connecting...")
    try:
        ws = websocket.create_connection(WS_URL, timeout=10)
        print("   CONNECTED")
    except Exception as e:
        print(f"   FAILED: {e}")
        sys.exit(1)

    ws.send(json.dumps({"type": "EXTENSION_READY", "source": "grok-test"}))

    print("2. Waiting 5s (should stay connected)...")
    time.sleep(5)
    print(f"   readyState: {ws.connected}")

    print("3. Disconnecting...")
    ws.close()
    print("   DISCONNECTED")

    print("4. Reconnecting...")
    try:
        ws2 = websocket.create_connection(WS_URL, timeout=10)
        ws2.send(json.dumps({"type": "EXTENSION_READY", "source": "grok-test-reconnect"}))
        print(f"   CONNECTED (readyState: {ws2.connected})")
        ws2.close()
        print("   DISCONNECTED")
    except Exception as e:
        print(f"   FAILED: {e}")
        sys.exit(1)

    print("\nDone - all OK")


if __name__ == "__main__":
    main()
