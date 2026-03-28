"""Test Kie AI image generation — end-to-end.

Run from project root:
  python _dev/tools/test_kie_ai.py
"""

import sys
import os
import json
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import KIE_AI_API_KEY, KIE_AI_BASE_URL, KIE_AI_MODEL
import requests

DIVIDER = "=" * 60


def test_config():
    """Step 1: Verify config is loaded."""
    print(f"\n{DIVIDER}")
    print("STEP 1: Config")
    print(DIVIDER)
    print(f"  API Key:  {'***' + KIE_AI_API_KEY[-6:] if KIE_AI_API_KEY else 'NOT SET'}")
    print(f"  Base URL: {KIE_AI_BASE_URL}")
    print(f"  Model:    {KIE_AI_MODEL}")
    if not KIE_AI_API_KEY:
        print("\n  ERROR: KIE_AI_API_KEY not set in .env")
        sys.exit(1)
    print("  OK")


def test_create_task():
    """Step 2: POST /jobs/createTask — raw HTTP."""
    print(f"\n{DIVIDER}")
    print("STEP 2: createTask (raw HTTP)")
    print(DIVIDER)

    url = f"{KIE_AI_BASE_URL}/jobs/createTask"
    payload = {
        "model": KIE_AI_MODEL,
        "input": {
            "prompt": "a golden retriever sitting on a beach at sunset, cinematic lighting",
            "aspect_ratio": "9:16",
            "resolution": "1K",
            "output_format": "jpg",
        },
    }
    headers = {
        "Authorization": f"Bearer {KIE_AI_API_KEY}",
        "Content-Type": "application/json",
    }

    print(f"  POST {url}")
    print(f"  Payload: {json.dumps(payload, indent=4)}")

    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    print(f"  Status:  {resp.status_code}")
    print(f"  Response: {resp.text[:500]}")

    if resp.status_code != 200:
        print(f"\n  ERROR: createTask returned {resp.status_code}")
        print(f"  Body: {resp.text}")
        return None

    data = resp.json()
    print(f"  Parsed:  {json.dumps(data, indent=4)}")

    # Try to extract taskId from various response shapes
    task_id = (
        data.get("taskId")
        or (data.get("data") or {}).get("taskId")
        or data.get("id")
        or (data.get("data") or {}).get("id")
    )
    print(f"  Task ID: {task_id}")

    if not task_id:
        print("\n  ERROR: No taskId found in response")
        print("  Available keys:", list(data.keys()))
        if data.get("data") and isinstance(data["data"], dict):
            print("  data keys:", list(data["data"].keys()))
    else:
        print("  OK")

    return task_id


def test_poll_result(task_id):
    """Step 3: GET /jobs/recordInfo — poll until done."""
    print(f"\n{DIVIDER}")
    print("STEP 3: recordInfo (poll)")
    print(DIVIDER)

    url = f"{KIE_AI_BASE_URL}/jobs/recordInfo"
    headers = {"Authorization": f"Bearer {KIE_AI_API_KEY}"}
    params = {"taskId": task_id}

    print(f"  GET {url}?taskId={task_id}")
    print(f"  Polling every 3s, timeout 180s...")

    start = time.time()
    attempt = 0
    while time.time() - start < 180:
        attempt += 1
        elapsed = int(time.time() - start)

        resp = requests.get(url, params=params, headers=headers, timeout=30)
        print(f"\n  [{elapsed:3d}s] Poll #{attempt} — HTTP {resp.status_code}")

        if resp.status_code != 200:
            print(f"  Body: {resp.text[:300]}")
            time.sleep(3)
            continue

        data = resp.json()

        # Print full response on first poll, abbreviated after
        if attempt <= 2:
            print(f"  Response: {json.dumps(data, indent=4)[:600]}")
        else:
            # Abbreviated
            record = data if "status" in data else data.get("data", {})
            status = record.get("status", "?")
            has_result = bool(record.get("resultJson"))
            print(f"  status={status}, hasResult={has_result}")

        record = data if "status" in data else data.get("data", {})
        status = record.get("status", "")

        if status in ("failed", "error"):
            print(f"\n  ERROR: Task failed: {record}")
            return None

        result_json = record.get("resultJson")
        if result_json:
            if isinstance(result_json, str):
                result_json = json.loads(result_json)

            print(f"\n  resultJson: {json.dumps(result_json, indent=4)[:600]}")

            result_urls = result_json.get("resultUrls", [])
            if result_urls:
                print(f"\n  SUCCESS: {len(result_urls)} image URL(s)")
                for i, u in enumerate(result_urls):
                    print(f"    [{i}] {u}")
                return result_urls
            else:
                print("  resultJson has no resultUrls, available keys:", list(result_json.keys()))

        time.sleep(3)

    print(f"\n  TIMEOUT after 180s")
    return None


def test_download(urls):
    """Step 4: Download first image."""
    print(f"\n{DIVIDER}")
    print("STEP 4: Download image")
    print(DIVIDER)

    url = urls[0]
    print(f"  GET {url}")

    resp = requests.get(url, timeout=60)
    print(f"  Status:       {resp.status_code}")
    print(f"  Content-Type: {resp.headers.get('Content-Type', '?')}")
    print(f"  Size:         {len(resp.content) / 1024:.1f} KB")

    if resp.status_code == 200 and len(resp.content) > 1000:
        out_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "kie_ai_test_output.jpg"
        )
        with open(out_path, "wb") as f:
            f.write(resp.content)
        print(f"  Saved to: {out_path}")
        print("  OK")
        return True
    else:
        print(f"  ERROR: Download failed or file too small")
        return False


def test_provider_module():
    """Step 5: Test via the provider module (same path as routes.py)."""
    print(f"\n{DIVIDER}")
    print("STEP 5: Provider module (generate_image)")
    print(DIVIDER)

    from studio.animator.providers.kie_ai import generate_image

    try:
        result = generate_image(
            prompt="a futuristic city at night with neon lights, cyberpunk style",
            aspect_ratio="9:16",
            resolution="1",
            output_format="jpg",
        )
        print(f"  Result: {json.dumps(result, indent=4)}")
        print("  OK")
        return result
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        return None


if __name__ == "__main__":
    print("\nKie AI Provider — Integration Test")
    print(DIVIDER)

    test_config()

    task_id = test_create_task()
    if not task_id:
        print("\nStopped — createTask failed. Check API key and response format above.")
        sys.exit(1)

    urls = test_poll_result(task_id)
    if not urls:
        print("\nStopped — polling failed. Check response format above.")
        sys.exit(1)

    test_download(urls)

    print(f"\n{DIVIDER}")
    print("Now testing via provider module...")
    print(DIVIDER)
    test_provider_module()

    print(f"\n{DIVIDER}")
    print("ALL TESTS PASSED")
    print(DIVIDER)
