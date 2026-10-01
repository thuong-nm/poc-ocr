"""Image loading (EXIF rotation, HEIC) and quality assessment. Never fails silently: emits warnings."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from .config import QACfg
from .schema import QAReport

log = logging.getLogger(__name__)

try:  # HEIC/HEIF support (iPhone photos)
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:  # pragma: no cover
    HEIF_OK = False


class ImageLoadError(RuntimeError):
    pass


@dataclass
class LoadedImage:
    bgr: np.ndarray
    sha256: str
    orig_size: tuple[int, int]  # (w, h) after EXIF transpose, before downscale
    scale: float  # applied downscale factor
    warnings: list[str]


def load_image(path: str | Path, max_side: int = 5000) -> LoadedImage:
    path = Path(path)
    if not path.exists():
        raise ImageLoadError(f"file not found: {path}")
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    warnings: list[str] = []
    if path.suffix.lower() in (".heic", ".heif") and not HEIF_OK:
        raise ImageLoadError("HEIC input requires pillow-heif, which is not installed")
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)  # honour camera orientation tag
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            if im.mode == "L":
                im = im.convert("RGB")
            rgb = np.asarray(im)
    except Exception as e:
        raise ImageLoadError(f"cannot decode image {path}: {e}") from e
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    scale = 1.0
    if max(h, w) > max_side:
        scale = max_side / max(h, w)
        bgr = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        warnings.append(f"image downscaled from {w}x{h} by {scale:.2f} (max_image_side={max_side})")
    return LoadedImage(bgr=bgr, sha256=sha, orig_size=(w, h), scale=scale, warnings=warnings)


def blur_variance(bgr: np.ndarray, ref_long_side: int = 1600) -> float:
    """Variance of the Laplacian on a resolution-normalized grayscale image (higher = sharper)."""
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr
    s = ref_long_side / max(g.shape[:2])
    g = cv2.resize(g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def glare_ratio(bgr: np.ndarray, mask: np.ndarray | None = None) -> float:
    """Fraction of (document) pixels that are clipped highlights clearly brighter than the paper."""
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sel = mask > 0 if mask is not None else np.ones(g.shape, bool)
    if sel.sum() == 0:
        return 0.0
    paper = float(np.median(g[sel]))
    clipped = (g >= 250) & (hsv[..., 1] < 40) & ((g.astype(np.int16) - paper) > 18) & sel
    # ignore isolated pixels: glare is blobby
    clipped = cv2.morphologyEx(clipped.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    return float(clipped.sum() / sel.sum())


def assess(bgr: np.ndarray, cfg: QACfg, doc_mask: np.ndarray | None = None) -> QAReport:
    h, w = bgr.shape[:2]
    rep = QAReport(width_px=w, height_px=h, blur_laplacian_var=blur_variance(bgr),
                   glare_ratio=glare_ratio(bgr, doc_mask))
    if rep.blur_laplacian_var < cfg.min_blur_var:
        rep.warnings.append(f"blurry image (laplacian var {rep.blur_laplacian_var:.0f} < {cfg.min_blur_var:.0f})")
    if max(w, h) < cfg.min_long_side_px:
        rep.warnings.append(f"low resolution ({w}x{h}); recommended long side >= {cfg.min_long_side_px}px")
    if rep.glare_ratio > cfg.max_glare_ratio:
        rep.warnings.append(f"glare/highlight clipping on {rep.glare_ratio:.1%} of the page")
    return rep


def finalize_coverage(rep: QAReport, coverage: float | None, boundary_found: bool, est_dpi: float | None, cfg: QACfg) -> None:
    rep.document_coverage = coverage
    rep.boundary_found = boundary_found
    rep.estimated_dpi = est_dpi
    if coverage is not None and boundary_found and coverage < cfg.min_coverage:
        rep.warnings.append(f"document covers only {coverage:.0%} of the photo; move closer")
    if not boundary_found:
        rep.warnings.append("document boundary not detected; assuming the photo is already cropped")
    if est_dpi is not None and est_dpi < 120:
        rep.warnings.append(f"effective resolution ~{est_dpi:.0f} dpi on the page (<120): small text may be unreadable")
