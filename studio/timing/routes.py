"""Timing Module — Force Alignment Routes"""

import json
import os
import re
import subprocess
import time
import threading
import warnings
from datetime import datetime

import numpy as np
import soundfile as sf
from flask import Blueprint, jsonify, request, send_from_directory
from loguru import logger
from werkzeug.utils import secure_filename

from config import ALIGN_DIR, TRASH_DIR, BIN_DIR, generate_project_id
from studio.ffmpeg_utils import find_ffmpeg
from studio.io_utils import move_to_unique_path, safe_json_write

timing_bp = Blueprint("timing", __name__)

# ---------------------------------------------------------------------------
# Alignment model (stable-ts / Whisper)
# ---------------------------------------------------------------------------
alignment_model = None
alignment_lock = threading.Lock()
alignment_available = None


def _check_alignment_available():
    global alignment_available
    if alignment_available is not None:
        return alignment_available
    try:
        import stable_whisper  # noqa: F401
        alignment_available = True
    except ImportError:
        alignment_available = False
    return alignment_available


def _load_alignment_model():
    global alignment_model
    if alignment_model is not None:
        return alignment_model
    import stable_whisper
    with alignment_lock:
        if alignment_model is None:
            alignment_model = stable_whisper.load_model("tiny.en")
    return alignment_model
