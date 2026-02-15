import logging
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def init_db() -> None:
    settings = get_settings()
    with sqlite3.connect(settings.sqlite_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_uploads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_hash TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    logger.info("SQLite cache initialized at %s", settings.sqlite_path)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    settings = get_settings()
    conn = sqlite3.connect(settings.sqlite_path)
    try:
        yield conn
    finally:
        conn.close()


def is_hash_processed(image_hash: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT 1 FROM processed_uploads WHERE image_hash = ? LIMIT 1", (image_hash,)
        )
        exists = cursor.fetchone() is not None
    logger.info("Hash %s processed: %s", image_hash, exists)
    return exists


def save_processed_hash(image_hash: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed_uploads(image_hash) VALUES (?)", (image_hash,)
        )
        conn.commit()
    logger.info("Saved processed hash %s", image_hash)
