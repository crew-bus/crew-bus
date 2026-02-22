#!/usr/bin/env python3
"""
Generate macOS app icon PNGs for Crew Bus.

Design: dark circle (#161b22) with subtle blue glow ring (#58a6ff at 30% opacity)
and centered alien emoji.

Outputs icon_16.png through icon_1024.png into the AppIcon.appiconset directory.

Usage:
    pip install Pillow
    python scripts/generate_icon.py
"""

import os
import math
from PIL import Image, ImageDraw, ImageFont

# --- Configuration ---
SIZES = [16, 32, 64, 128, 256, 512, 1024]
BG_COLOR = (22, 27, 34)           # #161b22
GLOW_COLOR = (88, 166, 255)       # #58a6ff
GLOW_OPACITY = 0.30
CIRCLE_RATIO = 0.90               # circle fills 90% of canvas

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
OUTPUT_DIR = os.path.join(
    PROJECT_ROOT,
    "macos", "CrewBus", "Resources",
    "Assets.xcassets", "AppIcon.appiconset",
)


def generate_icon(size: int) -> Image.Image:
    """Generate a single icon at the given pixel size."""
    img = Image.new("RGBA", (size, size), BG_COLOR + (255,))
    draw = ImageDraw.Draw(img)

    cx, cy = size / 2, size / 2
    radius = (size * CIRCLE_RATIO) / 2

    # --- Draw glow rings (multiple concentric semi-transparent rings) ---
    glow_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)

    # Draw several rings outward from the circle edge for a soft glow effect
    num_glow_rings = max(2, size // 32)
    for i in range(num_glow_rings, 0, -1):
        ring_radius = radius + i * max(1, size // 64)
        alpha = int(255 * GLOW_OPACITY * (1 - i / (num_glow_rings + 1)))
        ring_width = max(1, size // 64)
        bbox = [
            cx - ring_radius, cy - ring_radius,
            cx + ring_radius, cy + ring_radius,
        ]
        glow_draw.ellipse(bbox, outline=GLOW_COLOR + (alpha,), width=ring_width)

    img = Image.alpha_composite(img, glow_layer)
    draw = ImageDraw.Draw(img)

    # --- Draw main dark circle ---
    circle_bbox = [
        cx - radius, cy - radius,
        cx + radius, cy + radius,
    ]
    draw.ellipse(circle_bbox, fill=BG_COLOR + (255,))

    # --- Inner glow ring (just inside the circle edge) ---
    inner_glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ig_draw = ImageDraw.Draw(inner_glow)
    ring_width = max(1, size // 48)
    ig_draw.ellipse(circle_bbox, outline=GLOW_COLOR + (int(255 * 0.5),), width=ring_width)
    img = Image.alpha_composite(img, inner_glow)

    # --- Draw alien emoji centered ---
    # Try Apple Color Emoji first (macOS), fall back to other options
    emoji = "\U0001F47D"  # 👽
    font_size = int(size * 0.50)
    font = None

    font_paths = [
        "/System/Library/Fonts/Apple Color Emoji.ttc",
        "/System/Library/Fonts/AppleColorEmoji.ttc",
        "/Library/Fonts/Apple Color Emoji.ttc",
    ]

    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue

    if font is None:
        # Fallback: try by name
        try:
            font = ImageFont.truetype("Apple Color Emoji", font_size)
        except Exception:
            # Last resort: default font (won't render emoji nicely but won't crash)
            print(f"  WARNING: Could not load emoji font for size {size}. Using default.")
            font = ImageFont.load_default()

    # Measure text and center it
    bbox_text = draw.textbbox((0, 0), emoji, font=font)
    tw = bbox_text[2] - bbox_text[0]
    th = bbox_text[3] - bbox_text[1]
    tx = cx - tw / 2 - bbox_text[0]
    ty = cy - th / 2 - bbox_text[1]

    # Draw emoji onto image
    emoji_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    emoji_draw = ImageDraw.Draw(emoji_layer)
    emoji_draw.text((tx, ty), emoji, font=font, embedded_color=True)
    img = Image.alpha_composite(img, emoji_layer)

    return img


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Generating Crew Bus app icons into:\n  {OUTPUT_DIR}\n")

    for size in SIZES:
        icon = generate_icon(size)
        # Convert to RGB for PNG (no transparency in final macOS icon)
        icon_rgb = Image.new("RGB", icon.size, BG_COLOR)
        icon_rgb.paste(icon, mask=icon.split()[3])
        filename = f"icon_{size}.png"
        path = os.path.join(OUTPUT_DIR, filename)
        icon_rgb.save(path, "PNG")
        print(f"  {filename}  ({size}x{size})")

    print(f"\nDone! {len(SIZES)} icons generated.")


if __name__ == "__main__":
    main()
