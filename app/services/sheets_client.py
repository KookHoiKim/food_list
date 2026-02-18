import json
import logging
from datetime import date, datetime
from typing import Any, Iterable

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import Resource, build

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADER_COLUMNS = [
    "id",
    "added_at",
    "purchase_date",
    "name_raw",
    "name_norm",
    "qty",
    "unit",
    "storage",
    "category",
    "default_days",
    "expiry_estimated",
    "expiry_override",
    "status",
    "source",
    "source_hash",
    "note",
]


class SheetsClient:
    def __init__(
        self,
        *,
        spreadsheet_id: str | None = None,
        sheet_name: str | None = None,
        credentials_json: str | None = None,
    ) -> None:
        settings = None
        if spreadsheet_id is None or sheet_name is None or credentials_json is None:
            settings = get_settings()

        self.spreadsheet_id = spreadsheet_id or settings.spreadsheet_id
        self.sheet_name = sheet_name or settings.sheet_name
        self._credentials_json = credentials_json or settings.google_credentials_json
        self._service = self._build_service()

    def ensure_header(self) -> None:
        """Ensure the first row has header columns when the sheet is empty."""
        header_range = f"{self.sheet_name}!1:1"
        response = (
            self._service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=header_range,
                majorDimension="ROWS",
            )
            .execute()
        )
        values = response.get("values", [])

        if values and any(cell.strip() for cell in values[0] if isinstance(cell, str)):
            return

        logger.info("Header missing or empty. Initializing sheet header row")
        (
            self._service.spreadsheets()
            .values()
            .update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A1:P1",
                valueInputOption="RAW",
                body={"values": [HEADER_COLUMNS]},
            )
            .execute()
        )

    def append_rows(self, rows: Iterable[dict[str, Any]]) -> int:
        """Append rows after header check.

        Returns the number of appended rows.
        """
        self.ensure_header()

        prepared_rows: list[list[Any]] = []

        for row in rows:
            prepared_rows.append([_to_sheet_value(row.get(column)) for column in HEADER_COLUMNS])

        if not prepared_rows:
            logger.info("No rows to append")
            return 0

        (
            self._service.spreadsheets()
            .values()
            .append(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!A:P",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": prepared_rows},
            )
            .execute()
        )
        logger.info("Appended %d row(s) to sheet without source_hash deduplication", len(prepared_rows))
        return len(prepared_rows)

    def list_rows(self) -> list[dict[str, Any]]:
        """Read rows from the sheet and return list[dict] keyed by header columns."""
        header_response = (
            self._service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!1:1",
                majorDimension="ROWS",
            )
            .execute()
        )
        header_values = header_response.get("values", [])
        if not header_values:
            return []

        headers = [str(cell).strip() for cell in header_values[0]]
        if not any(headers):
            return []

        rows_response = (
            self._service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=f"{self.sheet_name}!2:100000",
                majorDimension="ROWS",
            )
            .execute()
        )
        data_rows = rows_response.get("values", [])

        parsed_rows: list[dict[str, Any]] = []
        for row in data_rows:
            parsed_row: dict[str, Any] = {}
            for idx, header in enumerate(headers):
                if not header:
                    continue
                parsed_row[header] = row[idx] if idx < len(row) else ""
            parsed_rows.append(parsed_row)

        return parsed_rows

    def _build_service(self) -> Resource:
        credentials_info = _parse_credentials_json(self._credentials_json)
        credentials = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
        return build("sheets", "v4", credentials=credentials)



def _parse_credentials_json(credentials_json: str) -> dict[str, Any]:
    raw = credentials_json.strip()
    if raw.startswith("{"):
        return json.loads(raw)

    with open(raw, encoding="utf-8") as fp:
        return json.load(fp)



def _to_sheet_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
