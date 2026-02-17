#!/usr/bin/env python3
"""Dump a document's truncated text to a file for subagent processing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.config import load_settings
from lib.db import DB

MAX_CHARS = 16000  # Enough for all 3 layers

def main():
    doc_id = sys.argv[1]
    out_path = sys.argv[2]

    settings = load_settings(str(Path(__file__).parent / ".env"))
    db = DB(settings.database_url)

    with db.conn() as conn:
        row = conn.execute(
            "SELECT doc_id, title, category, full_text FROM report_document WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()

    if not row:
        print(f"ERROR: doc_id {doc_id} not found", file=sys.stderr)
        sys.exit(1)

    text = row["full_text"] or ""
    if len(text) > MAX_CHARS:
        head = int(MAX_CHARS * 0.7)
        tail = MAX_CHARS - head
        text = text[:head] + "\n\n[...truncated...]\n\n" + text[-tail:]

    with open(out_path, "w") as f:
        f.write(text)

    print(f"OK: {row['title']} ({len(text)} chars)")

if __name__ == "__main__":
    main()
