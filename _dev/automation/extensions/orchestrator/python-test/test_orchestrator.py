"""
STS Orchestrator — Integration Test Suite

Tests all orchestrator capabilities via WebSocket:
  1. Ping — verify extension is alive
  2. List Tabs — enumerate all browser tabs
  3. Focus by Name — find and activate gemini/grok tabs
  4. Screenshot — capture any tab by name or ID
  5. Diagnose — full system health report

Usage:
    python test_orchestrator.py              # Run all tests
    python test_orchestrator.py --test ping  # Run single test
    python test_orchestrator.py --port 5050  # Custom port
"""

import argparse
import json
import os
import sys
import time

from orch_client import OrchClient, PASS, FAIL, INFO, WARN


def log(tag, msg):
    ts = time.strftime("%H:%M:%S")
    print(f"  [{ts}] [{tag}] {msg}")


# ── Test 1: Ping ─────────────────────────────────────

def test_ping(orch):
    print("\n-- Test 1: Ping --")
    if orch.ping():
        log(PASS, "Orchestrator responded to ping")
        return True
    else:
        log(FAIL, "No pong received")
        return False


# ── Test 2: List Tabs ────────────────────────────────

def test_list_tabs(orch):
    print("\n-- Test 2: List Tabs --")
    tabs = orch.list_tabs()
    if tabs is None:
        log(FAIL, "No response from list_tabs")
        return False

    log(PASS, f"Got {len(tabs)} tabs")

    # Show STS-relevant tabs
    sts_tabs = [t for t in tabs if any(k in (t.get("url") or "").lower()
                for k in ["gemini.google", "grok.com", "localhost", "scripttoscene"])]
    for t in sts_tabs:
        active = " (ACTIVE)" if t.get("active") else ""
        log(INFO, f"  [{t['id']}] {t.get('title', '?')[:50]}{active}")

    if not sts_tabs:
        log(INFO, "  No STS-relevant tabs found")

    return True


# ── Test 3: Focus by Name ───────────────────────────

def test_focus(orch):
    print("\n-- Test 3: Focus by Name --")
    ok = True

    # Try focusing known tabs
    for name in ["gemini", "grok"]:
        result = orch.focus_by_name(name)
        if result and result.get("ok"):
            log(PASS, f"Focused {name} tab (id={result.get('tabId')})")
        elif result and result.get("error"):
            log(WARN, f"Could not focus {name}: {result['error']}")
        else:
            log(WARN, f"No response for focus_by_name({name})")

    # Focus studio tab
    result = orch.focus_by_name("localhost")
    if result and result.get("ok"):
        log(PASS, f"Focused Studio tab")
    else:
        log(INFO, "Studio tab not found (may not be open)")

    return ok


# ── Test 4: Screenshot ──────────────────────────────

def test_screenshot(orch):
    print("\n-- Test 4: Screenshot --")
    ok = True
    captured = 0

    for name in ["gemini", "grok"]:
        path = orch.screenshot(name=name, label=f"test-{name}")
        if path:
            log(PASS, f"Captured {name} screenshot")
            captured += 1
        else:
            log(WARN, f"Could not screenshot {name} (tab may not be open)")

    if captured == 0:
        log(WARN, "No screenshots captured — open Gemini/Grok tabs and retry")

    return captured > 0


# ── Test 5: Diagnose ────────────────────────────────

def test_diagnose(orch):
    print("\n-- Test 5: Diagnose --")
    report = orch.diagnose()
    if not report or report.get("type") != "diagnose_report":
        log(FAIL, "No diagnose_report received")
        return False

    log(PASS, f"Diagnose report received (ts={report.get('ts')})")

    # Orchestrator status
    o = report.get("orchestrator", {})
    log(INFO, f"  Orchestrator WS: {'connected' if o.get('wsConnected') else 'DISCONNECTED'}")

    # Extension tabs
    extensions = report.get("extensions", {})
    for name, ext in extensions.items():
        count = ext.get("tabsOpen", 0)
        status = f"{count} tab(s) open" if count > 0 else "not open"
        log(INFO, f"  {name}: {status}")
        for t in ext.get("tabs", []):
            active = " (ACTIVE)" if t.get("active") else ""
            log(INFO, f"    [{t['id']}] {t.get('title', '?')[:40]}{active}")

    # Total tabs
    all_tabs = report.get("tabs", [])
    log(INFO, f"  Total browser tabs: {len(all_tabs)}")

    # Save report
    save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diag-output")
    os.makedirs(save_dir, exist_ok=True)
    # Strip screenshot data before saving
    json_path = os.path.join(save_dir, f"diag-{time.strftime('%Y%m%d-%H%M%S')}.json")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)
    log(INFO, f"  Report saved: {json_path}")

    return True


# ── Main ────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="STS Orchestrator Integration Tests")
    parser.add_argument("--test", choices=["ping", "tabs", "focus", "screenshot", "diagnose"],
                        help="Run single test")
    parser.add_argument("--port", type=int, default=None, help="Flask port (auto-discovers if omitted)")
    args = parser.parse_args()

    print("=" * 56)
    print("  STS Orchestrator — Integration Test Suite")
    print("=" * 56)

    try:
        orch = OrchClient(port=args.port)
        log(PASS, f"Connected to orchestrator WS")
    except Exception as e:
        log(FAIL, f"Could not connect: {e}")
        sys.exit(1)

    tests = {
        "ping": ("Ping", test_ping),
        "tabs": ("List Tabs", test_list_tabs),
        "focus": ("Focus by Name", test_focus),
        "screenshot": ("Screenshot", test_screenshot),
        "diagnose": ("Diagnose", test_diagnose),
    }

    if args.test:
        name, fn = tests[args.test]
        fn(orch)
    else:
        results = {}
        for key, (name, fn) in tests.items():
            results[key] = fn(orch)
            time.sleep(0.5)

        # Summary
        print("\n" + "=" * 56)
        print("  Results")
        print("=" * 56)
        all_passed = True
        for key, (name, _) in tests.items():
            status = PASS if results.get(key) else FAIL
            print(f"  [{status}] {name}")
            if not results.get(key):
                all_passed = False

        print()
        if all_passed:
            print("  All tests passed.")
        else:
            print("  Some tests failed — check output above.")

    orch.close()


if __name__ == "__main__":
    main()
