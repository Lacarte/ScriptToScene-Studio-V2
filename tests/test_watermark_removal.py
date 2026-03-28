import os
import shutil
import tempfile
import unittest
import uuid

import cv2
import numpy as np

from studio.storyboard.watermark import _remover, remove_watermark


class WatermarkRemovalTests(unittest.TestCase):
    def setUp(self):
        self._temp_paths = []

    def tearDown(self):
        while self._temp_paths:
            path = self._temp_paths.pop()
            shutil.rmtree(path, ignore_errors=True)

    def _make_tempdir(self, prefix):
        temp_root = os.path.join(tempfile.gettempdir(), "sts_test_work")
        os.makedirs(temp_root, exist_ok=True)
        path = os.path.join(temp_root, f"{prefix}{uuid.uuid4().hex[:8]}")
        os.makedirs(path, exist_ok=False)
        self._temp_paths.append(path)
        return path

    def _make_base_image(self, low_contrast=False):
        height = 1024
        width = 572
        y = np.linspace(0, 1, height, dtype=np.float32)[:, None]
        x = np.linspace(0, 1, width, dtype=np.float32)[None, :]
        strength = 0.35 if low_contrast else 1.0

        image = np.zeros((height, width, 3), dtype=np.float32)
        image[:, :, 0] = 45 + 90 * x + 40 * y + strength * 18 * np.sin(8 * x + 2 * y)
        image[:, :, 1] = 55 + 70 * (1 - x) + 60 * y + strength * 14 * np.cos(5 * x + 6 * y)
        image[:, :, 2] = 65 + 40 * x + 85 * (1 - y) + strength * 12 * np.sin(3 * x + 9 * y)
        return np.clip(image, 0, 255).astype(np.uint8)

    def _make_smooth_pastel_image(self):
        height = 1024
        width = 572
        y = np.linspace(0, 1, height, dtype=np.float32)[:, None]
        x = np.linspace(0, 1, width, dtype=np.float32)[None, :]

        image = np.zeros((height, width, 3), dtype=np.float32)
        image[:, :, 0] = 230 - 28 * y + 6 * x
        image[:, :, 1] = 208 + 12 * y + 5 * x
        image[:, :, 2] = 188 + 22 * y + 4 * x
        return np.clip(image, 0, 255).astype(np.uint8)

    def _watermark_region(self, image, alpha_map, margin=19, logo_value=255.0):
        result = image.astype(np.float32).copy()
        logo_h, logo_w = alpha_map.shape
        x = result.shape[1] - logo_w - margin
        y = result.shape[0] - logo_h - margin
        roi = result[y:y + logo_h, x:x + logo_w]
        result[y:y + logo_h, x:x + logo_w] = (
            alpha_map[:, :, None] * logo_value
            + (1.0 - alpha_map[:, :, None]) * roi
        )
        return np.clip(result, 0, 255).astype(np.uint8), (x, y)

    def _dark_ghost_region(self, image, alpha_map, margin=19):
        result = image.astype(np.float32).copy()
        logo_h, logo_w = alpha_map.shape
        x = result.shape[1] - logo_w - margin
        y = result.shape[0] - logo_h - margin
        result[y:y + logo_h, x:x + logo_w] -= alpha_map[:, :, None] * 48.0
        return np.clip(result, 0, 255).astype(np.uint8), (x, y)

    def _clean_glow_region(self, image, margin=19):
        result = image.astype(np.float32).copy()
        alpha_map = _remover.alpha_map_small
        logo_h, logo_w = alpha_map.shape
        x = result.shape[1] - logo_w - margin
        y = result.shape[0] - logo_h - margin

        yy, xx = np.mgrid[:logo_h, :logo_w].astype(np.float32)
        center_x = (logo_w - 1) / 2.0
        center_y = (logo_h - 1) / 2.0
        dist = np.sqrt((xx - center_x) ** 2 + (yy - center_y) ** 2)
        glow = np.clip(1.0 - dist / (logo_w * 0.62), 0.0, 1.0) ** 1.6

        result[y:y + logo_h, x:x + logo_w] += glow[:, :, None] * 26.0
        return np.clip(result, 0, 255).astype(np.uint8)

    def _write_png(self, path, image):
        wrote = cv2.imwrite(path, image)
        self.assertTrue(wrote, msg=f"Failed to write test image: {path}")

    def test_remove_watermark_handles_margin_19_exports(self):
        alpha_map = _remover.alpha_map_small
        self.assertIsNotNone(alpha_map)

        for low_contrast in (False, True):
            with self.subTest(low_contrast=low_contrast):
                tempdir = self._make_tempdir("watermark_remove_")
                path = os.path.join(tempdir, "image.png")
                original = self._make_base_image(low_contrast=low_contrast)
                watermarked, (x, y) = self._watermark_region(original, alpha_map)
                self._write_png(path, watermarked)

                self.assertTrue(remove_watermark(path))

                cleaned = cv2.imread(path)
                self.assertIsNotNone(cleaned)
                roi_h, roi_w = alpha_map.shape
                image_mae = np.mean(np.abs(cleaned.astype(np.int16) - original.astype(np.int16)))
                roi_mae = np.mean(
                    np.abs(
                        cleaned[y:y + roi_h, x:x + roi_w].astype(np.int16)
                        - original[y:y + roi_h, x:x + roi_w].astype(np.int16)
                    )
                )
                self.assertLess(image_mae, 0.05)
                self.assertLess(roi_mae, 2.0)

    def test_remove_watermark_prefers_inpaint_for_smooth_pastel_corner(self):
        alpha_map = _remover.alpha_map_small
        self.assertIsNotNone(alpha_map)

        tempdir = self._make_tempdir("watermark_pastel_")
        path = os.path.join(tempdir, "image.png")
        original = self._make_smooth_pastel_image()
        watermarked, (x, y) = self._watermark_region(original, alpha_map)
        self._write_png(path, watermarked)

        self.assertTrue(remove_watermark(path))

        cleaned = cv2.imread(path)
        self.assertIsNotNone(cleaned)
        roi_h, roi_w = alpha_map.shape
        image_mae = np.mean(np.abs(cleaned.astype(np.int16) - original.astype(np.int16)))
        roi_mae = np.mean(
            np.abs(
                cleaned[y:y + roi_h, x:x + roi_w].astype(np.int16)
                - original[y:y + roi_h, x:x + roi_w].astype(np.int16)
            )
        )
        self.assertLess(image_mae, 0.05)
        self.assertLess(roi_mae, 1.5)

    def test_remove_watermark_skips_clean_glow_without_rewriting(self):
        tempdir = self._make_tempdir("watermark_clean_glow_")
        path = os.path.join(tempdir, "image.png")
        clean = self._clean_glow_region(self._make_base_image(low_contrast=False))
        self._write_png(path, clean)
        with open(path, "rb") as handle:
            before = handle.read()

        self.assertTrue(remove_watermark(path))

        with open(path, "rb") as handle:
            after = handle.read()
        self.assertEqual(before, after)

    def test_remove_watermark_skips_dark_ghost_without_rewriting(self):
        alpha_map = _remover.alpha_map_small
        self.assertIsNotNone(alpha_map)

        tempdir = self._make_tempdir("watermark_dark_ghost_")
        path = os.path.join(tempdir, "image.png")
        ghost, _ = self._dark_ghost_region(self._make_base_image(low_contrast=True), alpha_map)
        self._write_png(path, ghost)
        with open(path, "rb") as handle:
            before = handle.read()

        self.assertTrue(remove_watermark(path))

        with open(path, "rb") as handle:
            after = handle.read()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
