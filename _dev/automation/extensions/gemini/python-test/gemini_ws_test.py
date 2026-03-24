"""
Gemini Image Generator — WebSocket Test Server
================================================
Standalone test server that mimics the ScriptToScene Studio backend
for the Gemini Automa image generation workflow.

Endpoints:
  WS  ws://localhost:5050/ws/image-gemini   — WebSocket for Automa extension
  GET http://localhost:5050                  — Dashboard UI (status + controls)

Protocol (Automa → Server):
  { type: "EXTENSION_READY", source: "automa-gemini" }
  { type: "IMAGE_UPLOAD", projectId, scene, image: { data, source_url } }

Protocol (Server → Automa):
  { type: "IMAGE_JOB", projectId, scenes: [...], autoType: true }
  { type: "PONG" }

Usage:
  pip install websockets aiohttp
  python gemini_ws_test.py
  python gemini_ws_test.py --prompts prompts.txt
  python gemini_ws_test.py --prompts prompts.txt --project pp_TEST01
"""

import argparse
import asyncio
import base64
import datetime
import io
import json
import os
import sys
import webbrowser

# Fix Windows console encoding for Unicode output
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from pathlib import Path

try:
    import websockets
except ImportError:
    print("Install websockets:  pip install websockets")
    sys.exit(1)

try:
    from aiohttp import web
except ImportError:
    print("Install aiohttp:  pip install aiohttp")
    sys.exit(1)


# ── Config ────────────────────────────────────────────────────
HOST = "localhost"
PORT = 5055
WS_PATH = "/ws/image-gemini"
OUTPUT_DIR = Path(__file__).parent / "output"

# ── State ─────────────────────────────────────────────────────
clients: set = set()
job_state = {
    "project_id": None,
    "scenes": {},       # scene_num -> { prompt, status, image_path }
    "total": 0,
    "completed": 0,
    "failed": 0,
    "started_at": None,
}
pending_job = None  # Queued job to send on next client connect


# ── Prompt Loading ────────────────────────────────────────────
DEFAULT_PROMPTS = [
    "A serene mountain landscape at golden hour with dramatic clouds",
    "A futuristic cyberpunk city street at night with neon signs",
    "A cute corgi puppy sitting in a field of sunflowers, watercolor style",
]


def load_prompts(path: str | None) -> list[str]:
    """Load prompts from file (one per line) or use defaults."""
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            prompts = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        if prompts:
            print(f"Loaded {len(prompts)} prompts from {path}")
            return prompts
    print(f"Using {len(DEFAULT_PROMPTS)} default prompts")
    return DEFAULT_PROMPTS


def build_job(prompts: list[str], project_id: str, aspect_ratio: str = "9:16") -> dict:
    """Build an IMAGE_JOB message from prompts."""
    scenes = []
    for i, prompt in enumerate(prompts):
        scenes.append({
            "scene": i,
            "prompt": prompt,
        })
        job_state["scenes"][str(i)] = {
            "prompt": prompt,
            "status": "pending",
            "image_path": None,
        }
    job_state["project_id"] = project_id
    job_state["total"] = len(prompts)
    job_state["completed"] = 0
    job_state["failed"] = 0
    job_state["started_at"] = datetime.datetime.now().isoformat()

    return {
        "type": "IMAGE_JOB",
        "projectId": project_id,
        "aspectRatio": aspect_ratio,
        "scenes": scenes,
        "autoType": True,
    }


# ── Image Saving ──────────────────────────────────────────────
def save_image(project_id: str, scene_num: int, image_data: str) -> str:
    """Save a base64 image to disk. Returns the file path."""
    project_dir = OUTPUT_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    # Strip data URI prefix if present
    if "," in image_data:
        header, b64 = image_data.split(",", 1)
        # Detect extension from MIME
        if "png" in header:
            ext = ".png"
        elif "webp" in header:
            ext = ".webp"
        elif "jpeg" in header or "jpg" in header:
            ext = ".jpg"
        else:
            ext = ".png"
    else:
        b64 = image_data
        ext = ".png"

    filename = f"scene_{scene_num:03d}{ext}"
    filepath = project_dir / filename
    filepath.write_bytes(base64.b64decode(b64))

    size_kb = filepath.stat().st_size / 1024
    print(f"  💾 Saved: {filepath} ({size_kb:.0f} KB)")
    return str(filepath)


