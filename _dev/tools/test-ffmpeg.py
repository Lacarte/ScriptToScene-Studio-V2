"""FFmpeg scene rendering test — prints result + writes err.log on failure.

Auto-discovers the first available media file under output/animator/<pid>/<scene>/
instead of pointing at a hardcoded (and now-removed) output/assets/ path.
"""
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FFMPEG_BIN = os.path.join(ROOT, "bin", "ffmpeg.exe")


def find_sample_media():
    animator_dir = os.path.join(ROOT, "output", "animator")
    exts = (".webp", ".png", ".jpg", ".jpeg")
    if not os.path.isdir(animator_dir):
        return None
    for project in sorted(os.listdir(animator_dir)):
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


media_path = find_sample_media()
if not media_path:
    print("No animator media found under output/animator/ — generate a project first.")
    sys.exit(1)
print(f"Using media: {media_path}")

output_path = "test_scene.mp4"
duration = 2.4
width, height = 1080, 1920
fps = 30
codec = "libx264"
pixel_format = "yuv420p"
crf = 23

filters = [
    f"scale='if(gte(iw/ih,{width}/{height}),-2,{width})':'if(gte(iw/ih,{width}/{height}),{height},-2)'",
    f"crop={width}:{height}",
    f"fps={fps}"
]
vf = ','.join(filters)

cmd = [
    FFMPEG_BIN, '-y',
    '-loop', '1',
    '-i', media_path,
    '-t', str(duration),
    '-vf', vf,
    '-c:v', codec,
    '-pix_fmt', pixel_format,
    '-preset', 'fast',
    '-crf', str(crf),
    output_path
]

print("Running command:", " ".join(cmd))
try:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        with open("err.log", "w") as f:
            f.write(f"RC: {result.returncode}\nOUT: {result.stdout}\nERR: {result.stderr}\n")
    else:
        print("Success!")
except Exception as e:
    print(f"EXCEPTION: {e}")
    with open("err.log", "w") as f:
        f.write(f"EXCEPTION: {e}")
