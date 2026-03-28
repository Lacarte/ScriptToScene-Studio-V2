"""Generate overlay PNGs for the ScriptToScene timeline editor (1080×1920, 9:16)."""

import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter

W, H = 1080, 1920
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "resources", "overlays")
os.makedirs(OUT, exist_ok=True)


def save(img, name):
    path = os.path.join(OUT, f"{name}.png")
    img.save(path, "PNG")
    print(f"  + {name}.png ({os.path.getsize(path) // 1024} KB)")


# ── 1. Vignette ──────────────────────────────────────────────
def make_vignette():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cx, cy = W / 2, H / 2
    max_dist = math.sqrt(cx**2 + cy**2)
    pixels = img.load()
    for y in range(H):
        for x in range(W):
            d = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            t = d / max_dist
            # Start fading at 45% from center, full black at edges
            alpha = int(max(0, min(255, (t - 0.45) / 0.55 * 220)))
            pixels[x, y] = (0, 0, 0, alpha)
    return img


# ── 2. Scanlines ─────────────────────────────────────────────
def make_scanlines():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for y in range(0, H, 4):
        draw.line([(0, y), (W, y)], fill=(0, 0, 0, 50), width=2)
    return img


# ── 3. Letterbox (cinematic 2.35:1 bars) ─────────────────────
def make_letterbox():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 2.35:1 within 9:16 → bars at top and bottom
    bar_h = 160
    draw.rectangle([0, 0, W, bar_h], fill=(0, 0, 0, 255))
    draw.rectangle([0, H - bar_h, W, H], fill=(0, 0, 0, 255))
    return img


# ── 4. Dust & Scratches ──────────────────────────────────────
def make_dust_scratches():
    random.seed(42)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dust particles
    for _ in range(300):
        x, y = random.randint(0, W), random.randint(0, H)
        r = random.randint(1, 3)
        a = random.randint(30, 90)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, a))

    # Scratches (vertical-ish lines)
    for _ in range(8):
        x = random.randint(0, W)
        drift = random.randint(-30, 30)
        a = random.randint(20, 60)
        for seg in range(0, H, 2):
            if random.random() > 0.3:
                x += random.randint(-1, 1)
                draw.line([(x, seg), (x + drift // H, seg + 2)], fill=(255, 255, 255, a), width=1)

    # Hair fibers
    for _ in range(5):
        x0 = random.randint(0, W)
        y0 = random.randint(0, H)
        length = random.randint(80, 250)
        angle = random.uniform(-0.3, 0.3)
        a = random.randint(25, 55)
        pts = []
        for i in range(length):
            pts.append((x0 + i * math.cos(angle) + random.uniform(-0.5, 0.5),
                         y0 + i * math.sin(angle) + random.uniform(-0.5, 0.5)))
        for i in range(len(pts) - 1):
            draw.line([pts[i], pts[i + 1]], fill=(255, 255, 255, a), width=1)

    return img


# ── 5. Light Leak (warm amber from top-right) ────────────────
def make_light_leak():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pixels = img.load()
    # Source point: top-right
    sx, sy = W * 0.85, H * 0.08
    max_dist = math.sqrt(W**2 + H**2)
    for y in range(H):
        for x in range(W):
            d = math.sqrt((x - sx) ** 2 + (y - sy) ** 2)
            t = 1.0 - min(d / (max_dist * 0.55), 1.0)
            t = t ** 2.2  # falloff curve
            a = int(t * 100)
            r = int(255 * min(1, t * 1.2))
            g = int(180 * t)
            b = int(80 * t)
            if a > 0:
                pixels[x, y] = (r, g, b, a)
    return img


# ── 6. CRT Monitor ───────────────────────────────────────────
def make_crt():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Horizontal scanlines (RGB sub-pixel feel)
    for y in range(0, H, 6):
        draw.line([(0, y), (W, y)], fill=(0, 0, 0, 35), width=1)
        draw.line([(0, y + 2), (W, y + 2)], fill=(0, 0, 0, 18), width=1)
    # Vignette rim
    cx, cy = W / 2, H / 2
    max_dist = math.sqrt(cx**2 + cy**2)
    pixels = img.load()
    for y in range(H):
        for x in range(W):
            d = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            t = d / max_dist
            edge_alpha = int(max(0, min(255, (t - 0.6) / 0.4 * 180)))
            r, g, b, a = pixels[x, y]
            new_a = min(255, a + edge_alpha)
            pixels[x, y] = (0, 0, 0, new_a)
    return img


# ── 7. Soft Glow Haze ────────────────────────────────────────
def make_glow_haze():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pixels = img.load()
    # Soft white haze from bottom (dreamy/ethereal look)
    for y in range(H):
        t = 1.0 - (y / H)  # 1.0 at top, 0.0 at bottom
        t = 1.0 - t  # flip: 1.0 at bottom
        t = t ** 3  # steep falloff
        a = int(t * 60)
        if a > 0:
            for x in range(W):
                pixels[x, y] = (255, 255, 255, a)
    # Blur it
    img = img.filter(ImageFilter.GaussianBlur(radius=40))
    return img


# ── 8. Film Border (sprocket holes + frame edge) ─────────────
def make_film_border():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    border = 36
    corner_r = 16
    # Outer fill (black film stock)
    draw.rectangle([0, 0, W, H], fill=(15, 12, 10, 255))
    # Inner transparent window with rounded corners
    inner = [border, border + 60, W - border, H - border - 60]
    draw.rounded_rectangle(inner, radius=corner_r, fill=(0, 0, 0, 0))
    # Sprocket holes along top and bottom
    hole_r = 12
    hole_spacing = 90
    for x in range(hole_spacing, W - hole_spacing // 2, hole_spacing):
        # Top row
        draw.rounded_rectangle(
            [x - hole_r, 18, x + hole_r, 18 + hole_r * 2],
            radius=4, fill=(40, 35, 32, 255)
        )
        # Bottom row
        draw.rounded_rectangle(
            [x - hole_r, H - 18 - hole_r * 2, x + hole_r, H - 18],
            radius=4, fill=(40, 35, 32, 255)
        )
    return img


# ── 9. Chromatic Fringe (RGB split on edges) ──────────────────
def make_chromatic_fringe():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pixels = img.load()
    cx, cy = W / 2, H / 2
    max_dist = math.sqrt(cx**2 + cy**2)
    for y in range(H):
        for x in range(W):
            d = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            t = max(0, (d / max_dist - 0.5) / 0.5)  # 0 at center, 1 at edge
            t = t ** 2
            if t > 0.01:
                # Red shifted outward, cyan shifted inward
                angle = math.atan2(y - cy, x - cx)
                a = int(t * 45)
                # Alternate R and C based on angle quadrant
                if (x > cx) != (y > cy):
                    pixels[x, y] = (255, 40, 40, a)
                else:
                    pixels[x, y] = (40, 200, 255, a)
    return img


# ── Generate all ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Generating overlays (1080×1920)...\n")

    generators = [
        ("vignette-dark", make_vignette),
        ("scanlines-subtle", make_scanlines),
        ("letterbox-cinematic", make_letterbox),
        ("dust-and-scratches", make_dust_scratches),
        ("light-leak-amber", make_light_leak),
        ("crt-monitor", make_crt),
        ("glow-haze-bottom", make_glow_haze),
        ("film-border-sprocket", make_film_border),
        ("chromatic-fringe", make_chromatic_fringe),
    ]

    for name, gen in generators:
        img = gen()
        save(img, name)

    print(f"\nDone — {len(generators)} overlays written to {OUT}")
