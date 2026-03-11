"""
Automa Workflow Pusher — Pure Python, zero dependencies.

Commands:
  python automa-pusher.py patch              Patch Automa for upsert support (one time)
  python automa-pusher.py patch --revert     Revert the patch
  python automa-pusher.py <file.json> ...    Auto-push via browser (default)
  python automa-pusher.py --ui               Start web UI at http://localhost:3457
  python automa-pusher.py --headless <file>  Push via Chrome DevTools Protocol (no browser)
"""

import http.server
import json
import os
import shutil
import socket
import sys
import time
import webbrowser
import urllib.parse
from pathlib import Path

PORT = 3457
WORKFLOWS_DIR = Path(__file__).parent / "workflows"
AUTOMA_EXT_ID = "infppggnoaenmfagbfknfkancpbljcca"


# =============================================================================
# PATCH
# =============================================================================

UPSERT_HANDLER = (
    ',n.on("upsert-workflow",(async({workflow:e})=>{try{const{workflows:r}'
    '=await t().storage.local.get("workflows");let o=null,i=null;if(Array'
    '.isArray(r)){const t=r.findIndex(t=>t.name===e.name);t!==-1&&(o=r[t]'
    ',i=t)}else if(r&&typeof r==="object"){for(const[t,n]of Object.entries'
    '(r)){if(n.name===e.name){o=n;i=t;break}}}if(o){const n={...o,...e,id'
    ':o.id,createdAt:o.createdAt,updatedAt:Date.now(),table:e.table||e.dat'
    'aColumns||o.table,dataColumns:o.dataColumns||[]};n.drawflow="string"='
    '=typeof n.drawflow?v(n.drawflow,n.drawflow):n.drawflow;if(Array.isAr'
    'ray(r)){r[i]=n}else{r[o.id]=n}await t().storage.local.set({workflows'
    ':r});s("workflow:added",{workflowId:o.id,workflowData:n},"background"'
    ');console.log("[automa-patch] Updated workflow:",e.name)}else{const n='
    'crypto.getRandomValues(new Uint8Array(21)).reduce((e,t)=>(e+((t&=63)<'
    '36?t.toString(36):t<62?(t-26).toString(36).toUpperCase():t>62?"-":"_"'
    ')),"");const a={...e,id:n,dataColumns:[],createdAt:Date.now(),table:e'
    '.table||e.dataColumns};a.drawflow="string"==typeof a.drawflow?v(a.dra'
    'wflow,a.drawflow):a.drawflow;if(Array.isArray(r)){r.push(a)}else{r[n]'
    '=a}await t().storage.local.set({workflows:r});s("workflow:added",{wor'
    'kflowId:n,workflowData:a},"background");console.log("[automa-patch] C'
    'reated workflow:",e.name)}}catch(e){console.error("[automa-patch] upse'
    'rt error:",e)}}))'
)

INJECTION_NEEDLE = ',n.on("add-team-workflow"'


def find_automa_dir():
    """Find Automa extension directory across common Chrome profile locations."""
    local_app = os.environ.get("LOCALAPPDATA", "")
    if not local_app:
        home = Path.home()
        candidates = [
            home / "Library/Application Support/Google/Chrome/Default/Extensions" / AUTOMA_EXT_ID,
            home / ".config/google-chrome/Default/Extensions" / AUTOMA_EXT_ID,
        ]
    else:
        candidates = [
            Path(local_app) / "Google/Chrome/User Data/Default/Extensions" / AUTOMA_EXT_ID,
        ]

    for base in candidates:
        if base.exists():
            versions = sorted([d for d in base.iterdir() if d.is_dir()])
            if versions:
                return versions[-1]

    return None


def patch(revert=False):
    ext_dir = find_automa_dir()
    if not ext_dir:
        print("ERROR: Automa extension not found.")
        print("Make sure Automa is installed in Chrome.")
        sys.exit(1)

    bundle = ext_dir / "webService.bundle.js"
    backup = ext_dir / "webService.bundle.js.backup"

    print(f"Automa found: {ext_dir}")

    if revert:
        if backup.exists():
            shutil.copy2(backup, bundle)
            print("Reverted to original.")
        else:
            print("No backup found — nothing to revert.")
        return

    original = bundle.read_text(encoding="utf-8")

    if "upsert-workflow" in original:
        print("Already patched! Nothing to do.")
        return

    pos = original.find(INJECTION_NEEDLE)
    if pos == -1:
        print("ERROR: Could not find injection point.")
        print("Automa version may have changed. Try updating the patch.")
        sys.exit(1)

    if not backup.exists():
        shutil.copy2(bundle, backup)
        print(f"Backup: {backup}")

    patched = original[:pos] + UPSERT_HANDLER + original[pos:]
    bundle.write_text(patched, encoding="utf-8")

    print("\nPatched successfully!")
    print('Added "upsert-workflow" event handler.')
    print("\nNow reload Automa in chrome://extensions (click the reload icon).")


