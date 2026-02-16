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
SOURCE_HASH_COLUMN_INDEX = HEADER_COLUMNS.index("source_hash")


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

    def has_hash_recently(self, source_hash: str, lookback_rows: int = 200) -> bool:
        """Return True if source_hash exists in recent rows."""
        if not source_hash.strip():
            return False

        hash_column_letter = _column_letter(SOURCE_HASH_COLUMN_INDEX + 1)
        hash_range = f"{self.sheet_name}!{hash_column_letter}2:{hash_column_letter}"
        response = (
            self._service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self.spreadsheet_id,
                range=hash_range,
                majorDimension="COLUMNS",
            )
            .execute()
        )
        columns = response.get("values", [])
        hashes = columns[0] if columns else []
        recent_hashes = [str(value).strip() for value in hashes[-lookback_rows:]]
        return source_hash.strip() in recent_hashes

    def append_rows(self, rows: Iterable[dict[str, Any]], lookback_rows: int = 200) -> int:
        """Append rows after header check and recent-hash deduplication.

        Returns the number of appended rows.
        """
        self.ensure_header()

        prepared_rows: list[list[Any]] = []
        buffered_hashes: set[str] = set()

        for row in rows:
            source_hash = str(row.get("source_hash", "")).strip()
            if source_hash:
                if source_hash in buffered_hashes:
                    logger.info("Skipping duplicate row in current batch (source_hash=%s)", source_hash)
                    continue
                if self.has_hash_recently(source_hash, lookback_rows=lookback_rows):
                    logger.info("Skipping duplicate row already in sheet (source_hash=%s)", source_hash)
                    continue
                buffered_hashes.add(source_hash)

            prepared_rows.append([_to_sheet_value(row.get(column)) for column in HEADER_COLUMNS])

        if not prepared_rows:
            logger.info("No rows to append after deduplication")
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
        logger.info("Appended %d row(s) to sheet", len(prepared_rows))
        return len(prepared_rows)

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



def _column_letter(column_index_1_based: int) -> str:
    if column_index_1_based < 1:
        raise ValueError("column_index_1_based must be >= 1")

    result = ""
    index = column_index_1_based
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result
