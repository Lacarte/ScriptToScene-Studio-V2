from pathlib import Path
import os
import subprocess

import pytest

from studio.editor import video_processor


@pytest.mark.parametrize("width,height,position,expected", [
    (1080, 1920, "top_right", "W-w-32"),
    (1920, 1080, "bottom_left", "H-h-32"),
    (1080, 1080, "center", "(W-w)/2"),
])
def test_logo_overlay_scales_and_positions_across_profiles(monkeypatch, tmp_path, width, height, position, expected):
    root = tmp_path
    logo = root / "output" / "branding" / "logo.png"
    logo.parent.mkdir(parents=True)
    logo.write_bytes(b"logo")
    source = root / "in.mp4"
    source.write_bytes(b"video")
    output = root / "out.mp4"
    commands = []
    monkeypatch.setattr(video_processor, "ROOT_DIR", str(root))
    monkeypatch.setattr(video_processor.subprocess, "run", lambda cmd, **kwargs: commands.append(cmd) or type("R", (), {"returncode": 0, "stderr": ""})())
    processor = video_processor.VideoProcessor({"output": {"resolution": {"width": width, "height": height}}})
    processor._apply_logo_overlay(str(source), str(output), {
        "path": "/output/branding/logo.png", "position": position,
        "size": 10, "opacity": 0.75, "margin": 32,
    })
    filter_graph = commands[0][commands[0].index("-filter_complex") + 1]
    assert f"scale={int(width * .1)}:-2" in filter_graph
    assert expected in filter_graph
    assert "aa=0.750" in filter_graph


@pytest.mark.parametrize("width,height,position", [
    (90, 160, "top_left"),
    (160, 90, "bottom_right"),
    (120, 120, "center"),
])
def test_logo_overlay_renders_in_expected_region(tmp_path, width, height, position):
    from PIL import Image

    ffmpeg = video_processor.FFMPEG_BIN
    if not ffmpeg or not os.path.isfile(ffmpeg):
        pytest.skip("Bundled FFmpeg is unavailable")
    root = tmp_path
    logo = root / "output" / "branding" / "logo.png"
    logo.parent.mkdir(parents=True)
    Image.new("RGBA", (20, 10), (255, 0, 0, 255)).save(logo)
    source = root / "in.mp4"
    rendered = root / "rendered.mp4"
    frame = root / "frame.png"
    subprocess.run([
        ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c=blue:s={width}x{height}:d=0.2",
        "-pix_fmt", "yuv420p", str(source),
    ], check=True, capture_output=True)
    old_root = video_processor.ROOT_DIR
    try:
        video_processor.ROOT_DIR = str(root)
        processor = video_processor.VideoProcessor({
            "output": {"resolution": {"width": width, "height": height}, "preset": "ultrafast"},
        })
        processor._apply_logo_overlay(str(source), str(rendered), {
            "path": "/output/branding/logo.png", "position": position,
            "size": 20, "opacity": 1, "margin": 4,
        })
    finally:
        video_processor.ROOT_DIR = old_root
    subprocess.run([ffmpeg, "-y", "-i", str(rendered), "-frames:v", "1", str(frame)], check=True, capture_output=True)
    pixels = Image.open(frame).convert("RGB")
    red = [(x, y) for y in range(height) for x in range(width) if pixels.getpixel((x, y))[0] > 150 and pixels.getpixel((x, y))[2] < 100]
    assert red
    min_x, max_x = min(x for x, _ in red), max(x for x, _ in red)
    min_y, max_y = min(y for _, y in red), max(y for _, y in red)
    logo_w = round(width * 0.20)
    logo_h = round(logo_w / 2)
    expected = {
        "top_left": (4, 4),
        "bottom_right": (width - logo_w - 4, height - logo_h - 4),
        "center": ((width - logo_w) // 2, (height - logo_h) // 2),
    }[position]
    assert abs(min_x - expected[0]) <= 3
    assert abs(min_y - expected[1]) <= 3
    assert abs((max_x - min_x + 1) - logo_w) <= 4
