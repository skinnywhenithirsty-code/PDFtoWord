from __future__ import annotations

import os
from typing import Any

import requests


class LangflowError(RuntimeError):
    pass


def review_element(element: dict[str, Any]) -> dict[str, Any]:
    """Ask Langflow to propose a classification for one ambiguous element.

    This is optional and never used for deterministic extraction. The caller
    must validate the returned suggestion before applying it.
    """
    base_url = os.getenv("LANGFLOW_URL", "").rstrip("/")
    flow_id = os.getenv("LANGFLOW_FLOW_ID", "")
    api_key = os.getenv("LANGFLOW_API_KEY", "")

    if not base_url or not flow_id:
        raise LangflowError("Set LANGFLOW_URL and LANGFLOW_FLOW_ID to enable AI review")

    payload = {
        "input_value": (
            "Classify this PDF text element. Return a JSON object with "
            "type (heading, paragraph, list_item, caption, or unknown), "
            "level (integer or null), and rationale. Do not invent text. "
            f"Element: {element}"
        ),
        "input_type": "chat",
        "output_type": "chat",
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    try:
        response = requests.post(
            f"{base_url}/api/v1/run/{flow_id}",
            json=payload,
            headers=headers,
            timeout=(5, 60),
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise LangflowError(f"Langflow request failed: {exc}") from exc