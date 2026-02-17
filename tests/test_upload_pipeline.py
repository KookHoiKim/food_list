from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes
from app.models.inventory import InventoryExtraction, InventoryItem


class _FakeSheetsClient:
    def __init__(self) -> None:
        self.appended_rows = []

    def append_rows(self, rows):
        self.appended_rows = list(rows)
        return len(self.appended_rows)


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


def test_upload_runs_full_pipeline(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(spreadsheet_id="sheet-123", sheet_name="Fridge"),
    )
    monkeypatch.setattr(routes, "calculate_image_hash", lambda _: "abc123")
    monkeypatch.setattr(routes, "is_hash_processed", lambda _: False)
    monkeypatch.setattr(routes, "save_upload", lambda **_: None)

    extraction = InventoryExtraction(
        items=[
            InventoryItem(name="우유 1L", quantity=1, unit="개"),
            InventoryItem(name="양파", quantity=2, unit="개"),
        ]
    )

    async def _fake_extract_inventory_from_image(*, image_bytes: bytes, mime_type: str):
        assert image_bytes
        assert mime_type == "image/jpeg"
        return extraction

    monkeypatch.setattr(routes, "extract_inventory_from_image", _fake_extract_inventory_from_image)
    fake_sheets = _FakeSheetsClient()
    monkeypatch.setattr(routes, "SheetsClient", lambda: fake_sheets)

    client = _build_test_client()
    response = client.post(
        "/upload",
        files={"file": ("sample.jpg", b"\xff\xd8\xffdummy", "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["duplicate"] is False
    assert body["num_items_extracted"] == 2
    assert body["num_rows_appended"] == 2
    assert body["sheet"] == {"spreadsheet_id": "sheet-123", "sheet_name": "Fridge"}
    assert len(body["items_preview"]) == 2
    assert "processing_seconds" in body


def test_upload_duplicate_skips_pipeline(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(spreadsheet_id="sheet-123", sheet_name="Fridge"),
    )
    monkeypatch.setattr(routes, "calculate_image_hash", lambda _: "dup-hash")
    monkeypatch.setattr(routes, "is_hash_processed", lambda _: True)

    async def _should_not_call(*args, **kwargs):
        raise AssertionError("Gemini should not be called for duplicates")

    monkeypatch.setattr(routes, "extract_inventory_from_image", _should_not_call)

    client = _build_test_client()
    response = client.post(
        "/upload",
        files={"file": ("sample.jpg", b"\xff\xd8\xffdummy", "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["duplicate"] is True
    assert body["num_items_extracted"] == 0
    assert body["num_rows_appended"] == 0
    assert body["items_preview"] == []


def test_upload_returns_stage_on_gemini_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(spreadsheet_id="sheet-123", sheet_name="Fridge"),
    )
    monkeypatch.setattr(routes, "calculate_image_hash", lambda _: "abc123")
    monkeypatch.setattr(routes, "is_hash_processed", lambda _: False)
    monkeypatch.setattr(routes, "save_upload", lambda **_: None)

    async def _raise_extract_error(*, image_bytes: bytes, mime_type: str):
        raise RuntimeError("gemini unavailable")

    monkeypatch.setattr(routes, "extract_inventory_from_image", _raise_extract_error)

    client = _build_test_client()
    response = client.post(
        "/upload",
        files={"file": ("sample.jpg", b"\xff\xd8\xffdummy", "image/jpeg")},
    )

    assert response.status_code == 502
    body = response.json()
    assert body["stage"] == "gemini_extract"
    assert "processing_seconds" in body
