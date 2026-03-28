"""Gemini watermark removal using py-gemini-watermark-remover.

Gemini exports saved through the browser workflow can place the watermark
closer to the bottom-right edge than the library's built-in default. We
therefore do a tight local search near the corner, validate the match, and
only then apply reverse alpha blending.
"""

import cv2
import numpy as np
from gemini_watermark_remover import WatermarkRemover, WatermarkSize
from loguru import logger
from PIL import Image

_remover = WatermarkRemover()

_TEMPLATE_SCORE_MIN = 0.45
_BRIGHTNESS_DIFF_MIN = 8.0
_EDGE_DENSITY_MAX = 0.14
_BLEND_FACTORS = np.linspace(0.30, 1.00, 29)
_INPAINT_ALPHA_THRESHOLDS = (0.12, 0.18, 0.24)

# Observed Gemini exports sit closer to the edge than the package defaults,
# so we search a narrow band of plausible margins rather than the whole corner.
_MARGIN_RANGES = {
    WatermarkSize.SMALL: (10, 40),
    WatermarkSize.LARGE: (20, 80),
}


def _alpha_map_for_size(size):
    if size == WatermarkSize.SMALL:
        return _remover.alpha_map_small
    if size == WatermarkSize.LARGE:
        return _remover.alpha_map_large
    return None


def _safe_correlation(lhs, rhs):
    lhs_flat = lhs.astype(np.float32).reshape(-1)
    rhs_flat = rhs.astype(np.float32).reshape(-1)
    if np.std(lhs_flat) < 1e-6 or np.std(rhs_flat) < 1e-6:
        return 0.0

    corr = np.corrcoef(lhs_flat, rhs_flat)[0, 1]
    if np.isnan(corr):
        return 0.0
    return float(corr)


def _candidate_metrics(region, alpha_map):
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY).astype(np.float32)
    template = (alpha_map * 255).astype(np.float32)
    high_alpha_mask = alpha_map > 0.30
    low_alpha_mask = alpha_map < 0.10

    brightness_diff = 0.0
    if np.any(high_alpha_mask) and np.any(low_alpha_mask):
        brightness_diff = float(
            np.mean(gray[high_alpha_mask]) - np.mean(gray[low_alpha_mask])
        )

    correlation = _safe_correlation(gray, template)
    return correlation, brightness_diff


def _artifact_score(correlation, brightness_diff):
    """Score how visible the watermark pattern still is after restoration.

    Positive correlation and positive brightness bias mean watermark residue.
    Strongly negative values mean we have started to carve a dark ghost into
    the image, which should also be penalized.
    """

    return (
        max(0.0, correlation) * 1.8
        + max(0.0, brightness_diff - 2.0) / 16.0
        + max(0.0, -correlation - 0.18) * 1.2
        + max(0.0, -brightness_diff - 6.0) / 8.0
    )


def _pattern_residue_metrics(region, alpha_map):
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY).astype(np.float32)
    template = (alpha_map * 255).astype(np.float32)
    centered_template = template - np.mean(template)
    blurred = cv2.GaussianBlur(gray, (0, 0), 4.0)
    residual = gray - blurred
    high_alpha_mask = alpha_map > 0.30
    low_alpha_mask = alpha_map < 0.10

    residue_correlation = abs(_safe_correlation(residual, centered_template))
    residue_gap = 0.0
    if np.any(high_alpha_mask) and np.any(low_alpha_mask):
        residue_gap = float(
            np.mean(np.abs(residual[high_alpha_mask]))
            - np.mean(np.abs(residual[low_alpha_mask]))
        )

    return residue_correlation, max(0.0, residue_gap)


def _border_score(image, x, y, patch):
    patch_h, patch_w = patch.shape[:2]
    score = 0.0
    count = 0

    if y > 0:
        score += float(
            np.mean(
                np.abs(
                    patch[0].astype(np.float32)
                    - image[y - 1, x:x + patch_w].astype(np.float32)
                )
            )
        )
        count += 1
    if y + patch_h < image.shape[0]:
        score += float(
            np.mean(
                np.abs(
                    patch[-1].astype(np.float32)
                    - image[y + patch_h, x:x + patch_w].astype(np.float32)
                )
            )
        )
        count += 1
    if x > 0:
        score += float(
            np.mean(
                np.abs(
                    patch[:, 0].astype(np.float32)
                    - image[y:y + patch_h, x - 1].astype(np.float32)
                )
            )
        )
        count += 1
    if x + patch_w < image.shape[1]:
        score += float(
            np.mean(
                np.abs(
                    patch[:, -1].astype(np.float32)
                    - image[y:y + patch_h, x + patch_w].astype(np.float32)
                )
            )
        )
        count += 1

    return score / max(count, 1)


