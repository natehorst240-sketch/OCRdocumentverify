# Aviation Maintenance Records Processor

A local-first tool for digitizing scanned aircraft maintenance records, OCR-ing
them, reconstructing forms, and running compliance gap analysis against
regulatory requirements (AD/ASB/ICA) and a Veryon export. Everything runs on
your machine — no internet or hosting required.

## Status

**Sprint 1 — Project Setup** ✅

- Project folder structure
- `requirements.txt` with all dependencies
- SQLite database with full schema (`database.py`)
- Local Qwen2.5 client via Ollama (`qwen_client.py`)
- Streamlit app that boots, initializes the DB, and reports system status

Later sprints add ingestion + OCR (Sprint 2), form reconstruction (Sprint 3),
gap analysis (Sprint 4), and a template builder (Sprint 5).

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

## Configuration

Environment variables (all optional):

| Variable      | Default                  | Purpose                     |
|---------------|--------------------------|-----------------------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API base URL         |
| `QWEN_MODEL`  | `qwen2.5:7b`             | Model name to use           |
| `QWEN_TIMEOUT`| `120`                    | Per-request timeout seconds |

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
