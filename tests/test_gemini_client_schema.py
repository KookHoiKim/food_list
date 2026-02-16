import pytest
from pydantic import ValidationError

from app.services.gemini_client import parse_items_json


def test_parse_items_json_valid_array() -> None:
    raw = """
    [
      {
        "name_raw": "신라면",
        "qty": 2,
        "unit": "팩",
        "confidence": 0.96
      },
      {
        "name_raw": "우유",
        "qty": null,
        "unit": null,
        "confidence": 0.42
      }
    ]
    """

    items = parse_items_json(raw)

    assert len(items) == 2
    assert items[0].name_raw == "신라면"
    assert items[0].qty == 2
    assert items[1].qty is None


def test_parse_items_json_rejects_non_array() -> None:
    raw = '{"items": []}'

    with pytest.raises(ValidationError):
        parse_items_json(raw)


def test_parse_items_json_rejects_out_of_range_confidence() -> None:
    raw = '[{"name_raw":"사과","qty":1,"unit":"개","confidence":1.4}]'

    with pytest.raises(ValidationError):
        parse_items_json(raw)
