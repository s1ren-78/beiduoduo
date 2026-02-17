#!/usr/bin/env python3
"""Write extraction results to DB. Reads JSON from stdin."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.config import load_settings
from lib.db import DB
from lib.db_structured import upsert_metadata, upsert_theses, upsert_metrics

MODEL = "claude-opus-4-6-via-claude-code"

def main():
    data = json.load(sys.stdin)
    settings = load_settings(str(Path(__file__).parent / ".env"))
    db = DB(settings.database_url)
    db.ensure_schema(Path(__file__).parent / "schema.sql")

    doc_id = data["doc_id"]
    wrote = []

    if data.get("metadata"):
        upsert_metadata(db, doc_id, data["metadata"], MODEL)
        wrote.append("L1")
    if data.get("theses") is not None:
        upsert_theses(db, doc_id, data["theses"], MODEL)
        wrote.append(f"L2({len(data['theses'])})")
    if data.get("metrics") is not None:
        upsert_metrics(db, doc_id, data["metrics"], MODEL)
        wrote.append(f"L3({len(data['metrics'])})")

    print(f"OK: {doc_id} — {', '.join(wrote)}")

if __name__ == "__main__":
    main()
