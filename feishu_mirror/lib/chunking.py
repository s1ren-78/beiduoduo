from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChunkConfig:
    max_chars: int = 1200
    overlap: int = 120


def split_text_to_chunks(text: str, cfg: ChunkConfig | None = None) -> list[dict]:
    cfg = cfg or ChunkConfig()
    cleaned = "\n".join(line.rstrip() for line in text.splitlines())
    if not cleaned.strip():
        return []

    chunks: list[dict] = []
    cursor = 0
    chunk_index = 0
    total_len = len(cleaned)

    while cursor < total_len:
        end = min(cursor + cfg.max_chars, total_len)
        if end < total_len:
            newline_break = cleaned.rfind("\n", cursor, end)
            if newline_break > cursor + 200:
                end = newline_break

        snippet = cleaned[cursor:end].strip()
        if snippet:
            chunks.append(
                {
                    "chunk_index": chunk_index,
                    "section": None,
                    "content": snippet,
                    "start_offset": cursor,
                    "end_offset": end,
                    "meta": {},
                }
            )
            chunk_index += 1

        if end >= total_len:
            break

        cursor = max(end - cfg.overlap, cursor + 1)

    return chunks
