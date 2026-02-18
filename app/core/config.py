from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    gemini_api_key: str = Field(alias="GEMINI_API_KEY")
    spreadsheet_id: str = Field(
        validation_alias=AliasChoices("SPREADSHEET_ID", "GOOGLE_SHEET_ID")
    )
    google_credentials_json: str = Field(
        validation_alias=AliasChoices("GOOGLE_CREDENTIALS_JSON", "SERVICE_ACCOUNT_CREDENTIALS_JSON")
    )
    sqlite_path: str = Field(default="./inventory_cache.db", alias="SQLITE_PATH")
    sheet_name: str = Field(default="Fridge", alias="SHEET_NAME")
    upload_token: str = Field(alias="UPLOAD_TOKEN")
    image_retention_days: int = Field(default=7, alias="IMAGE_RETENTION_DAYS")
    gemini_inline_max_bytes: int = Field(default=4 * 1024 * 1024, alias="GEMINI_INLINE_MAX_BYTES")
    gemini_preprocess_enabled: bool = Field(default=True, alias="GEMINI_PREPROCESS_ENABLED")

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    @property
    def sqlite_file(self) -> Path:
        return Path(self.sqlite_path)

    @property
    def google_sheet_id(self) -> str:
        """Backward-compatible alias."""
        return self.spreadsheet_id


@lru_cache
def get_settings() -> Settings:
    return Settings()
