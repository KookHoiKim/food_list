"""Deprecated Gemini extractor module.

Use app.services.gemini_client.extract_items_from_image as the single extraction path.
"""

from app.services.gemini_client import Item, extract_items_from_image


async def extract_inventory_from_image(image_bytes: bytes, mime_type: str) -> list[Item]:
    """Backward-compatible wrapper around unified gemini_client extractor."""
    _ = mime_type
    return extract_items_from_image(image_bytes=image_bytes)
