"""Pixel-level PNG comparison for Visual Conformance (Pillow)."""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageChops, ImageDraw

from governed_ai.core.design_authority.hashing import sha256_bytes


@dataclass(slots=True)
class PixelCompareResult:
    diff_ratio: float
    differing_pixels: int
    total_unmasked: int
    reference_hash: str
    observed_hash: str
    reference_dimensions: tuple[int, int]
    observed_dimensions: tuple[int, int]
    dimensions_match: bool
    resized: bool
    masked_regions_applied: list[dict[str, Any]]
    diff_image_bytes: bytes | None
    blocking_reason: str | None = None


def _decode_png(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image.convert("RGBA")


def _parse_rect(region: Any) -> dict[str, int] | None:
    if not isinstance(region, dict):
        return None
    x = region.get("x", region.get("left"))
    y = region.get("y", region.get("top"))
    w = region.get("width", region.get("w"))
    h = region.get("height", region.get("h"))
    if None in (x, y, w, h):
        return None
    try:
        return {
            "x": int(x),
            "y": int(y),
            "width": max(0, int(w)),
            "height": max(0, int(h)),
        }
    except (TypeError, ValueError):
        return None


def _build_mask(
    size: tuple[int, int],
    masked_regions: list[Any] | None,
) -> tuple[Image.Image, list[dict[str, Any]]]:
    """Return an L-mode mask (255 = compare, 0 = ignore) and applied region meta."""
    width, height = size
    mask = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(mask)
    applied: list[dict[str, Any]] = []
    for region in masked_regions or []:
        rect = _parse_rect(region)
        if rect is None:
            applied.append(
                {
                    "region": region,
                    "applied": False,
                    "reason": "selector_or_invalid_rect_not_maskable",
                }
            )
            continue
        x0 = max(0, rect["x"])
        y0 = max(0, rect["y"])
        x1 = min(width, rect["x"] + rect["width"])
        y1 = min(height, rect["y"] + rect["height"])
        if x1 > x0 and y1 > y0:
            draw.rectangle([x0, y0, x1 - 1, y1 - 1], fill=0)
            applied.append({**rect, "applied": True})
        else:
            applied.append({**rect, "applied": False, "reason": "outside_image_bounds"})
    return mask, applied


def compare_png_pixels(
    *,
    reference_png: bytes,
    observed_png: bytes,
    masked_regions: list[Any] | None = None,
    allow_resize: bool = False,
    difference_threshold: float | None = None,
) -> PixelCompareResult:
    """Compare two PNG payloads; return ratio over unmasked pixels.

    Dimension mismatch is blocking unless ``allow_resize`` is True (then the
    observed image is resized to the reference size before differencing).
    """
    ref_hash = sha256_bytes(reference_png)
    obs_hash = sha256_bytes(observed_png)
    reference = _decode_png(reference_png)
    observed = _decode_png(observed_png)
    ref_size = reference.size
    obs_size = observed.size
    dimensions_match = ref_size == obs_size
    resized = False

    if not dimensions_match and not allow_resize:
        return PixelCompareResult(
            diff_ratio=1.0,
            differing_pixels=0,
            total_unmasked=0,
            reference_hash=ref_hash,
            observed_hash=obs_hash,
            reference_dimensions=ref_size,
            observed_dimensions=obs_size,
            dimensions_match=False,
            resized=False,
            masked_regions_applied=[],
            diff_image_bytes=None,
            blocking_reason="dimension_mismatch",
        )

    if not dimensions_match and allow_resize:
        observed = observed.resize(ref_size, Image.Resampling.NEAREST)
        resized = True

    mask, applied = _build_mask(ref_size, masked_regions)
    diff = ImageChops.difference(reference, observed)
    # Flatten alpha: treat any channel delta as a differing pixel.
    bands = diff.split()
    intensity = bands[0]
    for band in bands[1:]:
        intensity = ImageChops.lighter(intensity, band)

    # Pixels where mask==0 are ignored (forced equal).
    intensity = ImageChops.composite(
        intensity, Image.new("L", ref_size, 0), mask
    )

    # Count differing unmasked pixels (intensity > 0).
    differing = 0
    total_unmasked = 0
    mask_px = mask.load()
    inten_px = intensity.load()
    width, height = ref_size
    for y in range(height):
        for x in range(width):
            if mask_px[x, y] == 0:
                continue
            total_unmasked += 1
            if inten_px[x, y] > 0:
                differing += 1

    ratio = 0.0 if total_unmasked == 0 else differing / float(total_unmasked)
    buf = io.BytesIO()
    # Visualize: red where different and unmasked.
    vis = Image.new("RGBA", ref_size, (0, 0, 0, 0))
    vis_px = vis.load()
    for y in range(height):
        for x in range(width):
            if mask_px[x, y] == 0:
                continue
            if inten_px[x, y] > 0:
                vis_px[x, y] = (255, 0, 0, 180)
    vis.save(buf, format="PNG")
    diff_bytes = buf.getvalue()

    blocking = None
    if difference_threshold is not None and ratio > float(difference_threshold):
        blocking = "diff_exceeds_threshold"

    return PixelCompareResult(
        diff_ratio=ratio,
        differing_pixels=differing,
        total_unmasked=total_unmasked,
        reference_hash=ref_hash,
        observed_hash=obs_hash,
        reference_dimensions=ref_size,
        observed_dimensions=obs_size,
        dimensions_match=dimensions_match,
        resized=resized,
        masked_regions_applied=applied,
        diff_image_bytes=diff_bytes,
        blocking_reason=blocking,
    )
