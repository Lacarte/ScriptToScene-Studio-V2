"""
STS DevTools — Python diagnostic & test runner.

Connects to the STS Flask API and ai-web-auto WebSocket to run
comprehensive diagnostics, smoke tests, and pipeline validation.

Usage:
    python sts_devtools.py                   # interactive mode
    python sts_devtools.py --test all        # run all module tests
    python sts_devtools.py --test tts,scenes # test specific modules
    python sts_devtools.py --diagnose        # full system diagnosis
    python sts_devtools.py --monitor         # live pipeline monitor
"""

import asyncio
import argparse
import json
import sys
import time
from pathlib import Path

import httpx
from loguru import logger

# Add ai-web-auto backend to path (external project)
_AWA_ROOT = Path(r"D:\@Workspace\@Development\@Projects\ai-web-auto")
if _AWA_ROOT.exists():
    sys.path.insert(0, str(_AWA_ROOT))
    from ai_web_auto_backend.core.server import WebSocketServer
    from ai_web_auto_backend.core.models import Command, ResponseStatus
    HAS_AWA = True
else:
    HAS_AWA = False

STS_BASE = "http://localhost:5050"

# ── STS API Client ──────────────────────────────────────────────────────────


class STSClient:
    """Thin wrapper around the STS Flask API."""

    def __init__(self, base_url: str = STS_BASE):
        self.base = base_url.rstrip("/")
        self.http = httpx.AsyncClient(base_url=self.base, timeout=30)

    async def get(self, path: str):
        r = await self.http.get(path)
        r.raise_for_status()
        return r.json() if "json" in r.headers.get("content-type", "") else r.text

    async def post(self, path: str, body: dict | None = None):
        r = await self.http.post(path, json=body)
        r.raise_for_status()
        return r.json() if "json" in r.headers.get("content-type", "") else r.text

    async def close(self):
        await self.http.aclose()


# ── Module Tests ────────────────────────────────────────────────────────────


class ModuleTester:
    """Run targeted tests on each STS module."""

    def __init__(self, client: STSClient):
        self.client = client
        self.results: list[dict] = []

    def _pass(self, module: str, name: str, data=None):
        self.results.append({"module": module, "name": name, "status": "pass", "data": data})
        logger.success(f"  ✓ {name}")

    def _fail(self, module: str, name: str, error: str):
        self.results.append({"module": module, "name": name, "status": "fail", "error": error})
        logger.error(f"  ✗ {name} — {error}")

    async def test_health(self):
        logger.info("Testing: health")
        try:
            h = await self.client.get("/api/health")
            self._pass("health", "API reachable", h)
            if h.get("tts"):
                self._pass("health", "TTS engine")
            else:
                self._fail("health", "TTS engine", "Not loaded")
            if h.get("alignment"):
                self._pass("health", "Alignment engine")
            else:
                self._fail("health", "Alignment engine", "Not loaded")
        except Exception as e:
            self._fail("health", "API reachable", str(e))

    async def test_tts(self):
        logger.info("Testing: tts")
        try:
            voices = await self.client.get("/api/tts/voices")
            count = len(voices) if isinstance(voices, list) else "?"
            self._pass("tts", f"Kokoro voices ({count})")
        except Exception as e:
            self._fail("tts", "Kokoro voices", str(e))

        try:
            iw = await self.client.get("/api/tts/voices?provider=inworld")
            count = len(iw) if isinstance(iw, list) else "?"
            self._pass("tts", f"Inworld voices ({count})")
        except Exception as e:
            self._fail("tts", "Inworld voices", str(e))

        try:
            models = await self.client.get("/api/tts/models")
            self._pass("tts", "Models endpoint", models)
        except Exception as e:
            self._fail("tts", "Models endpoint", str(e))

    async def test_scenes(self):
        logger.info("Testing: scenes")
        try:
            t = await self.client.get("/api/scenes/templates")
            count = len(t) if isinstance(t, list) else "?"
            self._pass("scenes", f"Templates ({count})")
        except Exception as e:
            self._fail("scenes", "Templates", str(e))

        try:
            wh = await self.client.get("/api/scenes/webhook-url")
            if wh:
                self._pass("scenes", "Webhook configured", wh)
            else:
                self._fail("scenes", "Webhook", "Not set")
        except Exception as e:
            self._fail("scenes", "Webhook", str(e))

    async def test_storyboard(self):
        logger.info("Testing: storyboard")
        try:
            m = await self.client.get("/api/storyboard/image-models")
            count = len(m) if isinstance(m, list) else "?"
            self._pass("storyboard", f"Image models ({count})")
        except Exception as e:
            self._fail("storyboard", "Image models", str(e))

        try:
            wh = await self.client.get("/api/storyboard/webhook-url")
            if wh:
                self._pass("storyboard", "Webhook configured", wh)
            else:
                self._fail("storyboard", "Webhook", "Not set")
        except Exception as e:
            self._fail("storyboard", "Webhook", str(e))

    async def test_pipeline(self):
        logger.info("Testing: pipeline")
        try:
            jobs = await self.client.get("/api/pipeline/jobs")
            count = len(jobs) if isinstance(jobs, list) else "?"
            self._pass("pipeline", f"Jobs endpoint ({count} jobs)")
        except Exception as e:
            self._fail("pipeline", "Jobs endpoint", str(e))

        try:
            pf = await self.client.post("/api/pipeline/preflight")
            self._pass("pipeline", "Preflight check", pf)
        except Exception as e:
            self._fail("pipeline", "Preflight check", str(e))

    async def test_niches(self):
        logger.info("Testing: niches")
        try:
            n = await self.client.get("/api/niches")
            count = len(n) if isinstance(n, dict) else "?"
            self._pass("niches", f"Presets loaded ({count})")
        except Exception as e:
            self._fail("niches", "Presets", str(e))

    async def test_music(self):
        logger.info("Testing: music")
        try:
            lib = await self.client.get("/api/music/library")
            count = len(lib) if isinstance(lib, list) else "?"
            self._pass("music", f"Library ({count} tracks)")
        except Exception as e:
            self._fail("music", "Library", str(e))

    async def test_story(self):
        logger.info("Testing: story")
        try:
            cats = await self.client.get("/api/story/categories")
            count = len(cats) if isinstance(cats, list) else "?"
            self._pass("story", f"Categories ({count})")
        except Exception as e:
            self._fail("story", "Categories", str(e))

        try:
            wh = await self.client.get("/api/story/webhook-url")
            if wh:
                self._pass("story", "Webhook configured", wh)
            else:
                self._fail("story", "Webhook", "Not set")
        except Exception as e:
            self._fail("story", "Webhook", str(e))

    async def run_all(self):
        for method in [self.test_health, self.test_tts, self.test_scenes,
                       self.test_storyboard, self.test_pipeline, self.test_niches,
                       self.test_music, self.test_story]:
            await method()
        return self.summary()

    async def run_modules(self, modules: list[str]):
        test_map = {
            "health": self.test_health, "tts": self.test_tts,
            "scenes": self.test_scenes, "storyboard": self.test_storyboard,
            "pipeline": self.test_pipeline, "niches": self.test_niches,
            "music": self.test_music, "story": self.test_story,
        }
        for m in modules:
            fn = test_map.get(m)
            if fn:
                await fn()
            else:
                logger.warning(f"Unknown module: {m}")
        return self.summary()

    def summary(self) -> dict:
        passed = sum(1 for r in self.results if r["status"] == "pass")
        failed = sum(1 for r in self.results if r["status"] == "fail")
        return {"total": len(self.results), "passed": passed, "failed": failed, "tests": self.results}


