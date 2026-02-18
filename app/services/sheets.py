import json
import logging

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from app.core.config import get_settings
from app.services.gemini_client import Item

logger = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def append_inventory_to_sheet(extraction: list[Item]) -> None:
    settings = get_settings()
    credentials_info = json.loads(settings.google_credentials_json)
    credentials = Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
    service = build("sheets", "v4", credentials=credentials)

    values = [[item.name_raw, item.qty, item.unit] for item in extraction]
    body = {"values": values}
    range_name = f"{settings.sheet_name}!A:C"

    logger.info("Appending %d rows to Google Sheets", len(values))
    (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=settings.google_sheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        )
        .execute()
    )
