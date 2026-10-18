from __future__ import annotations

import logging
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .pipeline import process_pdf
from .schemas import JobRequest, JobStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Document Engine API",
    version="0.1.0",
    description="Local PDF extraction, structure normalization, and DOCX export service.",
)

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def _set_job(job_id: str, **values: Any) -> None:
    with _jobs_lock:
        _jobs[job_id].update(values)


def _run_job(job_id: str, request: JobRequest) -> None:
    _set_job(job_id, status="running", stage="extracting", progress=5, message="Inspecting PDF")
    try:
        result = process_pdf(
            request.pdf_path,
            output_dir=request.output_dir,
            export_docx=request.export_docx,
            run_ai_review=request.run_ai_review,
        )
        _set_job(
            job_id,
            status="completed",
            stage="completed",
            progress=100,
            message="Processing complete",
            document_json=result["json_path"],
            docx_path=result["docx_path"],
            markdown_path=result["markdown_path"],
            output_dir=result["output_dir"],
            result=result,
        )
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        _set_job(
            job_id,
            status="failed",
            stage="failed",
            progress=100,
            message="Processing failed",
            error=str(exc),
        )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "document-engine"}


@app.post("/jobs", response_model=JobStatus, status_code=202)
def create_job(request: JobRequest) -> JobStatus:
    path = Path(request.pdf_path).expanduser()
    if not path.is_file():
        raise HTTPException(status_code=400, detail="pdf_path does not exist")
    if path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="pdf_path must point to a PDF file")

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "stage": "queued",
            "progress": 0,
            "message": "Queued",
            "document_json": None,
            "docx_path": None,
            "error": None,
        }
    thread = threading.Thread(target=_run_job, args=(job_id, request), daemon=True)
    thread.start()
    return JobStatus(**_jobs[job_id])


@app.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str) -> JobStatus:
    with _jobs_lock:
        item = _jobs.get(job_id)
        if not item:
            raise HTTPException(status_code=404, detail="Unknown job ID")
        return JobStatus(**{k: item.get(k) for k in JobStatus.model_fields})


@app.get("/jobs/{job_id}/result")
def get_job_result(job_id: str) -> JSONResponse:
    with _jobs_lock:
        item = _jobs.get(job_id)
        if not item:
            raise HTTPException(status_code=404, detail="Unknown job ID")
        if item["status"] != "completed":
            raise HTTPException(status_code=409, detail=f"Job is {item['status']}")
        result = item.get("result")
    return JSONResponse(content=result)


@app.get("/documents/{document_id}")
def get_document(document_id: str) -> dict[str, Any]:
    # Only serves JSON files in completed jobs. This is a local development API;
    # add stronger authorization/path controls before exposing it to a network.
    with _jobs_lock:
        matches = [
            j for j in _jobs.values()
            if j.get("status") == "completed"
            and j.get("result", {}).get("document", {}).get("document_id") == document_id
        ]
        if not matches:
            raise HTTPException(status_code=404, detail="Document not found in completed jobs")
        return matches[-1]["result"]["document"]