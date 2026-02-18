"""Deprecated schema validation helper.

Use app.services.gemini_client.parse_items_json for validation.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def validate_inventory_json(payload: dict[str, Any]) -> bool:
    logger.warning(
        "validate_inventory_json is deprecated; use gemini_client.parse_items_json instead"
    )
    items = payload.get("items")
    if not isinstance(items, list):
        return False
    return True