def _search_bounds(image_width, image_height, size, alpha_map):
    logo_h, logo_w = alpha_map.shape
    min_margin, max_margin = _MARGIN_RANGES.get(
        size,
        (max(8, logo_w // 5), max(logo_w, logo_w // 2)),
    )

    x_start = max(0, image_width - logo_w - max_margin)
    y_start = max(0, image_height - logo_h - max_margin)
    x_end = min(image_width - logo_w, image_width - logo_w - min_margin)
    y_end = min(image_height - logo_h, image_height - logo_h - min_margin)

    if x_end < x_start or y_end < y_start:
        return None

    return x_start, y_start, x_end, y_end


def _locate_watermark(image, size, alpha_map):
    h, w = image.shape[:2]
    bounds = _search_bounds(w, h, size, alpha_map)
    if bounds is None:
        return None

    x_start, y_start, x_end, y_end = bounds
    logo_h, logo_w = alpha_map.shape
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    template = (alpha_map * 255).astype(np.float32)

    search = gray[y_start:y_end + logo_h, x_start:x_end + logo_w]
    if search.shape[0] < logo_h or search.shape[1] < logo_w:
        return None

    result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    x = x_start + max_loc[0]
    y = y_start + max_loc[1]
    roi = image[y:y + logo_h, x:x + logo_w]
    correlation, brightness_diff = _candidate_metrics(roi, alpha_map)
    edges = cv2.Canny(roi, 50, 150)

    return {
        "size": size,
        "alpha_map": alpha_map,
        "x": x,
        "y": y,
        "width": logo_w,
        "height": logo_h,
        "template_score": float(max_val),
        "correlation": correlation,
        "brightness_diff": brightness_diff,
        "edge_density": float(np.mean(edges > 0)),
    }


def _is_confident_match(candidate):
    if candidate is None:
        return False

    return (
        candidate["template_score"] >= _TEMPLATE_SCORE_MIN
        and candidate["brightness_diff"] >= _BRIGHTNESS_DIFF_MIN
        and candidate["edge_density"] <= _EDGE_DENSITY_MAX
    )


def _select_cleanup(roi, alpha_map, min_factor=0.30):
    full_cleanup = _remover.remove_watermark_from_region(roi, alpha_map)
    roi_f = roi.astype(np.float32)
    cleanup_f = full_cleanup.astype(np.float32)

    best_region = full_cleanup
    best_score = float("inf")
    best_factor = 1.0
    best_metrics = (0.0, 0.0)

    for factor in _BLEND_FACTORS:
        if factor < min_factor:
            continue

        blended = np.clip(roi_f + factor * (cleanup_f - roi_f), 0, 255).astype(np.uint8)
        correlation, brightness_diff = _candidate_metrics(blended, alpha_map)
        score = _artifact_score(correlation, brightness_diff)
        if score < best_score:
            best_score = score
            best_factor = float(factor)
            best_region = blended
            best_metrics = (correlation, brightness_diff)

    return best_region, best_factor, best_score, best_metrics


def _select_inpaint_cleanup(image, x, y, roi, alpha_map):
    best_patch = roi.copy()
    best_combined_score = float("inf")
    best_threshold = _INPAINT_ALPHA_THRESHOLDS[0]
    best_metrics = (0.0, 0.0)
    best_border_score = 0.0

    for threshold in _INPAINT_ALPHA_THRESHOLDS:
        mask = (alpha_map >= threshold).astype(np.uint8) * 255
        mask = cv2.GaussianBlur(mask, (5, 5), 0)
        mask = cv2.dilate(
            mask,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
            iterations=1,
        )
        patch = cv2.inpaint(roi, mask, 3, cv2.INPAINT_TELEA)
        correlation, brightness_diff = _candidate_metrics(patch, alpha_map)
        artifact_score = _artifact_score(correlation, brightness_diff)
        border_score = _border_score(image, x, y, patch)
        combined_score = artifact_score + border_score * 0.5
        if combined_score < best_combined_score:
            best_patch = patch
            best_combined_score = combined_score
            best_threshold = threshold
            best_metrics = (correlation, brightness_diff)
            best_border_score = border_score

    return best_patch, best_threshold, best_combined_score, best_metrics, best_border_score


def _should_prefer_inpaint(candidate, roi):
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.float32)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1].astype(np.float32)
    sat_mean = float(np.mean(saturation))
    sat_std = float(np.std(saturation))
    gray_std = float(np.std(gray))

    return (
        (
            candidate["edge_density"] <= 0.08
            and sat_mean <= 55.0
            and sat_std <= 22.0
        )
        or (
            candidate["edge_density"] <= 0.08
            and candidate["brightness_diff"] <= 28.0
            and gray_std <= 18.0
            and sat_std <= 25.0
        )
    )


def _evaluate_candidate_pattern(image, x, y, patch, alpha_map, original_residue_gap):
    correlation, brightness_diff = _candidate_metrics(patch, alpha_map)
    residue_correlation, residue_gap = _pattern_residue_metrics(patch, alpha_map)
    border_score = _border_score(image, x, y, patch)
    improvement = original_residue_gap - residue_gap

    score = (
        residue_gap * 3.0
        + residue_correlation * 2.0
        + border_score * 0.35
        + max(0.0, correlation - 0.35) * 0.5
        + max(0.0, brightness_diff - 2.0) / 16.0
    )
    verified = (
        residue_gap <= 0.75
        and improvement >= 0.75
        and border_score <= 1.20
    )

    return {
        "score": score,
        "verified": verified,
        "correlation": correlation,
        "brightness_diff": brightness_diff,
        "residue_correlation": residue_correlation,
        "residue_gap": residue_gap,
        "border_score": border_score,
        "improvement": improvement,
    }


