# First-run smoke test (homelab)

A 10-minute checklist to confirm the stack works after `docker compose up`.
Most steps need **no scans and no LLM** — they use the demo seeder.

## 0. Start it

```bash
cp .env.example .env          # qwen2.5:7b (GPU) or qwen2.5:3b (CPU)
docker compose up -d
docker compose logs -f app    # wait for "You can now view your Streamlit app"
```

First boot is slow: it builds the image, pulls the model (`ollama-pull`), and
PaddleOCR downloads its models on the first OCR run. All one-time.

Open `http://<server-ip>:8501`.

## 1. Dashboard

- [ ] Page loads with no errors.
- [ ] **Database** shows green (`records.db` ready).
- [ ] **Qwen / Ollama** shows green. If red, the app still works — matching just
      falls back to keyword-only (see step 4).

## 2. Seed demo data

```bash
docker compose exec app python seed_demo.py
```

- [ ] Prints table counts (4 requirements, 2 pages, 4 Veryon tasks).
- [ ] Refresh the Dashboard — the metrics reflect those counts.

> The seeder **wipes** documents/pages/requirements/veryon_tasks/compliance
> first. Don't run it once you have real data.

## 3. Template Builder

- [ ] Open **Template Builder** → select **Sample Work Order**.
- [ ] The field table shows 7 rows (work_order_no, date, …).
- [ ] Add a row, click **Save template** → success message.
- [ ] Create a **New template**, save it, confirm it appears in the dropdown,
      then **Delete** it.

## 4. Gap Analysis

- [ ] Open **Gap Analysis** → **Run compliance matching**.
- [ ] Metrics populate. **With Qwen on**, expect some *Complied*. **With Qwen
      off**, results are keyword-only and conservative (mostly *Needs Review* /
      *Outstanding*) — that's the intended safe degradation, not a bug.
- [ ] **Compare to Veryon** → the three categories populate; toggle each.
- [ ] Enter a tail number (e.g. `N109SP`) → **Generate Excel gap report** →
      download. Open it: three tabs, color-coded headers, dated filename.

## 5. Veryon upload path (optional)

- [ ] Open **Upload Veryon Export**, upload `examples/sample_veryon_export.xlsx`.
- [ ] Import succeeds; the resolved column map is shown.

## 6. OCR / Reconstruct (needs a real scan)

These exercise PaddleOCR/OpenCV and can't be faked:

- [ ] **Upload Records** → upload a scanned JPG/PNG/PDF with "Run OCR" on →
      extracted text appears (first run downloads OCR models — slow once).
- [ ] **Upload Requirements** → upload an AD/ASB/ICA PDF → structured rows
      appear (needs Qwen).
- [ ] **Reconstruct Form** → upload a scanned form → form type detected, boxes
      annotated → pick **Sample Work Order** → map fields → download filled PDF.

## If something fails

- Qwen red → `docker compose logs ollama`; confirm the model pulled
  (`docker compose exec ollama ollama list`).
- OCR errors → ensure the build finished; first OCR downloads models (needs
  outbound network on first run).
- App won't start → `docker compose ps` and `docker compose logs app`.