# ── WebSocket Handler ─────────────────────────────────────────
async def ws_handler(websocket):
    """Handle a single Automa WebSocket connection."""
    clients.add(websocket)
    remote = websocket.remote_address
    print(f"\n🔌 Client connected: {remote}")

    # Flush pending job to newly connected client
    if pending_job:
        try:
            await websocket.send(json.dumps(pending_job))
            print(f"📤 Sent queued IMAGE_JOB ({len(pending_job['scenes'])} scenes) to {remote}")
        except Exception as e:
            print(f"⚠  Failed to send queued job: {e}")

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                print(f"⚠  Bad JSON from {remote}")
                continue

            msg_type = msg.get("type", "")

            if msg_type == "EXTENSION_READY":
                source = msg.get("source", "unknown")
                print(f"✅ Extension ready (source: {source})")
                # Send pending job if not already sent
                if pending_job:
                    await websocket.send(json.dumps(pending_job))
                    print(f"📤 Sent IMAGE_JOB ({len(pending_job['scenes'])} scenes)")

            elif msg_type == "IMAGE_UPLOAD":
                await handle_image_upload(msg)

            elif msg_type == "PING":
                await websocket.send(json.dumps({"type": "PONG"}))

            elif msg_type == "STATUS_UPDATE":
                scene = msg.get("scene")
                status = msg.get("status", "")
                print(f"📊 Scene {scene}: {status}")
                if str(scene) in job_state["scenes"]:
                    job_state["scenes"][str(scene)]["status"] = status

            else:
                print(f"❓ Unknown message type: {msg_type}")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(websocket)
        print(f"🔌 Client disconnected: {remote}")


async def handle_image_upload(msg: dict):
    """Process an IMAGE_UPLOAD message — save base64 image to disk."""
    project_id = msg.get("projectId", "")
    scene_num = msg.get("scene")
    image = msg.get("image", {})
    image_data = image.get("data", "") if isinstance(image, dict) else ""

    if not project_id or scene_num is None or not image_data:
        print("⚠  IMAGE_UPLOAD missing fields")
        return

    scene_key = str(scene_num)
    data_size = len(image_data) * 3 // 4 // 1024
    print(f"\n📥 IMAGE_UPLOAD: {project_id} scene {scene_num} (~{data_size} KB)")

    try:
        filepath = save_image(project_id, int(scene_num), image_data)
        if scene_key in job_state["scenes"]:
            job_state["scenes"][scene_key]["status"] = "completed"
            job_state["scenes"][scene_key]["image_path"] = filepath
            job_state["completed"] += 1
    except Exception as e:
        print(f"  ❌ Save failed: {e}")
        if scene_key in job_state["scenes"]:
            job_state["scenes"][scene_key]["status"] = "error"
            job_state["failed"] += 1

    # Check if all done
    total = job_state["total"]
    done = job_state["completed"] + job_state["failed"]
    print(f"  📊 Progress: {done}/{total} ({job_state['completed']} ok, {job_state['failed']} failed)")
    if done >= total and total > 0:
        print(f"\n🎉 All {total} scenes complete!")


# ── HTTP Dashboard ────────────────────────────────────────────
async def dashboard_handler(request):
    """Simple HTML dashboard showing job status."""
    html = build_dashboard_html()
    return web.Response(text=html, content_type="text/html")


async def api_status_handler(request):
    """JSON API for job status."""
    return web.json_response(job_state)


async def api_send_job_handler(request):
    """POST endpoint to send/re-send the job to connected clients."""
    global pending_job
    if not pending_job:
        return web.json_response({"error": "No job loaded"}, status=400)

    sent = 0
    for ws in list(clients):
        try:
            await ws.send(json.dumps(pending_job))
            sent += 1
        except Exception:
            pass

    return web.json_response({"sent_to": sent, "scenes": len(pending_job["scenes"])})


