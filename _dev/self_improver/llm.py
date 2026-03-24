"""LLM client for subjective scoring via OpenRouter (Gemini 2.5 Flash)."""

import json
import os
import re

import requests

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("STS_SCORER_MODEL", "google/gemini-2.5-flash")


def _strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers if present."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def call_llm(system_prompt: str, user_prompt: str) -> dict:
    """Call Gemini 2.5 Flash via OpenRouter. Returns parsed JSON dict."""
    global OPENROUTER_API_KEY, OPENROUTER_MODEL
    # Re-read from env in case dotenv loaded after module import
    if not OPENROUTER_API_KEY:
        OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
        OPENROUTER_MODEL = os.environ.get("STS_SCORER_MODEL", "google/gemini-2.5-flash")
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "No OPENROUTER_API_KEY set. Add it to .env or export it."
        )

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
        },
        timeout=120,
    )
    resp.raise_for_status()

    content = resp.json()["choices"][0]["message"]["content"]
    content = _strip_markdown_fences(content)
    return json.loads(content)


def call_llm_with_images(system_prompt: str, user_text: str, image_paths: list) -> dict:
    """Call Gemini 2.5 Flash with images (vision). Returns parsed JSON dict."""
    global OPENROUTER_API_KEY, OPENROUTER_MODEL
    if not OPENROUTER_API_KEY:
        OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
        OPENROUTER_MODEL = os.environ.get("STS_SCORER_MODEL", "google/gemini-2.5-flash")
    if not OPENROUTER_API_KEY:
        raise RuntimeError("No OPENROUTER_API_KEY set.")

    import base64

    # Build multimodal content array
    content_parts = [{"type": "text", "text": user_text}]
    for img_path in image_paths:
        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        ext = str(img_path).rsplit(".", 1)[-1].lower()
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(ext, "image/jpeg")
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_parts},
            ],
            "temperature": 0.3,
        },
        timeout=180,
    )
    resp.raise_for_status()

    text = resp.json()["choices"][0]["message"]["content"]
    text = _strip_markdown_fences(text)
    return json.loads(text)
