# Aviation Maintenance Records Processor

A local-first tool for digitizing scanned aircraft maintenance records, OCR-ing
them, reconstructing forms, and running compliance gap analysis against
regulatory requirements (AD/ASB/ICA) and a Veryon export. Everything runs on
your machine — no internet or hosting required.

## Status

**Sprint 1 — Project Setup** ✅

- Project folder structure, `requirements.txt`, SQLite schema (`database.py`),
  Qwen2.5 client via Ollama (`qwen_client.py`), Streamlit app with status page.

**Sprint 2 — Document Ingestion** ✅

- Upload scanned records (JPG/PNG/PDF); PDFs split to per-page images (`ocr.py`).
- Preprocess (grayscale, denoise, deskew) + PaddleOCR per page, stored in SQLite.
- Upload AD/ASB/ICA PDFs; pdfplumber text + Qwen structuring, with dedup
  (`pdf_parser.py`).
- Upload Veryon Excel export; loose column mapping into `veryon_tasks`
  (`veryon_import.py`).

**Sprint 3 — Form Detection & Reconstruction** ✅

- Classify the scanned form type with a confidence score + manual override
  (`form_detector.classify_form_type`).
- Detect field boxes with OpenCV and OCR each box individually; show an
  annotated image (`form_detector.detect_boxes` / `ocr_boxes`).
- Map boxes to template fields via Qwen, editable before export, with learned
  corrections saved per form type (`field_mapper.py`, `templates.py`).
- Generate a filled PDF by overlaying text at template coordinates
  (`pdf_writer.fill_pdf`, reportlab + pypdf).

**Sprint 4 — Compliance Gap Analysis** ✅

- Match records to requirements: deterministic keyword pre-filter, then Qwen
  confirmation with a confidence score; low-confidence matches flagged for
  review (`compliance_engine.run_matching`). Degrades to keyword-only scoring
  when Qwen is unavailable.
- Compare against the Veryon export: matched / missing-from-Veryon /
  missing-from-records (`compliance_engine.compare_to_veryon`).
- Export a color-coded Excel gap report with three tabs, named by date and tail
  number (`excel_export.build_gap_report`).

Later sprints add a template builder (Sprint 5).

### Architecture note: how much actually needs the LLM?

Most of the pipeline is a deterministic Python engine — OCR (PaddleOCR), PDF
and Excel parsing, OpenCV box detection, and PDF filling need no LLM. Qwen is
used only for the fuzzy-language parts: structuring free-form regulatory text,
classifying/mapping unfamiliar forms, and confirming semantic compliance
matches. Those LLM calls are isolated in `qwen_client.py` and the modules that
call it, so they can be stubbed or swapped for rules/embeddings if desired.

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com/) running locally with the Qwen model:

  ```bash
  ollama pull qwen2.5:7b
  ```

  Ollama serves at `http://localhost:11434` by default.

- Tesseract / PaddleOCR system deps are needed for Sprint 2 OCR. For PDF
  rasterization, `pdf2image` requires `poppler` installed on the system.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

The app opens in your browser, creates `records.db` on first run, and shows
whether the database and Qwen backend are reachable.

You can sanity-check the backend pieces independently:

```bash
python database.py     # creates records.db, prints table counts
python qwen_client.py  # checks Ollama and sends a test prompt
```

## Self-hosting on a home server (Docker)

Run the whole package — Streamlit app **and** the local Ollama LLM — with one
command. All persistent state lives under `./data`, so backups are a copy of
that one folder.

```bash
cp .env.example .env          # pick your model (qwen2.5:7b GPU / qwen2.5:3b CPU)
docker compose up -d          # builds the app, pulls the model, starts everything
```

Then open `http://<server-ip>:8501`. The compose stack:

- **auto-pulls the model** on first start (the `ollama-pull` one-shot),
- **restarts on crash/reboot** (`restart: unless-stopped`),
- has **healthchecks** on both the app and Ollama so the app only starts once
  the LLM is ready,
- keeps the DB, uploads, output, and templates under `./data` for easy backup.

### Recommended hardware

- **Reliable for a small team:** 6–8 core CPU, **32 GB RAM**, an **NVIDIA
  12 GB GPU** (e.g. RTX 3060 12GB), 500 GB NVMe — runs `qwen2.5:7b` snappily.
  Enable the GPU by uncommenting the `deploy:` block under the `ollama` service
  (requires the NVIDIA Container Toolkit on the host).
- **Budget / CPU-only:** 16 GB RAM minimum; set `QWEN_MODEL=qwen2.5:3b` in
  `.env` for tolerable speed.

### Reliability extras

- **UPS + graceful shutdown** — protects SQLite from corruption on power loss.
- **Backups** — `scripts/backup.sh` takes a consistent SQLite snapshot and
  archives `./data` with retention. Schedule it via cron:

  ```
  0 2 * * *  cd /srv/ocrdocumentverify && scripts/backup.sh >> backup.log 2>&1
  ```

- **Auth** — Streamlit has no built-in login; keep it on a trusted LAN or front
  it with a reverse proxy / Cloudflare Tunnel for HTTPS + access control.

## Configuration

Environment variables (all optional):

| Variable      | Default                  | Purpose                     |
|---------------|--------------------------|-----------------------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API base URL         |
| `QWEN_MODEL`  | `qwen2.5:7b`             | Model name to use           |
| `QWEN_TIMEOUT`| `120`                    | Per-request timeout seconds |
| `RECORDS_DB`  | `./records.db`           | SQLite path (set to a mounted volume when hosting) |

## Project layout

```
app.py                # Streamlit main app
requirements.txt
database.py           # SQLite setup and queries
qwen_client.py        # Ollama / Qwen API wrapper
templates/            # Field map JSONs per form type (Sprint 5)
uploads/              # Uploaded scans
output/               # Generated PDFs and Excel files
records.db            # SQLite database (created on first run)
```
