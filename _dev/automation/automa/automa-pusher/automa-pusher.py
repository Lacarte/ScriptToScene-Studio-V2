"""
Automa Workflow Pusher — Pure Python, zero dependencies.

Pushes Automa workflow JSON files into the Chrome extension by serving a
localhost page that dispatches CustomEvents.  Automa's content script
(webService.bundle.js) runs on every localhost page and picks up the events.

Commands:
  python automa-pusher.py <file.json> ...    Auto-push via browser (default)
  python automa-pusher.py --ui               Start web UI at http://localhost:3457
"""

import http.server
import json
import os
import re
import socket
import sys
import time
import webbrowser
import urllib.parse
from datetime import datetime
from pathlib import Path

PORT = 3457
WORKFLOWS_DIR = Path(__file__).parent / "workflows"
AUTOMA_EXT_ID = "infppggnoaenmfagbfknfkancpbljcca"


# =============================================================================
# PUSH (default mode) — localhost server + CustomEvent, the Automa-native way
# =============================================================================

def _stamp_description(wf):
    """Append update timestamp to workflow description, replacing any previous stamp."""
    desc = wf.get("description", "")
    desc = re.sub(r'\s*\|\s*Pushed:.*$', '', desc)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    wf["description"] = (f"{desc} | Pushed: {now}").strip(" |")


