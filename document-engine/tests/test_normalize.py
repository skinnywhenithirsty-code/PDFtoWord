from src.normalize_structure import normalize


def test_heading_and_paragraph_are_preserved():
    raw = {
        "document_id": "sample",
        "source_file": "/tmp/sample.pdf",
        "page_count": 1,
        "pages": [{
            "page_number": 1, "width": 595, "height": 842,
            "has_text": True, "extracted_text_chars": 40, "image_count": 0,
        }],
        "blocks": [
            {
                "id": "p1-b0", "text": "BAB I PENDAHULUAN", "page_number": 1,
                "bbox": [40, 40, 300, 60], "font_sizes": [18], "font_names": ["Arial-Bold"],
                "source": "pymupdf", "block_index": 0,
            },
            {
                "id": "p1-b1", "text": "Latar belakang penelitian.", "page_number": 1,
                "bbox": [40, 90, 500, 110], "font_sizes": [10], "font_names": ["Arial"],
                "source": "pymupdf", "block_index": 1,
            },
        ],
        "image_assets": [],
        "warnings": [],
    }
    result = normalize(raw)
    assert len(result.toc) >= 1
    assert any(e.type == "paragraph" for e in result.elements)
    assert result.toc[0].title == "BAB I PENDAHULUAN"