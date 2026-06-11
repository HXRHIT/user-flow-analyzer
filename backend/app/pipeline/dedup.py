"""Step 2 - keyframe selection: perceptual-hash dedup + blank (secure) frame detection.

Financial/banking apps block OS screen capture on password screens, which shows up
as (near-)black frames. We label those instead of discarding them so the timeline
can show a "secure section".
"""
from PIL import Image, ImageStat
import imagehash

from .. import config
from ..models import Frame

BLANK_BRIGHTNESS = 12  # 0-255 mean brightness below which a frame is "blank/secure"
COLOR_DISTANCE = 25    # max per-channel RGB delta that still counts as "same screen"


def _is_blank(img: Image.Image) -> bool:
    return ImageStat.Stat(img.convert("L")).mean[0] < BLANK_BRIGHTNESS


def _mean_rgb(img: Image.Image) -> tuple[float, float, float]:
    r, g, b = ImageStat.Stat(img.convert("RGB")).mean
    return (r, g, b)


def _color_delta(a: tuple, b: tuple) -> float:
    return max(abs(x - y) for x, y in zip(a, b))


def select_keyframes(frames: list[Frame]) -> list[Frame]:
    """Keep a frame only when it differs enough from the last kept frame.

    pHash captures structural change; a mean-color check catches frames that share
    structure but differ in color (pHash of flat regions collapses to the same hash).
    """
    kept: list[Frame] = []
    last_hash = None
    last_color = None
    for f in frames:
        with Image.open(f.path) as img:
            blank = _is_blank(img)
            h = imagehash.phash(img)
            color = _mean_rgb(img)
        f.phash = str(h)
        f.is_blank = blank
        if blank:
            # keep at most one blank frame per contiguous secure section
            if kept and kept[-1].is_blank:
                continue
            kept.append(f)
            last_hash = None
            last_color = None
            continue
        if (
            last_hash is not None
            and (h - last_hash) <= config.PHASH_DISTANCE
            and _color_delta(color, last_color) <= COLOR_DISTANCE
        ):
            continue
        kept.append(f)
        last_hash = h
        last_color = color
    return kept
