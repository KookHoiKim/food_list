import pytest
from pydantic import ValidationError

from app.services.gemini_client import parse_items_json


def test_unified_schema_accepts_nullable_qty_and_unit() -> None:
    raw = '[{"name_raw":"양파","qty":null,"unit":null,"confidence":0.5}]'

    items = parse_items_json(raw)

    assert items[0].qty is None
    assert items[0].unit is None
    assert items[0].name_norm


def test_unified_schema_rejects_missing_confidence() -> None:
    raw = '[{"name_raw":"양파","qty":1,"unit":"개"}]'

    with pytest.raises(ValidationError):
        parse_items_json(raw)