# ── System Diagnosis ────────────────────────────────────────────────────────


async def diagnose(client: STSClient):
    """Full system diagnosis — checks everything."""
    logger.info("=" * 60)
    logger.info("STS System Diagnosis")
    logger.info("=" * 60)

    # 1. API reachability
    logger.info("\n[1/5] API Connectivity")
    try:
        h = await client.get("/api/health")
        logger.success(f"  STS API: OK — {json.dumps(h)}")
    except Exception as e:
        logger.error(f"  STS API: UNREACHABLE — {e}")
        logger.error("  Cannot continue diagnosis. Is STS running?")
        return

    # 2. All module tests
    logger.info("\n[2/5] Module Tests")
    tester = ModuleTester(client)
    summary = await tester.run_all()
    logger.info(f"\n  Results: {summary['passed']} pass, {summary['failed']} fail")

    # 3. Project inventory
    logger.info("\n[3/5] Project Inventory")
    try:
        projects = await client.get("/api/projects")
        if isinstance(projects, list):
            logger.info(f"  {len(projects)} projects found")
            for p in projects[:5]:
                pid = p.get("project_id", p.get("id", "?"))
                logger.info(f"    {pid}")
        else:
            logger.info(f"  Projects response: {type(projects)}")
    except Exception as e:
        logger.warning(f"  Projects: {e}")

    # 4. Pipeline job history
    logger.info("\n[4/5] Pipeline Jobs")
    try:
        jobs = await client.get("/api/pipeline/jobs")
        if isinstance(jobs, list):
            logger.info(f"  {len(jobs)} jobs in history")
            for j in jobs[:5]:
                jid = j.get("job_id", j.get("id", "?"))
                status = j.get("status", "?")
                logger.info(f"    {jid} — {status}")
    except Exception as e:
        logger.warning(f"  Jobs: {e}")

    # 5. Extension connectivity
    logger.info("\n[5/5] Extension Preflight")
    try:
        pf = await client.post("/api/pipeline/preflight")
        logger.info(f"  Preflight: {json.dumps(pf)}")
    except Exception as e:
        logger.warning(f"  Preflight: {e}")

    logger.info("\n" + "=" * 60)
    logger.info("Diagnosis complete")
    logger.info("=" * 60)


