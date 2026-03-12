"""FFmpeg scene rendering test — prints result + writes err.log on failure."""
import subprocess

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
