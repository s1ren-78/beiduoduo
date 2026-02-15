from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .chunking import split_text_to_chunks
from .db import DB
from .feishu_api import FeishuAuth, FeishuClient


@dataclass
class FeishuSyncStats:
    whitelist_entries: int = 0
    docs_seen: int = 0
    docs_ingested: int = 0
    docs_skipped_unchanged: int = 0
    chunks_written: int = 0
    failures: int = 0

    def asdict(self) -> dict[str, Any]:
        return {
            "whitelist_entries": self.whitelist_entries,
            "docs_seen": self.docs_seen,
            "docs_ingested": self.docs_ingested,
            "docs_skipped_unchanged": self.docs_skipped_unchanged,
            "chunks_written": self.chunks_written,
            "failures": self.failures,
        }


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _from_ms(ms: int | str | None) -> datetime | None:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000.0, tz=timezone.utc)
    except Exception:
        return None


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _append_jsonl(base: Path, domain: str, payload: dict[str, Any]) -> None:
    day = _now_utc().strftime("%Y-%m-%d")
    folder = base / domain / day
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / "events.jsonl"
    with out.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _ingest_doc_token(
    *,
    db: DB,
    client: FeishuClient,
    raw_root: Path,
    doc_token: str,
    category: str,
    entry_type: str,
    entry_token: str,
    incremental: bool,
    run_id: str,
    stats: FeishuSyncStats,
) -> None:
    stats.docs_seen += 1

    raw_content = client.get_doc_raw_content(doc_token)
    meta = client.get_doc_meta(doc_token)
    text = (raw_content.get("content") or "").strip()
    title = meta.get("document", {}).get("title") or doc_token
    updated_time = _from_ms(meta.get("document", {}).get("revision_id")) or _now_utc()
    content_hash = _text_hash(text)
    source_id = f"feishu:doc:{doc_token}"

    _append_jsonl(
        raw_root,
        "feishu_doc",
        {
            "run_id": run_id,
            "fetched_at": _now_utc().isoformat(),
            "entry_type": entry_type,
            "entry_token": entry_token,
            "doc_token": doc_token,
            "meta": meta,
            "raw_content": raw_content,
        },
    )

    if incremental and db.get_document_hash("feishu", source_id) == content_hash:
        stats.docs_skipped_unchanged += 1
        return

    source_file_id = db.upsert_source_file(
        source_type="feishu",
        source_id=source_id,
        file_path=f"feishu://docx/{doc_token}",
        file_name=title,
        file_ext=".docx",
        category=category,
        file_size=len(text.encode("utf-8", errors="ignore")),
        file_mtime=updated_time,
        content_hash=content_hash,
        is_supported=True,
        unsupported_reason=None,
        meta={
            "run_id": run_id,
            "entry_type": entry_type,
            "entry_token": entry_token,
        },
    )

    doc_id = db.upsert_document(
        source_type="feishu",
        source_id=source_id,
        title=title,
        category=category,
        source_file_id=source_file_id,
        full_text=text,
        content_hash=content_hash,
        updated_time=updated_time,
        meta={
            "run_id": run_id,
            "entry_type": entry_type,
            "entry_token": entry_token,
            "doc_token": doc_token,
        },
    )

    chunks = split_text_to_chunks(text)
    db.replace_chunks(doc_id=doc_id, chunks=chunks, updated_time=updated_time)
    stats.docs_ingested += 1
    stats.chunks_written += len(chunks)


