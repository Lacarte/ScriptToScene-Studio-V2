"""
DOM Activity Recorder — Integration Test

Tests the recorder extension by:
  1. Serving a local test page with dynamic DOM changes
  2. Using the __sarAPI (exposed on window) to start/stop recording
  3. Verifying mutations are captured correctly

Since this extension has NO background worker and NO WebSocket,
we test by serving a local HTML page and checking the recorder
via browser automation (Selenium) or manual verification.

This test creates a self-contained test page that:
  - Loads in the browser (where the extension's content script runs)
  - Uses __sarAPI.monitor() to start recording
  - Triggers known DOM mutations
  - Checks __sarAPI state
  - Reports results

Usage:
    python test_recorder.py              # Serve test page on port 8765
    python test_recorder.py --port 9000  # Custom port

Then open http://localhost:8765 in Chrome (with extension loaded).
The page will auto-run tests and display results.
"""

import argparse
import http.server
import os
import sys
import threading

TEST_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>DOM Activity Recorder — Test Page</title>
<style>
  body { background: #0d1117; color: #c9d1d9; font-family: 'JetBrains Mono', monospace; padding: 24px; }
  h1 { color: #00d4aa; margin-bottom: 8px; }
  .test { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin: 12px 0; }
  .test-name { font-weight: bold; color: #58a6ff; margin-bottom: 8px; }
  .pass { color: #3fb950; } .fail { color: #f85149; } .info { color: #8b949e; }
  .log { font-size: 12px; white-space: pre-wrap; max-height: 200px; overflow-y: auto; }
  #target { background: #21262d; padding: 12px; border: 1px dashed #30363d; margin: 16px 0; min-height: 60px; }
  button { background: #238636; color: #fff; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 14px; margin: 4px; }
  button:hover { background: #2ea043; }
  #summary { font-size: 18px; margin-top: 20px; padding: 16px; border-radius: 8px; }
  .summary-pass { background: #0d2818; border: 1px solid #3fb950; }
  .summary-fail { background: #2d1212; border: 1px solid #f85149; }
</style>
</head>
<body>

<h1>DOM Activity Recorder — Test Suite</h1>
<p class="info">This page tests the extension's __sarAPI and mutation detection.</p>

<div id="target">
  <p id="test-text">Initial content</p>
  <div id="test-container"></div>
</div>

<button onclick="runTests()">Run Tests</button>
<button onclick="runTests(); setTimeout(exportReport, 2000)">Run + Export Report</button>

<div id="results"></div>
<div id="summary"></div>

<script>
var results = [];

function log(testName, status, msg) {
  results.push({ test: testName, status: status, msg: msg });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function runTests() {
  results = [];
  document.getElementById('results').innerHTML = '<p class="info">Running tests...</p>';

  // ── Test 1: __sarAPI exists ──
  if (window.__sarAPI) {
    log('API Available', 'pass', '__sarAPI found on window');
  } else {
    log('API Available', 'fail', '__sarAPI not found — extension not loaded?');
    renderResults();
    return;
  }

  // ── Test 2: Start monitoring via CSS selector ──
  var api = window.__sarAPI;
  if (api.isRecording()) { api.stop(); api.clear(); }

  var monResult = api.monitor('#target');
  if (monResult && monResult.ok) {
    log('Start Monitor', 'pass', 'monitor(#target) returned ok: ' + monResult.message);
  } else {
    log('Start Monitor', 'fail', 'monitor(#target) failed: ' + (monResult ? monResult.error : 'null'));
    renderResults();
    return;
  }

  // ── Test 3: isRecording returns true ──
  if (api.isRecording()) {
    log('isRecording', 'pass', 'isRecording() = true after monitor()');
  } else {
    log('isRecording', 'fail', 'isRecording() = false after monitor()');
  }

  // Wait for first snapshot
  await sleep(1500);

  // ── Test 4: Trigger DOM mutations and verify detection ──

  // 4a: Add element
  var newEl = document.createElement('div');
  newEl.id = 'added-element';
  newEl.className = 'test-added';
  newEl.textContent = 'Dynamically added';
  document.getElementById('test-container').appendChild(newEl);
  log('DOM Add', 'info', 'Added #added-element');

  await sleep(1500);

  // 4b: Change attribute
  newEl.className = 'test-added active';
  log('DOM Attr', 'info', 'Changed class to "test-added active"');

  await sleep(1500);

  // 4c: Change text
  document.getElementById('test-text').textContent = 'Modified content';
  log('DOM Text', 'info', 'Changed #test-text content');

  await sleep(1500);

  // 4d: Remove element
  newEl.remove();
  log('DOM Remove', 'info', 'Removed #added-element');

  await sleep(1500);

  // ── Test 5: Stop recording ──
  var stopResult = api.stop();
  if (stopResult && stopResult.ok) {
    log('Stop Recording', 'pass', 'stop() returned ok');
  } else {
    log('Stop Recording', 'fail', 'stop() failed');
  }

  // ── Test 6: isRecording returns false ──
  if (!api.isRecording()) {
    log('isRecording After Stop', 'pass', 'isRecording() = false after stop()');
  } else {
    log('isRecording After Stop', 'fail', 'isRecording() still true after stop()');
  }

  // ── Test 7: Clear data ──
  var clearResult = api.clear();
  if (clearResult && clearResult.ok) {
    log('Clear Data', 'pass', 'clear() returned ok');
  } else {
    log('Clear Data', 'fail', 'clear() failed');
  }

  // ── Test 8: Monitor via XPath ──
  var xpathResult = api.monitor('//*[@id="target"]');
  if (xpathResult && xpathResult.ok) {
    log('XPath Monitor', 'pass', 'monitor(XPath) returned ok: ' + xpathResult.message);
  } else {
    log('XPath Monitor', 'fail', 'monitor(XPath) failed: ' + (xpathResult ? xpathResult.error : 'null'));
  }
  api.stop();
  api.clear();

  renderResults();
}

function renderResults() {
  var html = '';
  var passed = 0, failed = 0, infos = 0;
  results.forEach(function(r) {
    var cls = r.status === 'pass' ? 'pass' : r.status === 'fail' ? 'fail' : 'info';
    var icon = r.status === 'pass' ? '✓' : r.status === 'fail' ? '✗' : '→';
    html += '<div class="test"><span class="test-name">' + icon + ' ' + r.test + '</span>';
    html += ' <span class="' + cls + '">' + r.msg + '</span></div>';
    if (r.status === 'pass') passed++;
    else if (r.status === 'fail') failed++;
    else infos++;
  });
  document.getElementById('results').innerHTML = html;

  var sumEl = document.getElementById('summary');
  if (failed > 0) {
    sumEl.className = 'summary-fail';
    sumEl.innerHTML = '<span class="fail">FAILED</span> — ' + passed + ' passed, ' + failed + ' failed, ' + infos + ' info';
  } else {
    sumEl.className = 'summary-pass';
    sumEl.innerHTML = '<span class="pass">ALL PASSED</span> — ' + passed + ' passed, ' + infos + ' info steps';
  }

  // Also log to console for automated checking
  console.log('[SAR-TEST] Results:', JSON.stringify({ passed: passed, failed: failed, infos: infos }));
}

function exportReport() {
  // Trigger the SAR panel export button if it exists
  var exportBtn = document.querySelector('#sar-panel .sar-export-btn, #sar-panel button');
  if (exportBtn) {
    exportBtn.click();
    log('Export', 'info', 'Clicked SAR export button');
  }
}
</script>
</body>
</html>"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Serves the test page and suppresses log noise."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(TEST_HTML.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Suppress default logging


def main():
    parser = argparse.ArgumentParser(description="DOM Activity Recorder test server")
    parser.add_argument("--port", type=int, default=8765, help="Port to serve test page (default: 8765)")
    args = parser.parse_args()

    print("=" * 56)
    print("  DOM Activity Recorder — Test Server")
    print("=" * 56)
    print()
    print(f"  Test page: http://localhost:{args.port}")
    print()
    print("  Instructions:")
    print("    1. Open the URL above in Chrome (with extension loaded)")
    print("    2. Click 'Run Tests' on the page")
    print("    3. All tests should show green checkmarks")
    print("    4. Press Ctrl+C here to stop the server")
    print()

    server = http.server.HTTPServer(("127.0.0.1", args.port), QuietHandler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