# =============================================================================
# PUSH (auto mode) — embed workflow data directly in HTML, zero API calls
# =============================================================================

def push_files(files):
    """Embed workflow JSON in an HTML page, serve it once, done."""
    # Load all workflows
    workflows = []
    for f in files:
        src = Path(f)
        if not src.exists():
            print(f"File not found: {f}")
            continue
        wf = json.loads(src.read_text(encoding="utf-8"))
        name = wf.get("name", src.name)
        workflows.append({"name": name, "data": wf})
        print(f'  {name}')

    if not workflows:
        print("No valid workflow files.")
        return

    # Build self-contained HTML with workflow data embedded inline
    wf_json = json.dumps([w["data"] for w in workflows], ensure_ascii=False)
    wf_names = json.dumps([w["name"] for w in workflows], ensure_ascii=False)

    html = (
        '<!DOCTYPE html><html><head><title>Pushing...</title>'
        '<style>'
        'body{font-family:system-ui;max-width:600px;margin:40px auto;padding:0 20px;background:#1a1a2e;color:#eee}'
        'h2{color:#00d4aa}.log{background:#16213e;padding:16px;border-radius:8px;font-family:monospace;font-size:.9em;line-height:1.8}'
        '.ok{color:#00d4aa}.err{color:#e74c3c}'
        '.done{margin-top:20px;padding:16px;background:#0d2818;border:1px solid #00d4aa;border-radius:8px;text-align:center;color:#00d4aa;font-weight:600}'
        '</style></head><body>'
        '<h2 id="h">Pushing workflows...</h2>'
        '<div class="log" id="log"></div>'
        '<script>'
        'const W=' + wf_json + ';'
        'const N=' + wf_names + ';'
        'const log=document.getElementById("log");'
        'function msg(t,c){log.innerHTML+="<div class=\'"+(c||"")+"\'>"+t+"</div>";}'
        '(async()=>{'
        'for(let i=0;i<W.length;i++){'
        'try{'
        'window.dispatchEvent(new CustomEvent("__automa-ext__",{detail:{type:"upsert-workflow",data:{workflow:W[i]}}}));'
        'msg("Pushed: "+N[i],"ok");'
        '}catch(e){msg("Failed: "+N[i]+" - "+e.message,"err");}'
        'if(i<W.length-1)await new Promise(r=>setTimeout(r,500));'
        '}'
        'document.getElementById("h").textContent="Push complete!";'
        'const d=document.createElement("div");d.className="done";'
        'd.textContent=W.length+" workflow(s) pushed to Automa. You can close this tab.";'
        'document.body.appendChild(d);'
        'fetch("/done").catch(()=>{});'
        '})();'
        '</script></body></html>'
    )

    # Find a free port
    port = _find_port()

    # Minimal server: serves the HTML once, then waits for /done
    done = [False]

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            if path == "/done":
                done[0] = True
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok")
            else:
                # Any path serves the push page (handles /, /auto-push, etc.)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))

    server = http.server.HTTPServer(("", port), Handler)
    server.timeout = 2

    url = f"http://localhost:{port}/?t={int(time.time())}"
    print(f"  Server: localhost:{port}")
    webbrowser.open(url)

    # Wait for /done callback (max 30s)
    deadline = time.time() + 30
    while time.time() < deadline and not done[0]:
        server.handle_request()

    server.server_close()

    if done[0]:
        print("Done!")
    else:
        print("Timed out — check Automa dashboard manually.")


def _find_port():
    """Find a free port, preferring PORT."""
    # Check if preferred port is free
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        if s.connect_ex(("127.0.0.1", PORT)) != 0:
            return PORT

    # Port busy — get a random free one
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = s.getsockname()[1]
    print(f"  Port {PORT} busy, using {port}")
    return port


# =============================================================================
# WEB UI (--ui mode) — persistent server with dashboard
# =============================================================================

class UIHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send_html(UI_HTML)
        elif path == "/api/workflows":
            self._serve_workflow_list()
        elif path.startswith("/api/workflow/"):
            self._serve_workflow(path[len("/api/workflow/"):])
        else:
            self.send_response(404)
            self.end_headers()

    def _send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def _serve_workflow_list(self):
        files = []
        for f in sorted(WORKFLOWS_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                files.append({"file": f.name, "name": data.get("name", f.name)})
            except Exception:
                files.append({"file": f.name, "name": f.name})
        self._send_json(files)

    def _serve_workflow(self, filename):
        filename = urllib.parse.unquote(filename)
        filepath = WORKFLOWS_DIR / filename
        if filepath.exists():
            self._send_json(json.loads(filepath.read_text(encoding="utf-8")))
        else:
            self.send_response(404)
            self.end_headers()


UI_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Automa Workflow Pusher</title>
  <style>
    body { font-family: system-ui; max-width: 700px; margin: 40px auto; padding: 0 20px; background: #1a1a2e; color: #eee; }
    h1 { color: #00d4aa; }
    .workflow { background: #16213e; border: 1px solid #0f3460; border-radius: 8px; padding: 16px; margin: 12px 0; display: flex; justify-content: space-between; align-items: center; }
    .workflow .name { font-weight: 600; font-size: 1.1em; }
    button { background: #00d4aa; color: #1a1a2e; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: 600; }
    button:hover { background: #00b894; }
    .status { margin-top: 8px; font-size: 0.9em; color: #aaa; }
    .success { color: #00d4aa; }
    .error { color: #e74c3c; }
    #push-all { margin: 20px 0; padding: 12px 32px; font-size: 1.1em; }
    .info { background: #0f3460; padding: 12px; border-radius: 6px; margin: 16px 0; font-size: 0.9em; }
  </style>
</head>
<body>
  <h1>Automa Workflow Pusher</h1>
  <div class="info">Place <code>.json</code> workflow files in <code>workflows/</code>, then click Push.</div>
  <button id="push-all">Push All Workflows</button>
  <div id="list"></div>
  <script>
    async function loadWorkflows() {
      const res = await fetch('/api/workflows');
      const workflows = await res.json();
      const list = document.getElementById('list');
      list.innerHTML = '';
      if (!workflows.length) { list.innerHTML = '<p style="color:#aaa">No workflows found</p>'; return; }
      for (const w of workflows) {
        const div = document.createElement('div');
        div.className = 'workflow';
        div.innerHTML = '<div><div class="name">' + w.name + '</div><div class="status" id="status-' + w.file + '"></div></div><button onclick="pushWorkflow(\\'' + w.file + '\\')">Push</button>';
        list.appendChild(div);
      }
    }
    async function pushWorkflow(file) {
      const el = document.getElementById('status-' + file);
      el.className = 'status'; el.textContent = 'Pushing...';
      try {
        const res = await fetch('/api/workflow/' + encodeURIComponent(file));
        const workflow = await res.json();
        window.dispatchEvent(new CustomEvent('__automa-ext__', {
          detail: { type: 'upsert-workflow', data: { workflow } }
        }));
        el.className = 'status success';
        el.textContent = 'Pushed! Check Automa dashboard.';
      } catch (err) { el.className = 'status error'; el.textContent = 'Error: ' + err.message; }
    }
    document.getElementById('push-all').onclick = async () => {
      const res = await fetch('/api/workflows');
      for (const w of await res.json()) { await pushWorkflow(w.file); await new Promise(r => setTimeout(r, 500)); }
    };
    loadWorkflows();
  </script>
</body>
</html>"""


def run_server():
    """Run persistent server with web UI."""
    WORKFLOWS_DIR.mkdir(exist_ok=True)
    print(f"Automa Workflow Pusher running at http://localhost:{PORT}")
    print(f"Workflow directory: {WORKFLOWS_DIR}")
    print(f"\nOpen http://localhost:{PORT} in Chrome to push workflows.")
    print("Press Ctrl+C to stop.\n")

    server = http.server.HTTPServer(("", PORT), UIHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


# =============================================================================
# HEADLESS (--headless mode) — Chrome DevTools Protocol, no browser tab
# =============================================================================

def headless_push(files):
    """Push workflows via Chrome DevTools Protocol — no UI, no browser tab."""
    import hashlib
    import struct
    from urllib.request import urlopen

    def ws_connect(url):
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname
        port = parsed.port or 80
        path = parsed.path or "/"

        sock = socket.create_connection((host, port), timeout=10)
        import base64
        key_b64 = base64.b64encode(os.urandom(16)).decode()

        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key_b64}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        )
        sock.sendall(handshake.encode())

        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += sock.recv(4096)

        if b"101" not in resp.split(b"\r\n")[0]:
            raise ConnectionError(f"WebSocket handshake failed: {resp[:200]}")

        return sock

    def ws_send(sock, text):
        import struct
        data = text.encode("utf-8")
        frame = bytearray()
        frame.append(0x81)
        mask_key = os.urandom(4)
        length = len(data)
        if length < 126:
            frame.append(0x80 | length)
        elif length < 65536:
            frame.append(0x80 | 126)
            frame.extend(struct.pack(">H", length))
        else:
            frame.append(0x80 | 127)
            frame.extend(struct.pack(">Q", length))
        frame.extend(mask_key)
        masked = bytearray(b ^ mask_key[i % 4] for i, b in enumerate(data))
        frame.extend(masked)
        sock.sendall(frame)

    def ws_recv(sock):
        import struct
        header = sock.recv(2)
        if len(header) < 2:
            return None
        payload_len = header[1] & 0x7F
        if payload_len == 126:
            payload_len = struct.unpack(">H", sock.recv(2))[0]
        elif payload_len == 127:
            payload_len = struct.unpack(">Q", sock.recv(8))[0]
        data = b""
        while len(data) < payload_len:
            chunk = sock.recv(payload_len - len(data))
            if not chunk:
                break
            data += chunk
        return data.decode("utf-8", errors="replace")

    # Connect to Chrome DevTools
    try:
        resp = urlopen("http://127.0.0.1:9222/json", timeout=5)
        tabs = json.loads(resp.read())
    except Exception:
        print("ERROR: Cannot connect to Chrome DevTools on port 9222.")
        print("Start Chrome with: chrome.exe --remote-debugging-port=9222")
        sys.exit(1)

    # Find a suitable tab
    ws_url = None
    for tab in tabs:
        if tab.get("type") == "page" and tab.get("webSocketDebuggerUrl"):
            url = tab.get("url", "")
            if "localhost" in url or "127.0.0.1" in url:
                ws_url = tab["webSocketDebuggerUrl"]
                print(f"Using tab: {url}")
                break

    if not ws_url:
        for tab in tabs:
            if tab.get("type") == "page" and tab.get("webSocketDebuggerUrl"):
                ws_url = tab["webSocketDebuggerUrl"]
                print(f"Using tab: {tab.get('url', '?')}")
                break

    if not ws_url:
        print("ERROR: No usable Chrome tab found.")
        sys.exit(1)

    sock = ws_connect(ws_url)
    msg_id = 1

    def cdp_send(method, params=None):
        nonlocal msg_id
        msg = {"id": msg_id, "method": method}
        if params:
            msg["params"] = params
        ws_send(sock, json.dumps(msg))
        msg_id += 1
        while True:
            raw = ws_recv(sock)
            if raw is None:
                return None
            data = json.loads(raw)
            if data.get("id") == msg_id - 1:
                return data

    # Navigate to localhost so Automa's content script is active
    cdp_send("Page.navigate", {"url": "http://localhost:1/__automa_push__"})
    time.sleep(1)

    # Push each workflow
    for f in files:
        src = Path(f)
        if not src.exists():
            print(f"  File not found: {f}")
            continue

        workflow = json.loads(src.read_text(encoding="utf-8"))
        name = workflow.get("name", src.name)

        js_code = (
            "window.dispatchEvent(new CustomEvent('__automa-ext__', "
            "{ detail: { type: 'upsert-workflow', data: { workflow: "
            + json.dumps(workflow, ensure_ascii=False)
            + " } } })); 'ok';"
        )

        result = cdp_send("Runtime.evaluate", {"expression": js_code})
        err = result.get("result", {}).get("exceptionDetails") if result else None
        if err:
            print(f"  FAILED: {name} -- {err}")
        else:
            print(f"  Pushed: {name}")

        time.sleep(0.5)

    sock.close()
    print("Done!")


# =============================================================================
# CLI
# =============================================================================

def main():
    args = sys.argv[1:]

    if not args:
        print(__doc__)
    elif args[0] == "patch":
        patch(revert="--revert" in args)
    elif args[0] in ("--help", "-h"):
        print(__doc__)
    elif args[0] == "--ui":
        run_server()
    elif args[0] == "--headless":
        if len(args) < 2:
            print("Usage: python automa-pusher.py --headless <file.json> ...")
            sys.exit(1)
        headless_push(args[1:])
    else:
        push_files(args)


if __name__ == "__main__":
    main()