def _sync_space(
    *,
    db: DB,
    client: FeishuClient,
    raw_root: Path,
    space_id: str,
    category: str,
    incremental: bool,
    run_id: str,
    stats: FeishuSyncStats,
) -> None:
    page_token: str | None = None
    while True:
        data = client.list_space_nodes(space_id, page_token=page_token)
        items = data.get("items") or []
        for node in items:
            if node.get("obj_type") != "docx":
                continue
            doc_token = node.get("obj_token")
            if not doc_token:
                continue
            try:
                _ingest_doc_token(
                    db=db,
                    client=client,
                    raw_root=raw_root,
                    doc_token=doc_token,
                    category=category,
                    entry_type="space",
                    entry_token=space_id,
                    incremental=incremental,
                    run_id=run_id,
                    stats=stats,
                )
            except Exception:
                stats.failures += 1

        page_token = data.get("page_token")
        has_more = bool(data.get("has_more"))
        if not has_more:
            break

    db.set_checkpoint(
        checkpoint_key=f"feishu:space:{space_id}",
        cursor=page_token,
        watermark_ts=_now_utc(),
        meta={"run_id": run_id},
    )


def _sync_folder(
    *,
    db: DB,
    client: FeishuClient,
    raw_root: Path,
    folder_token: str,
    category: str,
    incremental: bool,
    run_id: str,
    stats: FeishuSyncStats,
) -> None:
    page_token: str | None = None
    while True:
        data = client.list_drive_files(folder_token, page_token=page_token)
        files = data.get("files") or []
        for file_obj in files:
            if file_obj.get("type") != "docx":
                continue
            doc_token = file_obj.get("token")
            if not doc_token:
                continue
            try:
                _ingest_doc_token(
                    db=db,
                    client=client,
                    raw_root=raw_root,
                    doc_token=doc_token,
                    category=category,
                    entry_type="folder",
                    entry_token=folder_token,
                    incremental=incremental,
                    run_id=run_id,
                    stats=stats,
                )
            except Exception:
                stats.failures += 1

        page_token = data.get("next_page_token")
        has_more = bool(data.get("has_more"))
        if not has_more:
            break

    db.set_checkpoint(
        checkpoint_key=f"feishu:folder:{folder_token}",
        cursor=page_token,
        watermark_ts=_now_utc(),
        meta={"run_id": run_id},
    )


def sync_feishu(
    db: DB,
    *,
    app_id: str,
    app_secret: str,
    raw_root: Path,
    page_size: int,
    retry_max: int,
    retry_backoff_ms: int,
    incremental: bool,
    run_id: str,
) -> FeishuSyncStats:
    if not app_id or not app_secret:
        raise RuntimeError("FEISHU_APP_ID / FEISHU_APP_SECRET is required for feishu sync")

    stats = FeishuSyncStats()
    client = FeishuClient(
        FeishuAuth(app_id=app_id, app_secret=app_secret),
        page_size=page_size,
        retry_max=retry_max,
        retry_backoff_ms=retry_backoff_ms,
    )

    entries = db.whitelist_entries()
    stats.whitelist_entries = len(entries)

    for entry in entries:
        entry_type = entry["entry_type"]
        token = entry["entry_token"]
        category = entry.get("label") or f"feishu-{entry_type}"
        if entry_type == "space":
            _sync_space(
                db=db,
                client=client,
                raw_root=raw_root,
                space_id=token,
                category=category,
                incremental=incremental,
                run_id=run_id,
                stats=stats,
            )
        elif entry_type == "folder":
            _sync_folder(
                db=db,
                client=client,
                raw_root=raw_root,
                folder_token=token,
                category=category,
                incremental=incremental,
                run_id=run_id,
                stats=stats,
            )
        elif entry_type == "doc":
            try:
                _ingest_doc_token(
                    db=db,
                    client=client,
                    raw_root=raw_root,
                    doc_token=token,
                    category=category,
                    entry_type="doc",
                    entry_token=token,
                    incremental=incremental,
                    run_id=run_id,
                    stats=stats,
                )
            except Exception:
                stats.failures += 1
        else:
            # drive_file and unknown types are ignored in v1 sync implementation.
            continue

    db.set_checkpoint(
        checkpoint_key="feishu:global",
        cursor=None,
        watermark_ts=_now_utc(),
        meta={"run_id": run_id, "stats": stats.asdict()},
    )

    return stats
