"""One-off: purple interface pictures in servers/nextjs/public become green.

    python scripts/brand/rebrand_images.py

SVG colours follow the same rules as rebrand_colors.py. In PNG/JPG pictures
hues near purple are shifted towards the brand green, smoothly (full shift at
265°, none beyond ±75°), with lightness and alpha kept. Third-party marks (Discord, provider logos) stay.
"""

import colorsys
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from rebrand_colors import GREEN_HUE, recolor  # noqa: E402

PUBLIC = os.path.join(os.path.dirname(__file__), "..", "..", "servers", "nextjs", "public")
SKIP_DIRS = ("vendor", "providers", "brand")
SKIP_FILES = {
    "discord.png",
    "discord.svg",
    # Pictures of sample presentations and confetti: content, not the brand.
    "create_presentation_card_1.png",
    "create_presentation_card_2.png",
    "create_presentation_card_3.png",
    "report.png",
    "left-confetti.png",
    "right-confetti.png",
}
RASTER = (".png", ".jpg", ".jpeg")
PURPLE_CENTER = 265.0
FALLOFF = 75.0


def recolor_raster(path: str) -> int:
    image = Image.open(path)
    mode = image.mode
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    changed = 0
    for y in range(rgba.height):
        for x in range(rgba.width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            hue, light, sat = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
            if sat < 0.08:
                continue
            # Smooth: full shift at purple (265°), none beyond ±75°, so soft
            # gradients in illustrations stay soft (no hard hue edges).
            distance = abs((hue * 360 - PURPLE_CENTER + 180) % 360 - 180)
            weight = max(0.0, 1 - distance / FALLOFF) ** 1.5
            if weight <= 0:
                continue
            new_hue = (hue * 360 + weight * (GREEN_HUE * 360 - PURPLE_CENTER)) % 360 / 360
            nr, ng, nb = colorsys.hls_to_rgb(new_hue, light, sat * (1 - 0.15 * weight))
            pixels[x, y] = (round(nr * 255), round(ng * 255), round(nb * 255), a)
            changed += 1
    if changed:
        (rgba if mode in ("RGBA", "LA", "P") else rgba.convert("RGB")).save(path)
    return changed


def main() -> None:
    for directory, dirs, names in os.walk(PUBLIC):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            if name in SKIP_FILES:
                continue
            path = os.path.join(directory, name)
            relative = os.path.relpath(path, PUBLIC)
            if name.endswith(".svg"):
                with open(path, encoding="utf-8") as handle:
                    original = handle.read()
                updated, count = recolor(original)
                if count:
                    with open(path, "w", encoding="utf-8", newline="") as handle:
                        handle.write(updated)
                    print(f"svg {count:4d}  {relative}")
            elif name.lower().endswith(RASTER):
                count = recolor_raster(path)
                if count:
                    print(f"img {count:7d}  {relative}")


if __name__ == "__main__":
    main()
