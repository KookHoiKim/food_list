from io import BytesIO

JPEG_WIDTH_STEPS = (1600, 1200, 1000)
JPEG_QUALITY_STEPS = (85, 70)


def _to_rgb(image, image_module):
    if image.mode in {"RGB", "L"}:
        return image.convert("RGB")

    converted = image.convert("RGBA")
    background = image_module.new("RGB", converted.size, (255, 255, 255))
    background.paste(converted, mask=converted.split()[3])
    return background


def _encode_jpeg(image, *, quality: int) -> bytes:
    output = BytesIO()
    image.save(output, format="JPEG", quality=quality, optimize=True)
    return output.getvalue()


def preprocess_for_gemini(
    image_bytes: bytes,
    content_type: str,
    max_bytes: int,
) -> tuple[bytes, str, bool]:
    if len(image_bytes) <= max_bytes:
        return image_bytes, content_type, False

    from PIL import Image, ImageOps

    with Image.open(BytesIO(image_bytes)) as opened:
        image = _to_rgb(ImageOps.exif_transpose(opened), Image)

    for max_width in JPEG_WIDTH_STEPS:
        resized = image.copy()
        if resized.width > max_width:
            ratio = max_width / resized.width
            resized = resized.resize(
                (max_width, int(resized.height * ratio)), Image.Resampling.LANCZOS
            )

        for quality in JPEG_QUALITY_STEPS:
            candidate = _encode_jpeg(resized, quality=quality)
            if len(candidate) <= max_bytes:
                return candidate, "image/jpeg", True

    smallest = _encode_jpeg(
        (
            image.resize(
                (
                    min(image.width, JPEG_WIDTH_STEPS[-1]),
                    int(image.height * min(image.width, JPEG_WIDTH_STEPS[-1]) / image.width),
                ),
                Image.Resampling.LANCZOS,
            )
            if image.width > JPEG_WIDTH_STEPS[-1]
            else image
        ),
        quality=JPEG_QUALITY_STEPS[-1],
    )
    return smallest, "image/jpeg", True
