#!/usr/bin/env python3
"""OCR an image or PDF with Tesseract, with optional OpenCV preprocessing."""

import argparse
import sys
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
import pytesseract
from PIL import Image

PDF_SUFFIXES = {".pdf"}


def preprocess_pil(img: Image.Image) -> Image.Image:
    arr = np.array(img.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    thresh = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
    )
    return Image.fromarray(thresh)


def load_pages(path: Path, dpi: int) -> Iterable[Image.Image]:
    if path.suffix.lower() in PDF_SUFFIXES:
        from pdf2image import convert_from_path

        return convert_from_path(str(path), dpi=dpi)
    return [Image.open(path)]


def ocr_page(img: Image.Image, lang: str, psm: int, preprocess_image: bool) -> str:
    if preprocess_image:
        img = preprocess_pil(img)
    return pytesseract.image_to_string(img, lang=lang, config=f"--psm {psm}")


def ocr_page_pdf(
    img: Image.Image, lang: str, psm: int, preprocess_image: bool
) -> bytes:
    if preprocess_image:
        img = preprocess_pil(img)
    return pytesseract.image_to_pdf_or_hocr(
        img, lang=lang, config=f"--psm {psm}", extension="pdf"
    )


def run_ocr(
    path: Path, lang: str, psm: int, preprocess_image: bool, dpi: int
) -> str:
    pages = list(load_pages(path, dpi))
    if len(pages) == 1:
        return ocr_page(pages[0], lang, psm, preprocess_image)

    chunks = []
    for i, page in enumerate(pages, start=1):
        text = ocr_page(page, lang, psm, preprocess_image)
        chunks.append(f"--- page {i} ---\n{text}")
    return "\n".join(chunks)


def run_ocr_pdf(
    path: Path, lang: str, psm: int, preprocess_image: bool, dpi: int
) -> bytes:
    """Produce a searchable PDF (image + invisible text layer)."""
    import io

    from pypdf import PdfReader, PdfWriter

    pages = load_pages(path, dpi)
    writer = PdfWriter()
    for page in pages:
        page_bytes = ocr_page_pdf(page, lang, psm, preprocess_image)
        reader = PdfReader(io.BytesIO(page_bytes))
        for p in reader.pages:
            writer.add_page(p)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="path to input image or PDF")
    parser.add_argument(
        "-o", "--output", type=Path, help="output .txt path (defaults to stdout)"
    )
    parser.add_argument(
        "--pdf-output",
        type=Path,
        help="write a searchable PDF here instead of plain text",
    )
    parser.add_argument("-l", "--lang", default="eng", help="Tesseract language code")
    parser.add_argument(
        "--psm",
        type=int,
        default=3,
        help="Tesseract page segmentation mode (default 3: auto)",
    )
    parser.add_argument(
        "--no-preprocess",
        action="store_true",
        help="skip OpenCV preprocessing (denoise + adaptive threshold)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="render DPI for PDF pages (default 300)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"error: {args.input} not found", file=sys.stderr)
        return 1

    if args.pdf_output:
        pdf_bytes = run_ocr_pdf(
            args.input, args.lang, args.psm, not args.no_preprocess, args.dpi
        )
        args.pdf_output.write_bytes(pdf_bytes)
        print(
            f"wrote {len(pdf_bytes)} bytes to {args.pdf_output}", file=sys.stderr
        )
        return 0

    text = run_ocr(
        args.input, args.lang, args.psm, not args.no_preprocess, args.dpi
    )

    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {len(text)} chars to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
