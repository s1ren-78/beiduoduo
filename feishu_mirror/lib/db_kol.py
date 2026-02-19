"""Database operations for KOL watchlist (per-owner isolation)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .db import DB


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _make_kol_id(name: str) -> str:
    """Name -> slug: 'Sam Altman' -> 'sam_altman'."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    return slug


def _generate_search_queries(name: str, title: str) -> list[str]:
    """Auto-generate search queries from name + title."""
    queries = [f'"{name}" {title}']
    if title:
        queries.append(f'"{name}" opinion statement')
    else:
        queries.append(f'"{name}" latest news')
    return queries


def upsert_kol(
    db: DB,
    owner_id: str,
    name: str,
    title: str = "",
    category: str = "",
    search_queries: list[str] | None = None,
    meta: dict | None = None,
) -> dict[str, Any]:
    """Insert or update a KOL for a specific owner. Returns the row dict."""
    kol_id = _make_kol_id(name)
    if not search_queries:
        search_queries = _generate_search_queries(name, title)
    now = _now_iso()
    queries_json = json.dumps(search_queries, ensure_ascii=False)
    meta_json = json.dumps(meta or {}, ensure_ascii=False)

    with db.conn() as conn:
        conn.execute(
            """
            INSERT INTO kol_watchlist(owner_id, kol_id, name, title, category, search_queries, enabled, meta, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT (owner_id, kol_id)
            DO UPDATE SET name = excluded.name,
                          title = excluded.title,
                          category = excluded.category,
                          search_queries = excluded.search_queries,
                          enabled = 1,
                          meta = excluded.meta,
                          updated_at = excluded.updated_at
            """,
            (owner_id, kol_id, name.strip(), title.strip(), category.strip(), queries_json, meta_json, now, now),
        )
        cur = conn.execute(
            "SELECT * FROM kol_watchlist WHERE owner_id = ? AND kol_id = ?",
            (owner_id, kol_id),
        )
        row = cur.fetchone()
    row["search_queries"] = json.loads(row["search_queries"])
    row["meta"] = json.loads(row["meta"])
    return row


def disable_kol(db: DB, owner_id: str, name_or_id: str) -> dict[str, Any] | None:
    """Soft-delete a KOL for a specific owner. Match by kol_id first, then fuzzy name. Returns row or None."""
    now = _now_iso()
    slug = _make_kol_id(name_or_id)

    with db.conn() as conn:
        # Try exact kol_id match within this owner
        cur = conn.execute(
            "SELECT * FROM kol_watchlist WHERE owner_id = ? AND kol_id = ? AND enabled = 1",
            (owner_id, slug),
        )
        row = cur.fetchone()

        # Fuzzy name match within this owner
        if not row:
            cur = conn.execute(
                "SELECT * FROM kol_watchlist WHERE owner_id = ? AND enabled = 1 AND name LIKE ?",
                (owner_id, f"%{name_or_id.strip()}%"),
            )
            row = cur.fetchone()

        if not row:
            return None

        conn.execute(
            "UPDATE kol_watchlist SET enabled = 0, updated_at = ? WHERE id = ?",
            (now, row["id"]),
        )
    row["enabled"] = 0
    row["search_queries"] = json.loads(row["search_queries"])
    row["meta"] = json.loads(row["meta"])
    return row


def get_kol_list(
    db: DB,
    owner_id: str | None = None,
    category: str | None = None,
    enabled_only: bool = True,
) -> list[dict[str, Any]]:
    """List KOLs, optionally filtered by owner and/or category."""
    with db.conn() as conn:
        sql = "SELECT * FROM kol_watchlist WHERE 1=1"
        params: list[Any] = []
        if owner_id is not None:
            sql += " AND owner_id = ?"
            params.append(owner_id)
        if enabled_only:
            sql += " AND enabled = 1"
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY id ASC"
        rows = conn.execute(sql, params).fetchall()

    for r in rows:
        r["search_queries"] = json.loads(r["search_queries"])
        r["meta"] = json.loads(r["meta"])
    return rows


def get_distinct_owners(db: DB) -> list[str]:
    """Return all distinct owner_ids that have at least one enabled KOL."""
    with db.conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT owner_id FROM kol_watchlist WHERE enabled = 1 AND owner_id != ''"
        ).fetchall()
    return [r["owner_id"] for r in rows]


def seed_from_json(db: DB, json_path: str | Path, owner_id: str = "") -> int:
    """Import KOLs from kol_config.json (idempotent). Returns count inserted."""
    path = Path(json_path)
    if not path.exists():
        return 0

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    count = 0
    for k in raw.get("kols", []):
        if not k.get("enabled", True):
            continue
        upsert_kol(
            db,
            owner_id=owner_id,
            name=k["name"],
            title=k.get("title", ""),
            category=k.get("category", ""),
            search_queries=k.get("search_queries"),
        )
        count += 1
    return count
