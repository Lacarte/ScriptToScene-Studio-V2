"""Pipeline Runner & Output Collector.

Runs the STS pipeline via HTTP API and collects all outputs into a structured snapshot.
Can also load snapshots from existing projects without running the pipeline.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

from .config import (
    PIPELINE_RUN_URL, PIPELINE_PROGRESS_URL,
    TTS_DIR, ALIGN_DIR, SEGMENT_DIR, SCENES_DIR,
    STORYBOARD_DIR, PIPELINE_DIR,
    POLL_INTERVAL_SECONDS, PIPELINE_TIMEOUT_SECONDS,
)


@dataclass
class PipelineSnapshot:
    """All outputs from a single pipeline run, collected from disk."""
    project_id: str
    config: dict = field(default_factory=dict)
    tts: dict = field(default_factory=dict)
    alignment: dict = field(default_factory=dict)
    segments: dict = field(default_factory=dict)
    scenes: dict = field(default_factory=dict)
    storyboard: dict = field(default_factory=dict)
    pipeline: dict = field(default_factory=dict)
    error: Optional[str] = None


def run_pipeline(
    text: str,
    *,
    voice: str = "af_heart",
    speed: float = 1.0,
    style: str = "cinematic",
    stop_after: str = "storyboard",
    niche_preset: Optional[str] = None,
    segment_config: Optional[dict] = None,
    custom_style_notes: Optional[str] = None,
    extra_config: Optional[dict] = None,
) -> tuple:
    """POST /api/pipeline/run. Returns (job_id, project_id)."""
    payload = {
        "text": text,
        "voice": voice,
        "speed": speed,
        "style": style,
        "stop_after": stop_after,
        "auto_scenes": True,
        "auto_storyboard": True,
    }
    if niche_preset:
        payload["niche_preset"] = niche_preset
    if segment_config:
        payload["segment_config"] = segment_config
    if custom_style_notes:
        payload["custom_style_notes"] = custom_style_notes
    if extra_config:
        payload.update(extra_config)

    resp = requests.post(PIPELINE_RUN_URL, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["job_id"], data["project_id"]


def run_pipeline_resume(
    project_id: str,
    resume_from: str,
    *,
    text: str = "",
    voice: str = "af_heart",
    speed: float = 1.0,
    style: str = "cinematic",
    stop_after: str = "storyboard",
    niche_preset: Optional[str] = None,
    segment_config: Optional[dict] = None,
    custom_style_notes: Optional[str] = None,
    extra_config: Optional[dict] = None,
) -> tuple:
    """POST /api/pipeline/run with resume_from. Returns (job_id, new_project_id)."""
    # Load text from existing pipeline config if not provided
    if not text:
        snap = collect_snapshot(project_id)
        text = snap.config.get("text", "")
        if not voice or voice == "af_heart":
            voice = snap.config.get("voice", voice)
        if speed == 1.0:
            speed = snap.config.get("speed", speed)
        if style == "cinematic":
            style = snap.config.get("style", style)

    payload = {
        "text": text,
        "voice": voice,
        "speed": speed,
        "style": style,
        "stop_after": stop_after,
        "auto_scenes": True,
        "auto_storyboard": True,
        "resume_from": resume_from,
        "resume_project_id": project_id,
    }
    if niche_preset:
        payload["niche_preset"] = niche_preset
    if segment_config:
        payload["segment_config"] = segment_config
    if custom_style_notes:
        payload["custom_style_notes"] = custom_style_notes
    if extra_config:
        payload.update(extra_config)

    resp = requests.post(PIPELINE_RUN_URL, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["job_id"], data["project_id"]


def wait_for_completion(job_id: str) -> str:
    """Poll SSE stream until terminal event. Returns 'done', 'error', or 'stopped'."""
    url = f"{PIPELINE_PROGRESS_URL}/{job_id}"
    deadline = time.time() + PIPELINE_TIMEOUT_SECONDS

    with requests.get(url, stream=True, timeout=PIPELINE_TIMEOUT_SECONDS) as resp:
        resp.raise_for_status()
        buffer = ""
        for chunk in resp.iter_content(chunk_size=256, decode_unicode=True):
            if time.time() > deadline:
                raise TimeoutError(f"Pipeline did not complete within {PIPELINE_TIMEOUT_SECONDS}s")

            buffer += chunk
            while "\n\n" in buffer:
                raw_event, buffer = buffer.split("\n\n", 1)
                for line in raw_event.strip().split("\n"):
                    if line.startswith("data: "):
                        try:
                            event = json.loads(line[6:])
                        except json.JSONDecodeError:
                            continue
                        step = event.get("step", "")
                        status = event.get("status", "")
                        msg = event.get("message", "")
                        print(f"    [{step}] {status}{': ' + msg if msg else ''}")
                        if step in ("done", "error", "stopped"):
                            return step

    return "error"


def collect_snapshot(project_id: str) -> PipelineSnapshot:
    """Read all pipeline outputs from disk into a PipelineSnapshot. Instant, no pipeline run."""
    snap = PipelineSnapshot(project_id=project_id)

    def _load(dir_path: Path, filename: str) -> dict:
        path = dir_path / project_id / filename
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    snap.tts = _load(TTS_DIR, "tts.json")
    snap.alignment = _load(ALIGN_DIR, "alignment.json")
    snap.segments = _load(SEGMENT_DIR, "segmented.json")
    snap.scenes = _load(SCENES_DIR, "scenes.json")
    snap.storyboard = _load(STORYBOARD_DIR, "storyboard.json")
    snap.pipeline = _load(PIPELINE_DIR, "pipeline.json")
    snap.config = snap.pipeline.get("config", {})

    return snap


def run_and_collect(text: str, *, retry_on_error: bool = True, **kwargs) -> PipelineSnapshot:
    """Run pipeline, wait, collect. Retries once on error."""
    attempts = 2 if retry_on_error else 1
    for attempt in range(1, attempts + 1):
        try:
            job_id, project_id = run_pipeline(text, **kwargs)
            print(f"  Pipeline started: job={job_id} project={project_id}")
            status = wait_for_completion(job_id)
            snap = collect_snapshot(project_id)
            if status == "error":
                snap.error = snap.pipeline.get("error", "Pipeline failed")
                if attempt < attempts:
                    print(f"  Pipeline error (attempt {attempt}), retrying...")
                    continue
            return snap
        except Exception as e:
            if attempt < attempts:
                print(f"  Exception (attempt {attempt}): {e}, retrying...")
                continue
            return PipelineSnapshot(project_id="", error=str(e))
    return PipelineSnapshot(project_id="", error="Exhausted retries")


def resume_and_collect(
    project_id: str, resume_from: str, *, retry_on_error: bool = True, **kwargs
) -> PipelineSnapshot:
    """Resume pipeline from a step, wait, collect."""
    attempts = 2 if retry_on_error else 1
    for attempt in range(1, attempts + 1):
        try:
            job_id, new_pid = run_pipeline_resume(project_id, resume_from, **kwargs)
            print(f"  Pipeline resumed from {resume_from}: job={job_id} project={new_pid}")
            status = wait_for_completion(job_id)
            snap = collect_snapshot(new_pid)
            if status == "error":
                snap.error = snap.pipeline.get("error", "Pipeline failed")
                if attempt < attempts:
                    print(f"  Pipeline error (attempt {attempt}), retrying...")
                    continue
            return snap
        except Exception as e:
            if attempt < attempts:
                print(f"  Exception (attempt {attempt}): {e}, retrying...")
                continue
            return PipelineSnapshot(project_id=project_id, error=str(e))
    return PipelineSnapshot(project_id=project_id, error="Exhausted retries")
