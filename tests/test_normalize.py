from datetime import date

from app.services.gemini_client import parse_items_json
from app.services.normalize import categorize_item, normalize_name


def test_normalize_name_removes_parentheses_and_capacity() -> None:
    assert normalize_name("서울우유 (무가당) 1L x2") == "서울우유"


def test_categorize_item_assigns_frozen_defaults() -> None:
    category, storage, default_days = categorize_item("냉동 만두", "만두")
    assert category == "frozen"
    assert storage == "냉동"
    assert default_days == 30


def test_parse_items_json_applies_expiry_from_purchase_date() -> None:
    raw = (
        '[{"name_raw":"우유 1L","qty":1,"unit":"개","confidence":0.9,"purchase_date":"2025-01-01"}]'
    )
    items = parse_items_json(raw)

    assert items[0].name_norm == "우유"
    assert items[0].category == "dairy"
    assert items[0].expiry_estimated == date(2025, 1, 8)