def remove_watermark(filepath: str) -> bool:
    """Remove the Gemini watermark from *filepath* in-place.

    Returns True when the file was handled successfully. Clean images are left
    untouched so repeated passes do not recompress or damage them.
    """

    try:
        image = cv2.imread(filepath)
        if image is None:
            logger.warning("Could not read image: {}", filepath)
            return False

        height, width = image.shape[:2]
        preferred_size = _remover.get_watermark_size(width, height)
        sizes_to_try = [preferred_size]
        if preferred_size == WatermarkSize.SMALL:
            sizes_to_try.append(WatermarkSize.LARGE)
        else:
            sizes_to_try.append(WatermarkSize.SMALL)

        best_candidate = None
        for size in sizes_to_try:
            alpha_map = _alpha_map_for_size(size)
            if alpha_map is None:
                continue

            logo_h, logo_w = alpha_map.shape
            if height < logo_h or width < logo_w:
                continue

            candidate = _locate_watermark(image, size, alpha_map)
            if candidate is None:
                continue

            if best_candidate is None:
                best_candidate = candidate
                continue

            current_strength = (
                candidate["template_score"] * 100.0 + candidate["brightness_diff"]
            )
            best_strength = (
                best_candidate["template_score"] * 100.0 + best_candidate["brightness_diff"]
            )
            if current_strength > best_strength:
                best_candidate = candidate

        if not _is_confident_match(best_candidate):
            logger.info("No Gemini watermark detected: {}", filepath)
            return True

        x = best_candidate["x"]
        y = best_candidate["y"]
        roi = image[y:y + best_candidate["height"], x:x + best_candidate["width"]]
        ext = filepath.rsplit(".", 1)[-1].lower()
        original_residue_correlation, original_residue_gap = _pattern_residue_metrics(
            roi,
            best_candidate["alpha_map"],
        )

        if original_residue_gap < 0.75:
            logger.info("No Gemini watermark pattern verified: {}", filepath)
            return True

        candidates = []

        min_factor = 0.30
        if ext in ("jpg", "jpeg") and best_candidate["brightness_diff"] < 25.0:
            min_factor = 0.55
        reverse_roi, blend_factor, _, _ = _select_cleanup(
            roi,
            best_candidate["alpha_map"],
            min_factor=min_factor,
        )
        reverse_eval = _evaluate_candidate_pattern(
            image,
            x,
            y,
            reverse_roi,
            best_candidate["alpha_map"],
            original_residue_gap,
        )
        candidates.append(
            {
                "method": "reverse",
                "detail": f"blend={blend_factor:.2f}",
                "patch": reverse_roi,
                "eval": reverse_eval,
            }
        )

        if _should_prefer_inpaint(best_candidate, roi) or reverse_eval["verified"] is False:
            inpaint_roi, threshold, _, _, _ = _select_inpaint_cleanup(
                image,
                x,
                y,
                roi,
                best_candidate["alpha_map"],
            )
            inpaint_eval = _evaluate_candidate_pattern(
                image,
                x,
                y,
                inpaint_roi,
                best_candidate["alpha_map"],
                original_residue_gap,
            )
            candidates.append(
                {
                    "method": "inpaint",
                    "detail": f"threshold={threshold:.2f}",
                    "patch": inpaint_roi,
                    "eval": inpaint_eval,
                }
            )

        verified_candidates = [candidate for candidate in candidates if candidate["eval"]["verified"]]
        if verified_candidates:
            best_output = min(verified_candidates, key=lambda candidate: candidate["eval"]["score"])
        else:
            best_output = min(candidates, key=lambda candidate: candidate["eval"]["score"])
            if best_output["eval"]["improvement"] < 0.75:
                logger.info(
                    "Skipped low-confidence watermark cleanup: {} (score={:.3f}, residue_gap={:.3f})",
                    filepath,
                    best_candidate["template_score"],
                    best_output["eval"]["residue_gap"],
                )
                return True

        image[y:y + best_candidate["height"], x:x + best_candidate["width"]] = best_output["patch"]

        if ext in ("jpg", "jpeg"):
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            Image.fromarray(rgb_image).save(
                filepath,
                quality=100,
                subsampling=0,
            )
        else:
            cv2.imwrite(filepath, image)

        logger.success(
            "Watermark removed: {} (size={}, score={:.3f}, method={}, {}, residue_gap={:.3f}, residue_corr={:.3f}, border={:.3f}, corr={:.3f}, diff={:.2f})",
            filepath,
            best_candidate["size"].name.lower(),
            best_candidate["template_score"],
            best_output["method"],
            best_output["detail"],
            best_output["eval"]["residue_gap"],
            best_output["eval"]["residue_correlation"],
            best_output["eval"]["border_score"],
            best_output["eval"]["correlation"],
            best_output["eval"]["brightness_diff"],
        )
        return True

    except Exception as exc:
        logger.warning("Watermark removal failed on {}: {}", filepath, exc)
        return False
