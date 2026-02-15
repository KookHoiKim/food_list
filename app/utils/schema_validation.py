import logging
from typing import Any

logger = logging.getLogger(__name__)


def validate_inventory_json(payload: dict[str, Any]) -> bool:
    """Validate extracted inventory JSON schema with lightweight checks."""
    items = payload.get("items")
    if not isinstance(items, list):
        logger.warning("Invalid schema: 'items' is not a list")
        return False

    for item in items:
        if not isinstance(item, dict):
            logger.warning("Invalid item type: %s", type(item))
            return False
        name = item.get("name")
        quantity = item.get("quantity")
        unit = item.get("unit")
        if not isinstance(name, str) or not name.strip():
            logger.warning("Invalid item name")
            return False
        if not isinstance(quantity, (int, float)) or quantity <= 0:
            logger.warning("Invalid item quantity")
            return False
        if not isinstance(unit, str) or not unit.strip():
            logger.warning("Invalid item unit")
            return False

    logger.debug("Schema validation success for %d items", len(items))
    return True
