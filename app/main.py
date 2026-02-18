import logging

from fastapi import FastAPI

from app.api.routes import UPLOAD_DIR, router
from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.db.cache import delete_uploads_older_than, init_db

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except Exception:  # pragma: no cover - optional runtime dependency guard
    BackgroundScheduler = None

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Food List Uploader", version="0.1.0")
app.include_router(router)
scheduler = BackgroundScheduler() if BackgroundScheduler else None


def cleanup_old_uploads() -> None:
    settings = get_settings()
    deleted = delete_uploads_older_than(days=settings.image_retention_days, upload_dir=UPLOAD_DIR)
    logger.info("Upload retention cleanup completed. deleted=%d", deleted)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    cleanup_old_uploads()
    if scheduler:
        scheduler.add_job(
            cleanup_old_uploads,
            "interval",
            days=1,
            id="image-retention-cleanup",
            replace_existing=True,
        )
        scheduler.start()
    logger.info("Application started and database initialized")


@app.on_event("shutdown")
def on_shutdown() -> None:
    if scheduler:
        scheduler.shutdown(wait=False)
