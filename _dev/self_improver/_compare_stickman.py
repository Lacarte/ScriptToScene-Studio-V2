"""6-scene stickman comparison across 6 models."""

import requests
import json
import time
import base64
import os
from pathlib import Path

API_KEY = os.environ.get("WAVESPEED_API_KEY", "")
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

SCENES = [
    {"role": "hook", "prompt": "wide shot, a simple black stick figure standing alone on a white background, arms hanging down, looking at a disco ball hanging from above, minimalist stickman animation style, clean black lines on pure white, flat design, no shading, bold outlines, hand-drawn feel"},
    {"role": "buildup", "prompt": "medium shot, three stick figures laughing and pointing at the main stick figure, speech bubbles with scribbled laughter, simple black lines on white background, minimalist stickman animation, comic panel style, bold outlines"},
    {"role": "buildup", "prompt": "close-up, the stick figure alone in a room practicing dance moves, motion lines around arms and legs showing movement, simple black lines on white, stickman animation style, dynamic pose, action lines radiating outward"},
    {"role": "peak", "prompt": "wide shot, the stick figure on a stage doing an impossible breakdance move, body twisted into a spiral shape, crowd of small stick figures below with arms raised, spotlight effect drawn as simple lines, black lines on white background, stickman animation, maximum energy"},
    {"role": "transition", "prompt": "medium shot, the audience stick figures erupting with excitement, exclamation marks and stars floating above the crowd, the dancer stick figure in a victory pose center stage, simple black lines on white, stickman animation style, celebratory mood"},
    {"role": "cta", "prompt": "wide shot, the winning stick figure walking away with a golden circle trophy on his head like a halo, his shadow on the ground also dancing with its own moves, simple black lines on white background with golden accent, stickman animation style, triumphant ending"},
]

MODELS = {
    "minimax ($0.0035)": {
        "url": "https://api.wavespeed.ai/api/v3/minimax/image-01/text-to-image",
        "make_body": lambda p: {"prompt": p, "aspect_ratio": "9:16"},
    },
    "gpt-1-mini ($0.02)": {
        "url": "https://api.wavespeed.ai/api/v3/openai/gpt-image-1-mini/text-to-image",
        "make_body": lambda p: {"prompt": p, "aspect_ratio": "9:16"},
    },
    "gpt-1.5 ($0.02)": {
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
    "flux-current ($0.005)": {
        "url": "https://api.wavespeed.ai/api/v3/wavespeed-ai/flux-dev-lora-ultra-fast",
        "make_body": lambda p: {
            "prompt": p,
            "loras": [{"path": "strangerzonehf/Flux-Super-Realism-LoRA", "scale": 1}],
            "num_images": 1, "size": "576*1024", "output_format": "jpeg",
            "num_inference_steps": 28, "guidance_scale": 3.5,
        },
    },
}


def submit(url, body):
    resp = requests.post(url, headers=HEADERS, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", {}).get("id")


def poll_all(jobs, max_wait=500):
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
        print("ERROR: Set WAVESPEED_API_KEY")
        return

    # Submit all
    jobs = {}
    for mname, mcfg in MODELS.items():
        print(f"Submitting {mname}...")
        for i, scene in enumerate(SCENES):
            try:
                pid = submit(mcfg["url"], mcfg["make_body"](scene["prompt"]))
                if pid:
                    jobs[(mname, i)] = pid
            except Exception as e:
                print(f"  Scene {i}: {e}")
            time.sleep(0.3)
        count = sum(1 for k in jobs if k[0] == mname)
        print(f"  {count} submitted")

    print(f"\nPolling {len(jobs)} images...")
    results = poll_all(jobs)
    print(f"\nCompleted: {len(results)}/{len(jobs)}")

    # Build HTML
    mnames = list(MODELS.keys())
    rows = []
    for i, scene in enumerate(SCENES):
        cells = [
            f'<td class="si"><strong>Scene {i}</strong><br>'
            f'<span class="role">{scene["role"]}</span><br>'
            f'<span class="p">{scene["prompt"][:80]}...</span></td>'
        ]
        for mn in mnames:
            url = results.get((mn, i))
            if url:
                try:
                    cells.append(f'<td><img src="{dl_img(url)}"></td>')
                except Exception:
                    cells.append('<td class="no">DL fail</td>')
            else:
                cells.append('<td class="no">Failed</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")

    hdr = "<th>Scene</th>" + "".join(f"<th>{n}</th>" for n in mnames)

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Stickman Model Comparison</title>
<style>
body{{background:#0a0a0a;color:#ccc;font-family:system-ui;padding:24px}}
h1{{color:#4ECDC4;font-size:20px}}
h2{{color:#888;font-size:13px;font-weight:400;margin-bottom:20px}}
table{{border-collapse:collapse;width:100%}}
th,td{{padding:8px;text-align:center;border:1px solid #222;vertical-align:top}}
th{{background:#111;color:#4ECDC4;font-size:11px;position:sticky;top:0;z-index:1}}
img{{max-width:160px;max-height:280px;border-radius:6px;display:block;margin:0 auto}}
.si{{background:#0d0d0d;text-align:left;width:140px;font-size:11px;color:#888}}
.role{{color:#4ECDC4;font-weight:700;font-size:10px;text-transform:uppercase}}
.p{{font-size:9px;color:#555;line-height:1.3}}
.no{{color:#555;font-style:italic;font-size:11px}}
</style></head><body>
<h1>Stickman Style - 6-Scene Model Comparison</h1>
<h2>Same stickman story, 6 models including current Flux — which actually makes stick figures?</h2>
<table><tr>{hdr}</tr>{"".join(rows)}</table>
</body></html>"""

    out = Path(__file__).parent / "model-compare" / "stickman-6scene-compare.html"
    out.write_text(html, encoding="utf-8")
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
