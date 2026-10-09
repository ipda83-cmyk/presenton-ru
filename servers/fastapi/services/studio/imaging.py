"""Pillow helpers for the Studio: decoding, upload-size limits, mask compositing."""

import io

from PIL import Image, ImageFilter, ImageOps

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
    soft = dilate(area, grow).filter(ImageFilter.BoxBlur(feather))
    return to_png(Image.composite(redrawn, base, soft))


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
