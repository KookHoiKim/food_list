import os
from io import BytesIO

import pytest

from app.services.image_preprocess import preprocess_for_gemini


def _build_large_png(width: int = 1800, height: int = 1800) -> bytes:
    Image = pytest.importorskip("PIL.Image")
    image = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_preprocess_for_gemini_noop_under_threshold() -> None:
    original = b"small-image"

    processed, mime_type, changed = preprocess_for_gemini(
        image_bytes=original,
        content_type="image/png",
        max_bytes=len(original),
    )

    assert processed == original
    assert mime_type == "image/png"
    assert changed is False


def test_preprocess_for_gemini_reduces_size_below_threshold() -> None:
    original = _build_large_png()

    processed, mime_type, changed = preprocess_for_gemini(
        image_bytes=original,
        content_type="image/png",
        max_bytes=600_000,
    )

    assert len(original) > 600_000
    assert changed is True
    assert mime_type == "image/jpeg"
    assert len(processed) <= 600_000
