from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .schemas import BBox, DocumentModel, Element, PageInfo, TableData, TocEntry

# Common heading-number patterns: 1, 1.2, 1.2.3, BAB I, A., 1).
NUMBERING_RE = re.compile(
    r"^\s*((?:BAB|CHAPTER|SECTION)\s+[IVXLCDM\d]+|"
    r"\d+(?:\.\d+){0,5}[.)]?|[A-Z][.)])\s+",
    re.IGNORECASE,
)
CAPTION_RE = re.compile(
    r"^\s*(Gambar|Figure|Fig\.?|Tabel|Table|Lampiran|Appendix)\s*"
    r"([A-Z]?\d+(?:[.-]\d+)*)?\s*[:.]?\s*",
    re.IGNORECASE,
)
ROMAN_BAB_RE = re.compile(r"^\s*BAB\s+([IVXLCDM]+)\b", re.IGNORECASE)
LIST_RE = re.compile(r"^\s*(?:[-•▪◦]|\d+[.)]|[a-zA-Z][.)])\s+")


def _bbox(raw: Any) -> BBox | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        return BBox(x0=float(raw[0]), y0=float(raw[1]), x1=float(raw[2]), y1=float(raw[3]))
    except (TypeError, ValueError):
        return None


def _looks_heading(block: dict[str, Any], median_font: float) -> bool:
    text = block["text"].strip()
    if len(text) > 180 or len(text.splitlines()) > 3:
        return False
    sizes = block.get("font_sizes", [])
    size = max(sizes) if sizes else 0
    numbered = bool(NUMBERING_RE.match(text))
    all_caps = len(text) >= 3 and text.upper() == text and any(c.isalpha() for c in text)
    title_like = text.istitle() and len(text.split()) <= 14
    short_and_large = size >= median_font * 1.16 and len(text.split()) <= 18
    return numbered or all_caps or title_like or short_and_large


