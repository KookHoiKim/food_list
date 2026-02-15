from app.utils.schema_validation import validate_inventory_json


def test_inventory_schema_validation_success() -> None:
    payload = {"items": [{"name": "Apple", "quantity": 3, "unit": "ea"}]}
    assert validate_inventory_json(payload) is True


def test_inventory_schema_validation_failure() -> None:
    payload = {"items": [{"name": "", "quantity": 0, "unit": ""}]}
    assert validate_inventory_json(payload) is False
