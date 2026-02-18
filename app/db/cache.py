import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def init_db() -> None:
    settings = get_settings()
    with sqlite3.connect(settings.sqlite_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS uploads (
                hash TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                original_filename TEXT,
                size_bytes INTEGER NOT NULL
            )
            """
        )
        conn.commit()
    logger.info("SQLite uploads table initialized at %s", settings.sqlite_path)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    settings = get_settings()
    conn = sqlite3.connect(settings.sqlite_path)
    try:
        yield conn
    finally:
        conn.close()


def is_hash_processed(file_hash: str) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("SELECT 1 FROM uploads WHERE hash = ? LIMIT 1", (file_hash,))
        exists = cursor.fetchone() is not None
    logger.info("Hash %s exists: %s", file_hash, exists)
    return exists


def save_upload(file_hash: str, original_filename: str | None, size_bytes: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO uploads(hash, original_filename, size_bytes)
            VALUES (?, ?, ?)
            """,
            (file_hash, original_filename, size_bytes),
        )
        conn.commit()
    logger.info("Saved upload record %s", file_hash)


def delete_uploads_older_than(days: int, upload_dir: Path) -> int:
    if days <= 0:
        return 0

    cutoff = datetime.now() - timedelta(days=days)
    cutoff_text = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        rows = conn.execute(
            "SELECT hash FROM uploads WHERE created_at < ?",
            (cutoff_text,),
        ).fetchall()

        if not rows:
            return 0

        deleted = 0
        for (file_hash,) in rows:
            for extension in (".jpg", ".png"):
                file_path = upload_dir / f"{file_hash}{extension}"
                if file_path.exists():
                    file_path.unlink()
            conn.execute("DELETE FROM uploads WHERE hash = ?", (file_hash,))
            deleted += 1

        conn.commit()

    logger.info("Deleted %d uploads older than %d days", deleted, days)
    return deleted
