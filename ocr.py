"""Image preprocessing and OCR for scanned maintenance records.

Heavy dependencies (OpenCV, PaddleOCR, pdf2image) are imported lazily inside
the functions that need them. This keeps module import cheap, lets the rest
of the app load even before the OCR stack is installed, and defers the
expensive PaddleOCR model load until the first page is actually processed.
"""

from pathlib import Path

# Supported raster inputs for the record uploader (US 2.1).
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}

_OCR_ENGINE = None


def _get_engine():
    """Return a cached PaddleOCR engine, loading it on first use."""
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        from paddleocr import PaddleOCR

        # angle classifier handles rotated scans; English logbooks/work orders.
        _OCR_ENGINE = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    return _OCR_ENGINE


def pdf_to_images(pdf_path: str | Path, out_dir: str | Path,
                  dpi: int = 300) -> list[Path]:
    """Rasterize each PDF page to a PNG and return the image paths (US 2.1)."""
    from pdf2image import convert_from_path

    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pages = convert_from_path(str(pdf_path), dpi=dpi)
    paths: list[Path] = []
    for i, image in enumerate(pages, start=1):
        target = out_dir / f"{pdf_path.stem}_page{i:03d}.png"
        image.save(target, "PNG")
        paths.append(target)
    return paths


def preprocess_image(image_path: str | Path):
    """Grayscale, denoise, and deskew a scan to improve OCR accuracy (US 2.2).

    Returns an OpenCV image (numpy array). Deskew estimates the dominant text
    angle from the foreground pixels and rotates the page back to level.
    """
    import cv2
    import numpy as np

    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)

    # Deskew: find the angle of the text block via min-area rectangle.
    inverted = cv2.bitwise_not(denoised)
    thresh = cv2.threshold(
        inverted, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU
    )[1]
    coords = np.column_stack(np.where(thresh > 0))
    if coords.size:
        angle = cv2.minAreaRect(coords)[-1]
        angle = -(90 + angle) if angle < -45 else -angle
        if abs(angle) > 0.1:
            h, w = denoised.shape
            matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
            denoised = cv2.warpAffine(
                denoised, matrix, (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )
    return denoised


def ocr_image(image) -> str:
    """OCR a preprocessed image and return joined text.

    For handwritten records the deployment can route OCR to the local Go neural
    network (``HANDWRITING_OCR=1``), which reads handwriting better than the
    print-tuned PaddleOCR engine. Any failure falls back to PaddleOCR so a
    misconfigured handwriting engine never breaks the pipeline.
    """
    try:
        import handwriting_ocr

        if handwriting_ocr.enabled():
            return handwriting_ocr.ocr_image(image)
    except Exception:
        # Fall through to PaddleOCR — the handwriting engine is best-effort.
        pass

    result = _get_engine().ocr(image, cls=True)
    lines: list[str] = []
    # PaddleOCR returns [[ [box, (text, score)], ... ]] per image.
    for page in result or []:
        for entry in page or []:
            text = entry[1][0]
            if text:
                lines.append(text)
    return "\n".join(lines)


def ocr_page(image_path: str | Path) -> str:
    """Full pipeline for one page: preprocess then OCR."""
    processed = preprocess_image(image_path)
    return ocr_image(processed)