def normalize(raw: dict[str, Any], docling_data: dict[str, Any] | None = None) -> DocumentModel:
    """Convert raw extraction into the engine's stable canonical document model.

    This first implementation uses deterministic layout/numbering heuristics.
    Docling's structured export is retained as metadata for later richer
    adapters; it is not blindly trusted to match one fixed upstream schema.
    """
    blocks = raw.get("blocks", [])
    all_sizes = [s for b in blocks for s in b.get("font_sizes", []) if s > 0]
    median_font = sorted(all_sizes)[len(all_sizes) // 2] if all_sizes else 10.0

    elements: list[Element] = []
    previous_heading_ids: dict[int, str] = {}
    pending_caption_ids: list[str] = []

    # Most PDF text is already roughly ordered by page and vertical position.
    blocks = sorted(
        blocks,
        key=lambda b: (b.get("page_number", 0), (b.get("bbox") or [0, 0, 0, 0])[1],
                       (b.get("bbox") or [0, 0, 0, 0])[0])
    )

    for block in blocks:
        text = block["text"].strip()
        if not text:
            continue
        numbered_match = NUMBERING_RE.match(text)
        numbering = numbered_match.group(1).strip() if numbered_match else None
        caption_match = CAPTION_RE.match(text)
        heading = _looks_heading(block, median_font)
        if caption_match:
            kind = "caption"
        elif heading:
            kind = "heading"
        elif LIST_RE.match(text):
            kind = "list_item"
        else:
            kind = "paragraph"

        # Estimate heading level from numbering depth, otherwise font size.
        level = None
        parent_id = None
        if kind == "heading":
            if numbering and re.match(r"^\d", numbering):
                level = min(6, numbering.rstrip(".)").count(".") + 1)
            elif ROMAN_BAB_RE.match(text) or re.match(r"^(CHAPTER|SECTION)\b", text, re.I):
                level = 1
            elif re.match(r"^[A-Z][.)]$", numbering or ""):
                level = 2
            else:
                sizes = block.get("font_sizes", [])
                size = max(sizes) if sizes else median_font
                level = 1 if size >= median_font * 1.35 else 2 if size >= median_font * 1.15 else 3

            for prior_level in sorted(previous_heading_ids):
                if prior_level < level:
                    parent_id = previous_heading_ids[prior_level]
            previous_heading_ids[level] = block["id"]
            for old_level in list(previous_heading_ids):
                if old_level > level:
                    del previous_heading_ids[old_level]

        element = Element(
            id=block["id"],
            type=kind,
            text=text,
            page_number=block.get("page_number"),
            bbox=_bbox(block.get("bbox")),
            parent_id=parent_id,
            level=level,
            numbering=numbering,
            source=block.get("source", "pymupdf"),
            confidence=0.65 if kind == "heading" else 0.9,
            metadata={
                "font_sizes": block.get("font_sizes", []),
                "font_names": block.get("font_names", []),
                "block_index": block.get("block_index"),
            },
        )
        elements.append(element)
        if kind == "caption":
            pending_caption_ids.append(element.id)

    # Add image elements as figures; associate the nearest caption on the same
    # page when available. Caption matching can be improved in a later pass.
    for image in raw.get("image_assets", []):
        same_page_captions = [
            e for e in elements if e.type == "caption" and e.page_number == image["page_number"]
        ]
        fig = Element(
            id=image["id"],
            type="figure",
            text="",
            page_number=image["page_number"],
            bbox=_bbox(image.get("bbox")),
            source="pymupdf",
            confidence=0.8,
            metadata={k: v for k, v in image.items() if k not in {"id", "page_number", "bbox"}},
        )
        if same_page_captions:
            # Choose the caption closest vertically to the image.
            image_y = (image.get("bbox") or [0, 0, 0, 0])[1]
            caption = min(
                same_page_captions,
                key=lambda e: abs((e.bbox.y0 if e.bbox else 0) - image_y)
            )
            fig.caption_for = caption.id
        elements.append(fig)

    # Detect simple tables from Docling's exported dictionary. This adapter is
    # intentionally conservative because the export schema can vary by version.
    if docling_data:
        _append_docling_tables(docling_data, elements)

    toc = [
        TocEntry(
            id=f"toc-{e.id}",
            level=e.level or 1,
            title=e.text,
            page_number=e.page_number,
            numbering=e.numbering,
            element_id=e.id,
        )
        for e in elements if e.type == "heading"
    ]
    page_infos = [PageInfo(**p) for p in raw.get("pages", [])]
    tables = [e for e in elements if e.type == "table"]
    figures = [e for e in elements if e.type == "figure"]

    model = DocumentModel(
        document_id=raw.get("document_id", "document"),
        source_file=raw.get("source_file", ""),
        page_count=raw.get("page_count", len(page_infos)),
        pages=page_infos,
        elements=elements,
        toc=toc,
        tables=tables,
        figures=figures,
        warnings=list(raw.get("warnings", [])),
        validation={
            "heading_count": len(toc),
            "table_count": len(tables),
            "figure_count": len(figures),
            "paragraph_count": sum(e.type == "paragraph" for e in elements),
            "used_docling": bool(docling_data),
            "notes": [
                "Heading levels are heuristic; review low-confidence headings.",
                "Image blocks may include decorative logos and background images.",
                "Native table extraction is best-effort and may require Docling-specific adapter updates."
            ],
        },
    )
    return model


def _append_docling_tables(data: dict[str, Any], elements: list[Element]) -> None:
    """Best-effort adapter for Docling's exported JSON table items."""
    counter = 0

    def walk(value: Any):
        nonlocal counter
        if isinstance(value, dict):
            label = str(value.get("label", value.get("type", ""))).lower()
            if "table" in label and any(k in value for k in ("data", "cells", "table_cells")):
                raw_table = value.get("data", value.get("cells", value.get("table_cells")))
                rows: list[list[str]] = []
                if isinstance(raw_table, list):
                    for row in raw_table:
                        if isinstance(row, list):
                            rows.append([str(cell.get("text", "") if isinstance(cell, dict) else cell) for cell in row])
                        elif isinstance(row, dict):
                            rows.append([str(row.get("text", ""))])
                counter += 1
                elements.append(Element(
                    id=f"docling-table-{counter}",
                    type="table",
                    text="",
                    source="docling",
                    confidence=0.75,
                    table=TableData(rows=rows),
                    metadata={"docling_label": label},
                ))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data)