def build_dashboard_html() -> str:
    scenes_html = ""
    for num in sorted(job_state["scenes"].keys(), key=lambda x: int(x)):
        sc = job_state["scenes"][num]
        status = sc["status"]
        color = {
            "pending": "#888",
            "typing": "#f0ad4e",
            "generating": "#5bc0de",
            "completed": "#5cb85c",
            "error": "#d9534f",
        }.get(status, "#888")
        prompt_short = sc["prompt"][:80] + ("..." if len(sc["prompt"]) > 80 else "")
        img_tag = ""
        if sc.get("image_path") and os.path.isfile(sc["image_path"]):
            # Use actual filename from saved path (handles .png/.webp/.jpg)
            img_filename = os.path.basename(sc["image_path"])
            img_tag = f'<img src="/output/{job_state["project_id"]}/{img_filename}" style="max-width:200px;max-height:140px;border-radius:8px;margin-top:8px;border:1px solid var(--border);display:block;">'
        # Status icons
        status_icon = {"pending": "\u23F3", "typing": "\u270D\uFE0F", "generating": "\u2728", "completed": "\u2713", "error": "\u2717"}.get(status, "\u23F3")
        scenes_html += f"""
        <div class="scene-item" style="border-left-color:{color};">
            <div class="scene-num" style="color:{color};">{status_icon} #{num}</div>
            <div class="scene-body">
                <div class="scene-prompt">{prompt_short}</div>
                <div class="scene-status" style="color:{color};">{status.upper()}</div>
                {img_tag}
            </div>
        </div>"""

    total = job_state["total"]
    done = job_state["completed"]
    pct = (done / total * 100) if total else 0
    ws_count = len(clients)

    client_color = "#34d399" if ws_count else "#f87171"
    client_label = "Connected" if ws_count else "No clients"

    return f"""<!DOCTYPE html>
<html><head>
<title>STS Gemini — Dashboard</title>
<meta http-equiv="refresh" content="3">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0c0e14; --sf: #12151e; --el: #1a1e2a; --bd: #1f2536;
    --t1: #e2e8f0; --t2: #64748b; --tm: #475569;
    --ac: #2dd4bf; --ad: #2dd4bf33; --dn: #f87171; --dd: #f8717133;
    --ok: #34d399; --od: #34d39933;
  }}
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'DM Sans', sans-serif; background: var(--bg); color: var(--t1);
         min-height: 100vh; padding: 32px 48px; }}

  /* Header */
  .header {{ display: flex; align-items: center; gap: 16px; margin-bottom: 28px; }}
  .logo {{ width: 38px; height: 38px; border-radius: 10px;
           background: linear-gradient(135deg, var(--ac), #06b6d4);
           display: flex; align-items: center; justify-content: center;
           font-family: 'JetBrains Mono', monospace; font-weight: 600;
           font-size: 13px; color: #0c0e14; letter-spacing: -0.5px;
           box-shadow: 0 0 20px var(--ad); flex-shrink: 0; }}
  .header h1 {{ font-size: 22px; font-weight: 700; letter-spacing: -0.5px; }}
  .ws-url {{ font-family: 'JetBrains Mono', monospace; font-size: 12px;
             color: var(--tm); background: var(--el); border: 1px solid var(--bd);
             padding: 5px 12px; border-radius: 8px; }}
  .conn-badge {{ display: inline-flex; align-items: center; gap: 6px;
                 padding: 4px 12px 4px 10px; border-radius: 100px;
                 font-family: 'JetBrains Mono', monospace; font-size: 10px;
                 font-weight: 600; letter-spacing: 0.4px; text-transform: uppercase;
                 margin-left: auto; }}
  .conn-badge.on {{ background: var(--od); color: var(--ok); border: 1px solid rgba(52,211,153,.15); }}
  .conn-badge.off {{ background: var(--dd); color: var(--dn); border: 1px solid rgba(248,113,113,.15); }}
  .conn-dot {{ width: 6px; height: 6px; border-radius: 50%; }}
  .conn-badge.on .conn-dot {{ background: var(--ok); box-shadow: 0 0 8px var(--ok);
                              animation: pulse 2s ease-in-out infinite; }}
  .conn-badge.off .conn-dot {{ background: var(--dn); box-shadow: 0 0 8px var(--dn); }}
  @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.4}} }}

  /* Stats row */
  .stats {{ display: flex; gap: 14px; margin-bottom: 24px; }}
  .stat {{ background: var(--sf); border: 1px solid var(--bd); padding: 16px 24px;
           border-radius: 14px; text-align: center; min-width: 110px; flex: 1;
           transition: border-color 0.2s; }}
  .stat:hover {{ border-color: rgba(45,212,191,0.2); }}
  .stat .val {{ font-family: 'JetBrains Mono', monospace; font-size: 32px;
                font-weight: 600; line-height: 1.1; }}
  .stat .lbl {{ font-family: 'JetBrains Mono', monospace; font-size: 10px;
                color: var(--tm); text-transform: uppercase; letter-spacing: 1.2px;
                margin-top: 6px; }}

  /* Progress */
  .progress {{ height: 5px; background: var(--el); border-radius: 5px;
               overflow: hidden; margin-bottom: 24px; }}
  .progress-bar {{ height: 100%; border-radius: 5px;
                   background: linear-gradient(90deg, var(--ac), #06b6d4);
                   transition: width 0.5s cubic-bezier(.4,0,.2,1); position: relative; }}
  .progress-bar::after {{ content: ''; position: absolute; inset: 0;
                          background: linear-gradient(90deg, transparent, rgba(255,255,255,.15) 50%, transparent);
                          animation: shimmer 2s ease-in-out infinite; }}
  @keyframes shimmer {{ 0%{{transform:translateX(-100%)}} 100%{{transform:translateX(100%)}} }}

  /* Action bar */
  .action-bar {{ display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }}
  .action-btn {{ background: linear-gradient(135deg, var(--ac), #06b6d4); border: none;
                 color: #0c0e14; padding: 11px 28px; border-radius: 10px; cursor: pointer;
                 font-family: 'DM Sans', sans-serif; font-size: 13px; font-weight: 700;
                 letter-spacing: 0.2px; transition: all 0.15s; box-shadow: 0 2px 12px var(--ad); }}
  .action-btn:hover {{ box-shadow: 0 4px 24px var(--ad); transform: translateY(-1px); }}
  .action-btn:active {{ transform: scale(0.98); }}
  .project-tag {{ font-family: 'JetBrains Mono', monospace; font-size: 11px;
                  color: var(--tm); }}
  .project-tag b {{ color: var(--t2); font-weight: 600; }}

  /* Scenes */
  .scenes {{ display: flex; flex-direction: column; gap: 6px; }}
  .scene-item {{ display: flex; gap: 14px; align-items: flex-start; padding: 14px 18px;
                 background: var(--sf); border: 1px solid var(--bd); border-radius: 12px;
                 border-left: 3px solid transparent; transition: all 0.15s; }}
  .scene-item:hover {{ background: var(--el); border-color: rgba(45,212,191,0.12); }}
  .scene-num {{ font-family: 'JetBrains Mono', monospace; min-width: 60px;
                font-weight: 600; font-size: 13px; padding-top: 1px; flex-shrink: 0; }}
  .scene-body {{ flex: 1; min-width: 0; }}
  .scene-prompt {{ color: #94a3b8; font-size: 13px; line-height: 1.5; }}
  .scene-status {{ font-family: 'JetBrains Mono', monospace; font-size: 11px;
                   font-weight: 600; margin-top: 5px; letter-spacing: 0.5px; }}
  .empty {{ color: var(--tm); text-align: center; padding: 32px; font-size: 13px; }}
</style>
</head><body>
<div class="header">
    <div class="logo">STS</div>
    <h1>STS Gemini</h1>
    <span class="ws-url">ws://localhost:{PORT}{WS_PATH}</span>
    <span class="conn-badge {'on' if ws_count else 'off'}">
        <span class="conn-dot"></span>{ws_count} {'client' if ws_count == 1 else 'clients'}
    </span>
</div>
<div class="stats">
    <div class="stat"><div class="val" style="color:{client_color}">{ws_count}</div>
        <div class="lbl">Clients</div></div>
    <div class="stat"><div class="val" style="color:var(--t2)">{total}</div><div class="lbl">Total</div></div>
    <div class="stat"><div class="val" style="color:var(--ok)">{done}</div><div class="lbl">Done</div></div>
    <div class="stat"><div class="val" style="color:var(--dn)">{job_state['failed']}</div><div class="lbl">Failed</div></div>
    <div class="stat"><div class="val" style="color:var(--ac)">{pct:.0f}%</div><div class="lbl">Progress</div></div>
</div>
<div class="progress"><div class="progress-bar" style="width:{pct}%"></div></div>
<div class="action-bar">
    <form method="POST" action="/api/send-job" style="display:inline;">
        <button type="submit" class="action-btn">Re-send Job to Clients</button>
    </form>
    <span class="project-tag">Project \u2022 <b>{job_state['project_id'] or '\u2014'}</b></span>
</div>
<div class="scenes">{scenes_html or '<div class="empty">No scenes loaded</div>'}</div>
</body></html>"""


