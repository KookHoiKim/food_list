from app.utils.hash_utils import calculate_image_hash


def test_calculate_image_hash_is_deterministic() -> None:
    data = b"sample_image_bytes"
    assert calculate_image_hash(data) == calculate_image_hash(data)
