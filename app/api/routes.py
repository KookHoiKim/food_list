import logging
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.db.cache import is_hash_processed, save_upload
from app.services.gemini import extract_inventory_from_image
from app.services.normalize import categorize_item, estimate_expiry, normalize_name
from app.services.sheets_client import SheetsClient
from app.utils.hash_utils import calculate_image_hash

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
SUPPORTED_CONTENT_TYPES = {"image/jpeg", "image/png"}
UPLOAD_DIR = Path("./data/uploads")
EXTENSION_BY_CONTENT_TYPE = {"image/jpeg": ".jpg", "image/png": ".png"}


class PipelineStageError(Exception):
    def __init__(self, stage: str, status_code: int, message: str) -> None:
        super().__init__(message)
        self.stage = stage
        self.status_code = status_code
        self.message = message


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/upload")
async def upload_inventory_image(file: UploadFile = File(...)) -> dict[str, object]:
    started_at = time.perf_counter()
    settings = get_settings()

    try:
        validation_started = time.perf_counter()
        if file.content_type not in SUPPORTED_CONTENT_TYPES:
            raise PipelineStageError(
                stage="validate_input",
                status_code=400,
                message="Only JPG and PNG files are supported",
            )

        image_bytes = await file.read()
        file_size = len(image_bytes)
        if file_size == 0:
            raise PipelineStageError(stage="validate_input", status_code=400, message="Uploaded file is empty")
        if file_size > MAX_UPLOAD_SIZE_BYTES:
            raise PipelineStageError(
                stage="validate_input",
                status_code=413,
                message="File size exceeds limit (10MB)",
            )
        logger.info("[stage=validate_input] done in %.3fs", time.perf_counter() - validation_started)

        hash_started = time.perf_counter()
        try:
            file_hash = calculate_image_hash(image_bytes)
            is_duplicate = is_hash_processed(file_hash)

            if not is_duplicate:
                UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                extension = EXTENSION_BY_CONTENT_TYPE.get(file.content_type, ".jpg")
                destination = UPLOAD_DIR / f"{file_hash}{extension}"
                destination.write_bytes(image_bytes)
                save_upload(file_hash=file_hash, original_filename=file.filename, size_bytes=file_size)
        except Exception as exc:  # noqa: BLE001
            raise PipelineStageError(stage="hash_and_save", status_code=500, message=str(exc)) from exc
        logger.info("[stage=hash_and_save] done in %.3fs", time.perf_counter() - hash_started)

        if is_duplicate:
            elapsed = time.perf_counter() - started_at
            logger.info("Duplicate upload detected: %s", file_hash)
            return {
                "duplicate": True,
                "num_items_extracted": 0,
                "num_rows_appended": 0,
                "sheet": {
                    "spreadsheet_id": settings.spreadsheet_id,
                    "sheet_name": settings.sheet_name,
                },
                "items_preview": [],
                "processing_seconds": round(elapsed, 3),
            }

        gemini_started = time.perf_counter()
        try:
            extraction = await extract_inventory_from_image(image_bytes=image_bytes, mime_type=file.content_type)
        except Exception as exc:  # noqa: BLE001
            raise PipelineStageError(stage="gemini_extract", status_code=502, message=str(exc)) from exc
        logger.info("[stage=gemini_extract] done in %.3fs", time.perf_counter() - gemini_started)

        normalize_started = time.perf_counter()
        try:
            purchase_date = datetime.now().date()
            rows_to_append: list[dict[str, object]] = []
            preview: list[dict[str, object]] = []
            for item in extraction.items:
                name_norm = normalize_name(item.name)
                category, storage, default_days = categorize_item(item.name, name_norm)
                expiry_estimated = estimate_expiry(purchase_date, default_days)

                row = {
                    "id": str(uuid4()),
                    "added_at": datetime.now().isoformat(timespec="seconds"),
                    "purchase_date": purchase_date,
                    "name_raw": item.name,
                    "name_norm": name_norm,
                    "qty": item.quantity,
                    "unit": item.unit,
                    "storage": storage,
                    "category": category,
                    "default_days": default_days,
                    "expiry_estimated": expiry_estimated,
                    "expiry_override": "",
                    "status": "active",
                    "source": "gemini",
                    "source_hash": file_hash,
                    "note": "",
                }
                rows_to_append.append(row)

                if len(preview) < 5:
                    preview.append(
                        {
                            "name_raw": item.name,
                            "name_norm": name_norm,
                            "qty": item.quantity,
                            "unit": item.unit,
                            "category": category,
                            "storage": storage,
                            "expiry_estimated": expiry_estimated.isoformat(),
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            raise PipelineStageError(stage="normalize_items", status_code=500, message=str(exc)) from exc
        logger.info("[stage=normalize_items] done in %.3fs", time.perf_counter() - normalize_started)

        sheets_started = time.perf_counter()
        try:
            sheets_client = SheetsClient()
            num_rows_appended = sheets_client.append_rows(rows_to_append)
        except Exception as exc:  # noqa: BLE001
            raise PipelineStageError(stage="append_sheet", status_code=502, message=str(exc)) from exc
        logger.info("[stage=append_sheet] done in %.3fs", time.perf_counter() - sheets_started)

        elapsed = time.perf_counter() - started_at
        return {
            "duplicate": False,
            "num_items_extracted": len(extraction.items),
            "num_rows_appended": num_rows_appended,
            "sheet": {
                "spreadsheet_id": settings.spreadsheet_id,
                "sheet_name": settings.sheet_name,
            },
            "items_preview": preview,
            "processing_seconds": round(elapsed, 3),
        }
    except PipelineStageError as exc:
        elapsed = time.perf_counter() - started_at
        logger.exception("Upload pipeline failed at stage=%s", exc.stage)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "stage": exc.stage,
                "message": exc.message,
                "processing_seconds": round(elapsed, 3),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        elapsed = time.perf_counter() - started_at
        logger.exception("Upload pipeline failed at unknown stage")
        return JSONResponse(
            status_code=500,
            content={
                "stage": "unknown",
                "message": str(exc),
                "processing_seconds": round(elapsed, 3),
            },
        )
