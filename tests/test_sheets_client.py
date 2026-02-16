from datetime import date

from app.services.sheets_client import HEADER_COLUMNS, SheetsClient, _column_letter, _to_sheet_value


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


def test_has_hash_recently_uses_lookback(monkeypatch):
    fake_service = _FakeService(
        get_responses=[{"values": [["old", "middle", "latest"]]}]
    )
    monkeypatch.setattr(SheetsClient, "_build_service", lambda self: fake_service)
    client = SheetsClient(
        spreadsheet_id="sheet-id",
        sheet_name="Fridge",
        credentials_json='{"type": "service_account"}',
    )

    assert client.has_hash_recently("latest", lookback_rows=2)
    assert not client.has_hash_recently("old", lookback_rows=2)


def test_append_rows_skips_duplicates_and_uses_user_entered(monkeypatch):
    fake_service = _FakeService(
        get_responses=[{}, {"values": [["existing-hash"]]}, {"values": [["existing-hash"]]}]
    )
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
                "source_hash": "new-hash",
            },
            {
                "id": "2",
                "name_raw": "중복",
                "source_hash": "new-hash",
            },
            {
                "id": "3",
                "name_raw": "기존",
                "source_hash": "existing-hash",
            },
        ]
    )

    assert appended == 1
    assert len(fake_service.values_api.append_calls) == 1
    call = fake_service.values_api.append_calls[0]
    assert call["valueInputOption"] == "USER_ENTERED"
    assert call["body"]["values"][0][0] == "1"
    assert call["body"]["values"][0][2] == "2025-01-01"


def test_column_letter_and_sheet_value_helpers():
    assert _column_letter(1) == "A"
    assert _column_letter(15) == "O"
    assert _column_letter(27) == "AA"
    assert _to_sheet_value(None) == ""
    assert _to_sheet_value(date(2025, 1, 1)) == "2025-01-01"
