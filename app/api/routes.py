import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.db.cache import is_hash_processed, save_processed_hash
from app.services.gemini import extract_inventory_from_image
from app.services.sheets import append_inventory_to_sheet
from app.utils.hash_utils import calculate_image_hash

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/upload")
async def upload_inventory_image(file: UploadFile = File(...)) -> dict[str, object]:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Image file only")

    image_bytes = await file.read()
    image_hash = calculate_image_hash(image_bytes)

    if is_hash_processed(image_hash):
        logger.info("Duplicate upload detected: %s", image_hash)
        return {"status": "skipped", "reason": "duplicate_upload", "image_hash": image_hash}

    try:
        extraction = await extract_inventory_from_image(image_bytes, file.content_type)
        append_inventory_to_sheet(extraction)
        save_processed_hash(image_hash)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to process upload")
        raise HTTPException(status_code=500, detail=f"Processing failed: {exc}") from exc

    return {
        "status": "processed",
        "image_hash": image_hash,
        "item_count": len(extraction.items),
    }
