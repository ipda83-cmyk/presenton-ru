"""One-off: the interface's Presenton purple becomes KVANTOR green.

    python scripts/brand/rebrand_colors.py [--dry-run]

Rules (servers/nextjs/app and components, interface only):
- a saturated purple (hue 235–300°) becomes a brand green chosen by lightness,
  so text and buttons keep their contrast: light #03B015, mid #02940F,
  dark #027A0E, very dark #01530A;
- a light purple tint (backgrounds, borders) becomes the same-lightness green tint;
- rgb()/rgba() purples likewise (alpha kept);
- Tailwind purple/violet/indigo/fuchsia-N classes become green-N;
- the warm stops of the Presenton gradient become light lime.
Colours of slide content (chart palettes, slide HTML, demo content) are left alone.
"""

import colorsys
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "servers", "nextjs")
FOLDERS = ("app", "components")
EXCLUDED = {
    "components/slide-editor/charts/ChartColorPalette.tsx",
    "components/slide-editor/charts/TemplateV2ChartJsElement.tsx",
    "components/slide-editor/content/demoContent.ts",
}
GREEN_HUE = 125 / 360
WARM_STOPS = {"#F4DCD3": "#E2F7D9", "#FDE4C2": "#F2FADB", "#FFE6A6": "#E9F9C3", "#FCE7D4": "#F1FADF"}


def is_purple(r: float, g: float, b: float) -> bool:
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    # Near-black with a purple cast is still black text.
    return 235 <= hue * 360 <= 300 and sat > 0.35 and light >= 0.2


def green_for(r: float, g: float, b: float) -> tuple[int, int, int]:
    _, light, sat = colorsys.rgb_to_hls(r, g, b)
    if light >= 0.75:
        nr, ng, nb = colorsys.hls_to_rgb(GREEN_HUE, light, min(sat, 1.0) * 0.75)
        return round(nr * 255), round(ng * 255), round(nb * 255)
    if light >= 0.62:
        return 0x03, 0xB0, 0x15
    if light >= 0.55:
        return 0x02, 0x94, 0x0F
    if light >= 0.40:
        return 0x02, 0x7A, 0x0E
    return 0x01, 0x53, 0x0A


HEX = re.compile(r"#([0-9a-fA-F]{6})([0-9a-fA-F]{2})?(?![0-9a-fA-F])")
RGB = re.compile(r"rgba?\(\s*(\d{1,3})(\s*,\s*|\s+)(\d{1,3})(\s*,\s*|\s+)(\d{1,3})")
TAILWIND = re.compile(
    r"\b((?:bg|text|border|ring|from|via|to|fill|stroke|outline|decoration|shadow|accent|caret|divide|placeholder)"
    r"-)(?:purple|violet|indigo|fuchsia)-(\d{2,3})\b"
)


def recolor(text: str) -> tuple[str, int]:
    count = 0

    def hex_sub(match: re.Match) -> str:
        nonlocal count
        value = match.group(1)
        r, g, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
        if not is_purple(r, g, b):
            return match.group(0)
        count += 1
        nr, ng, nb = green_for(r, g, b)
        return f"#{nr:02X}{ng:02X}{nb:02X}{match.group(2) or ''}"

    def rgb_sub(match: re.Match) -> str:
        nonlocal count
        r, g, b = (int(match.group(i)) for i in (1, 3, 5))
        if max(r, g, b) > 255 or not is_purple(r / 255, g / 255, b / 255):
            return match.group(0)
        count += 1
        nr, ng, nb = green_for(r / 255, g / 255, b / 255)
        prefix = match.group(0)[: match.group(0).index("(") + 1]
        space = match.group(0)[match.group(0).index("(") + 1 : match.start(1) - match.start(0)]
        return f"{prefix}{space}{nr}{match.group(2)}{ng}{match.group(4)}{nb}"

    def tailwind_sub(match: re.Match) -> str:
        nonlocal count
        count += 1
        return f"{match.group(1)}green-{match.group(2)}"

    # Warm stops of the Presenton gradient (lilac → pink → peach) become light lime.
    for warm, lime in WARM_STOPS.items():
        text, n = re.subn(re.escape(warm), lime, text, flags=re.IGNORECASE)
        count += n
    text = HEX.sub(hex_sub, text)
    text = RGB.sub(rgb_sub, text)
    text = TAILWIND.sub(tailwind_sub, text)
    return text, count


def main() -> None:
    dry = "--dry-run" in sys.argv
    total = 0
    for folder in FOLDERS:
        for directory, _, names in os.walk(os.path.join(ROOT, folder)):
            for name in names:
                if not name.endswith((".tsx", ".ts", ".css")):
                    continue
                path = os.path.join(directory, name)
                relative = os.path.relpath(path, ROOT).replace(os.sep, "/")
                if relative in EXCLUDED:
                    continue
                with open(path, encoding="utf-8") as handle:
                    original = handle.read()
                updated, count = recolor(original)
                if count:
                    total += count
                    print(f"{count:4d}  {relative}")
                    if not dry:
                        with open(path, "w", encoding="utf-8", newline="") as handle:
                            handle.write(updated)
    print(f"{total} colours {'would change' if dry else 'changed'}")


if __name__ == "__main__":
    main()
