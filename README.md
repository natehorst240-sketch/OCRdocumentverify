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

**Sprint 5 — Template Management** ✅

- Build a form template without editing code: name it, tag the aircraft type,
  optionally attach a blank PDF, and enter field coordinates in a table
  (`Template Builder` page, `templates.py`).
- A guarded coordinate-grid preview of the blank PDF helps read off X/Y points;
  it degrades to a plain message if rendering fails.
- Templates are saved as JSON in `/templates`, reused on every future scan, and
  editable or deletable. This unblocks the full **Reconstruct Form** flow.

All five sprints are complete. The design is intentionally spartan: numeric
coordinate entry via Streamlit's built-in data editor rather than a fragile
click-to-place component.

**Scheduled Inspections & Aircraft Config** (post-sprint, field-driven)

- **Upload Inspections** — OEM maintenance-manual Chapter 4 (Airworthiness
  Limitations) and Chapter 5 (Time Limits / Scheduled Maintenance) tables are
  extracted with pdfplumber (deterministic — no OCR/LLM), reviewed in an
  editable grid, and stored as requirements (`inspection_parser.py`). These are
  the bulk of a real inspection program.
- **Aircraft Profile** — per-tail configuration (serial number, installed
  optional equipment, installed part numbers) that applicability decisions
  depend on, since manuals are generic.
- **Applicability engine** (`applicability.py`) — resolves each requirement
  against the active aircraft into Applies / Not applicable / Review. Strictly
  conservative: the only automatic exclusion is a confident serial-range miss;
  anything unresolved stays Review and is still treated as applicable, so a
  required inspection is never silently dropped. Deterministic (runs on the
  no-LLM N100). Gap Analysis shows the Applies/Review/N-A counts and hides
  not-applicable items by default.

### Handwriting recognition (Go neural network)

`handwriting/` is a self-contained, pure-Go neural network (standard library
only) that reads handwritten logbook scans — the one task PaddleOCR, tuned for
printed text, handles poorly. It runs fully locally (no LLM, no Python ML stack)
as a single static binary with a trained alphanumeric model embedded, and plugs into
this app three ways:

- **UI:** the **Read Handwritten Log** page uploads a scan, transcribes it, and
  shows a per-character confidence overlay (green = confident, red = shaky).
- **Pipeline:** set `HANDWRITING_OCR=1` and `ocr.ocr_image` routes handwriting
  through the Go engine (via `handwriting_ocr.py`), falling back to PaddleOCR on
  any error.
- **Your own data:** `export-glyphs` + `train -dir` (and `Dockerfile.train`) let
  you train the model on your real logs before publishing — see
  [`handwriting/TRAINING.md`](handwriting/TRAINING.md).

See [`handwriting/README.md`](handwriting/README.md) for build, training, and
packaging (int8 quantization, embedded model, cross-compile, USB).

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

### No-LLM mode (low-RAM hosts, e.g. an 8 GB N100)

Set `DISABLE_LLM=1` to run the deterministic pipeline without Ollama: form
classification and field mapping become manual, requirements are entered by
hand, and compliance matching uses keyword scoring (conservative — it flags for
review rather than auto-confirming). Fits comfortably in 8 GB.

```bash
docker compose -f docker-compose.nollm.yml up -d   # app only, no Ollama
```

A common split: **no-LLM app on the N100**, full **LLM stack on a desktop**.
Same codebase, same data layout — only the `DISABLE_LLM` flag differs. (If you
want LLM smarts from the N100 without hosting the model there, leave LLM mode on
and point `OLLAMA_HOST` at the desktop instead.)

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

## Distribute to someone without Docker

Two ways to hand the whole app to a Windows user, both bundling a private Python
runtime + the Go handwriting engine so there's nothing for them to install:

- **A real installer (`setup.exe`)** — Start-Menu shortcut, optional desktop
  icon, uninstaller. Best for a non-technical recipient. Build it with
  `build_installer.bat`; see [`WINDOWS_INSTALLER.md`](WINDOWS_INSTALLER.md).
- **A portable folder/zip** — no install at all; runs from a folder or USB
  stick. Best for locked-down machines. Covered just below.

### Portable Windows bundle

For a recipient who can't install Docker or anything else (locked-down machine,
no admin rights), build a **self-contained portable folder** — a private Python
runtime + the app + a double-click launcher.

**You build it once** (on any Windows machine with internet):

```bat
build_portable.bat
```

This downloads an embeddable Python into `.\runtime` and installs the
dependencies into it (uses `requirements-lite.txt` — no OCR stack, small and
reliable; run `build_portable.bat full` for the heavy OCR build). Then:

1. Delete `.venv\` and `__pycache__\` to keep the size down.
2. **Zip the whole folder** and send it (e.g. via file share).

**The recipient** unzips it anywhere and **double-clicks `run.bat`** — a browser
opens at `http://localhost:8501`. No Docker, no installer, no admin rights. It
runs in no-LLM mode, bound to localhost only (nothing exposed on their network).

What works in the lite bundle: inspections, requirements, Veryon import, gap
analysis, applicability, templates, filled-PDF output. What needs the full build
(+ a separate Ollama install): live OCR of scanned records and Reconstruct Form.



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
