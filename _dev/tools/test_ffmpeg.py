import os
import subprocess

from typing import List

FFMPEG_BIN = r"D:\@Workspace\@Development\@Scripts\@Python\ScriptToScene-Studio\bin\ffmpeg.exe"
media_path = r"D:\@Workspace\@Development\@Scripts\@Python\ScriptToScene-Studio\output\assets\pp_ER7T57\0\0.webp"
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
result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    print("STDOUT:", result.stdout)
    print("STDERR:")
    print(result.stderr)
else:
    print("Success!")
