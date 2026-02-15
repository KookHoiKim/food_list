import base64
import json
import logging

import httpx

from app.core.config import get_settings
from app.models.inventory import InventoryExtraction
from app.utils.schema_validation import validate_inventory_json

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-1.5-flash"


def build_prompt() -> str:
    return (
        "이미지에서 품목 목록을 추출해 JSON으로만 응답하세요. "
        "형식: {\"items\":[{\"name\":\"string\",\"quantity\":number,\"unit\":\"string\"}]}"
    )


async def extract_inventory_from_image(image_bytes: bytes, mime_type: str) -> InventoryExtraction:
    settings = get_settings()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
        f"?key={settings.gemini_api_key}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": build_prompt()},
                    {"inline_data": {"mime_type": mime_type, "data": image_base64}},
                ]
            }
        ],
        "generationConfig": {"temperature": 0.0, "response_mime_type": "application/json"},
    }

    logger.info("Calling Gemini API for extraction")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        body = response.json()

    text_output = body["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(text_output)
    if not validate_inventory_json(parsed):
        raise ValueError("Gemini response did not match expected schema")
    extraction = InventoryExtraction.model_validate(parsed)
    logger.info("Extracted %d inventory items", len(extraction.items))
    return extraction
