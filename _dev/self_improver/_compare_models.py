"""Generate 6-scene storyboard across 5 models for side-by-side comparison."""

import requests
import json
import time
import base64
import os
from pathlib import Path

API_KEY = os.environ.get("WAVESPEED_API_KEY", "")
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

SCENES = [
    {"role": "hook", "prompt": "extreme close-up, a single match being struck in complete darkness, the flame illuminating a weathered old hand holding it, warm orange glow against pitch black, cinematic dramatic lighting, photorealistic, shallow depth of field"},
    {"role": "buildup", "prompt": "wide shot, an abandoned Victorian library at night, thousands of dusty books on towering shelves, a single candle flickering on a desk, moonlight streaming through broken stained glass windows, dark moody atmosphere, cinematic composition"},
    {"role": "buildup", "prompt": "medium shot, an old woman sitting alone at the desk writing furiously in a leather journal, surrounded by stacks of handwritten letters, warm candlelight on her face, determined expression, cinematic portrait lighting"},
    {"role": "peak", "prompt": "bird-eye view, hundreds of paper airplanes made from the letters flying out of the library windows into a starlit night sky, magical realism, glowing paper trails against dark blue sky, cinematic wide angle, breathtaking scale"},
    {"role": "transition", "prompt": "close-up, a young girl in a modern city catching one of the paper airplanes, her face lit with wonder and curiosity, golden hour sunlight, urban background softly blurred, cinematic shallow depth of field, emotional moment"},
    {"role": "cta", "prompt": "wide shot, the young girl and the old woman sitting together in the restored library now filled with light and flowers, both reading from the same journal, warm golden afternoon light, hopeful atmosphere, cinematic composition, symmetrical framing"},
]

MODELS = {
    "minimax-01 ($0.0035)": {
        "url": "https://api.wavespeed.ai/api/v3/minimax/image-01/text-to-image",
        "make_body": lambda p: {"prompt": p, "aspect_ratio": "9:16"},
    },
    "gpt-image-1-mini ($0.02)": {
        "url": "https://api.wavespeed.ai/api/v3/openai/gpt-image-1-mini/text-to-image",
        "make_body": lambda p: {"prompt": p, "aspect_ratio": "9:16"},
    },
    "gpt-image-1.5 ($0.02)": {
        "url": "https://api.wavespeed.ai/api/v3/openai/gpt-image-1.5/text-to-image",
        "make_body": lambda p: {"prompt": p, "aspect_ratio": "9:16"},
    },
    "lucid-origin ($0.02)": {
        "url": "https://api.wavespeed.ai/api/v3/leonardoai/lucid-origin",
        "make_body": lambda p: {"prompt": p, "num_images": 1, "width": 576, "height": 1024},
    },
    "reve ($0.025)": {
        "url": "https://api.wavespeed.ai/api/v3/reve/text-to-image",
        "make_body": lambda p: {"prompt": p, "aspect_ratio": "9:16"},
    },
}


def submit(url, body):
    resp = requests.post(url, headers=HEADERS, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", {}).get("id")


def poll_all(jobs, max_wait=400):
    results = {}
    pending = dict(jobs)
    deadline = time.time() + max_wait
    while pending and time.time() < deadline:
        time.sleep(5)
        done = []
        for key, pid in list(pending.items()):
            try:
                r = requests.get(
                    f"https://api.wavespeed.ai/api/v3/predictions/{pid}/result",
                    headers=HEADERS, timeout=10,
                )
                rd = r.json()
                status = rd.get("data", {}).get("status", "")
                if status == "completed":
                    outputs = rd.get("data", {}).get("outputs", [])
                    if outputs:
                        results[key] = outputs[0]
                    done.append(key)
                elif status in ("failed", "error"):
                    done.append(key)
            except Exception:
                pass
        for k in done:
            del pending[k]
        if done:
            print(f"  {len(results)}/{len(jobs)} done, {len(pending)} pending...")
    return results


def dl_img(url):
    r = requests.get(url, timeout=30)
    ext = url.rsplit(".", 1)[-1].split("?")[0][:4]
    mime = {"jpeg": "image/jpeg", "jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "image/png")
    return f"data:{mime};base64,{base64.b64encode(r.content).decode()}"


def main():
    if not API_KEY:
        print("ERROR: Set WAVESPEED_API_KEY env var")
        return

    # Submit all jobs
    jobs = {}
    for mname, mcfg in MODELS.items():
        print(f"Submitting {mname}...")
        for i, scene in enumerate(SCENES):
            try:
                pid = submit(mcfg["url"], mcfg["make_body"](scene["prompt"]))
                if pid:
                    jobs[(mname, i)] = pid
                    print(f"  Scene {i}: submitted")
                else:
                    print(f"  Scene {i}: no prediction ID")
            except Exception as e:
                print(f"  Scene {i}: {e}")
            time.sleep(0.3)

    print(f"\nWaiting for {len(jobs)} images...")
    results = poll_all(jobs)
    print(f"\nCompleted: {len(results)}/{len(jobs)} images")

    # Build HTML
    model_names = list(MODELS.keys())
    rows = []
    for i, scene in enumerate(SCENES):
        cells = [
            f'<td class="si"><strong>Scene {i}</strong><br>'
            f'<span class="role">{scene["role"]}</span><br>'
            f'<span class="p">{scene["prompt"][:90]}...</span></td>'
        ]
        for mname in model_names:
            url = results.get((mname, i))
            if url:
                try:
                    uri = dl_img(url)
                    cells.append(f'<td><img src="{uri}"></td>')
                except Exception:
                    cells.append('<td class="no">Download failed</td>')
            else:
                cells.append('<td class="no">Failed</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")

    header = "<th>Scene</th>" + "".join(f"<th>{n}</th>" for n in model_names)

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>6-Scene Model Comparison</title>
<style>
body{{background:#0a0a0a;color:#ccc;font-family:system-ui;padding:24px}}
h1{{color:#4ECDC4;font-size:20px}}
h2{{color:#888;font-size:13px;font-weight:400;margin-bottom:20px}}
table{{border-collapse:collapse;width:100%}}
th,td{{padding:8px;text-align:center;border:1px solid #222;vertical-align:top}}
th{{background:#111;color:#4ECDC4;font-size:11px;position:sticky;top:0;z-index:1}}
img{{max-width:180px;max-height:320px;border-radius:6px;display:block;margin:0 auto}}
.si{{background:#0d0d0d;text-align:left;width:160px;font-size:11px;color:#888}}
.role{{color:#4ECDC4;font-weight:700;font-size:10px;text-transform:uppercase}}
.p{{font-size:9px;color:#555;line-height:1.3}}
.no{{color:#555;font-style:italic;font-size:11px}}
</style></head><body>
<h1>6-Scene Storyboard - Model Comparison</h1>
<h2>Same cinematic story, 5 models, 6 scenes each (30 images total)</h2>
<table><tr>{header}</tr>{"".join(rows)}</table>
</body></html>"""

    out = Path(__file__).parent / "model-6scene-compare.html"
    out.write_text(html, encoding="utf-8")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