def _run_alignment(wav_path, prompt_text):
    try:
        model = _load_alignment_model()
        audio, sr = sf.read(wav_path, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != 16000:
            target_len = int(len(audio) * 16000 / sr)
            audio = np.interp(
                np.linspace(0, len(audio), target_len, endpoint=False),
                np.arange(len(audio), dtype=np.float32),
                audio,
            ).astype(np.float32)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = model.align(audio, prompt_text, language="en", fast_mode=True)
        for w in caught:
            msg = str(w.message)
            if "failed to align" in msg:
                logger.warning("Align partial: {}", msg)
            else:
                logger.debug("Align warning: {}", msg)
        alignment = []
        for w in result.all_words():
            word_text = w.word.strip()
            if word_text:
                alignment.append({
                    "word": word_text,
                    "begin": round(w.start, 3),
                    "end": round(w.end, 3),
                })
        # Post-process: validate and repair common alignment failures
        alignment = _validate_alignment(alignment, wav_path)
        return alignment if alignment else None
    except Exception:
        logger.exception("Alignment failed for {}", wav_path)
        return None


def _validate_alignment(alignment, wav_path=None):
    """Full alignment validation and repair pipeline.

    Catches and fixes:
    1. Zero-duration words (clustered at same timestamp)
    2. Out-of-order timestamps
    3. Overlapping words
    4. Large gaps where audio has speech (uses waveform energy)
    5. Words with end < begin (negative duration)
    """
    if not alignment:
        return alignment

    fixes = []

    # Step 1: Fix zero-duration word clusters
    alignment = _fix_zero_duration_words(alignment)
    zero_count = sum(1 for w in alignment if w["end"] - w["begin"] < 0.01)
    if zero_count:
        # Second pass: steal time from next word for remaining zero-dur
        for i in range(len(alignment)):
            if alignment[i]["end"] - alignment[i]["begin"] < 0.01 and i + 1 < len(alignment):
                alignment[i]["end"] = round(alignment[i]["begin"] + 0.05, 3)
                if alignment[i + 1]["begin"] < alignment[i]["end"]:
                    alignment[i + 1]["begin"] = alignment[i]["end"]
        fixed = zero_count - sum(1 for w in alignment if w["end"] - w["begin"] < 0.01)
        if fixed:
            fixes.append(f"fixed {fixed} zero-dur words")

    # Step 2: Fix negative durations (end < begin)
    for w in alignment:
        if w["end"] < w["begin"]:
            w["end"] = round(w["begin"] + 0.05, 3)
            fixes.append(f"fixed negative dur at {w['begin']:.2f}s")

    # Step 3: Sort by begin time (out-of-order words)
    was_sorted = all(alignment[i]["begin"] <= alignment[i + 1]["begin"]
                     for i in range(len(alignment) - 1))
    if not was_sorted:
        alignment.sort(key=lambda w: w["begin"])
        fixes.append("re-sorted out-of-order words")

    # Step 4: Fix overlaps (word end > next word begin)
    for i in range(len(alignment) - 1):
        if alignment[i]["end"] > alignment[i + 1]["begin"] + 0.001:
            alignment[i]["end"] = round(alignment[i + 1]["begin"], 3)

    # Step 5: Detect large gaps where audio has speech
    # If we have the audio file, check waveform energy in gap regions
    if wav_path:
        try:
            alignment = _fix_gaps_with_audio(alignment, wav_path)
        except Exception as e:
            logger.debug("Gap detection skipped: {}", e)

    if fixes:
        logger.info("Alignment validation: {}", ", ".join(fixes))

    return alignment


def _fix_gaps_with_audio(alignment, wav_path):
    """Detect gaps > 2s where audio has speech and redistribute words."""
    import numpy as np

    audio, sr = sf.read(wav_path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    def has_speech(start_s, end_s, threshold=0.01):
        """Check if audio region has speech energy."""
        s = int(start_s * sr)
        e = int(end_s * sr)
        if s >= len(audio) or e > len(audio) or s >= e:
            return False
        rms = np.sqrt(np.mean(audio[s:e] ** 2))
        return rms > threshold

    # Find gaps > 2s between consecutive words
    for i in range(len(alignment) - 1):
        gap_start = alignment[i]["end"]
        gap_end = alignment[i + 1]["begin"]
        gap = gap_end - gap_start

        if gap <= 2.0:
            continue

        # Check if there's speech in the gap
        if not has_speech(gap_start + 0.2, gap_end - 0.2):
            continue  # genuine silence, leave it

        # Speech detected in gap — find the run of words that should fill it
        # Collect all words from i+1 until we find one with proper duration
        run_start = i + 1
        run_end = run_start
        while run_end < len(alignment) and alignment[run_end]["end"] - alignment[run_end]["begin"] < 0.1:
            run_end += 1

        if run_end - run_start < 3:
            continue  # not enough words to fix

        # Find where speech actually ends (scan audio for silence)
        speech_end = gap_end
        for t in range(int(gap_end * 10), int(min(gap_end + 15, len(audio) / sr) * 10)):
            t_s = t / 10.0
            if not has_speech(t_s, t_s + 0.2, threshold=0.008):
                speech_end = t_s
                break

        # Redistribute words across the speech region
        time_start = gap_start + 0.1
        time_end = speech_end
        count = run_end - run_start
        if time_end > time_start and count > 0:
            slot = (time_end - time_start) / count
            for j in range(run_start, run_end):
                offset = j - run_start
                alignment[j]["begin"] = round(time_start + offset * slot, 3)
                alignment[j]["end"] = round(time_start + (offset + 1) * slot, 3)
            logger.info("Alignment gap fix: redistributed {} words across {:.1f}-{:.1f}s",
                        count, time_start, time_end)

    return alignment


def _fix_zero_duration_words(alignment):
    """Redistribute zero-duration words evenly across their time window.

    Whisper alignment sometimes fails to timestamp words after long silences,
    collapsing many words into begin==end at the same instant.  This finds
    all words clustered at the same timestamp and spreads them evenly across
    the time window up to the next properly-spaced word.
    """
    if not alignment:
        return alignment

    # Find clusters: groups of words sharing the same begin timestamp (within 0.02s)
    i = 0
    while i < len(alignment):
        w = alignment[i]
        # Look for a cluster: 3+ words within 0.02s of each other
        cluster_start = i
        cluster_time = w["begin"]
        while i < len(alignment) and abs(alignment[i]["begin"] - cluster_time) < 0.02:
            i += 1
        cluster_end = i  # exclusive
        cluster_count = cluster_end - cluster_start

        if cluster_count < 3:
            continue  # not a cluster, skip

        # Find the time window to redistribute into:
        # Start: the cluster timestamp (or prev word's end if earlier)
        time_start = cluster_time
        if cluster_start > 0:
            time_start = max(time_start, alignment[cluster_start - 1]["end"])

        # End: scan forward for a word with a different timestamp AND real duration
        time_end = time_start + 2.0  # fallback: 2 seconds
        for j in range(cluster_end, min(cluster_end + 20, len(alignment))):
            if alignment[j]["begin"] - cluster_time > 0.1 and alignment[j]["end"] - alignment[j]["begin"] >= 0.05:
                time_end = alignment[j]["begin"]
                break

        # Include any short-duration words between cluster and time_end
        # (they might be partially-timed words from the same failed region)
        actual_end = cluster_end
        for j in range(cluster_end, min(cluster_end + 10, len(alignment))):
            if alignment[j]["begin"] < time_end and alignment[j]["end"] - alignment[j]["begin"] < 0.05:
                actual_end = j + 1
            else:
                break

        total_words = actual_end - cluster_start
        if time_end > time_start and total_words > 0:
            slot = (time_end - time_start) / total_words
            for j in range(cluster_start, actual_end):
                offset = j - cluster_start
                alignment[j]["begin"] = round(time_start + offset * slot, 3)
                alignment[j]["end"] = round(time_start + (offset + 1) * slot, 3)

    return alignment


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@timing_bp.route("/api/alignment/history")
def list_force_alignments():
    items = []
    if not os.path.exists(ALIGN_DIR):
        return jsonify(items)
    for entry in os.listdir(ALIGN_DIR):
        entry_path = os.path.join(ALIGN_DIR, entry)
        if not os.path.isdir(entry_path) or entry == "TRASH":
            continue
        json_path = os.path.join(entry_path, "alignment.json")
        if not os.path.isfile(json_path):
            continue
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            words = meta.get("alignment", [])
            duration = round(words[-1]["end"], 2) if words else 0
            items.append({
                "type": "force-alignment",
                "project_id": meta.get("project_id", ""),
                "folder": meta.get("folder", entry),
                "source_file": meta.get("source_file", ""),
                "transcript": meta.get("transcript", ""),
                "word_count": meta.get("word_count", len(words)),
                "word_alignment": words,
                "duration_seconds": duration,
                "inference_time": meta.get("inference_time", 0),
                "timestamp": meta.get("timestamp", ""),
            })
        except (json.JSONDecodeError, OSError, IndexError, KeyError):
            pass
    items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return jsonify(items)


@timing_bp.route("/api/alignment/align", methods=["POST"])
@timing_bp.route("/api/timing/align", methods=["POST"])
def force_align():
    if not _check_alignment_available():
        return jsonify({"error": "Force alignment not available (stable-ts not installed)"}), 503

    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    text = request.form.get("text", "").strip()
    if not text:
        return jsonify({"error": "No transcript text provided"}), 400

    audio_file = request.files["audio"]
    original_name = secure_filename(audio_file.filename or "")
    if not original_name:
        return jsonify({"error": "Invalid filename"}), 400
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in (".wav", ".mp3", ".flac", ".ogg"):
        return jsonify({"error": f"Unsupported format: {ext}"}), 400

    project_id = generate_project_id("pm")
    folder_name = project_id
    job_dir = os.path.join(ALIGN_DIR, folder_name)
    os.makedirs(job_dir, exist_ok=True)

    audio_path = os.path.join(job_dir, original_name)
    audio_file.save(audio_path)

    wav_path = audio_path
    conv_path = None
    try:
        if ext != ".wav":
            ffmpeg = find_ffmpeg()
            if not ffmpeg:
                return jsonify({"error": "ffmpeg required for non-WAV files"}), 400
            conv_path = os.path.join(job_dir, os.path.splitext(original_name)[0] + "_conv.wav")
            result = subprocess.run(
                [ffmpeg, "-nostdin", "-y", "-i", audio_path, "-ar", "24000", "-ac", "1", conv_path],
                capture_output=True, timeout=60,
            )
            if result.returncode != 0:
                return jsonify({"error": "Audio conversion failed"}), 500
            wav_path = conv_path

        start = time.perf_counter()
        alignment = _run_alignment(wav_path, text)
        elapsed = time.perf_counter() - start

        if not alignment:
            return jsonify({"error": "Alignment produced no results"}), 500

        result_data = {
            "project_id": project_id,
            "source_file": original_name,
            "folder": folder_name,
            "transcript": text,
            "alignment": alignment,
            "word_count": len(alignment),
            "inference_time": round(elapsed, 3),
            "timestamp": datetime.now().isoformat(),
        }
        safe_json_write(os.path.join(job_dir, "alignment.json"), result_data, indent=2)

        logger.success("Force-aligned  {} | {} words in {:.2f}s -> {}", original_name, len(alignment), elapsed, folder_name)
        return jsonify(result_data)

    finally:
        if conv_path:
            try:
                os.unlink(conv_path)
            except OSError:
                pass


@timing_bp.route("/api/alignment/align-and-segment", methods=["POST"])
def align_and_segment():
    """Combined alignment + segmentation in one request.

    Same inputs as /api/alignment/align, plus optional segment_config JSON field.
    Returns both alignment and segmentation results.
    """
    from studio.timing.segmenter import run_segmenter, save_output
    from config import SEGMENTER_DIR

    if not _check_alignment_available():
        return jsonify({"error": "Force alignment not available"}), 503

    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    text = request.form.get("text", "").strip()
    if not text:
        return jsonify({"error": "No transcript text provided"}), 400

    audio_file = request.files["audio"]
    original_name = secure_filename(audio_file.filename or "")
    if not original_name:
        return jsonify({"error": "Invalid filename"}), 400
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in (".wav", ".mp3", ".flac", ".ogg"):
        return jsonify({"error": f"Unsupported format: {ext}"}), 400

    seg_config_str = request.form.get("segment_config", "")
    if seg_config_str:
        try:
            seg_config = json.loads(seg_config_str)
        except json.JSONDecodeError:
            return jsonify({"error": "segment_config must be valid JSON"}), 400
        if seg_config is not None and not isinstance(seg_config, dict):
            return jsonify({"error": "segment_config must be a JSON object"}), 400
    else:
        seg_config = None

    project_id = generate_project_id("pm")
    folder_name = project_id
    job_dir = os.path.join(ALIGN_DIR, folder_name)
    os.makedirs(job_dir, exist_ok=True)

    audio_path = os.path.join(job_dir, original_name)
    audio_file.save(audio_path)

    wav_path = audio_path
    conv_path = None
    try:
        if ext != ".wav":
            ffmpeg = find_ffmpeg()
            if not ffmpeg:
                return jsonify({"error": "ffmpeg required for non-WAV files"}), 400
            conv_path = os.path.join(job_dir, os.path.splitext(original_name)[0] + "_conv.wav")
            result = subprocess.run(
                [ffmpeg, "-nostdin", "-y", "-i", audio_path, "-ar", "24000", "-ac", "1", conv_path],
                capture_output=True, timeout=60,
            )
            if result.returncode != 0:
                return jsonify({"error": "Audio conversion failed"}), 500
            wav_path = conv_path

        # ── Alignment ──
        start = time.perf_counter()
        alignment = _run_alignment(wav_path, text)
        align_elapsed = time.perf_counter() - start

        if not alignment:
            return jsonify({"error": "Alignment produced no results"}), 500

        align_data = {
            "project_id": project_id,
            "source_file": original_name,
            "folder": folder_name,
            "transcript": text,
            "alignment": alignment,
            "word_count": len(alignment),
            "inference_time": round(align_elapsed, 3),
            "timestamp": datetime.now().isoformat(),
        }
        safe_json_write(os.path.join(job_dir, "alignment.json"), align_data, indent=2)

        # ── Segmentation ──
        seg_metadata = {
            "project_id": project_id,
            "source_folder": folder_name,
            "transcript": text,
        }

        seg_result = run_segmenter(alignment, seg_config, seg_metadata)

        seg_folder = project_id
        out_path = os.path.join(SEGMENTER_DIR, seg_folder, "segmented.json")
        save_output(seg_result, out_path)
        seg_result["output_folder"] = seg_folder
        seg_result["output_path"] = out_path

        logger.success("Align+Segment  {} | {} words in {:.2f}s | {} segments",
                       original_name, len(alignment), align_elapsed,
                       seg_result["stats"]["segment_count"])

        return jsonify({
            "alignment": align_data,
            "segmentation": seg_result,
        })

    finally:
        if conv_path:
            try:
                os.unlink(conv_path)
            except OSError:
                pass


@timing_bp.route("/api/alignment/<folder>", methods=["DELETE"])
@timing_bp.route("/api/timing/<folder>", methods=["DELETE"])
def delete_alignment(folder):
    folder = os.path.basename(folder)
    job_dir = os.path.join(ALIGN_DIR, folder)
    if os.path.isdir(job_dir):
        align_trash = os.path.join(TRASH_DIR, "alignments")
        move_to_unique_path(job_dir, align_trash, folder)
        return jsonify({"status": "deleted", "folder": folder})
    return jsonify({"error": "Folder not found"}), 404


@timing_bp.route("/output/alignments/<path:filename>")
def serve_alignment_audio(filename):
    return send_from_directory(ALIGN_DIR, filename)
