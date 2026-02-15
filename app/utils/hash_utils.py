import hashlib
import logging

logger = logging.getLogger(__name__)


def calculate_image_hash(data: bytes) -> str:
    """Calculate SHA-256 hash from image bytes."""
    digest = hashlib.sha256(data).hexdigest()
    logger.debug("Calculated image hash: %s", digest)
    return digest
