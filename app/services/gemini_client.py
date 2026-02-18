import base64
import json
import logging
from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError, model_validator

from app.core.config import get_settings
from app.services.normalize import categorize_item, estimate_expiry, normalize_name

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-1.5-flash"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_TIMEOUT_SECONDS = 30.0


class Item(BaseModel):
    name_raw: str = Field(min_length=1, description="상품명 원문")
    qty: float | None = Field(default=None, description="수량")
    unit: str | None = Field(default=None, description="단위")
    confidence: float = Field(ge=0.0, le=1.0, description="신뢰도(0~1)")
    name_norm: str = Field(default="", description="정규화된 상품명")
    category: str = Field(default="other", description="카테고리")
    storage: str = Field(default="실온", description="보관 위치")
    default_days: int = Field(default=7, ge=1, description="기본 보관일")
    purchase_date: date = Field(default_factory=date.today, description="구매일(서버 처리 시각 기준)")
    expiry_estimated: date | None = Field(default=None, description="예상 소비기한")

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def apply_postprocess(self) -> "Item":
        name_norm = normalize_name(self.name_raw)
        category, storage, default_days = categorize_item(self.name_raw, name_norm)

        self.name_norm = name_norm
        self.category = category
        self.storage = storage
        self.default_days = default_days
        self.expiry_estimated = estimate_expiry(self.purchase_date, self.default_days)
        return self


class ItemListResponse(RootModel[list[Item]]):
    pass


def extract_items_from_image(image_bytes: bytes) -> list[Item]:
    """Extract shopping-list items from an image using Gemini inline(base64) input.

    Retries once with a lower temperature when the first response is invalid
    or parsing fails.
    """
    if not image_bytes:
        raise ValueError("image_bytes must not be empty")

    settings = get_settings()
    if len(image_bytes) > settings.gemini_inline_max_bytes:
        raise ValueError("Image exceeds inline upload threshold; File API flow is required")

    mime_type = _guess_mime_type(image_bytes)
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    temperatures = [0.2, 0.0]
    last_error: Exception | None = None

    for attempt, temperature in enumerate(temperatures, start=1):
        try:
            raw_text = _request_items_json_inline(
                api_key=settings.gemini_api_key,
                image_base64=image_base64,
                mime_type=mime_type,
                temperature=temperature,
            )
            items = parse_items_json(raw_text)
            logger.info(
                "Gemini item extraction success (attempt=%d, count=%d)",
                attempt,
                len(items),
            )
            return items
        except (httpx.HTTPError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            logger.warning(
                "Gemini extraction failed on attempt %d/%d: %s",
                attempt,
                len(temperatures),
                exc,
            )

    raise RuntimeError("Failed to extract items from image") from last_error


def parse_items_json(raw_text: str) -> list[Item]:
    """Parse and validate Gemini JSON response. Response must be a JSON array."""
    cleaned = _strip_json_code_fence(raw_text)
    parsed = json.loads(cleaned)
    validated = ItemListResponse.model_validate(parsed)
    return validated.root


def _request_items_json_inline(
    *,
    api_key: str,
    image_base64: str,
    mime_type: str,
    temperature: float,
) -> str:
    payload = {
        "system_instruction": {
            "parts": [
                {
                    "text": (
                        "You extract items from Korean shopping-list screenshots. "
                        "Output JSON only, with no markdown, no prose, no code fences. "
                        "The output MUST be a JSON array of objects with keys: "
                        "name_raw, qty, unit, confidence. "
                        "Keep Korean names exactly as written. "
                        "If qty is uncertain, set qty to null and lower confidence."
                    )
                }
            ]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "다음 이미지에서 구매 품목을 추출하세요. "
                            "반드시 JSON 배열만 출력하세요.\n"
                            "스키마:\n"
                            "[\n"
                            "  {\n"
                            "    \"name_raw\": \"string\",\n"
                            "    \"qty\": number | null,\n"
                            "    \"unit\": \"string\" | null,\n"
                            "    \"confidence\": number\n"
                            "  }\n"
                            "]"
                        )
                    },
                    {"inline_data": {"mime_type": mime_type, "data": image_base64}},
                ],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "response_mime_type": "application/json",
        },
    }

    url = f"{GEMINI_BASE_URL}/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    with httpx.Client(timeout=DEFAULT_TIMEOUT_SECONDS) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()

    return _extract_text_from_response(response.json())


def _extract_text_from_response(body: dict[str, Any]) -> str:
    candidates = body.get("candidates", [])
    if not candidates:
        raise ValueError("Gemini response has no candidates")

    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    if not parts:
        raise ValueError("Gemini response has no content parts")

    text = parts[0].get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Gemini response text is empty")

    return text


def _strip_json_code_fence(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def _guess_mime_type(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return "image/jpeg"
