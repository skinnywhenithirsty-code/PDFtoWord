from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def inspect_pdf(pdf_path: str | Path) -> dict[str, Any]:
    """Extract reliable native PDF text, page metrics, and image references.

    This intentionally does not perform OCR. Scanned pages are flagged for a
    future OCR backend rather than silently treated as empty text.
    """
    path = Path(pdf_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"PDF does not exist: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError("Input must be a .pdf file")

    pages: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    image_assets: list[dict[str, Any]] = []
    warnings: list[str] = []

    with fitz.open(path) as doc:
        if doc.is_encrypted:
            raise ValueError("PDF is encrypted; unlock it before processing")
        for page_index, page in enumerate(doc):
            page_no = page_index + 1
            page_dict = page.get_text("dict", sort=True)
            page_text = page.get_text("text", sort=True).strip()
            images = page.get_images(full=True)
            pages.append({
                "page_number": page_no,
                "width": float(page.rect.width),
                "height": float(page.rect.height),
                "has_text": bool(page_text),
                "extracted_text_chars": len(page_text),
                "image_count": len(images),
            })

            for block_index, block in enumerate(page_dict.get("blocks", [])):
                bbox = block.get("bbox")
                if block.get("type") == 0:
                    lines = []
                    font_sizes = []
                    font_names = []
                    for line in block.get("lines", []):
                        span_text = "".join(span.get("text", "") for span in line.get("spans", []))
                        if span_text.strip():
                            lines.append(span_text)
                        for span in line.get("spans", []):
                            if span.get("text", "").strip():
                                font_sizes.append(float(span.get("size", 0)))
                                font_names.append(str(span.get("font", "")))
                    text = "\n".join(lines).strip()
                    if not text:
                        continue
                    blocks.append({
                        "id": f"p{page_no}-b{block_index}",
                        "text": text,
                        "page_number": page_no,
                        "bbox": bbox,
                        "font_sizes": font_sizes,
                        "font_names": font_names,
                        "source": "pymupdf",
                        "block_index": block_index,
                    })
                elif block.get("type") == 1:
                    # Preserve location/metadata; extraction of image bytes is
                    # deliberately separate to avoid ballooning JSON payloads.
                    image_assets.append({
                        "id": f"p{page_no}-img{block_index}",
                        "page_number": page_no,
                        "bbox": bbox,
                        "width": block.get("width"),
                        "height": block.get("height"),
                        "extension": block.get("ext"),
                    })

    if not blocks:
        warnings.append(
            "No embedded text was extracted. This may be a scanned PDF; OCR is not configured."
        )
    low_text_pages = [p["page_number"] for p in pages if p["extracted_text_chars"] < 20]
    if low_text_pages:
        warnings.append(f"Pages with little or no embedded text (possible scans): {low_text_pages}")

    return {
        "source_file": str(path),
        "document_id": path.stem,
        "page_count": len(pages),
        "pages": pages,
        "blocks": blocks,
        "image_assets": image_assets,
        "warnings": warnings,
    }


def try_docling(pdf_path: str | Path) -> dict[str, Any] | None:
    """Run Docling if installed; return its exported dict or None.

    PyMuPDF remains the reliable fallback. Docling APIs can evolve, so all
    Docling-specific failures are reported to the caller as a warning.
    """
    try:
        from docling.document_converter import DocumentConverter
        result = DocumentConverter().convert(str(pdf_path))
        document = result.document
        if hasattr(document, "export_to_dict"):
            return document.export_to_dict()
        if hasattr(document, "model_dump"):
            return document.model_dump()
        return {"text": document.export_to_markdown()}
    except ImportError:
        logger.info("Docling is not installed; using PyMuPDF extraction.")
    except Exception:
        logger.exception("Docling extraction failed; falling back to PyMuPDF.")
    return None