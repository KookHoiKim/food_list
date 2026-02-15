from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    gemini_api_key: str = Field(alias="GEMINI_API_KEY")
    google_sheet_id: str = Field(alias="GOOGLE_SHEET_ID")
    google_credentials_json: str = Field(alias="GOOGLE_CREDENTIALS_JSON")
    sqlite_path: str = Field(default="./inventory_cache.db", alias="SQLITE_PATH")
    sheet_name: str = Field(default="Inventory", alias="SHEET_NAME")

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    @property
    def sqlite_file(self) -> Path:
        return Path(self.sqlite_path)


@lru_cache
def get_settings() -> Settings:
    return Settings()
