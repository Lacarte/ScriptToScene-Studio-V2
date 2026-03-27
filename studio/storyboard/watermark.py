"""Gemini watermark removal using GeminiWatermarkTool (GWT).

Downloads the GWT binary on first use and provides a simple
`remove_watermark(filepath)` that operates in-place.

Binary location: BIN_DIR / GeminiWatermarkTool.exe  (Windows)
Override via env var GWT_BINARY_PATH.
"""

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

from loguru import logger

_REPO = "allenk/GeminiWatermarkTool"
_TAG = "latest"


def _get_binary_path() -> str:
    """Return path to the GWT binary, respecting env override."""
    env = os.environ.get("GWT_BINARY_PATH")
    if env and os.path.isfile(env):
        return env

    from config import BIN_DIR

    name = "GeminiWatermarkTool.exe" if sys.platform == "win32" else "GeminiWatermarkTool"
    return os.path.join(BIN_DIR, name)


def _asset_name() -> str:
    """Determine the correct release asset name for this platform."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        if machine in ("amd64", "x86_64"):
            return "GeminiWatermarkTool-windows-x64.zip"
        return "GeminiWatermarkTool-windows-arm64.zip"
    elif system == "linux":
        if machine in ("aarch64", "arm64"):
            return "GeminiWatermarkTool-linux-arm64.zip"
        return "GeminiWatermarkTool-linux-x64.zip"
    elif system == "darwin":
        if machine in ("arm64", "aarch64"):
            return "GeminiWatermarkTool-macos-arm64.zip"
        return "GeminiWatermarkTool-macos-x64.zip"
    raise RuntimeError(f"Unsupported platform: {system} {machine}")


def _download_binary(dest: str) -> None:
    """Download the latest GWT release binary to *dest*."""
    asset = _asset_name()
    url = f"https://github.com/{_REPO}/releases/{_TAG}/download/{asset}"
    logger.info("Downloading GeminiWatermarkTool from {}", url)

    dest_dir = os.path.dirname(dest)
    os.makedirs(dest_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, asset)
        urllib.request.urlretrieve(url, zip_path)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)

        # Find the binary inside the extracted files
        exe_name = "GeminiWatermarkTool.exe" if sys.platform == "win32" else "GeminiWatermarkTool"
        for root, _dirs, files in os.walk(tmp):
            for f in files:
                if f == exe_name:
                    src = os.path.join(root, f)
                    shutil.copy2(src, dest)
                    if sys.platform != "win32":
                        os.chmod(dest, 0o755)
                    logger.success("GWT binary installed: {}", dest)
                    return

    raise FileNotFoundError(f"Could not find {exe_name} in downloaded archive")


def ensure_binary() -> str:
    """Return path to GWT binary, downloading if needed."""
    path = _get_binary_path()
    if not os.path.isfile(path):
        _download_binary(path)
    return path


def remove_watermark(filepath: str) -> bool:
    """Remove Gemini watermark from *filepath* in-place.

    Returns True if watermark was removed, False if skipped or failed.
    """
    try:
        gwt = ensure_binary()
    except Exception as e:
        logger.warning("GWT binary not available, skipping watermark removal: {}", e)
        return False

    try:
        result = subprocess.run(
            [gwt, "-i", filepath, "-o", filepath, "--force", "--snap", "--no-banner"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            logger.success("Watermark removed: {}", filepath)
            return True
        else:
            stderr = result.stderr.strip() if result.stderr else ""
            logger.debug("GWT returned {}: {}", result.returncode, stderr)
            return False

    except subprocess.TimeoutExpired:
        logger.warning("GWT timed out on {}", filepath)
        return False
    except Exception as e:
        logger.warning("GWT failed on {}: {}", filepath, e)
        return False
