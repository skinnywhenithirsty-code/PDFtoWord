from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict


ElementType = Literal[
    "heading", "paragraph", "list_item", "table", "figure", "caption",
    "header", "footer", "page_number", "unknown"
]


class BBox(BaseModel):
    """PDF coordinates in points: x0, y0, x1, y1."""
    x0: float
    y0: float
    x1: float
    y1: float


class PageInfo(BaseModel):
    page_number: int
    width: float | None = None
    height: float | None = None
    has_text: bool = False
    extracted_text_chars: int = 0
    image_count: int = 0


class TableData(BaseModel):
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    markdown: str | None = None


class Element(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: ElementType = "unknown"
    text: str = ""
    page_number: int | None = None
    bbox: BBox | None = None
    parent_id: str | None = None
    level: int | None = None
    numbering: str | None = None
    caption_for: str | None = None
    asset_path: str | None = None
    table: TableData | None = None
    source: str = "pymupdf"
    confidence: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TocEntry(BaseModel):
    id: str
    level: int
    title: str
    page_number: int | None = None
    numbering: str | None = None
    element_id: str


class DocumentModel(BaseModel):
    schema_version: str = "1.0"
    document_id: str
    source_file: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    page_count: int = 0
    pages: list[PageInfo] = Field(default_factory=list)
    elements: list[Element] = Field(default_factory=list)
    toc: list[TocEntry] = Field(default_factory=list)
    tables: list[Element] = Field(default_factory=list)
    figures: list[Element] = Field(default_factory=list)
    validation: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class JobRequest(BaseModel):
    pdf_path: str
    output_dir: str | None = None
    run_ai_review: bool = False
    export_docx: bool = True


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    stage: str = "queued"
    progress: int = 0
    message: str = ""
    document_json: str | None = None
    docx_path: str | None = None
    error: str | None = None