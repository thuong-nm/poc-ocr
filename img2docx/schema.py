"""Versioned intermediate representation (IR). This JSON is the contract for review tools / ECM."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr

SCHEMA_VERSION = "1.0.0"

BlockType = Literal[
    "title", "paragraph", "list", "table", "header", "footer", "doc_number", "date",
    "stamp", "signature", "logo", "figure", "handwritten_note",
]
TEXT_TYPES = {"title", "paragraph", "list", "header", "footer", "doc_number", "date", "handwritten_note"}
IMAGE_TYPES = {"stamp", "signature", "logo", "figure"}
Direction = Literal["rtl", "ltr"]
Lang = Literal["ar", "en", "mixed"]


class BBox(BaseModel):
    """Pixel box in the *normalized page image* (after geometry correction)."""
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def area(self) -> float:
        return max(0.0, self.w) * max(0.0, self.h)

    def as_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]

    @classmethod
    def of(cls, xyxy) -> "BBox":
        x0, y0, x1, y1 = (float(v) for v in xyxy)
        return cls(x0=x0, y0=y0, x1=x1, y1=y1)


class Style(BaseModel):
    align: Literal["left", "right", "center", "justify"] | None = None
    size_pt: float | None = None
    bold: bool | None = None


class EngineOutput(BaseModel):
    """Raw output of one recognizer for a block (kept for audit / review)."""
    engine: str
    text: str | None = None
    html: str | None = None
    confidence: float | None = None
    mean_logprob: float | None = None
    seconds: float | None = None


class Block(BaseModel):
    id: str
    type: BlockType
    bbox: BBox
    order: int = -1
    text: str | None = None
    html: str | None = None
    image_path: str | None = None
    lang: Lang | None = None
    direction: Direction | None = None
    style: Style = Field(default_factory=Style)
    confidence: float | None = None
    source_engine: str | None = None
    layout_source: str | None = None  # e.g. "PP-DocLayout_plus-L:text@0.93" or "heuristic:lines"
    layout_score: float | None = None
    alternatives: list[EngineOutput] = Field(default_factory=list)
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    line_height_px: float | None = None
    _lines: list = PrivateAttr(default_factory=list)  # engine line boxes (transient, not serialized)


class Page(BaseModel):
    width_px: int
    height_px: int
    width_mm: float
    height_mm: float
    dpi: float
    direction: Direction = "rtl"
    rotation_applied: int = 0  # degrees clockwise applied to the photo
    paper: str | None = None  # "A4", "Letter" or None


class QAReport(BaseModel):
    width_px: int
    height_px: int
    blur_laplacian_var: float
    glare_ratio: float
    document_coverage: float | None = None
    estimated_dpi: float | None = None
    boundary_found: bool | None = None
    warnings: list[str] = Field(default_factory=list)


class DateRef(BaseModel):
    calendar: Literal["hijri", "gregorian"]
    raw: str
    normalized: str | None = None  # YYYY-MM-DD with Latin digits, when parseable
    block_id: str


class Metadata(BaseModel):
    doc_numbers: list[dict[str, str]] = Field(default_factory=list)  # {raw, value, block_id}
    dates: list[DateRef] = Field(default_factory=list)
    stamp_texts: list[dict[str, str]] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class ReviewSummary(BaseModel):
    page_score: float
    needs_review: bool
    reasons: list[str] = Field(default_factory=list)


class SourceInfo(BaseModel):
    path: str
    sha256: str
    width_px: int
    height_px: int


class Document(BaseModel):
    schema_version: str = SCHEMA_VERSION
    source: SourceInfo
    page: Page
    blocks: list[Block] = Field(default_factory=list)
    metadata: Metadata = Field(default_factory=Metadata)
    qa: QAReport
    review: ReviewSummary | None = None
    timings_s: dict[str, float] = Field(default_factory=dict)
    engines: dict[str, str] = Field(default_factory=dict)  # role -> engine id (with model id)
    config_digest: str | None = None

    def ordered_blocks(self) -> list[Block]:
        return sorted(self.blocks, key=lambda b: b.order)