# ── Trusted Types policy script (bypasses Gemini CSP) ─────────
TRUSTED_TYPES_JS = """\
// Create a default Trusted Types policy so Automa can inject <script> textContent.
// This script is loaded via <script src="..."> which is NOT blocked by Trusted Types.
if (window.trustedTypes && trustedTypes.createPolicy) {
  try {
    trustedTypes.createPolicy('default', {
      createScript: function(s) { return s; },
      createScriptURL: function(s) { return s; },
      createHTML: function(s) { return s; },
    });
    console.log('[STS] Trusted Types default policy created');
  } catch (e) {
    // Policy may already exist
    console.log('[STS] Trusted Types policy already exists or failed:', e.message);
  }
}
"""


async def trusted_types_handler(request):
    """Serve the Trusted Types policy script with permissive CORS."""
    return web.Response(
        text=TRUSTED_TYPES_JS,
        content_type="application/javascript",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache",
        },
    )


# ── Serve sync.js (the full STS Gemini sync script) ──────────
async def sync_js_handler(request):
    """Serve the full sync script. Loaded via <script src> to bypass Trusted Types."""
    sync_path = Path(__file__).parent.parent / "_sync_code.js"
    if not sync_path.is_file():
        return web.Response(text="// _sync_code.js not found", status=404,
                            content_type="application/javascript")
    code = sync_path.read_text(encoding="utf-8")
    # Wrap in IIFE so top-level return statements work
    wrapped = f"(function() {{\n{code}\n}})();"
    return web.Response(
        text=wrapped,
        content_type="application/javascript",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache",
        },
    )


