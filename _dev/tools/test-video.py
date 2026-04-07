"""Quick scene-render smoke test against an arbitrary animator media file.

Auto-discovers the first available file under output/animator/<pid>/<scene>/
so it keeps working as projects come and go.
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from studio.editor.video_processor import VideoProcessor


def find_sample_media():
    """Walk output/animator/ and return the first image/video file we find."""
    animator_dir = os.path.join(ROOT, "output", "animator")
    exts = (".webp", ".png", ".jpg", ".jpeg", ".mp4", ".webm", ".mov")
    for project in sorted(os.listdir(animator_dir)) if os.path.isdir(animator_dir) else []:
        proj_path = os.path.join(animator_dir, project)
        if not os.path.isdir(proj_path):
            continue
        for scene in sorted(os.listdir(proj_path)):
            scene_path = os.path.join(proj_path, scene)
            if not os.path.isdir(scene_path):
                continue
            for fname in sorted(os.listdir(scene_path)):
                if fname.lower().endswith(exts):
                    return os.path.join(scene_path, fname)
    return None


config = {
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "crf": 23,
    "codec": "libx264",
    "preset": "medium",
    "pixel_format": "yuv420p",
}
processor = VideoProcessor(config)

media = find_sample_media()
if not media:
    print("No animator media found under output/animator/ — generate a project first.")
    sys.exit(1)

print(f"Using media: {media}")
out = "test_simple.mp4"

try:
    processor._create_simple_scene(media, out, 2.4, "static")
    with open("err.log", "w") as f:
        f.write("Success!")
    print("Wrote", out)
except Exception as e:
    with open("err.log", "w") as f:
        f.write("ERROR: " + str(e))
    print("FAILED:", e)

