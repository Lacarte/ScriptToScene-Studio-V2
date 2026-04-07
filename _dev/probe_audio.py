"""Probe a long-path m4a to check if it's playable."""
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

from studio.ffmpeg_utils import find_ffmpeg

ffmpeg = find_ffmpeg()
ffprobe = ffmpeg.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")

music_root = r"D:\@Workspace\@Development\@Scripts\@Python\ScriptToScene-Studio\resources\sounds\music"
target_file = None
for sub in os.listdir(music_root):
    if "BreakingCopyright" in sub:
        for f in os.listdir(os.path.join(music_root, sub)):
            if "Instructions For Living" in f:
                target_file = os.path.join(music_root, sub, f)
                break
        break

if not target_file:
    print("File not found in directory listing.")
    sys.exit(1)

print(f"normal path  ({len(target_file)} chars):")
print(f"  exists = {os.path.isfile(target_file)}")

# Apply Windows long-path prefix
long_path = "\\\\?\\" + target_file
print(f"long path    ({len(long_path)} chars):")
print(f"  exists = {os.path.isfile(long_path)}")

if not os.path.isfile(long_path):
    print("File not accessible even with long-path prefix.")
    sys.exit(1)

print(f"  size   = {os.path.getsize(long_path):,} bytes")
print()
print("--- ffprobe ---")
r = subprocess.run(
    [
        ffprobe,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "default=noprint_wrappers=0",
        long_path,
    ],
    capture_output=True,
)
print(f"returncode: {r.returncode}")
print(r.stdout.decode("utf-8", errors="replace"))
err = r.stderr.decode("utf-8", errors="replace")
if err:
    print(f"STDERR: {err}")

print()
print("--- decode test (first 5 seconds to null sink) ---")
r2 = subprocess.run(
    [ffmpeg, "-v", "error", "-i", long_path, "-t", "5", "-f", "null", "-"],
    capture_output=True,
)
print(f"returncode: {r2.returncode}")
err2 = r2.stderr.decode("utf-8", errors="replace")
if err2:
    print(f"STDERR: {err2}")
if r2.returncode == 0:
    print("OK — first 5 seconds decoded cleanly. File is playable.")
else:
    print("Decode FAILED. File may be corrupt.")
