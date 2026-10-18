# document-engine

A local-first PDF extraction service intended to integrate with LibreOffice through an extension or desktop launcher.

## Current scope

- PyMuPDF extraction of embedded text, page dimensions, text block coordinates, and image-block metadata.
- Optional Docling pass, when installed and operational.
- Deterministic heuristic classification for headings, paragraphs, list items, and captions.
- Canonical JSON model with page provenance, element IDs, bounding boxes, and a generated heading outline.
- Markdown and semantic DOCX export.
- FastAPI job API for GUI integration.
- Optional Langflow client helper; AI suggestions are not automatically applied.

## Known limitations of this first version

- Scanned-PDF OCR is not implemented yet; pages with little embedded text are flagged.
- Table extraction is best-effort. Docling export schemas vary; validate against your installed Docling version and real documents.
- Image bytes are not exported/embedded in DOCX yet; image locations are recorded as metadata.
- Heading detection is heuristic. Always regression-test against your real PDFs.
- Generated TOC is a static list, not a Word field that automatically updates page numbers.
- The API is intended for localhost development. Do not expose it to a network without authentication, path restrictions, and resource limits.

## Install

Python 3.10+ recommended. Docling may install large dependencies and may require a compatible Python/platform combination.

```bash
cd /media/erafaza/Document/Programming/document-engine
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If Docling's install is problematic, first install the core dependencies and run with PyMuPDF only:

```bash
pip install pymupdf python-docx fastapi 'uvicorn[standard]' python-multipart 'pydantic>=2' requests
```

## Run API

From the `document-engine` directory:

```bash
source .venv/bin/activate
uvicorn src.api:app --host 127.0.0.1 --port 8765
```

Test health:

```bash
curl http://127.0.0.1:8765/health
```

Submit a job (use an absolute path):

```bash
curl -X POST http://127.0.0.1:8765/jobs \
  -H 'Content-Type: application/json' \
  -d '{"pdf_path":"/absolute/path/to/file.pdf","export_docx":true}'
```

Poll the `job_id` returned by the request:

```bash
curl http://127.0.0.1:8765/jobs/YOUR_JOB_ID
curl http://127.0.0.1:8765/jobs/YOUR_JOB_ID/result
```

## Run directly without API

```bash
python - <<'PY'
from src.pipeline import process_pdf
result = process_pdf("/absolute/path/to/file.pdf", export_docx=True)
print(result["json_path"])
print(result["docx_path"])
PY
```

## Langflow environment variables

Set these only when implementing and enabling an AI review workflow:

```bash
export LANGFLOW_URL="http://127.0.0.1:7860"
export LANGFLOW_FLOW_ID="your-flow-id"
export LANGFLOW_API_KEY="your-api-key"
```

The `review_element` helper in `src/langflow_client.py` sends a suggestion request. It does not apply the result to the canonical document. Add response parsing, schema validation, and an explicit acceptance policy before using AI output to modify a document.

## Output files

For `example.pdf`, default outputs are written to `example_processed/` next to the input:

- `example.document.json`
- `example.docx`
- `example.md`

## Security notes

- The API binds to loopback by default; keep it that way for a local-only workflow.
- Validate allowed input/output roots before using this service with arbitrary paths.
- Do not expose API keys in source control or in an extension package.
- Treat PDF content and LLM output as untrusted data.
