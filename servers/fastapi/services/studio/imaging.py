"""Pillow helpers for the Studio: decoding, upload-size limits, mask compositing."""

import io

import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageOps, ImageStat

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


# The edge around the area taken from the redrawn frame.
SEAM_SHARE = 0.012  # of the shorter side
SEAM_MIN = 6  # px
SEAM_FEATHER = 0.7  # of that edge: the blur stays outside the brush


def compose_masked(original: bytes, result: bytes, mask: bytes) -> bytes:
    """Keep the original outside the brushed area, with a narrow soft edge.

    Models redraw the whole frame and often shift or zoom it a little, so a wide
    blend of the two frames shows as a ghost over the picture. The redrawn frame
    is first aligned to the original; the area taken from it is the brush plus
    what really changed next to it (a longer inscription fits), never more than
    ~1.2x the selection around the brush (48 px .. half the shorter side).
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
    reach = dilate(area, round(min(max(selection * 1.2, 48), min(size) * 0.5)))
    redrawn, inside = align_frame(redrawn, base, area)
    redrawn = match_tone(redrawn, base, ImageChops.lighter(reach, ImageChops.invert(inside)))

    edge = max(SEAM_MIN, round(min(size) * SEAM_SHARE))
    taken = dilate(changed_next_to(area, redrawn, base, reach), edge)
    soft = taken.filter(ImageFilter.BoxBlur(max(2, round(edge * SEAM_FEATHER))))
    return to_png(Image.composite(redrawn, base, ImageChops.multiply(soft, inside)))


CHANGE_SIDE = 512
CHANGE_LEVEL = 28  # of 255, after a slight blur: redrawn texture stays below it
CHANGE_MAX_ELSEWHERE = 0.4  # that much changed far from the brush: another scene
CHANGE_BRIDGE = 9  # px of CHANGE_SIDE, window of the filter


def changed_next_to(
    area: Image.Image, redrawn: Image.Image, base: Image.Image, reach: Image.Image
) -> Image.Image:
    """The brush plus the changes connected to it inside `reach` (binary L map)."""
    scale = min(1.0, CHANGE_SIDE / max(base.size))
    small = (max(1, round(base.width * scale)), max(1, round(base.height * scale)))

    def pixels(image: Image.Image) -> np.ndarray:
        blurred = image.resize(small, Image.BOX).filter(ImageFilter.GaussianBlur(1.5))
        return np.asarray(blurred, dtype=np.int16)

    changed = np.abs(pixels(redrawn) - pixels(base)).max(axis=2) > CHANGE_LEVEL
    near = np.asarray(reach.resize(small, Image.NEAREST)) > 0
    if changed[~near].size and changed[~near].mean() > CHANGE_MAX_ELSEWHERE:
        return area
    seed = np.asarray(area.resize(small, Image.BOX)) > 0
    # Bridged a little: the letters of a longer inscription are not touching.
    bridged = Image.fromarray(np.uint8(changed) * 255).filter(ImageFilter.MaxFilter(CHANGE_BRIDGE))
    allowed = (np.asarray(bridged) > 0) & near
    region = seed.copy()
    for _ in range(max(small)):
        grown = region.copy()
        grown[1:] |= region[:-1]
        grown[:-1] |= region[1:]
        grown[:, 1:] |= region[:, :-1]
        grown[:, :-1] |= region[:, 1:]
        grown = (grown & allowed) | seed
        if np.array_equal(grown, region):
            break
        region = grown
    extra = Image.fromarray(np.uint8(region) * 255).resize(base.size, Image.NEAREST)
    return ImageChops.lighter(area, extra)


ALIGN_COARSE_SIDE = 192
ALIGN_FINE_SIDE = 1024
ALIGN_MAX_SHIFT = 0.1  # of the frame
ALIGN_MIN_CONTRAST = 6.0  # flat patches say nothing about position
ALIGN_MIN_MATCH = 0.6  # normalized correlation
ALIGN_MIN_PATCHES = 8
ALIGN_SCALE_RANGE = (0.85, 1.2)
ALIGN_MIN_GAIN = 0.9  # the mismatch outside the brush must really drop


def align_frame(
    redrawn: Image.Image, base: Image.Image, area: Image.Image
) -> tuple[Image.Image, Image.Image]:
    """The redrawn frame moved onto the original, and an L map of where it has
    pixels. A frame that cannot be matched (flat, or another scene) stays as is."""
    everywhere = Image.new("L", base.size, 255)
    margin = dilate(area, max(SEAM_MIN, round(min(base.size) * 0.05)))
    keep = ImageChops.invert(margin)

    coarse_base = _gray(base, ALIGN_COARSE_SIDE)
    coarse = _fit_shift(
        coarse_base,
        _gray(redrawn, ALIGN_COARSE_SIDE),
        _kept(keep, ALIGN_COARSE_SIDE),
        patch=16,
        stride=12,
        radius=max(2, round(ALIGN_COARSE_SIDE * ALIGN_MAX_SHIFT)),
    )
    if coarse is None:
        return redrawn, everywhere
    fine_base = _gray(base, ALIGN_FINE_SIDE)
    ratio = fine_base.shape[1] / coarse_base.shape[1]
    fine = _fit_shift(
        fine_base,
        _gray(redrawn, ALIGN_FINE_SIDE),
        _kept(keep, ALIGN_FINE_SIDE),
        patch=32,
        stride=40,
        radius=max(4, round(ratio * 2)),
        guess=(coarse[0], coarse[1], coarse[2] * ratio, coarse[3] * ratio),
    )
    if fine is None:
        return redrawn, everywhere
    scale_x, scale_y, shift_x, shift_y = fine
    if not all(ALIGN_SCALE_RANGE[0] <= value <= ALIGN_SCALE_RANGE[1] for value in (scale_x, scale_y)):
        return redrawn, everywhere
    to_full = base.width / fine_base.shape[1]
    data = (scale_x, 0, shift_x * to_full, 0, scale_y, shift_y * to_full)
    moved = redrawn.transform(base.size, Image.AFFINE, data, Image.BICUBIC)
    inside = everywhere.transform(base.size, Image.AFFINE, data, Image.NEAREST)

    usable = _kept(ImageChops.multiply(keep, inside), CHANGE_SIDE)
    if not usable.any():
        return redrawn, everywhere
    plain = _gray(base, CHANGE_SIDE)
    before = np.abs(plain - _gray(redrawn, CHANGE_SIDE))[usable].mean()
    after = np.abs(plain - _gray(moved, CHANGE_SIDE))[usable].mean()
    if after >= before * ALIGN_MIN_GAIN:
        return redrawn, everywhere
    return moved, inside


def _gray(image: Image.Image, side: int) -> np.ndarray:
    scale = min(1.0, side / max(image.size))
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return np.asarray(image.convert("L").resize(size, Image.BOX), dtype=np.float32)


def _kept(mask: Image.Image, side: int) -> np.ndarray:
    scale = min(1.0, side / max(mask.size))
    size = (max(1, round(mask.width * scale)), max(1, round(mask.height * scale)))
    return np.asarray(mask.resize(size, Image.BOX)) == 255


def _fit_shift(
    base: np.ndarray,
    other: np.ndarray,
    keep: np.ndarray,
    *,
    patch: int,
    stride: int,
    radius: int,
    guess: tuple[float, float, float, float] = (1.0, 1.0, 0.0, 0.0),
) -> tuple[float, float, float, float] | None:
    """Scale and shift (x' = sx * x + tx, y' = sy * y + ty) from `base` to `other`:
    patches outside the edit are searched for, wrong matches are fitted away."""
    height, width = base.shape
    sx, sy, tx, ty = guess
    points: list[tuple[float, float, float, float]] = []
    for top in range(0, height - patch + 1, stride):
        for left in range(0, width - patch + 1, stride):
            if not keep[top : top + patch, left : left + patch].all():
                continue
            piece = base[top : top + patch, left : left + patch]
            spread = piece.std()
            if spread < ALIGN_MIN_CONTRAST:
                continue
            start_x = round(sx * left + tx) - radius
            start_y = round(sy * top + ty) - radius
            x0, y0 = max(0, start_x), max(0, start_y)
            x1 = min(width, start_x + 2 * radius + patch)
            y1 = min(height, start_y + 2 * radius + patch)
            if x1 - x0 < patch or y1 - y0 < patch:
                continue
            windows = np.lib.stride_tricks.sliding_window_view(other[y0:y1, x0:x1], (patch, patch))
            means = windows.mean(axis=(2, 3), keepdims=True)
            scores = ((windows - means) * (piece - piece.mean())).mean(axis=(2, 3))
            scores = scores / np.maximum(windows.std(axis=(2, 3)) * spread, 1e-3)
            row, column = np.unravel_index(int(scores.argmax()), scores.shape)
            if scores[row, column] < ALIGN_MIN_MATCH:
                continue
            found_x = x0 + column
            found_y = y0 + row
            if 0 < column < scores.shape[1] - 1:
                found_x += _peak_offset(scores[row, column - 1 : column + 2])
            if 0 < row < scores.shape[0] - 1:
                found_y += _peak_offset(scores[row - 1 : row + 2, column])
            points.append((left, top, float(found_x), float(found_y)))
    if len(points) < ALIGN_MIN_PATCHES:
        return None
    table = np.array(points, dtype=np.float64)
    fitted_x = _robust_line(table[:, 0], table[:, 2])
    fitted_y = _robust_line(table[:, 1], table[:, 3])
    if fitted_x is None or fitted_y is None:
        return None
    return fitted_x[0], fitted_y[0], fitted_x[1], fitted_y[1]


def _peak_offset(values: np.ndarray) -> float:
    """Sub-pixel position of a peak from it and its two neighbours."""
    left, middle, right = (float(value) for value in values)
    bend = left - 2 * middle + right
    return 0.0 if abs(bend) < 1e-6 else max(-0.5, min(0.5, 0.5 * (left - right) / bend))


def _robust_line(source: np.ndarray, target: np.ndarray) -> tuple[float, float] | None:
    """target = scale * source + shift, dropping matches far from the common one."""
    used = np.ones(source.shape, dtype=bool)
    scale = shift = 0.0
    for _ in range(5):
        if used.sum() < ALIGN_MIN_PATCHES or np.ptp(source[used]) == 0:
            return None
        scale, shift = np.polyfit(source[used], target[used], 1)
        errors = np.abs(target - (scale * source + shift))
        used = errors <= max(1.0, 2.5 * float(np.median(errors[used])))
    if used.sum() < max(ALIGN_MIN_PATCHES, 0.3 * source.size):
        return None
    return float(scale), float(shift)


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
