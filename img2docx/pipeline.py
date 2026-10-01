"""End-to-end orchestration: photo -> IR JSON -> DOCX."""
from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import geometry as G
from . import illumination, postprocess as PP, qa as QA
from .confidence import agreement, page_review, score_block
from .config import Config, load_config
from .layout import LayoutAnalyzer, Region, colored_ink_mask, draw_regions, ink_mask, remove_rules, text_lines
from .reading_order import alignment_direction_hint, reading_order
from .recognizers import RecognitionResult, Recognizer, RegionHints, build_recognizer
from .schema import IMAGE_TYPES, TEXT_TYPES, BBox, Block, Document, EngineOutput, Page, SourceInfo, Style
from .tables import html_text

log = logging.getLogger("img2docx")


@dataclass
class ConversionResult:
    document: Document
    docx_path: Path | None
    json_path: Path | None
    timings_s: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return bool(self.document.review and self.document.review.needs_review)


def _setup_env(cfg: Config) -> None:
    root = Path(__file__).resolve().parent.parent
    cache = cfg.runtime.paddlex_cache or os.environ.get("PADDLE_PDX_CACHE_HOME") or str(root / "models" / "paddlex")
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", cache)
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "huggingface")
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    if cfg.runtime.offline:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def resolve_device(pref: str) -> str:
    """Device for Paddle models. CUDA only if the installed paddle wheel supports it."""
    if pref == "cpu":
        return "cpu"
    try:
        import paddle

        if paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0:
            return "gpu:0"
    except Exception:
        pass
    if pref == "cuda":
        log.warning("CUDA requested but paddle has no CUDA support here; paddle models run on CPU")
    return "cpu"


class Timer:
    def __init__(self):
        self.t: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            dt = time.perf_counter() - t0
            self.t[name] = round(self.t.get(name, 0.0) + dt, 4)
            log.info("stage %-14s %.2fs", name, dt)