def _open_in_chrome(url):
    """Open a URL in Chrome (supports chrome-extension:// URLs)."""
    import subprocess
    local = os.environ.get("LOCALAPPDATA", "")
    pf = os.environ.get("PROGRAMFILES", "")
    pf86 = os.environ.get("PROGRAMFILES(X86)", "")
    candidates = [
        os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            subprocess.Popen([p, url])
            return
    webbrowser.open(url)


def _find_port():
    """Find a free port, preferring PORT."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        if s.connect_ex(("127.0.0.1", PORT)) != 0:
            return PORT
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = s.getsockname()[1]
    print(f"  Port {PORT} busy, using {port}")
    return port


def push_files(files):
    """Serve a localhost page that pushes workflows via Automa's CustomEvent API."""
    # Load workflows and stamp descriptions
    workflows = []
    for f in files:
        src = Path(f)
        if not src.exists():
            print(f"  File not found: {f}")
            continue
        wf = json.loads(src.read_text(encoding="utf-8"))
        name = wf.get("name", src.name)
        _stamp_description(wf)
        src.write_text(json.dumps(wf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        workflows.append({"name": name, "data": wf})
        print(f"  {name}")

    if not workflows:
        print("No valid workflow files.")
        return

    # Embed workflow data directly in the HTML page — no API calls needed
    wf_json = json.dumps([w["data"] for w in workflows], ensure_ascii=False)
    wf_names = json.dumps([w["name"] for w in workflows], ensure_ascii=False)

    html = (
        '<!DOCTYPE html><html><head><title>Pushing...</title>'
        '<style>'
        'body{font-family:system-ui;max-width:600px;margin:40px auto;padding:0 20px;background:#1a1a2e;color:#eee}'
        'h2{color:#00d4aa}.log{background:#16213e;padding:16px;border-radius:8px;'
        'font-family:monospace;font-size:.9em;line-height:1.8}'
        '.ok{color:#00d4aa}.err{color:#e74c3c}.warn{color:#f39c12}'
        '.done{margin-top:20px;padding:16px;background:#0d2818;border:1px solid #00d4aa;'
        'border-radius:8px;text-align:center;color:#00d4aa;font-weight:600}'
        '</style></head><body>'
        '<h2 id="h">Pushing workflows...</h2>'
        '<div class="log" id="log"></div>'
        '<script>'
        'var W=' + wf_json + ';'
        'var N=' + wf_names + ';'
        'var log=document.getElementById("log");'
        'function msg(t,c){log.innerHTML+="<div class=\'"+(c||"")+"\'>"+t+"</div>";}'
        ''
        # Wait for Automa content script to initialize (checks document.body attribute)
        '(async function(){'
        'var atm=null;'
        'for(var w=0;w<20;w++){'
        'atm=document.body.getAttribute("data-atm-ext-installed");'
        'if(atm)break;'
        'await new Promise(function(r){setTimeout(r,250)});'
        '}'
        'if(!atm){'
        'msg("Automa extension not detected. Is it installed and enabled?","err");'
        'fetch("/done?status=no-automa").catch(function(){});return;'
        '}'
        'msg("Automa v"+atm+" detected","ok");'
        ''
        # Get existing workflows to check for duplicates
        'var existing=null;'
        'try{'
        'existing=await new Promise(function(resolve){'
        'var to=setTimeout(function(){resolve(null)},3000);'
        'window.addEventListener("__automa-ext__get-workflows",function(e){'
        'clearTimeout(to);resolve(e.detail);'
        '},{once:true});'
        'window.dispatchEvent(new CustomEvent("__automa-ext__",{'
        'detail:{type:"send-message",data:{type:"get-workflows"}}'
        '}));'
        '});'
        '}catch(e){}'
        'var existingNames={};'
        'if(existing){'
        'var wfList=Array.isArray(existing)?existing:Object.values(existing);'
        'for(var j=0;j<wfList.length;j++){if(wfList[j].name)existingNames[wfList[j].name]=true;}'
        '}'
        ''
        # Push each workflow via CustomEvent using add-workflow (built-in, no patching)
        # Note: add-workflow may navigate the page away, so signal /done BEFORE dispatch
        'var pushed=0;var skipped=0;'
        'for(var i=0;i<W.length;i++){'
        'if(existingNames[N[i]]){'
        'msg("Skipped: "+N[i]+" (already exists in Automa)","warn");'
        'skipped++;continue;'
        '}'
        'try{'
        # Signal done BEFORE dispatch since add-workflow may navigate away
        'if(i===W.length-1||true){'
        'navigator.sendBeacon("/done?status=ok&pushed="+(pushed+1)+"&skipped="+skipped);'
        '}'
        'window.dispatchEvent(new CustomEvent("__automa-ext__",{'
        'detail:{type:"add-workflow",data:{workflow:W[i]}}'
        '}));'
        'msg("Pushed: "+N[i],"ok");pushed++;'
        '}catch(e){msg("Failed: "+N[i]+" - "+e.message,"err");}'
        'await new Promise(function(r){setTimeout(r,500)});'
        '}'
        ''
        # If everything was skipped (no dispatch happened), page is still alive
        'if(pushed===0){'
        'document.getElementById("h").textContent="Push complete!";'
        'var d=document.createElement("div");d.className="done";'
        'd.textContent="No new workflows to push ("+skipped+" already exist).";'
        'document.body.appendChild(d);'
        'fetch("/done?status=ok&pushed=0&skipped="+skipped).catch(function(){});'
        '}'
        '})();'
        '</script></body></html>'
    )

    port = _find_port()

    done = [False]
    result_info = {"status": ""}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _handle_done(self):
            parsed = urllib.parse.urlparse(self.path)
            done[0] = True
            params = urllib.parse.parse_qs(parsed.query)
            result_info["status"] = params.get("status", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")

        def do_POST(self):
            # sendBeacon sends POST
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/done":
                self._handle_done()

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/done":
                self._handle_done()
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))

    server = http.server.HTTPServer(("", port), Handler)
    server.timeout = 2

    url = f"http://localhost:{port}/?t={int(time.time())}"
    print(f"  Server: localhost:{port}")
    webbrowser.open(url)

    deadline = time.time() + 30
    while time.time() < deadline and not done[0]:
        server.handle_request()

    server.server_close()

    if done[0]:
        status = result_info["status"]
        if status == "no-automa":
            print("Automa extension not detected. Is it installed and enabled?")
        elif status == "ok":
            print("Done!")
            automa_url = f"chrome-extension://{AUTOMA_EXT_ID}/newtab.html#/workflows"
            _open_in_chrome(automa_url)
            print("Opened Automa dashboard.")
        else:
            print("Done!")
    else:
        print("Timed out — check Automa dashboard manually.")


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
    .warn { color: #f39c12; }
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

    function checkAutomaPresent() {
      return document.body.getAttribute('data-atm-ext-installed') !== null;
    }

    function getAutomaWorkflows() {
      return new Promise((resolve) => {
        const timeout = setTimeout(() => resolve(null), 3000);
        window.addEventListener('__automa-ext__get-workflows', (e) => {
          clearTimeout(timeout);
          resolve(e.detail);
        }, { once: true });
        window.dispatchEvent(new CustomEvent('__automa-ext__', {
          detail: { type: 'send-message', data: { type: 'get-workflows' } }
        }));
      });
    }

    async function pushWorkflow(file) {
      const el = document.getElementById('status-' + file);
      el.className = 'status'; el.textContent = 'Checking Automa...';
      try {
        if (!checkAutomaPresent()) {
          el.className = 'status error';
          el.textContent = 'Automa not detected! Make sure the extension is enabled and refresh this page.';
          return;
        }

        const res = await fetch('/api/workflow/' + encodeURIComponent(file));
        const workflow = await res.json();

        el.textContent = 'Checking for duplicates...';
        const existing = await getAutomaWorkflows();
        if (existing) {
          const workflows = Array.isArray(existing) ? existing : Object.values(existing);
          const duplicate = workflows.find(w => w.name === workflow.name);
          if (duplicate) {
            el.className = 'status warn';
            el.textContent = 'Workflow "' + workflow.name + '" already exists in Automa. Delete it first to re-push.';
            return;
          }
        }

        el.textContent = 'Pushing to Automa...';
        window.dispatchEvent(new CustomEvent('__automa-ext__', {
          detail: { type: 'add-workflow', data: { workflow } }
        }));

        await new Promise(r => setTimeout(r, 2000));
        el.className = 'status success';
        el.textContent = 'Pushed successfully! Check Automa dashboard.';
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
# CLI
# =============================================================================

def main():
    args = sys.argv[1:]

    if not args:
        print(__doc__)
    elif args[0] in ("--help", "-h"):
        print(__doc__)
    elif args[0] == "--ui":
        run_server()
    else:
        push_files(args)


if __name__ == "__main__":
    main()
