from __future__ import annotations

import hashlib
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .chunking import split_text_to_chunks
from .db import DB
from .extractors import SUPPORTED_EXTENSIONS, extractor_for, sha256_text


@dataclass
class IngestStats:
    scanned: int = 0
    supported: int = 0
    unsupported: int = 0
    skipped_unchanged: int = 0
    ingested: int = 0
    chunks_written: int = 0
    failures: int = 0

    def asdict(self) -> dict[str, Any]:
        return {
            "scanned": self.scanned,
            "supported": self.supported,
            "unsupported": self.unsupported,
            "skipped_unchanged": self.skipped_unchanged,
            "ingested": self.ingested,
            "chunks_written": self.chunks_written,
            "failures": self.failures,
        }


def _file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fp:
        while True:
            chunk = fp.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def discover_local_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if "_index" in path.parts:
            continue
        if any(part.startswith(".") for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def _category_of(path: Path, root: Path) -> str | None:
    rel = path.relative_to(root)
    if len(rel.parts) <= 1:
        return "root"
    return rel.parts[0]


def ingest_local(
    db: DB,
    *,
    report_root: Path,
    incremental: bool,
    run_id: str,
) -> IngestStats:
    stats = IngestStats()
    for path in discover_local_files(report_root):
        stats.scanned += 1
        rel = path.relative_to(report_root).as_posix()
        category = _category_of(path, report_root)
        suffix = path.suffix.lower()
        source_id = f"local:{rel}"
        file_mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        file_size = path.stat().st_size

        if suffix not in SUPPORTED_EXTENSIONS:
            stats.unsupported += 1
            db.upsert_source_file(
                source_type="unsupported",
                source_id=source_id,
                file_path=str(path),
                file_name=path.name,
                file_ext=suffix,
                category=category,
                file_size=file_size,
                file_mtime=file_mtime,
                content_hash=_file_hash(path),
                is_supported=False,
                unsupported_reason="extension_not_supported",
                meta={"run_id": run_id},
            )
            continue

        stats.supported += 1
        extractor = extractor_for(path)
        if extractor is None:
            stats.unsupported += 1
            db.upsert_source_file(
                source_type="unsupported",
                source_id=source_id,
                file_path=str(path),
                file_name=path.name,
                file_ext=suffix,
                category=category,
                file_size=file_size,
                file_mtime=file_mtime,
                content_hash=_file_hash(path),
                is_supported=False,
                unsupported_reason="extractor_missing",
                meta={"run_id": run_id},
            )
            continue

        try:
            extracted = extractor(path)
            content_hash = sha256_text(extracted.text)
            source_file_id = db.upsert_source_file(
                source_type="local",
                source_id=source_id,
                file_path=str(path),
                file_name=path.name,
                file_ext=suffix,
                category=category,
                file_size=file_size,
                file_mtime=file_mtime,
                content_hash=content_hash,
                is_supported=True,
                unsupported_reason=None,
                meta={"run_id": run_id, **extracted.meta},
            )

            if incremental:
                existing_hash = db.get_document_hash("local", source_id)
                if existing_hash == content_hash:
                    stats.skipped_unchanged += 1
                    continue

            doc_id = db.upsert_document(
                source_type="local",
                source_id=source_id,
                title=extracted.title or path.stem,
                category=category,
                source_file_id=source_file_id,
                full_text=extracted.text,
                content_hash=content_hash,
                updated_time=file_mtime,
                meta={"run_id": run_id, **extracted.meta},
            )

            chunks = split_text_to_chunks(extracted.text)
            db.replace_chunks(doc_id=doc_id, chunks=chunks, updated_time=file_mtime)

            stats.ingested += 1
            stats.chunks_written += len(chunks)
        except Exception as exc:
            stats.failures += 1
            db.upsert_source_file(
                source_type="unsupported",
                source_id=source_id,
                file_path=str(path),
                file_name=path.name,
                file_ext=suffix,
                category=category,
                file_size=file_size,
                file_mtime=file_mtime,
                content_hash=_file_hash(path),
                is_supported=False,
                unsupported_reason=f"parse_error: {exc}",
                meta={"run_id": run_id, "trace": traceback.format_exc(limit=5)},
            )

    db.set_checkpoint(
        checkpoint_key="local:files",
        cursor=None,
        watermark_ts=datetime.now(timezone.utc),
        meta={"run_id": run_id, "stats": stats.asdict()},
    )
    return stats
