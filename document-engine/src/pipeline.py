from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .build_docx import build_docx
from .extract_pdf import inspect_pdf, try_docling
from .normalize_structure import normalize
from .schemas import DocumentModel

logger = logging.getLogger(__name__)


def process_pdf(
    pdf_path: str | Path,
    output_dir: str | Path | None = None,
    export_docx: bool = True,
    run_ai_review: bool = False,
) -> dict[str, Any]:
    """Run extraction -> normalization -> JSON -> optional DOCX export."""
    source = Path(pdf_path).expanduser().resolve()
    raw = inspect_pdf(source)
    docling_data = try_docling(source)

    # Docling is retained in raw metadata in future iterations. The current
    # normalizer's robust fallback is PyMuPDF plus a best-effort table adapter.
    model: DocumentModel = normalize(raw, docling_data=docling_data)

    # AI review is intentionally opt-in. The first version does not silently
    # mutate the canonical model from untrusted model output.
    if run_ai_review:
        model.warnings.append(
            "AI review was requested, but automatic mutation is disabled. "
            "Use langflow_client.review_element and validate suggestions explicitly."
        )

    destination = Path(output_dir).expanduser().resolve() if output_dir else source.parent / f"{source.stem}_processed"
    destination.mkdir(parents=True, exist_ok=True)

    json_path = destination / f"{source.stem}.document.json"
    json_path.write_text(
        model.model_dump_json(indent=2, exclude_none=True),
        encoding="utf-8",
    )

    docx_path = None
    if export_docx:
        docx_path = build_docx(model, destination / f"{source.stem}.docx")

    markdown_path = destination / f"{source.stem}.md"
    markdown_path.write_text(to_markdown(model), encoding="utf-8")

    return {
        "document": model.model_dump(mode="json", exclude_none=True),
        "json_path": str(json_path),
        "docx_path": docx_path,
        "markdown_path": str(markdown_path),
        "output_dir": str(destination),
    }


def to_markdown(model: DocumentModel) -> str:
    lines = [f"# {Path(model.source_file).stem}", ""]
    for element in model.elements:
        if element.type == "heading":
            level = min(max(element.level or 1, 1), 6)
            lines.extend(["#" * level + " " + element.text, ""])
        elif element.type == "list_item":
            lines.extend(["- " + element.text, ""])
        elif element.type == "caption":
            lines.extend(["*" + element.text + "*", ""])
        elif element.type == "figure":
            lines.extend([f"![Figure on page {element.page_number}]()", ""])
        elif element.type == "table" and element.table and element.table.rows:
            rows = element.table.rows
            width = max(len(r) for r in rows)
            lines.append("| " + " | ".join(rows[0] + [""] * (width-len(rows[0]))) + " |")
            lines.append("| " + " | ".join(["---"] * width) + " |")
            for row in rows[1:]:
                lines.append("| " + " | ".join(row + [""] * (width-len(row))) + " |")
            lines.append("")
        elif element.text.strip():
            lines.extend([element.text, ""])
    return "\n".join(lines).rstrip() + "\n"