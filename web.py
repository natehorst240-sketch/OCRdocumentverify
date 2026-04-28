#!/usr/bin/env python3
"""FastAPI upload UI for the OCR tool.

Run with: uvicorn web:app --reload
"""

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse

from ocr import run_ocr

app = FastAPI(title="OCR Tool")

INDEX_HTML = """\
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>OCR Tool</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
    label { display: block; margin: 0.75rem 0 0.25rem; }
    input, select { padding: 0.4rem; }
    button { margin-top: 1rem; padding: 0.6rem 1.2rem; font-size: 1rem; }
    .row { display: flex; gap: 1rem; flex-wrap: wrap; }
    .row > div { flex: 1; min-width: 180px; }
  </style>
</head>
<body>
  <h1>OCR Tool</h1>
  <form action="/ocr" method="post" enctype="multipart/form-data">
    <label for="file">Image or PDF</label>
    <input id="file" type="file" name="file" accept="image/*,application/pdf" required />
    <div class="row">
      <div>
        <label for="lang">Language</label>
        <input id="lang" type="text" name="lang" value="eng" />
      </div>
      <div>
        <label for="psm">PSM</label>
        <input id="psm" type="number" name="psm" value="3" min="0" max="13" />
      </div>
      <div>
        <label for="dpi">PDF DPI</label>
        <input id="dpi" type="number" name="dpi" value="300" min="72" max="600" />
      </div>
    </div>
    <label><input type="checkbox" name="preprocess" value="1" checked /> Preprocess (denoise + threshold)</label>
    <button type="submit">Run OCR</button>
  </form>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


@app.post("/ocr", response_class=PlainTextResponse)
async def ocr_endpoint(
    file: UploadFile = File(...),
    lang: str = Form("eng"),
    psm: int = Form(3),
    dpi: int = Form(300),
    preprocess: str = Form(""),
) -> str:
    suffix = Path(file.filename or "").suffix or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)

    try:
        return run_ocr(
            tmp_path,
            lang=lang,
            psm=psm,
            preprocess_image=bool(preprocess),
            dpi=dpi,
        )
    finally:
        tmp_path.unlink(missing_ok=True)
