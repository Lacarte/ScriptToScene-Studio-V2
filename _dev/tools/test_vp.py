import sys
import os
sys.path.append(os.path.join(os.getcwd(), "timeline-editor", "backend"))
from video_processor import VideoProcessor

# Initialize processor with same config
config = {
    "width": 1080,
    "height": 1920,
    "fps": 30,
    "crf": 23,
    "codec": "libx264",
    "preset": "medium",
    "pixel_format": "yuv420p"
}
processor = VideoProcessor(config)

media = r"output\assets\pp_ER7T57\0\0.webp"
out = "test_simple.mp4"

try:
    processor._create_simple_scene(media, out, 2.4, "static")
    with open("err.log", "w") as f:
        f.write("Success!")
except Exception as e:
    with open("err.log", "w") as f:
        f.write("ERROR: " + str(e))

