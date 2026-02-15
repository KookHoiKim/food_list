import logging

from fastapi import FastAPI

from app.api.routes import router
from app.core.logging_config import configure_logging
from app.db.cache import init_db

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Food List Uploader", version="0.1.0")
app.include_router(router)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    logger.info("Application started and database initialized")
