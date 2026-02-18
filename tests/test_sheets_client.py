from datetime import date

from app.services.sheets_client import (
    HEADER_COLUMNS,
    RowNotFoundError,
    SheetsClient,
    _column_letter_from_index,
    _to_sheet_value,
)


class _FakeRequest:
    def __init__(self, payload, recorder):
        self.payload = payload
        self.recorder = recorder

    def execute(self):
        self.recorder.append(self.payload)
        return self.payload.get("response", {})


class _FakeValuesApi:
    def __init__(self, get_responses):
        self.get_responses = list(get_responses)
        self.executed = []
        self.append_calls = []
        self.update_calls = []

    def get(self, **kwargs):
        response = self.get_responses.pop(0) if self.get_responses else {}
        return _FakeRequest({"kind": "get", "kwargs": kwargs, "response": response}, self.executed)

    def update(self, **kwargs):
        self.update_calls.append(kwargs)
        return _FakeRequest({"kind": "update", "kwargs": kwargs, "response": {}}, self.executed)

    def append(self, **kwargs):
        self.append_calls.append(kwargs)
        return _FakeRequest({"kind": "append", "kwargs": kwargs, "response": {}}, self.executed)


class _FakeSpreadsheetsApi:
    def __init__(self, values_api):
        self._values_api = values_api

    def values(self):
        return self._values_api


class _FakeService:
    def __init__(self, get_responses):
        self.values_api = _FakeValuesApi(get_responses)

    def spreadsheets(self):
        return _FakeSpreadsheetsApi(self.values_api)


def test_ensure_header_writes_header_on_empty_sheet(monkeypatch):
    fake_service = _FakeService(get_responses=[{}])
    monkeypatch.setattr(SheetsClient, "_build_service", lambda self: fake_service)

    client = SheetsClient(
        spreadsheet_id="sheet-id",
        sheet_name="Fridge",
        credentials_json='{"type": "service_account"}',
    )
    client.ensure_header()

    assert len(fake_service.values_api.update_calls) == 1
    body = fake_service.values_api.update_calls[0]["body"]
    assert body["values"][0] == HEADER_COLUMNS


def test_append_rows_keeps_same_source_hash_rows_and_uses_user_entered(monkeypatch):
    fake_service = _FakeService(get_responses=[{}])
    monkeypatch.setattr(SheetsClient, "_build_service", lambda self: fake_service)
    client = SheetsClient(
        spreadsheet_id="sheet-id",
        sheet_name="Fridge",
        credentials_json='{"type": "service_account"}',
    )

    appended = client.append_rows(
        [
            {
                "id": "1",
                "purchase_date": date(2025, 1, 1),
                "name_raw": "우유 1L",
                "name_norm": "우유",
                "qty": 1,
                "unit": "개",
                "storage": "냉장",
                "category": "dairy",
                "default_days": 7,
                "expiry_estimated": date(2025, 1, 8),
                "status": "active",
                "source": "ocr",
                "source_hash": "same-upload",
            },
            {
                "id": "2",
                "name_raw": "중복",
                "source_hash": "same-upload",
            },
            {
                "id": "3",
                "name_raw": "추가",
                "source_hash": "same-upload",
            },
        ]
    )

    assert appended == 3
    assert len(fake_service.values_api.append_calls) == 1
    call = fake_service.values_api.append_calls[0]
    assert call["valueInputOption"] == "USER_ENTERED"
    assert len(call["body"]["values"]) == 3
    assert call["body"]["values"][0][0] == "1"
    assert call["body"]["values"][0][2] == "2025-01-01"


def test_sheet_value_helper():
    assert _to_sheet_value(None) == ""
    assert _to_sheet_value(date(2025, 1, 1)) == "2025-01-01"


def test_list_rows_returns_dicts_by_header(monkeypatch):
    fake_service = _FakeService(
        get_responses=[
            {"values": [HEADER_COLUMNS]},
            {"values": [["1", "2025-01-01T00:00:00", "2025-01-01", "우유", "우유", "1"]]},
        ]
    )
    monkeypatch.setattr(SheetsClient, "_build_service", lambda self: fake_service)

    client = SheetsClient(
        spreadsheet_id="sheet-id",
        sheet_name="Fridge",
        credentials_json='{"type": "service_account"}',
    )

    rows = client.list_rows()

    assert len(rows) == 1
    assert rows[0]["id"] == "1"
    assert rows[0]["name_raw"] == "우유"
    assert rows[0]["qty"] == "1"
    assert rows[0]["status"] == ""


def test_list_rows_empty_header_returns_empty(monkeypatch):
    fake_service = _FakeService(get_responses=[{}])
    monkeypatch.setattr(SheetsClient, "_build_service", lambda self: fake_service)

    client = SheetsClient(
        spreadsheet_id="sheet-id",
        sheet_name="Fridge",
        credentials_json='{"type": "service_account"}',
    )

    assert client.list_rows() == []


def test_update_row_by_id_updates_only_selected_columns(monkeypatch):
    fake_service = _FakeService(get_responses=[{"values": [["item-1", "item-2"]]}])
    monkeypatch.setattr(SheetsClient, "_build_service", lambda self: fake_service)

    client = SheetsClient(
        spreadsheet_id="sheet-id",
        sheet_name="Fridge",
        credentials_json='{"type": "service_account"}',
    )

    client.update_row_by_id(
        "item-2",
        {"status": "used", "expiry_override": "2025-01-31", "note": "opened", "ignored": "x"},
    )

    assert len(fake_service.values_api.update_calls) == 3
    ranges = [call["range"] for call in fake_service.values_api.update_calls]
    assert "Fridge!M3" in ranges
    assert "Fridge!L3" in ranges
    assert "Fridge!P3" in ranges


def test_update_row_by_id_raises_not_found(monkeypatch):
    fake_service = _FakeService(get_responses=[{"values": [["item-1"]]}])
    monkeypatch.setattr(SheetsClient, "_build_service", lambda self: fake_service)

    client = SheetsClient(
        spreadsheet_id="sheet-id",
        sheet_name="Fridge",
        credentials_json='{"type": "service_account"}',
    )

    try:
        client.update_row_by_id("missing", {"note": "x"})
    except RowNotFoundError:
        pass
    else:
        raise AssertionError("Expected RowNotFoundError")


def test_update_row_by_id_requires_fields(monkeypatch):
    fake_service = _FakeService(get_responses=[{"values": [["item-1"]]}])
    monkeypatch.setattr(SheetsClient, "_build_service", lambda self: fake_service)

    client = SheetsClient(
        spreadsheet_id="sheet-id",
        sheet_name="Fridge",
        credentials_json='{"type": "service_account"}',
    )

    try:
        client.update_row_by_id("item-1", {"unknown": "x"})
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError")


def test_column_letter_from_index():
    assert _column_letter_from_index(0) == "A"
    assert _column_letter_from_index(15) == "P"
    assert _column_letter_from_index(26) == "AA"
