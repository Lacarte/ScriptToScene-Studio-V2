"""
Orchestrator — WebSocket handler.

Provides:
  WS  /ws/orchestrator  — WebSocket endpoint for the STS Orchestrator Chrome extension

The orchestrator extension manages tabs and takes screenshots.
This WS route simply relays messages bidirectionally.
"""

import json
import threading
from loguru import logger

_ws_clients = []
_ws_lock = threading.Lock()


def init_orchestrator_ws(sock):
    """Register the /ws/orchestrator WebSocket route."""

    @sock.route("/ws/orchestrator")
    def orchestrator_ws(ws):
        with _ws_lock:
            _ws_clients.append(ws)
            count = len(_ws_clients)
        logger.info("Orchestrator WS client connected (clients: {})", count)

        try:
            while True:
                raw = ws.receive()
                if raw is None:
                    break
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                logger.debug("Orchestrator WS <- {}", msg.get("type") or msg.get("command") or "unknown")
                _handle_message(msg, ws)
        except Exception as e:
            logger.info("Orchestrator WS closed: {}", e)
        finally:
            with _ws_lock:
                if ws in _ws_clients:
                    _ws_clients.remove(ws)
                count = len(_ws_clients)
            logger.info("Orchestrator WS client disconnected (clients: {})", count)


def _handle_message(msg, ws):
    """Handle messages from the orchestrator extension (or test clients)."""
    msg_type = msg.get("type") or msg.get("command") or ""

    if msg_type == "hello":
        logger.info("Orchestrator extension connected: v{}", msg.get("version", "?"))

    elif msg_type == "EXTENSION_READY":
        logger.info("Orchestrator test client connected: {}", msg.get("source", "?"))

    elif msg_type in ("tab_list", "tab_focused", "result", "pong",
                      "screenshot_result", "diagnose_report", "error"):
        # Responses from extension — relay to all OTHER clients (test scripts)
        _relay_to_others(msg, ws)

    else:
        # Commands from test scripts — relay to the extension
        _relay_to_extension(msg, ws)


def _relay_to_others(msg, sender_ws):
    """Send a message from the extension to all other connected clients."""
    raw = json.dumps(msg)
    with _ws_lock:
        for client in _ws_clients:
            if client is not sender_ws:
                try:
                    client.send(raw)
                except Exception:
                    pass


def _relay_to_extension(msg, sender_ws):
    """Send a command from a test client to the extension."""
    raw = json.dumps(msg)
    with _ws_lock:
        for client in _ws_clients:
            if client is not sender_ws:
                try:
                    client.send(raw)
                except Exception:
                    pass


def is_extension_connected():
    with _ws_lock:
        return len(_ws_clients) > 0