# ── Pipeline Monitor ────────────────────────────────────────────────────────


async def monitor_pipeline(client: STSClient):
    """Live pipeline monitor — polls job status."""
    logger.info("Pipeline Monitor — watching for active jobs (Ctrl+C to stop)")

    while True:
        try:
            jobs = await client.get("/api/pipeline/jobs")
            if isinstance(jobs, list):
                active = [j for j in jobs if j.get("status") in ("running", "pending")]
                if active:
                    for j in active:
                        jid = j.get("job_id", "?")
                        step = j.get("current_step", "?")
                        status = j.get("status", "?")
                        logger.info(f"  [{jid}] Step: {step} | Status: {status}")
                else:
                    logger.debug("  No active jobs")
        except Exception as e:
            logger.warning(f"  Poll error: {e}")
        await asyncio.sleep(3)


# ── Interactive CLI ─────────────────────────────────────────────────────────


async def interactive(client: STSClient):
    """Interactive command mode."""
    print("\n=== STS DevTools ===")
    print("Commands:")
    print("  test <module>    — Test a module (health, tts, scenes, storyboard, pipeline, niches, music, story)")
    print("  test all         — Run all tests")
    print("  diagnose         — Full system diagnosis")
    print("  monitor          — Live pipeline monitor")
    print("  projects         — List projects")
    print("  jobs             — List pipeline jobs")
    print("  api GET /path    — Call any STS API")
    print("  quit             — Exit\n")

    loop = asyncio.get_event_loop()
    while True:
        raw = await loop.run_in_executor(None, input, "sts> ")
        cmd = raw.strip()
        if not cmd:
            continue
        if cmd in ("quit", "exit", "q"):
            break

        if cmd == "test all":
            tester = ModuleTester(client)
            s = await tester.run_all()
            print(f"\n  {s['passed']} pass, {s['failed']} fail\n")
            continue

        if cmd.startswith("test "):
            modules = [m.strip() for m in cmd[5:].split(",")]
            tester = ModuleTester(client)
            s = await tester.run_modules(modules)
            print(f"\n  {s['passed']} pass, {s['failed']} fail\n")
            continue

        if cmd == "diagnose":
            await diagnose(client)
            continue

        if cmd == "monitor":
            try:
                await monitor_pipeline(client)
            except KeyboardInterrupt:
                print("\n  Stopped")
            continue

        if cmd == "projects":
            try:
                p = await client.get("/api/projects")
                print(json.dumps(p, indent=2) if isinstance(p, list) else str(p))
            except Exception as e:
                print(f"  Error: {e}")
            continue

        if cmd == "jobs":
            try:
                j = await client.get("/api/pipeline/jobs")
                print(json.dumps(j, indent=2) if isinstance(j, list) else str(j))
            except Exception as e:
                print(f"  Error: {e}")
            continue

        if cmd.startswith("api "):
            parts = cmd[4:].strip().split(" ", 1)
            method = parts[0].upper()
            path = parts[1] if len(parts) > 1 else "/"
            try:
                if method == "GET":
                    r = await client.get(path)
                elif method == "POST":
                    r = await client.post(path)
                else:
                    print(f"  Unsupported method: {method}")
                    continue
                print(json.dumps(r, indent=2) if isinstance(r, (dict, list)) else str(r))
            except Exception as e:
                print(f"  Error: {e}")
            continue

        print(f"  Unknown command: {cmd}")

    await client.close()


# ── Entry Point ─────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="STS DevTools — diagnostic & test runner")
    parser.add_argument("--test", help="Run module tests (comma-separated or 'all')")
    parser.add_argument("--diagnose", action="store_true", help="Full system diagnosis")
    parser.add_argument("--monitor", action="store_true", help="Live pipeline monitor")
    parser.add_argument("--base", default=STS_BASE, help=f"STS base URL (default: {STS_BASE})")
    args = parser.parse_args()

    client = STSClient(args.base)

    if args.test:
        tester = ModuleTester(client)
        if args.test == "all":
            s = await tester.run_all()
        else:
            s = await tester.run_modules([m.strip() for m in args.test.split(",")])
        print(f"\n{'=' * 40}")
        print(f"Total: {s['passed']} pass, {s['failed']} fail")
        print(f"{'=' * 40}")
        await client.close()
        sys.exit(1 if s["failed"] > 0 else 0)

    elif args.diagnose:
        await diagnose(client)
        await client.close()

    elif args.monitor:
        try:
            await monitor_pipeline(client)
        except KeyboardInterrupt:
            pass
        await client.close()

    else:
        await interactive(client)


if __name__ == "__main__":
    asyncio.run(main())
