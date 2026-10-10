"""Pillow helpers for the Studio: decoding, upload-size limits, mask compositing."""

import io

from PIL import Image, ImageFilter, ImageOps, ImageStat

# arckep /uploads accepts about 10 MB; keep a margin.
UPLOAD_LIMIT_BYTES = 9 * 1024 * 1024
UPLOAD_MAX_SIDE = 2048
MAX_SOURCE_PIXELS = 40_000_000  # refuse decompression bombs


class InvalidImageError(ValueError):
    pass


def open_image(data: bytes) -> Image.Image:
    """Decode any supported format, applying EXIF rotation."""
    try:
        image = Image.open(io.BytesIO(data))
        if image.width * image.height > MAX_SOURCE_PIXELS:
            raise InvalidImageError("image is too large")
        image.load()
    except InvalidImageError:
        raise
    except Exception as error:  # PIL raises many types for broken input
        raise InvalidImageError(str(error)) from error
    return ImageOps.exif_transpose(image)


def to_png(image: Image.Image) -> bytes:
    if image.mode not in ("RGB", "RGBA", "L", "LA"):
        image = image.convert("RGBA")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def png_bytes(data: bytes) -> bytes:
    return to_png(open_image(data))


def image_size(data: bytes) -> tuple[int, int]:
    image = open_image(data)
    return image.width, image.height


def fit_for_upload(data: bytes) -> bytes:
    """PNG no larger than the upload limit (longest side capped)."""
    image = open_image(data)
    encoded = to_png(image)
    if len(encoded) <= UPLOAD_LIMIT_BYTES and max(image.size) <= UPLOAD_MAX_SIDE:
        return encoded
    scale = min(1.0, UPLOAD_MAX_SIDE / max(image.size))
    while True:
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        encoded = to_png(image.resize(size, Image.LANCZOS))
        if len(encoded) <= UPLOAD_LIMIT_BYTES or scale < 0.1:
            return encoded
        scale *= 0.8


def resize_png(data: bytes, size: tuple[int, int]) -> bytes:
    image = open_image(data)
    if image.size == size:
        return to_png(image)
    return to_png(image.resize(size, Image.LANCZOS))


def pick_gpt_size(width: int, height: int) -> tuple[str, tuple[int, int]]:
    """Closest gpt-image size to the image's aspect ratio."""
    ratio = width / max(1, height)
    if ratio > 1.2:
        return "1536x1024", (1536, 1024)
    if ratio < 1 / 1.2:
        return "1024x1536", (1024, 1536)
    return "1024x1024", (1024, 1024)


def mask_edit_area(mask: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Binary L map of the area to change: transparent mask pixels (alpha < 128),
    as the Studio brush draws them; a mask without alpha uses white = change."""
    mask = mask.resize(size, Image.NEAREST) if mask.size != size else mask
    if mask.mode in ("RGBA", "LA") or "transparency" in mask.info:
        alpha = mask.convert("RGBA").getchannel("A")
        return alpha.point(lambda value: 255 if value < 128 else 0)
    return mask.convert("L").point(lambda value: 255 if value >= 128 else 0)


def compose_masked(original: bytes, result: bytes, mask: bytes) -> bytes:
    """Keep the original outside the brushed area, with a generous soft edge.

    Models often redraw the whole frame; this guarantees pixels outside the
    selection stay untouched. Same rules as the standalone Studio: the
    selection grows by ~1.2x its size (48 px .. half the shorter side) so a
    redrawn object fits, then a feather of ~0.4x that.
    """
    base = open_image(original).convert("RGB")
    size = base.size
    redrawn = open_image(result).convert("RGB")
    if redrawn.size != size:
        redrawn = redrawn.resize(size, Image.LANCZOS)
    area = mask_edit_area(open_image(mask), size)
    box = area.getbbox()
    if not box:
        return to_png(base)

    selection = max(box[2] - box[0], box[3] - box[1])
    grow = round(min(max(selection * 1.2, 48), min(size) * 0.5))
    feather = round(max(grow * 0.4, 20))
    grown = dilate(area, grow)
    soft = grown.filter(ImageFilter.BoxBlur(feather))
    redrawn = match_tone(redrawn, base, grown)
    return to_png(Image.composite(redrawn, base, soft))


TONE_SAMPLE_SIDE = 512
TONE_MIN_SHARE = 0.02  # of the frame, outside the edit, to trust the estimate
TONE_MAX_SHIFT = 24  # larger gaps are a different picture, not drift
TONE_GAIN_RANGE = (0.9, 1.1)
TONE_MIN_SPREAD = 12  # flat areas give no contrast information


def match_tone(redrawn: Image.Image, base: Image.Image, edit: Image.Image) -> Image.Image:
    """Undo a global colour drift of the redrawn frame.

    Models re-render the whole frame and often shift its tone slightly; across
    the wide blended edge that shows as a halo around the edit. Per channel,
    the redrawn frame's mean (and, where there is contrast, its spread) is
    fitted to the original outside the edit area, where both should match.
    A large gap there means the model redrew the scene; that is left as is.
    """
    scale = TONE_SAMPLE_SIDE / max(base.size)
    small = (max(1, round(base.width * scale)), max(1, round(base.height * scale)))
    keep = edit.resize(small, Image.NEAREST).point(lambda value: 0 if value else 255)
    if keep.histogram()[255] < TONE_MIN_SHARE * small[0] * small[1]:
        return redrawn
    want = ImageStat.Stat(base.resize(small, Image.BOX), keep)
    have = ImageStat.Stat(redrawn.resize(small, Image.BOX), keep)
    if any(abs(target - current) > TONE_MAX_SHIFT for target, current in zip(want.mean, have.mean)):
        return redrawn
    tables: list[int] = []
    for target, target_spread, current, current_spread in zip(
        want.mean, want.stddev, have.mean, have.stddev
    ):
        gain = 1.0
        if min(target_spread, current_spread) >= TONE_MIN_SPREAD:
            gain = min(max(target_spread / current_spread, TONE_GAIN_RANGE[0]), TONE_GAIN_RANGE[1])
        tables.extend(
            min(255, max(0, round((value - current) * gain + target)))
            for value in range(256)
        )
    return redrawn.point(tables)


def dilate(area: Image.Image, radius: int) -> Image.Image:
    """Grow a binary L map by about `radius` pixels.

    Done on a reduced copy so the max filter stays small (its cost grows with
    the square of the window); a blur would fade thin brush strokes to zero
    at large radii instead of growing them.
    """
    if radius <= 0:
        return area
    width, height = area.size
    factor = max(1, radius // 6)
    small = area.resize(
        (max(1, width // factor), max(1, height // factor)), Image.BOX
    ).point(lambda value: 255 if value > 0 else 0)
    window = 2 * max(1, round(radius / factor)) + 1
    small = small.filter(ImageFilter.MaxFilter(window))
    return small.resize((width, height), Image.NEAREST)
