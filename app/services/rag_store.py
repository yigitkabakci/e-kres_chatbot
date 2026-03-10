from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

GLOBAL_RAG_SESSION_ID = "__global_admin_data__"

# {session_id: [{"type": "pdf"|"web"|"admin_file", "source": "filename_or_url", "text": "...", "metric": int}, ...]}
_rag_store: dict[str, list[dict[str, Any]]] = {}


def store_rag_context(session_id: str, source_type: str, source_name: str, text: str, metric: int = 0) -> None:
    """PDF veya URL metnini oturumun RAG deposuna kaydet ya da guncelle."""
    items = _rag_store.setdefault(session_id, [])
    items[:] = [item for item in items if not (item["type"] == source_type and item["source"] == source_name)]
    items.append({
        "type": source_type,
        "source": source_name,
        "text": text,
        "metric": metric,
    })
    logger.info(
        "RAG deposuna eklendi: session=%s, tip=%s, kaynak=%s, %d karakter",
        session_id,
        source_type,
        source_name,
        len(text),
    )


def store_global_rag_context(source_type: str, source_name: str, text: str, metric: int = 0) -> None:
    store_rag_context(GLOBAL_RAG_SESSION_ID, source_type, source_name, text, metric)


def get_session_context(session_id: str) -> list[dict[str, Any]]:
    return _rag_store.get(session_id, [])


def get_combined_session_text(session_id: str, max_chars: int = 6000) -> str:
    """Oturumdaki ve global admin bilgisindeki RAG metinlerini birlestir."""
    items = [*get_session_context(GLOBAL_RAG_SESSION_ID), *get_session_context(session_id)]
    if not items:
        return ""

    combined: list[str] = []
    total_len = 0
    for item in items:
        header = f"\n[{item['type'].upper()}: {item['source']}]\n"
        chunk = header + item["text"] + "\n"
        combined.append(chunk)
        total_len += len(chunk)
        if total_len > max_chars:
            break
    return "".join(combined)[:max_chars]
