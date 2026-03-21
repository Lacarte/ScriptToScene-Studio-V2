import io
import json
import os
import queue
import shutil
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from flask import Flask

import config as app_config
import studio.editor.routes as editor_routes
import studio.pipeline.routes as pipeline_routes
import studio.timing.routes as timing_routes
from studio.assets.organizer import reconcile_project
from studio.build_scene_blueprints.routes import _apply_segmenter_timing


class ReliabilityRegressionTests(unittest.TestCase):
    def setUp(self):
        self._temp_paths = []

    def tearDown(self):
        while self._temp_paths:
            path = self._temp_paths.pop()
            shutil.rmtree(path, ignore_errors=True)

    def _make_tempdir(self, prefix):
        temp_root = os.path.join(tempfile.gettempdir(), "sts_test_work")
        os.makedirs(temp_root, exist_ok=True)
        path = os.path.join(temp_root, f"{prefix}{uuid.uuid4().hex[:8]}")
        os.makedirs(path, exist_ok=False)
        self._temp_paths.append(path)
        return path

    def test_scene_timing_total_duration_tracks_extended_scene_end(self):
        result = {
            "scenes": [
                {"index": 0, "duration": 0.4},
                {"index": 1, "duration": 0.3},
            ]
        }
        segments = [
            {"index": 0, "words": "a", "start": 0.2, "end": 0.4},
            {"index": 1, "words": "b", "start": 0.5, "end": 0.6},
        ]

        _apply_segmenter_timing(result, segments, segments)

        self.assertEqual(result["total_duration"], 2.0)
        self.assertGreaterEqual(
            result["total_duration"],
            result["scenes"][-1]["timeline_end"],
        )

    def test_editor_projects_route_skips_corrupt_project_manifest(self):
        projects_dir = self._make_tempdir("test_editor_projects_")
        bad_project_dir = os.path.join(projects_dir, "bad_project")
        os.makedirs(bad_project_dir, exist_ok=True)
        with open(os.path.join(bad_project_dir, "initial.json"), "w", encoding="utf-8") as handle:
            handle.write("{bad json")

        app = Flask(__name__)
        app.register_blueprint(editor_routes.editor_bp)

        with patch.object(editor_routes, "PROJECTS_DIR", projects_dir):
            response = app.test_client().get("/api/editor/projects")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])

    def test_project_discovery_route_skips_corrupt_scenes_manifest(self):
        scenes_dir = self._make_tempdir("test_editor_scenes_")
        projects_dir = self._make_tempdir("test_editor_project_manifests_")
        assets_dir = self._make_tempdir("test_editor_assets_")
        align_dir = self._make_tempdir("test_editor_align_")
        tts_dir = self._make_tempdir("test_editor_tts_")
        thumbs_dir = self._make_tempdir("test_editor_thumbs_")

        bad_project_dir = os.path.join(scenes_dir, "bad_project")
        os.makedirs(bad_project_dir, exist_ok=True)
        with open(os.path.join(bad_project_dir, "scenes.json"), "w", encoding="utf-8") as handle:
            handle.write("{bad json")

        app = Flask(__name__)
        app.register_blueprint(editor_routes.editor_bp)

        with patch.object(editor_routes, "SCENES_DIR", scenes_dir), \
             patch.object(editor_routes, "PROJECTS_DIR", projects_dir), \
             patch.object(editor_routes, "ASSETS_DIR", assets_dir), \
             patch.object(editor_routes, "ALIGN_DIR", align_dir), \
             patch.object(editor_routes, "TTS_DIR", tts_dir), \
             patch.object(editor_routes, "THUMBNAILS_DIR", thumbs_dir):
            response = app.test_client().get("/api/projects")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])

    def test_align_and_segment_rejects_invalid_segment_config(self):
        align_dir = self._make_tempdir("test_alignments_")
        segmenter_dir = self._make_tempdir("test_segmenters_")

        app = Flask(__name__)
        app.register_blueprint(timing_routes.timing_bp)

        with patch.object(timing_routes, "ALIGN_DIR", align_dir), \
             patch.object(timing_routes, "generate_project_id", return_value="pm_TEST"), \
             patch.object(timing_routes, "_check_alignment_available", return_value=True), \
             patch.object(
                 timing_routes,
                 "_run_alignment",
                 return_value=[{"word": "hello", "begin": 0.0, "end": 0.5}],
             ), \
             patch.object(app_config, "SEGMENTER_DIR", segmenter_dir):
            response = app.test_client().post(
                "/api/alignment/align-and-segment",
                data={
                    "text": "hello",
                    "segment_config": "{bad json",
                    "audio": (io.BytesIO(b"RIFF....WAVEfmt "), "voice.wav"),
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("segment_config", response.get_json()["error"])

    def test_reconcile_project_persists_job_only_repairs(self):
        assets_dir = self._make_tempdir("test_assets_reconcile_")
        project_id = "proj1"
        project_dir = os.path.join(assets_dir, project_id)
        scene_dir = os.path.join(project_dir, "0")
        os.makedirs(scene_dir, exist_ok=True)

        with open(os.path.join(scene_dir, "0.png"), "wb") as handle:
            handle.write(b"123")
        with open(os.path.join(project_dir, "metadata.json"), "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "scenes": {
                        "0": {
                            "scene": "0",
                            "source_urls": [],
                            "local_files": ["/output/assets/proj1/0/0.png"],
                            "file_count": 1,
                        }
                    }
                },
                handle,
            )
        with open(os.path.join(project_dir, "grabber_job.json"), "w", encoding="utf-8") as handle:
            json.dump({"status": "downloading", "scene_statuses": {}}, handle)

        updated = reconcile_project(assets_dir, project_id)

        self.assertEqual(updated, 1)
        with open(os.path.join(project_dir, "grabber_job.json"), "r", encoding="utf-8") as handle:
            repaired = json.load(handle)
        self.assertEqual(repaired["status"], "done")
        self.assertEqual(repaired["scene_statuses"]["0"]["status"], "ready")

    def test_pipeline_resume_from_assets_skips_scene_regeneration(self):
        calls = []

        def _record(name, result):
            def _fn(*args, **kwargs):
                calls.append(name)
                return result
            return _fn

        job_id = "job123"
        project_id = "pp_TEST"
        pipeline_routes._jobs[job_id] = {
            "queue": queue.Queue(),
            "status": "running",
            "project_id": project_id,
            "config": {
                "project_id": project_id,
                "text": "hello",
                "voice": "af_heart",
                "speed": 1.0,
                "style": "cinematic",
                "resume_from": "assets",
                "provider": "grok",
                "auto_scenes": True,
            },
            "results": {},
            "step_sequence": pipeline_routes.ALL_PIPELINE_STEPS,
            "step_statuses": {},
            "stop_requested": False,
            "created": time.time(),
        }

        prior = {
            "tts": {
                "wav_path": "voice.wav",
                "duration_seconds": 1.0,
                "words": 1,
                "folder": project_id,
                "filename": "voice.wav",
            },
            "timing": {
                "word_count": 1,
                "inference_time": 0.1,
                "folder": project_id,
                "alignment": [{"word": "hello", "begin": 0.0, "end": 1.0}],
                "transcript": "hello",
            },
            "segment": {
                "segments": [{"words": "hello"}],
                "stats": {"segment_count": 1, "avg_duration": 1.0},
            },
            "scenes": {
                "scenes": [{"image_prompt": "prompt", "index": 0}],
            },
        }

        with patch.object(pipeline_routes, "_load_prior_results", return_value=prior), \
             patch.object(pipeline_routes, "_save_pipeline_timing", return_value=None), \
             patch.object(pipeline_routes, "_save_pipeline_json", return_value=None), \
             patch.object(pipeline_routes, "_step_scenes", _record("scenes", prior["scenes"])), \
             patch.object(
                 pipeline_routes,
                 "_step_assets",
                 _record("assets", {"total": 1, "ready": 1, "errors": 0}),
             ), \
             patch.object(
                 pipeline_routes,
                 "_step_assemble",
                 _record(
                     "assemble",
                     {
                         "scene_count": 1,
                         "total_duration": 1.0,
                         "has_audio": True,
                         "has_captions": False,
                         "assembled_data": {"scenes": [{"mediaUrl": "x", "duration": 1.0}]},
                     },
                 ),
             ), \
             patch.object(
                 pipeline_routes,
                 "_step_export",
                 _record("export", {"filename": "out.mp4", "resolution": "1080x1920"}),
             ):
            try:
                pipeline_routes._run_pipeline(job_id)
            finally:
                pipeline_routes._jobs.pop(job_id, None)

        self.assertEqual(calls, ["assets", "assemble", "export"])


if __name__ == "__main__":
    unittest.main()
