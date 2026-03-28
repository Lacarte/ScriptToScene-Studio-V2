"""Quick connect/disconnect test for Gemini WS."""
import json, sys, time

try:
    import websocket
except ImportError:
    sys.exit("pip install websocket-client")

URL = "ws://127.0.0.1:5050/ws/image-gemini"

print("1. Connecting...")
ws = websocket.create_connection(URL, timeout=5)
ws.send(json.dumps({"type": "EXTENSION_READY", "source": "test"}))
print("   CONNECTED")

# drain any pending messages
ws.settimeout(2)
try:
    while True:
        msg = json.loads(ws.recv())
        print(f"   got: {msg.get('type')}")
except:
    pass

print("2. Waiting 5s (should stay connected)...")
time.sleep(5)
print(f"   readyState: {ws.connected}")

print("3. Disconnecting...")
ws.close()
print("   DISCONNECTED")

print("4. Reconnecting...")
ws2 = websocket.create_connection(URL, timeout=5)
ws2.send(json.dumps({"type": "EXTENSION_READY", "source": "test-reconnect"}))
print(f"   CONNECTED (readyState: {ws2.connected})")
ws2.close()
print("   DISCONNECTED")

print("\nDone - all OK")
