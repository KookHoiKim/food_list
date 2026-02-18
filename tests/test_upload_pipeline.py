from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes
from app.core.metrics import metrics_tracker
from app.services.gemini_client import Item


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


def _mock_settings() -> SimpleNamespace:
    return SimpleNamespace(
        spreadsheet_id="sheet-123",
        sheet_name="Fridge",
        upload_token="secret-token",
        gemini_inline_max_bytes=4 * 1024 * 1024,
    )


def _reset_metrics() -> None:
    metrics_tracker.reset()


def test_upload_requires_token(monkeypatch) -> None:
    _reset_metrics()
    monkeypatch.setattr(routes, "get_settings", _mock_settings)

    client = _build_test_client()
    response = client.post(
        "/upload",
        files={"file": ("sample.jpg", b"\xff\xd8\xffdummy", "image/jpeg")},
    )

    assert response.status_code == 401


def test_upload_runs_full_pipeline(monkeypatch) -> None:
    _reset_metrics()
    monkeypatch.setattr(routes, "get_settings", _mock_settings)
    monkeypatch.setattr(routes, "calculate_image_hash", lambda _: "abc123")
    monkeypatch.setattr(routes, "is_hash_processed", lambda _: False)
    monkeypatch.setattr(routes, "save_upload", lambda **_: None)

    extraction = [
        Item(name_raw="우유 1L", qty=1, unit="개", confidence=0.9),
        Item(name_raw="양파", qty=2, unit="개", confidence=0.8),
    ]

    def _fake_extract_items_from_image(*, image_bytes: bytes):
        assert image_bytes
        return extraction

    monkeypatch.setattr(routes, "extract_items_from_image", _fake_extract_items_from_image)
    fake_sheets = _FakeSheetsClient()
    monkeypatch.setattr(routes, "SheetsClient", lambda: fake_sheets)

    client = _build_test_client()
    response = client.post(
        "/upload",
        headers={"X-Upload-Token": "secret-token"},
        files={"file": ("sample.jpg", b"\xff\xd8\xffdummy", "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["duplicate"] is False
    assert body["num_items_extracted"] == 2
    assert body["num_rows_appended"] == 2
    assert body["sheet"] == {"spreadsheet_id": "sheet-123", "sheet_name": "Fridge"}
    assert len(body["items_preview"]) == 2
    assert "confidence" in body["items_preview"][0]
    assert "processing_seconds" in body


def test_upload_duplicate_skips_pipeline(monkeypatch) -> None:
    _reset_metrics()
    monkeypatch.setattr(routes, "get_settings", _mock_settings)
    monkeypatch.setattr(routes, "calculate_image_hash", lambda _: "dup-hash")

    calls = {"is_hash_processed": 0, "save_upload": 0}

    def _is_hash_processed(file_hash: str) -> bool:
        calls["is_hash_processed"] += 1
        assert file_hash == "dup-hash"
        return True

    monkeypatch.setattr(routes, "is_hash_processed", _is_hash_processed)

    def _save_upload(**kwargs):
        calls["save_upload"] += 1

    monkeypatch.setattr(routes, "save_upload", _save_upload)

    def _should_not_call(*args, **kwargs):
        raise AssertionError("Gemini should not be called for duplicates")

    monkeypatch.setattr(routes, "extract_items_from_image", _should_not_call)

    client = _build_test_client()
    response = client.post(
        "/upload",
        headers={"X-Upload-Token": "secret-token"},
        files={"file": ("sample.jpg", b"\xff\xd8\xffdummy", "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["duplicate"] is True
    assert body["num_items_extracted"] == 0
    assert body["num_rows_appended"] == 0
    assert body["items_preview"] == []
    assert calls["is_hash_processed"] == 1
    assert calls["save_upload"] == 0


def test_upload_returns_stage_on_gemini_failure(monkeypatch) -> None:
    _reset_metrics()
    monkeypatch.setattr(routes, "get_settings", _mock_settings)
    monkeypatch.setattr(routes, "calculate_image_hash", lambda _: "abc123")
    monkeypatch.setattr(routes, "is_hash_processed", lambda _: False)
    monkeypatch.setattr(routes, "save_upload", lambda **_: None)

    def _raise_extract_error(*, image_bytes: bytes):
        raise RuntimeError("gemini unavailable")

    monkeypatch.setattr(routes, "extract_items_from_image", _raise_extract_error)

    client = _build_test_client()
    response = client.post(
        "/upload",
        headers={"X-Upload-Token": "secret-token"},
        files={"file": ("sample.jpg", b"\xff\xd8\xffdummy", "image/jpeg")},
    )

    assert response.status_code == 502
    body = response.json()
    assert body["stage"] == "gemini_extract"
    assert "processing_seconds" in body


def test_web_page_served() -> None:
    _reset_metrics()
    client = _build_test_client()
    response = client.get("/web")

    assert response.status_code == 200
    assert "이미지 업로드" in response.text
    assert "X-Upload-Token" in response.text


def test_metrics_endpoint_reports_counts(monkeypatch) -> None:
    _reset_metrics()
    monkeypatch.setattr(routes, "get_settings", _mock_settings)
    monkeypatch.setattr(routes, "calculate_image_hash", lambda _: "abc123")
    monkeypatch.setattr(routes, "is_hash_processed", lambda _: False)
    monkeypatch.setattr(routes, "save_upload", lambda **_: None)

    extraction = [Item(name_raw="우유", qty=1, unit="개", confidence=0.8)]

    def _fake_extract_items_from_image(*, image_bytes: bytes):
        return extraction

    monkeypatch.setattr(routes, "extract_items_from_image", _fake_extract_items_from_image)
    fake_sheets = _FakeSheetsClient()
    monkeypatch.setattr(routes, "SheetsClient", lambda: fake_sheets)

    client = _build_test_client()
    upload_response = client.post(
        "/upload",
        headers={"X-Upload-Token": "secret-token"},
        files={"file": ("sample.jpg", b"\xff\xd8\xffdummy", "image/jpeg")},
    )
    assert upload_response.status_code == 200

    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200
    metrics = metrics_response.json()
    assert metrics["total_uploads"] == 1
    assert metrics["duplicates"] == 0
    assert metrics["sheets_append_success"] == 1
    assert metrics["gemini_calls"] == 1


def test_upload_large_image_skips_gemini_call(monkeypatch) -> None:
    _reset_metrics()
    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(
            spreadsheet_id="sheet-123",
            sheet_name="Fridge",
            upload_token="secret-token",
            gemini_inline_max_bytes=4,
        ),
    )
    monkeypatch.setattr(routes, "calculate_image_hash", lambda _: "abc123")
    monkeypatch.setattr(routes, "is_hash_processed", lambda _: False)
    monkeypatch.setattr(routes, "save_upload", lambda **_: None)

    client = _build_test_client()
    response = client.post(
        "/upload",
        headers={"X-Upload-Token": "secret-token"},
        files={"file": ("sample.jpg", b"12345", "image/jpeg")},
    )

    assert response.status_code == 502
    body = response.json()
    assert body["stage"] == "gemini_extract"
    metrics = client.get("/metrics").json()
    assert metrics["gemini_calls"] == 0


def test_upload_accepts_null_qty_unit(monkeypatch) -> None:
    _reset_metrics()
    monkeypatch.setattr(routes, "get_settings", _mock_settings)
    monkeypatch.setattr(routes, "calculate_image_hash", lambda _: "abc123")
    monkeypatch.setattr(routes, "is_hash_processed", lambda _: False)
    monkeypatch.setattr(routes, "save_upload", lambda **_: None)

    extraction = [Item(name_raw="두부", qty=None, unit=None, confidence=0.45)]

    monkeypatch.setattr(routes, "extract_items_from_image", lambda *, image_bytes: extraction)
    fake_sheets = _FakeSheetsClient()
    monkeypatch.setattr(routes, "SheetsClient", lambda: fake_sheets)

    client = _build_test_client()
    response = client.post(
        "/upload",
        headers={"X-Upload-Token": "secret-token"},
        files={"file": ("sample.jpg", b"\xff\xd8\xffdummy", "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items_preview"][0]["qty"] is None
    assert body["items_preview"][0]["unit"] is None
    assert fake_sheets.appended_rows[0]["qty"] is None
    assert fake_sheets.appended_rows[0]["unit"] is None