class Pipeline:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or load_config()
        _setup_env(self.cfg)
        self.device = resolve_device(self.cfg.runtime.device)
        g = self.cfg.geometry
        tcmd = None
        try:
            from .recognizers.tesseract import resolve_tesseract_cmd

            tcmd = resolve_tesseract_cmd(self.cfg.recognition.tesseract.cmd)
        except Exception:
            pass
        self.orienter = G.OrientationDetector(g.orientation, tesseract_cmd=tcmd, device=self.device) if g.orientation != "none" else None
        self._dewarper = None
        self.layout = LayoutAnalyzer(self.cfg.layout, self.device)
        self._recognizers: dict[str, Recognizer | None] = {}
        self.engines: dict[str, str] = {"layout": self.layout.engine_id}

    # ---------------------------------------------------------------- engines
    def recognizer(self, name: str) -> Recognizer | None:
        if name not in self._recognizers:
            try:
                self._recognizers[name] = build_recognizer(name, self.cfg.recognition, self.device)
            except Exception as e:
                log.error("recognizer %s unavailable: %s", name, e)
                self._recognizers[name] = None
        return self._recognizers[name]

    def dewarper(self):
        if self.cfg.geometry.dewarp == "uvdoc" and self._dewarper is None:
            try:
                self._dewarper = G.UVDocDewarper(self.device)
            except Exception as e:
                log.warning("UVDoc unavailable: %s", e)
                self._dewarper = False
        return self._dewarper or None

    def primary_for(self, region_type: str) -> str:
        return self.cfg.recognition.primary_by_type.get(region_type, self.cfg.recognition.primary)

    def _recognize(self, name: str, crop, rtype, hints, flags: list[str]) -> RecognitionResult | None:
        rec = self.recognizer(name)
        if rec is None:
            return None
        try:
            return rec.recognize(crop, rtype, hints)
        except Exception as e:
            log.warning("%s failed on %s region: %s", name, rtype, e)
            flags.append(f"{name} failed: {type(e).__name__}")
            return None

    # ---------------------------------------------------------------- main
    def convert(self, image_path: str | Path, output_path: str | Path | None = None, json_path: str | Path | None = None,
                debug_dir: str | Path | None = None) -> ConversionResult:
        tm = Timer()
        cfg = self.cfg
        image_path = Path(image_path)
        dbg = Path(debug_dir) if debug_dir else None
        if dbg:
            import shutil

            for sub in ("crops", "raw"):
                shutil.rmtree(dbg / sub, ignore_errors=True)
            (dbg / "crops").mkdir(parents=True, exist_ok=True)
            (dbg / "raw").mkdir(parents=True, exist_ok=True)
        out_docx = Path(output_path) if output_path else image_path.with_suffix(".docx")
        out_json = Path(json_path) if json_path else out_docx.with_suffix(".json")
        assets_dir = out_docx.parent / f"{out_docx.stem}_assets"

        with tm.stage("load"):
            li = QA.load_image(image_path, cfg.runtime.max_image_side)
        with tm.stage("geometry"):
            geo = G.correct(li.bgr, cfg.geometry, self.orienter, self.dewarper())
        with tm.stage("qa"):
            mask = None
            if geo.quad is not None:
                mask = np.zeros(li.bgr.shape[:2], np.uint8)
                cv2.fillConvexPoly(mask, geo.quad.astype(np.int32), 255)
            rep = QA.assess(li.bgr, cfg.qa, mask)
            QA.finalize_coverage(rep, geo.coverage, geo.quad is not None, geo.est_dpi * li.scale if geo.est_dpi else None, cfg.qa)
            rep.warnings = li.warnings + rep.warnings
            for w in rep.warnings:
                log.warning("QA: %s", w)
        with tm.stage("illumination"):
            page = illumination.flatten(geo.page, cfg.illumination.kernel_frac) if cfg.illumination.enabled else geo.page
        if dbg:
            cv2.imwrite(str(dbg / "00_input.jpg"), li.bgr)
            cv2.imwrite(str(dbg / "01_geometry.jpg"), geo.page)
            cv2.imwrite(str(dbg / "02_illumination.jpg"), page)
        H, W = page.shape[:2]
        with tm.stage("layout"):
            regions = self.layout.analyze(page)
            gray = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
            ink = remove_rules(ink_mask(gray))
            hint = alignment_direction_hint(text_lines(ink, W), W) or "rtl"
        if dbg:
            cv2.imwrite(str(dbg / "03_layout_raw.jpg"), draw_regions(page, regions))

        with tm.stage("recognition"):
            blocks = self._recognize_regions(page, regions, ink, hint, assets_dir, out_json.parent, dbg)
        with tm.stage("postprocess"):
            blocks = self._split_number_date_lines(blocks)
            for b in blocks:
                b.type = PP.refine_type(b)
            self._positional_types(blocks, W, H)
            direction = PP.page_direction(blocks, hint)
            if direction != hint:
                self._rerun_tables(page, blocks, direction, ink)
            order = reading_order([tuple(b.bbox.as_list()) for b in blocks], [b.type for b in blocks], direction)
            for k, i in enumerate(order):
                blocks[i].order = k
            blocks.sort(key=lambda b: b.order)
            for i, b in enumerate(blocks):  # stable ids in reading order
                b.id = f"b{i + 1:03d}"
            self._estimate_styles(blocks, W, H, geo, direction)
            md = PP.build_metadata(blocks)
        with tm.stage("confidence"):
            review = page_review(blocks, rep, cfg.confidence)
        px_per_mm = W / geo.width_mm
        doc = Document(
            source=SourceInfo(path=str(image_path), sha256=li.sha256, width_px=li.orig_size[0], height_px=li.orig_size[1]),
            page=Page(width_px=W, height_px=H, width_mm=round(geo.width_mm, 2), height_mm=round(geo.height_mm, 2),
                      dpi=round(px_per_mm * 25.4, 1), direction=direction, rotation_applied=geo.rotation, paper=geo.paper),
            blocks=blocks, metadata=md, qa=rep, review=review, engines=dict(self.engines), config_digest=cfg.digest(),
        )
        doc.metadata.extra["geometry_notes"] = geo.notes
        doc.metadata.extra["skew_deg"] = round(geo.skew_deg, 2)
        with tm.stage("docx"):
            from .docx_builder import build_docx

            out_json.parent.mkdir(parents=True, exist_ok=True)
            build_docx(doc, out_docx, cfg.docx, out_json.parent)
        doc.timings_s = dict(tm.t)
        doc.timings_s["total"] = round(sum(tm.t.values()), 4)
        out_json.write_text(doc.model_dump_json(indent=1), encoding="utf-8")
        if dbg:
            labels = [f"{b.order}:{b.type}" for b in blocks]
            cv2.imwrite(str(dbg / "04_layout_final.jpg"), draw_regions(page, blocks, labels))
            (dbg / "ir.json").write_text(doc.model_dump_json(indent=1), encoding="utf-8")
        log.info("converted %s in %.2fs (needs_review=%s)", image_path.name, doc.timings_s["total"], review.needs_review)
        return ConversionResult(doc, out_docx, out_json, doc.timings_s, rep.warnings)

    # ---------------------------------------------------------------- recognition
    def _recognize_regions(self, page, regions: list[Region], ink, hint, assets_dir: Path, json_dir: Path, dbg) -> list[Block]:
        cfg = self.cfg
        H, W = page.shape[:2]
        col = colored_ink_mask(page)
        stamps = [r for r in regions if r.type == "stamp"]
        blocks: list[Block] = []
        for i, r in enumerate(regions):
            x0, y0, x1, y1 = (int(round(v)) for v in r.bbox)
            pad = 6 if r.type != "table" else 10
            cx0, cy0, cx1, cy1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
            crop = page[cy0:cy1, cx0:cx1].copy()
            if crop.size == 0:
                continue
            bid = f"r{i:03d}"
            b = Block(id=bid, type=r.type, bbox=BBox.of(r.bbox), layout_source=r.source, layout_score=round(r.score, 3))
            if r.type in IMAGE_TYPES:
                assets_dir.mkdir(parents=True, exist_ok=True)
                img = page[y0:y1, x0:x1]
                p = assets_dir / f"{bid}_{r.type}.png"
                cv2.imwrite(str(p), ink_on_transparent(img) if r.type in ("stamp", "signature") else whiten_paper(img))
                b.image_path = os.path.relpath(p, json_dir)
                if r.type == "stamp" and cfg.recognition.ocr_stamps_to_metadata:
                    res = self._recognize(self.primary_for("stamp"), crop, "stamp", RegionHints(direction=hint, page_w=W), [])
                    if res and res.text:
                        b.text = res.text.strip() or None
                        b.source_engine = res.engine
                        b.confidence = res.confidence
                blocks.append(b)
                if dbg:
                    cv2.imwrite(str(dbg / "crops" / f"{bid}_{r.type}.png"), crop)
                continue
            # suppress coloured stamp ink over printed text (stamps overlapping text)
            if r.type != "handwritten_note":
                for s in stamps:
                    ix0, iy0 = max(cx0, int(s.bbox[0])), max(cy0, int(s.bbox[1]))
                    ix1, iy1 = min(cx1, int(s.bbox[2])), min(cy1, int(s.bbox[3]))
                    if ix1 > ix0 and iy1 > iy0:
                        sub = crop[iy0 - cy0:iy1 - cy0, ix0 - cx0:ix1 - cx0]
                        m = col[iy0:iy1, ix0:ix1] > 0
                        m = cv2.dilate(m.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
                        sub[m] = np.median(crop.reshape(-1, 3), axis=0).astype(np.uint8)
            lh, n_lines = self._line_height(ink[cy0:cy1, cx0:cx1], W)
            b.line_height_px = lh
            hints = RegionHints(direction=hint, line_height_px=lh, n_lines=n_lines, page_w=W)
            flags: list[str] = []
            pname = self.primary_for(r.type)
            res = self._recognize(pname, crop, r.type, hints, flags)
            if res is not None:
                self.engines.setdefault(f"primary:{pname}", res.engine)
            if res is None and pname != "tesseract":
                res = self._recognize("tesseract", crop, r.type, hints, flags)
                flags.append("primary engine unavailable; used tesseract")
            if res is None:
                res = RecognitionResult(text="", confidence=0.0, engine="none")
            b.text, b.html = res.text, res.html
            b.source_engine = res.engine
            b.alternatives.append(EngineOutput(engine=res.engine, text=res.text, html=res.html, confidence=res.confidence,
                                               mean_logprob=res.mean_logprob, seconds=round(res.seconds, 3)))
            flags += res.flags
            agree = None
            res2 = None
            sname = cfg.recognition.secondary
            if sname != "none" and sname != pname and r.type not in ("handwritten_note", "table"):
                h2 = RegionHints(direction=PP.text_direction(res.text, hint), line_height_px=lh, n_lines=n_lines, page_w=W)
                res2 = self._recognize(sname, crop, r.type, h2, [])
                if res2 is not None:
                    b.alternatives.append(EngineOutput(engine=res2.engine, text=res2.text, html=res2.html,
                                                       confidence=res2.confidence, seconds=round(res2.seconds, 3)))
                    ign = sname in cfg.confidence.agreement_ignore_digits_for or pname in cfg.confidence.agreement_ignore_digits_for
                    agree = agreement(res.text or "", res2.text or "", ignore_digits=ign)
            b._lines = res.lines  # transient, used for line splitting / justification
            engine_conf = res.confidence
            if res2 is not None and not (res.text or "").strip() and (res2.text or "").strip() and (res2.confidence or 0) >= 0.6:
                # primary produced nothing but the cross-check engine read the region confidently
                b.text, b.source_engine, b._lines = res2.text, res2.engine, res2.lines
                engine_conf, agree = res2.confidence * 0.85, None
                flags.append(f"primary engine returned no text; using {res2.engine}")
            if res2 is not None and pname == "vlm" and res2.text:
                # small VLMs misread / reorder digit groups in RTL lines (verified on Qwen3-VL-2B):
                # for digit-heavy lines a confident classic engine wins
                if (cfg.recognition.numeric_prefer_classic and sname == "tesseract"
                        and max(_digit_ratio(res.text), _digit_ratio(res2.text)) > 0.15
                        and (res2.confidence or 0) >= 0.75 and (agree is None or agree < 0.98)):
                    b.text, b.source_engine, b._lines = res2.text, res2.engine, res2.lines
                    engine_conf = res2.confidence
                    flags.append("digit-heavy text: classic engine preferred over VLM")
                n_v, n_c = len(PP.TASHKEEL.findall(res.text or "")), len(PP.TASHKEEL.findall(res2.text))
                if n_v >= 3 and n_c == 0 and b.source_engine == res.engine:
                    flags.append(f"{n_v} diacritics only in VLM output (possible hallucinated tashkeel)")
                    engine_conf = (engine_conf or 0) * 0.85
            text_for_lang = b.text if b.text is not None else (html_text(b.html) if b.html else "")
            b.lang = PP.detect_lang(text_for_lang)
            b.direction = PP.text_direction(text_for_lang, hint)  # type: ignore[assignment]
            score_block(b, engine_conf, agree, flags, cfg.confidence)
            if dbg:
                cv2.imwrite(str(dbg / "crops" / f"{bid}_{r.type}.png"), crop)
                for alt in b.alternatives:
                    safe = alt.engine.split("[")[0].split(":")[0].replace("/", "_")
                    (dbg / "raw" / f"{bid}.{safe}.txt").write_text((alt.html or alt.text or ""), encoding="utf-8")
            blocks.append(b)
        return blocks

    @staticmethod
    def _line_height(ink_crop: np.ndarray, page_w: int) -> tuple[float | None, int | None]:
        if ink_crop.size == 0:
            return None, None
        lines = text_lines(ink_crop, page_w)
        hs = [b[3] - b[1] for b in lines]
        return (float(np.median(hs)) if hs else None), (len(lines) or None)

    def _rerun_tables(self, page, blocks: list[Block], direction: str, ink) -> None:
        for b in blocks:
            if b.type != "table":
                continue
            x0, y0, x1, y1 = (int(v) for v in b.bbox.as_list())
            crop = page[max(0, y0 - 10):y1 + 10, max(0, x0 - 10):x1 + 10]
            res = self._recognize(self.primary_for("table"), crop, "table",
                                  RegionHints(direction=direction, line_height_px=b.line_height_px, page_w=page.shape[1]), [])
            if res and res.html:
                b.html = res.html
                b.direction = direction  # type: ignore[assignment]

    def _split_number_date_lines(self, blocks: list[Block]) -> list[Block]:
        """A layout box holding 'number / date / date' lines becomes one block per line."""
        out = []
        for b in blocks:
            lines = [l for l in (b.text or "").split("\n") if l.strip()]
            if b.type in ("paragraph", "header", "title") and len(lines) >= 2:
                kinds = [PP.line_kind(l) for l in lines]
                if sum(k is not None for k in kinds) >= max(2, len(lines) - 0):
                    eng_lines = getattr(b, "_lines", []) or []
                    n = len(lines)
                    for k, (ln, kind) in enumerate(zip(lines, kinds)):
                        if k < len(eng_lines) and eng_lines[k].bbox and len(eng_lines) == n:
                            lx0, ly0, lx1, ly1 = eng_lines[k].bbox
                            bb = BBox(x0=b.bbox.x0 - 6 + lx0, y0=b.bbox.y0 - 6 + ly0, x1=b.bbox.x0 - 6 + lx1, y1=b.bbox.y0 - 6 + ly1)
                        else:
                            hh = b.bbox.h / n
                            bb = BBox(x0=b.bbox.x0, y0=b.bbox.y0 + k * hh, x1=b.bbox.x1, y1=b.bbox.y0 + (k + 1) * hh)
                        nb = b.model_copy(deep=True, update={"id": f"{b.id}_{k}", "text": ln, "bbox": bb,
                                                             "type": kind or b.type, "alternatives": []})
                        out.append(nb)
                    continue
            out.append(b)
        return out

    def _estimate_styles(self, blocks: list[Block], W: int, H: int, geo, direction: str) -> None:
        cfg = self.cfg.docx
        px_per_mm = W / geo.width_mm
        body = [b for b in blocks if b.type in ("paragraph", "title", "list", "table", "doc_number", "date")]
        cl = min((b.bbox.x0 for b in body), default=W * 0.08)
        cr = max((b.bbox.x1 for b in body), default=W * 0.92)
        cw = max(1.0, cr - cl)
        for b in blocks:
            st = b.style
            if b.type == "title":
                st.bold = True
            if b.line_height_px and cfg.font_size_from_line_height:
                ink_pt = b.line_height_px / px_per_mm * 2.83465
                f = cfg.line_height_to_pt_latin if b.lang == "en" else cfg.line_height_to_pt_ar
                st.size_pt = round(ink_pt * f * 2) / 2
            if b.type not in TEXT_TYPES:
                st.align = self._pos_align(b, cl, cr, direction)
                continue
            rel_w = b.bbox.w / cw
            centered = abs(b.bbox.cx - (cl + cr) / 2) < 0.04 * cw
            n_lines = (b.text or "").count("\n") + 1
            if centered and rel_w < 0.85:
                st.align = "center"
            elif rel_w > 0.9 and n_lines > 1:
                st.align = "justify" if self._is_justified(b) else ("right" if direction == "rtl" else "left")
            else:
                st.align = self._pos_align(b, cl, cr, direction)

    @staticmethod
    def _positional_types(blocks: list[Block], W: int, H: int) -> None:
        """Letterhead text sits beside the logo / header blocks; footers at the bottom; short
        centred single lines between letterhead and body are titles."""
        top = [b for b in blocks if b.type in ("header", "logo") and b.bbox.y1 < H * 0.22]
        band = max((b.bbox.y1 for b in top), default=None)
        for b in blocks:
            if b.type not in ("paragraph", "title") or not b.text:
                continue
            if band is not None and b.bbox.cy < band and b.bbox.y1 < H * 0.22:
                b.type = "header"
            elif b.bbox.y0 > H * 0.93:
                b.type = "footer"
        for b in blocks:
            if b.type != "paragraph" or not b.text:
                continue
            t = b.text.strip()
            centred = abs(b.bbox.cx - W / 2) < 0.04 * W
            if centred and "\n" not in t and len(t) <= 60 and not t.endswith((".", "،", ",", ":")) and b.bbox.w < 0.6 * W:
                b.type = "title"

    @staticmethod
    def _pos_align(b: Block, cl: float, cr: float, direction: str) -> str:
        cw = cr - cl
        if b.bbox.x1 > cr - 0.05 * cw and b.bbox.x0 < cl + 0.05 * cw:
            return "right" if direction == "rtl" else "left"
        if b.bbox.x1 > cr - 0.06 * cw:
            return "right"
        if b.bbox.x0 < cl + 0.06 * cw:
            return "left"
        c = (b.bbox.cx - cl) / cw
        return "left" if c < 0.38 else ("right" if c > 0.62 else "center")

    @staticmethod
    def _is_justified(b: Block) -> bool:
        lines = getattr(b, "_lines", None) or []
        bbs = [l.bbox for l in lines if l.bbox]
        if len(bbs) < 3:
            return False
        full = bbs[:-1]
        lw = [x1 - x0 for x0, _, x1, _ in full]
        return min(lw) > 0.97 * max(lw)


def _digit_ratio(s: str | None) -> float:
    s = "".join((s or "").split())
    return sum(c.isdigit() for c in s) / len(s) if s else 0.0


def whiten_paper(img: np.ndarray) -> np.ndarray:
    """Levels so the (flattened) paper becomes pure white; ink colours are kept."""
    paper = np.percentile(img.reshape(-1, 3), 90, axis=0).astype(np.float32)
    out = img.astype(np.float32) * (255.0 / np.maximum(paper, 1))
    return np.clip(out, 0, 255).astype(np.uint8)


def ink_on_transparent(img: np.ndarray) -> np.ndarray:
    """BGRA: alpha from darkness relative to the paper -> stamp/signature can sit over text."""
    w = whiten_paper(img)
    lum = cv2.cvtColor(w, cv2.COLOR_BGR2GRAY).astype(np.float32)
    alpha = np.clip((255 - lum) * 1.6, 0, 255)
    alpha[alpha < 25] = 0
    return np.dstack([w, alpha.astype(np.uint8)])


_PIPELINES: dict[str, Pipeline] = {}


def convert(image_path, output_path=None, config: Config | str | None = None, json_path=None, debug_dir=None) -> ConversionResult:
    """Python API. `config` may be a Config, a YAML path, or None (defaults)."""
    if not isinstance(config, Config):
        config = load_config(config)
    key = config.digest()
    if key not in _PIPELINES:
        _PIPELINES[key] = Pipeline(config)
    return _PIPELINES[key].convert(image_path, output_path, json_path, debug_dir)