# ── Serve static output images ────────────────────────────────
async def output_file_handler(request):
    """Serve saved images for the dashboard preview."""
    rel = request.match_info.get("path", "")
    filepath = OUTPUT_DIR / rel
    if filepath.is_file():
        return web.FileResponse(filepath)
    return web.Response(status=404)


# ── Main ──────────────────────────────────────────────────────
async def main(prompts: list[str], project_id: str, aspect_ratio: str = "9:16"):
    global pending_job

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pending_job = build_job(prompts, project_id, aspect_ratio)

    print(f"╔══════════════════════════════════════════════════╗")
    print(f"║  Gemini Image WS Test Server                    ║")
    print(f"╠══════════════════════════════════════════════════╣")
    print(f"║  WebSocket:  ws://{HOST}:{PORT}{WS_PATH:<15}  ║")
    print(f"║  Dashboard:  http://{HOST}:{PORT:<24} ║")
    print(f"║  Project:    {project_id:<36} ║")
    print(f"║  Scenes:     {len(prompts):<36} ║")
    print(f"╚══════════════════════════════════════════════════╝")
    print()
    for i, p in enumerate(prompts):
        tag = f"[{project_id}|{i}]"
        print(f"  Scene {i}: {p[:60]}{'...' if len(p) > 60 else ''} {tag}")
    print()
    print("Waiting for Automa extension to connect...\n")

    # Start WebSocket server
    ws_server = await websockets.serve(ws_handler, HOST, PORT, ping_interval=30, ping_timeout=10)

    # Start HTTP server on same port — use a different port for dashboard
    app = web.Application()
    app.router.add_get("/", dashboard_handler)
    app.router.add_get("/api/status", api_status_handler)
    app.router.add_post("/api/send-job", api_send_job_handler)
    app.router.add_get("/trusted-types-policy.js", trusted_types_handler)
    app.router.add_get("/sync.js", sync_js_handler)
    app.router.add_get("/output/{path:.*}", output_file_handler)

    # aiohttp on a separate port since websockets owns 5050
    runner = web.AppRunner(app)
    await runner.setup()
    http_site = web.TCPSite(runner, HOST, PORT + 1)
    await http_site.start()
    dashboard_url = f"http://{HOST}:{PORT + 1}"
    print(f"📊 Dashboard: {dashboard_url}\n")
    webbrowser.open(dashboard_url)

    try:
        await asyncio.Future()  # Run forever
    except asyncio.CancelledError:
        pass
    finally:
        ws_server.close()
        await runner.cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gemini Image WS Test Server")
    parser.add_argument("--prompts", "-p", help="Path to prompts file (one per line)")
    parser.add_argument("--project", default="pp_GEMTEST", help="Project ID (default: pp_GEMTEST)")
    parser.add_argument("--aspect", default="9:16", help="Aspect ratio (default: 9:16)")
    parser.add_argument("--port", type=int, default=PORT, help=f"WebSocket port (default: {PORT})")
    args = parser.parse_args()

    PORT = args.port
    prompts = load_prompts(args.prompts)

    try:
        asyncio.run(main(prompts, args.project, args.aspect))
    except KeyboardInterrupt:
        print("\n\nShutdown.")
