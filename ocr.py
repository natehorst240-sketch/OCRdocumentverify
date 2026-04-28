#!/usr/bin/env python3
"""OCR an image with Tesseract, with optional OpenCV preprocessing."""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image


def preprocess(image_path: Path) -> Image.Image:
    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10)
    thresh = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
    )
    return Image.fromarray(thresh)


def run_ocr(image_path: Path, lang: str, psm: int, preprocess_image: bool) -> str:
    if preprocess_image:
        img = preprocess(image_path)
    else:
        img = Image.open(image_path)

    config = f"--psm {psm}"
    return pytesseract.image_to_string(img, lang=lang, config=config)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="path to input image")
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
    args = parser.parse_args()

    if not args.image.exists():
        print(f"error: {args.image} not found", file=sys.stderr)
        return 1

    text = run_ocr(args.image, args.lang, args.psm, not args.no_preprocess)

    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {len(text)} chars to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
