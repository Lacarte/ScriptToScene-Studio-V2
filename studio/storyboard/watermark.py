"""Gemini watermark removal using py-gemini-watermark-remover.

Uses template matching to locate the watermark precisely, then applies
the library's reverse alpha blending for pixel-perfect recovery.
Falls back to cv2.inpaint if the watermark can't be matched.
"""

import cv2
import numpy as np
from gemini_watermark_remover import WatermarkRemover, WatermarkSize
from loguru import logger

_remover = WatermarkRemover()

# Search region: bottom-right corner area to look for the watermark
_SEARCH_MARGIN = 120


def _locate_watermark(gray, alpha_map):
    """Find the best-match position of the alpha map in the bottom-right corner.

    Uses normalised cross-correlation between the alpha map (as a bright
    overlay template) and the image corner. Returns (x, y) in full-image
    coordinates, or None if no confident match.
    """
    h, w = gray.shape
    logo_h, logo_w = alpha_map.shape

    # Crop the bottom-right search region
    sy = max(0, h - _SEARCH_MARGIN)
    sx = max(0, w - _SEARCH_MARGIN)
    corner = gray[sy:, sx:].astype(np.float32)

    # The watermark is alpha-blended white over the image, so areas with
    # high alpha will be brighter than surroundings. Use alpha map as template.
    template = (alpha_map * 255).astype(np.float32)

    if corner.shape[0] < template.shape[0] or corner.shape[1] < template.shape[1]:
        return None

    result = cv2.matchTemplate(corner, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val < 0.15:
        return None

    # Convert to full-image coordinates
    return (sx + max_loc[0], sy + max_loc[1])


def _inpaint_fallback(image, x1, y1, x2, y2):
    """Inpaint the watermark region when alpha blending can't be used."""
    roi = image[y1:y2, x1:x2]
    roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.float32)

    # Build mask from deviation against border
    border = np.concatenate([roi_gray[:4, :].flatten(), roi_gray[:, :4].flatten()])
    bg_mean = np.mean(border)
    bg_std = max(np.std(border), 3.0)
    diff = np.abs(roi_gray - bg_mean)
    mask = (diff > max(bg_std * 2.5, 15.0)).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.dilate(mask, kernel, iterations=1)

    if cv2.countNonZero(mask) < 10:
        return

    image[y1:y2, x1:x2] = cv2.inpaint(roi, mask, 5, cv2.INPAINT_TELEA)


def remove_watermark(filepath: str) -> bool:
    """Remove Gemini sparkle watermark from *filepath* in-place.

    Tries both SMALL (48x48) and LARGE (96x96) alpha maps via template
    matching, picks the best match, then applies the library's reverse
    alpha blending. Falls back to cv2.inpaint if no match is found.

    Returns True if processed, False on error.
    """
    try:
        image = cv2.imread(filepath)
        if image is None:
            logger.warning("Could not read image: {}", filepath)
            return False

        h, w = image.shape[:2]
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)

        # Try both sizes via template matching, pick best
        best_pos = None
        best_alpha = None
        best_score = -1

        for size_enum, alpha_map in [
            (WatermarkSize.SMALL, _remover.alpha_map_small),
            (WatermarkSize.LARGE, _remover.alpha_map_large),
        ]:
            if alpha_map is None:
                continue

            logo_h, logo_w = alpha_map.shape
            sy = max(0, h - _SEARCH_MARGIN)
            sx = max(0, w - _SEARCH_MARGIN)
            corner = gray[sy:, sx:]

            if corner.shape[0] < logo_h or corner.shape[1] < logo_w:
                continue

            template = (alpha_map * 255).astype(np.float32)
            result = cv2.matchTemplate(corner, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val > best_score:
                best_score = max_val
                best_pos = (sx + max_loc[0], sy + max_loc[1])
                best_alpha = alpha_map

        if best_pos is not None and best_score >= 0.15:
            x, y = best_pos
            logo_h, logo_w = best_alpha.shape

            # Clip to image bounds
            x1, y1 = max(0, x), max(0, y)
            x2 = min(w, x + logo_w)
            y2 = min(h, y + logo_h)
            ax1, ay1 = x1 - x, y1 - y
            ax2 = ax1 + (x2 - x1)
            ay2 = ay1 + (y2 - y1)

            roi = image[y1:y2, x1:x2]
            alpha = best_alpha[ay1:ay2, ax1:ax2]
            image[y1:y2, x1:x2] = _remover.remove_watermark_from_region(
                roi, alpha
            )
        else:
            # Fallback: inpaint the expected watermark region
            logo_size = 48
            margin = 18
            x1 = max(0, w - margin - logo_size - 4)
            y1 = max(0, h - margin - logo_size - 4)
            x2 = min(w, w - margin + 4)
            y2 = min(h, h - margin + 4)
            _inpaint_fallback(image, x1, y1, x2, y2)

        # Save
        ext = filepath.rsplit(".", 1)[-1].lower()
        if ext in ("jpg", "jpeg"):
            cv2.imwrite(filepath, image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        else:
            cv2.imwrite(filepath, image)

        logger.success("Watermark removed: {}", filepath)
        return True

    except Exception as e:
        logger.warning("Watermark removal failed on {}: {}", filepath, e)
        return False
