"""One-shot probe: connect to Studio backend WS and ask the live Grok extension for state.

Connects as a 2nd peer to /ws/animator-grok-video-grabber, sends DIAGNOSE,
the backend relays it to the connected Grok extension which replies with
DIAGNOSE_REPORT (relayed back to us). Prints the report and exits.
"""
import json, sys, time
from simple_websocket import Client

URL = "ws://localhost:5050/ws/animator-grok-video-grabber"

ws = Client.connect(URL)
ws.send(json.dumps({"type": "DIAGNOSE"}))
print("[probe] DIAGNOSE sent — waiting for report...", file=sys.stderr)
end = time.time() + 10
while time.time() < end:
    try:
        raw = ws.receive(timeout=8.0)
    except Exception as e:
        print(f"[probe] recv error: {e}", file=sys.stderr); break
    if raw is None:
        continue
    try:
        msg = json.loads(raw)
    except Exception:
        print(f"[probe] non-json: {raw[:120]}", file=sys.stderr); continue
    mt = msg.get("type")
    if mt == "DIAGNOSE_REPORT":
        print(json.dumps(msg, indent=2))
        sys.exit(0)
    print(f"[probe] other: {mt}", file=sys.stderr)
print("[probe] timeout — no DIAGNOSE_REPORT", file=sys.stderr)
sys.exit(2)
