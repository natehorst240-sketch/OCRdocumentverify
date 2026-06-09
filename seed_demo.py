"""Populate the database with demo data for a first-run smoke test.

Lets you exercise Dashboard, Gap Analysis, and the Veryon comparison without
uploading or OCR'ing anything. Pure SQLite — no OCR/LLM dependencies.

    python seed_demo.py            # wipe + seed the configured database
    RECORDS_DB=/data/records.db python seed_demo.py   # target a hosted DB

This CLEARS the documents, pages, requirements, veryon_tasks and compliance
tables first, so do not run it against a database with real records.
"""

import database

# (doc_number, req_type, description, interval, required_action)
REQUIREMENTS = [
    ("AD 2021-12-05", "AD", "Replace tail rotor blade", "one-time",
     "Replace tail rotor blade P/N 109-3000"),
    ("AD 2022-03-10", "AD", "Inspect main gearbox mounts", "100 hrs",
     "Inspect main gearbox mounts for cracking"),
    ("ASB 109-145", "ASB", "Hydraulic pump overhaul", "3000 hrs",
     "Overhaul hydraulic pump"),
    ("ICA 32-10", "ICA", "Landing gear actuator lubrication", "50 hrs",
     "Lubricate landing gear actuator"),
]

# Fake "OCR'd" record pages — text chosen to keyword-match some requirements.
RECORD_PAGES = [
    "Work Order 4471. Replaced tail rotor blade per AD 2021-12-05 on "
    "2026-01-15 at 3200 hrs. Technician J. Ramirez.",
    "Lubricated landing gear actuator per ICA 32-10. Completed 2026-02-01 "
    "at 3240 hrs.",
]

# (task_code, description, interval, last_compliance_date)
VERYON_TASKS = [
    ("TR-001", "Tail rotor blade replacement", "one-time", "2026-01-15"),
    ("LG-050", "Landing gear actuator lube", "50 hrs", "2026-02-01"),
    ("MGB-100", "Main gearbox mount inspection", "100 hrs", "2025-09-12"),
    ("ELT-001", "ELT battery replacement", "24 months", "2024-06-01"),
]


def seed(db_path=database.DB_PATH) -> dict:
    database.init_db(db_path)
    for table in ("compliance", "pages", "documents", "requirements",
                  "veryon_tasks"):
        database.clear_table(table, db_path)

    for doc_number, req_type, desc, interval, action in REQUIREMENTS:
        database.add_requirement(doc_number, req_type, desc, interval=interval,
                                 required_action=action,
                                 source_file="demo_requirements.pdf",
                                 db_path=db_path)

    doc_id = database.add_document("demo_logbook.pdf", "(demo)", "pdf",
                                   "record", len(RECORD_PAGES), db_path=db_path)
    for i, text in enumerate(RECORD_PAGES, start=1):
        database.add_page(doc_id, i, "demo_logbook.pdf", extracted_text=text,
                          db_path=db_path)

    for code, desc, interval, last in VERYON_TASKS:
        database.add_veryon_task(code, desc, interval=interval,
                                 last_compliance_date=last,
                                 source_file="demo_veryon.xlsx", db_path=db_path)

    return database.table_counts(db_path)


if __name__ == "__main__":
    counts = seed()
    print("Demo data seeded. Table counts:")
    for table, n in counts.items():
        print(f"  {table}: {n}")
    print("\nOpen the app → Gap Analysis → 'Run compliance matching'.")
