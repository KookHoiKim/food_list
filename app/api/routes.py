import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.db.cache import is_hash_processed, save_upload
from app.utils.hash_utils import calculate_image_hash

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
SUPPORTED_CONTENT_TYPES = {"image/jpeg", "image/png"}
UPLOAD_DIR = Path("./data/uploads")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/upload")
async def upload_inventory_image(file: UploadFile = File(...)) -> dict[str, object]:
    if file.content_type not in SUPPORTED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Only JPG and PNG files are supported")

    image_bytes = await file.read()
    file_size = len(image_bytes)
    if file_size > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File size exceeds limit (10MB)")

    file_hash = calculate_image_hash(image_bytes)

    if is_hash_processed(file_hash):
        logger.info("Duplicate upload detected: %s", file_hash)
        return {"duplicate": True, "hash": file_hash}

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / f"{file_hash}.jpg"
    destination.write_bytes(image_bytes)
    save_upload(file_hash=file_hash, original_filename=file.filename, size_bytes=file_size)

    return {
        "duplicate": False,
        "hash": file_hash,
        "saved_path": str(destination),
        "size_bytes": file_size,
    }
