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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="path to input image or PDF")
    parser.add_argument(
        "-o", "--output", type=Path, help="output .txt path (defaults to stdout)"
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
