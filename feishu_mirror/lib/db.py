from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


@dataclass
class SearchRow:
    doc_id: str
    title: str
    source_type: str
    category: str | None
    chunk_id: str
    score: float
    quote: str
    start_offset: int
    end_offset: int
    file_path: str | None
    updated_at: str | None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _uuid4() -> str:
    return str(uuid.uuid4())


def dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
    fields = [col[0] for col in cursor.description]
    return dict(zip(fields, row))


class DB:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    @contextmanager
    def conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = dict_factory
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ensure_schema(self, schema_file: Path) -> None:
        sql = schema_file.read_text(encoding="utf-8")
        with self.conn() as conn:
            conn.executescript(sql)

    def start_sync_run(self, scope: str, mode: str, reason: str) -> str:
        run_id = _uuid4()
        with self.conn() as conn:
            conn.execute(
                """
                INSERT INTO report_sync_run(run_id, scope, mode, reason, status, started_at)
                VALUES (?, ?, ?, ?, 'running', ?)
                """,
                (run_id, scope, mode, reason, _now_iso()),
            )
        return run_id

    def finish_sync_run(self, run_id: str, status: str, stats: dict[str, Any], error_text: str | None) -> None:
        ended = _now_iso() if status in ("success", "failed") else None
        with self.conn() as conn:
            conn.execute(
                """
                UPDATE report_sync_run
                   SET status = ?,
                       ended_at = COALESCE(?, ended_at),
                       stats = ?,
                       error_text = ?
                 WHERE run_id = ?
                """,
                (status, ended, json.dumps(stats, ensure_ascii=False), error_text, run_id),
            )

    def get_checkpoint(self, checkpoint_key: str) -> dict[str, Any] | None:
        with self.conn() as conn:
            cur = conn.execute(
                "SELECT checkpoint_key, cursor, watermark_ts, updated_at, meta FROM report_checkpoint WHERE checkpoint_key = ?",
                (checkpoint_key,),
            )
            row = cur.fetchone()
            return row if row else None

    def set_checkpoint(
        self,
        checkpoint_key: str,
        cursor: str | None,
        watermark_ts: datetime | None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        payload = json.dumps(meta or {}, ensure_ascii=False)
        ts = watermark_ts.isoformat() if watermark_ts else None
        with self.conn() as conn:
            conn.execute(
                """
                INSERT INTO report_checkpoint(checkpoint_key, cursor, watermark_ts, meta, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (checkpoint_key)
                DO UPDATE SET cursor = excluded.cursor,
                              watermark_ts = excluded.watermark_ts,
                              meta = excluded.meta,
                              updated_at = excluded.updated_at
                """,
                (checkpoint_key, cursor, ts, payload, _now_iso()),
            )

    def upsert_source_file(
        self,
        *,
        source_type: str,
        source_id: str,
        file_path: str | None,
        file_name: str | None,
        file_ext: str | None,
        category: str | None,
        file_size: int | None,
        file_mtime: datetime | None,
        content_hash: str | None,
        is_supported: bool,
        unsupported_reason: str | None,
        meta: dict[str, Any],
    ) -> int:
        mtime_str = file_mtime.isoformat() if file_mtime else None
        meta_str = json.dumps(meta, ensure_ascii=False)
        now = _now_iso()
        with self.conn() as conn:
            conn.execute(
                """
                INSERT INTO report_source_file(
                    source_type, source_id, file_path, file_name, file_ext,
                    category, file_size, file_mtime, content_hash,
                    is_supported, unsupported_reason, meta, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (source_type, source_id)
                DO UPDATE SET file_path = excluded.file_path,
                              file_name = excluded.file_name,
                              file_ext = excluded.file_ext,
                              category = excluded.category,
                              file_size = excluded.file_size,
                              file_mtime = excluded.file_mtime,
                              content_hash = excluded.content_hash,
                              is_supported = excluded.is_supported,
                              unsupported_reason = excluded.unsupported_reason,
                              meta = excluded.meta,
                              updated_at = excluded.updated_at
                """,
                (
                    source_type, source_id, file_path, file_name, file_ext,
                    category, file_size, mtime_str, content_hash,
                    1 if is_supported else 0, unsupported_reason, meta_str, now, now,
                ),
            )
            cur = conn.execute(
                "SELECT id FROM report_source_file WHERE source_type = ? AND source_id = ?",
                (source_type, source_id),
            )
            return int(cur.fetchone()["id"])

    def get_document_hash(self, source_type: str, source_id: str) -> str | None:
        with self.conn() as conn:
            cur = conn.execute(
                "SELECT content_hash FROM report_document WHERE source_type = ? AND source_id = ?",
                (source_type, source_id),
            )
            row = cur.fetchone()
            return row["content_hash"] if row else None

    def upsert_document(
        self,
        *,
        source_type: str,
        source_id: str,
        title: str,
        category: str | None,
        source_file_id: int | None,
        full_text: str,
        content_hash: str,
        updated_time: datetime | None,
        meta: dict[str, Any],
    ) -> str:
        meta_str = json.dumps(meta, ensure_ascii=False)
        updated_str = updated_time.isoformat() if updated_time else None
        now = _now_iso()

        with self.conn() as conn:
            # Check if exists
            cur = conn.execute(
                "SELECT doc_id FROM report_document WHERE source_type = ? AND source_id = ?",
                (source_type, source_id),
            )
            existing = cur.fetchone()

            if existing:
                doc_id = existing["doc_id"]
                conn.execute(
                    """
                    UPDATE report_document
                       SET title = ?, category = ?, source_file_id = ?,
                           full_text = ?, content_hash = ?, updated_time = ?,
                           meta = ?, synced_at = ?
                     WHERE doc_id = ?
                    """,
                    (title, category, source_file_id, full_text, content_hash,
                     updated_str, meta_str, now, doc_id),
                )
            else:
                doc_id = _uuid4()
                conn.execute(
                    """
                    INSERT INTO report_document(
                        doc_id, source_type, source_id, title, category,
                        source_file_id, full_text, content_hash, updated_time, meta, synced_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (doc_id, source_type, source_id, title, category,
                     source_file_id, full_text, content_hash, updated_str, meta_str, now),
                )
            return doc_id

    def replace_chunks(
        self,
        *,
        doc_id: str,
        chunks: Iterable[dict[str, Any]],
        updated_time: datetime | None = None,
    ) -> None:
        updated_str = (updated_time or datetime.now(timezone.utc)).isoformat()
        chunk_list = list(chunks)

        with self.conn() as conn:
            # Delete old FTS entries
            conn.execute(
                "DELETE FROM report_chunk_fts WHERE doc_id = ?", (doc_id,)
            )
            # Delete old chunks
            conn.execute("DELETE FROM report_chunk WHERE doc_id = ?", (doc_id,))

            for chunk in chunk_list:
                chunk_id = _uuid4()
                conn.execute(
                    """
                    INSERT INTO report_chunk(
                        chunk_id, doc_id, chunk_index, section, content,
                        start_offset, end_offset, updated_time, meta
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        doc_id,
                        int(chunk["chunk_index"]),
                        chunk.get("section"),
                        chunk["content"],
                        int(chunk["start_offset"]),
                        int(chunk["end_offset"]),
                        updated_str,
                        json.dumps(chunk.get("meta", {}), ensure_ascii=False),
                    ),
                )
                # Insert into FTS
                conn.execute(
                    "INSERT INTO report_chunk_fts(chunk_id, doc_id, content) VALUES (?, ?, ?)",
                    (chunk_id, doc_id, chunk["content"]),
                )

    def search(
        self,
        *,
        query: str,
        top_k: int,
        source: str | None,
        tag: str | None,
        from_ts: datetime | None,
        to_ts: datetime | None,
    ) -> list[SearchRow]:
        where = []
        params: list[Any] = []

        if source:
            where.append("d.source_type = ?")
            params.append(source)
        if tag:
            where.append("d.category = ?")
            params.append(tag)
        if from_ts:
            where.append("COALESCE(d.updated_time, d.synced_at) >= ?")
            params.append(from_ts.isoformat())
        if to_ts:
            where.append("COALESCE(d.updated_time, d.synced_at) <= ?")
            params.append(to_ts.isoformat())

        where_clause = (" AND " + " AND ".join(where)) if where else ""

        sql = f"""
            SELECT
              d.doc_id,
              d.title,
              d.source_type,
              d.category,
              c.chunk_id,
              fts.rank AS score,
              c.content AS quote,
              c.start_offset,
              c.end_offset,
              sf.file_path,
              COALESCE(d.updated_time, d.synced_at) AS updated_at
            FROM report_chunk_fts fts
            JOIN report_chunk c ON c.chunk_id = fts.chunk_id
            JOIN report_document d ON d.doc_id = c.doc_id
            LEFT JOIN report_source_file sf ON sf.id = d.source_file_id
            WHERE report_chunk_fts MATCH ?
            {where_clause}
            ORDER BY fts.rank
            LIMIT ?
        """
        all_params = [query, *params, top_k]

        with self.conn() as conn:
            cur = conn.execute(sql, all_params)
            rows = cur.fetchall()
            return [
                SearchRow(
                    doc_id=row["doc_id"],
                    title=row["title"],
                    source_type=row["source_type"],
                    category=row["category"],
                    chunk_id=row["chunk_id"],
                    score=float(row["score"] or 0),
                    quote=row["quote"],
                    start_offset=int(row["start_offset"]),
                    end_offset=int(row["end_offset"]),
                    file_path=row.get("file_path"),
                    updated_at=row.get("updated_at"),
                )
                for row in rows
            ]

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        with self.conn() as conn:
            cur = conn.execute(
                """
                SELECT
                  d.doc_id,
                  d.source_type,
                  d.source_id,
                  d.title,
                  d.category,
                  d.full_text,
                  d.content_hash,
                  d.updated_time,
                  d.synced_at,
                  d.meta,
                  sf.file_path,
                  sf.file_name,
                  sf.file_ext
                FROM report_document d
                LEFT JOIN report_source_file sf ON sf.id = d.source_file_id
                WHERE d.doc_id = ?
                """,
                (doc_id,),
            )
            doc = cur.fetchone()
            if not doc:
                return None

            cur2 = conn.execute(
                """
                SELECT
                  chunk_id,
                  chunk_index,
                  section,
                  content,
                  start_offset,
                  end_offset,
                  updated_time,
                  meta
                FROM report_chunk
                WHERE doc_id = ?
                ORDER BY chunk_index ASC
                """,
                (doc_id,),
            )
            chunks = cur2.fetchall()
            doc["chunks"] = chunks
            return doc

    def sync_status(self) -> dict[str, Any]:
        with self.conn() as conn:
            cur = conn.execute(
                """
                SELECT
                  MAX(CASE WHEN scope IN ('local','all') AND mode='full' AND status='success' THEN ended_at END) AS last_local_full,
                  MAX(CASE WHEN scope IN ('local','all') AND mode='incremental' AND status='success' THEN ended_at END) AS last_local_incremental,
                  MAX(CASE WHEN scope IN ('feishu','all') AND mode='full' AND status='success' THEN ended_at END) AS last_feishu_full,
                  MAX(CASE WHEN scope IN ('feishu','all') AND mode='incremental' AND status='success' THEN ended_at END) AS last_feishu_incremental,
                  COUNT(CASE WHEN status='failed' THEN 1 END) AS failed_runs
                FROM report_sync_run
                """
            )
            summary = cur.fetchone() or {}

            cur2 = conn.execute(
                """
                SELECT checkpoint_key, cursor, watermark_ts, updated_at, meta
                FROM report_checkpoint
                ORDER BY updated_at DESC
                LIMIT 50
                """
            )
            checkpoints = cur2.fetchall()
            summary["checkpoints"] = checkpoints
            return summary

    def whitelist_entries(self) -> list[dict[str, Any]]:
        with self.conn() as conn:
            cur = conn.execute(
                """
                SELECT id, entry_type, entry_token, label, enabled, meta, created_at, updated_at
                FROM report_whitelist
                WHERE enabled = 1
                ORDER BY id ASC
                """
            )
            return cur.fetchall()

    def recent_sync_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.conn() as conn:
            cur = conn.execute(
                """
                SELECT run_id, scope, mode, reason, status, started_at, ended_at, stats, error_text, created_at
                FROM report_sync_run
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            return cur.fetchall()
