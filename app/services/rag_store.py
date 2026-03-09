"""
e-Kres Chatbot API — Unified RAG Store
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Oturum bazli dinamik bilgi tabani.
Sisteme yuklenen PDF ve taranan Web URL metinlerini saklar.
Her session (kullanici oturumu) icin ozel bir context olusturur.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# {session_id: [{"type": "pdf"|"web", "source": "filename_or_url", "text": "...", "pages_or_words": int}, ...]}
_rag_store: dict[str, list[dict[str, Any]]] = {}


def store_rag_context(session_id: str, source_type: str, source_name: str, text: str, metric: int = 0) -> None:
    """PDF veya URL metnini oturumun RAG deposuna kaydet."""
    if session_id not in _rag_store:
        _rag_store[session_id] = []
        
    _rag_store[session_id].append({
        "type": source_type,      # "pdf" veya "web"
        "source": source_name,    # "menu.pdf" veya "https://example.com"
        "text": text,
        "metric": metric,         # sayfa sayisi veya kelime sayisi
    })
    
    logger.info(
        "RAG deposuna eklendi: session=%s, tip=%s, kaynak=%s, %d karakter",
        session_id, source_type, source_name, len(text)
    )


def get_session_context(session_id: str) -> list[dict[str, Any]]:
    """Oturuma ait tum PDF ve Web iceriklerini dondur."""
    return _rag_store.get(session_id, [])


def get_combined_session_text(session_id: str, max_chars: int = 6000) -> str:
    """Oturumdaki tum RAG metinlerini LLM'e vermek icin birlestir."""
    items = get_session_context(session_id)
    if not items:
        return ""
        
    combined = []
    total_len = 0
    
    for item in items:
        # Orn: "[PDF: menu.pdf]" veya "[WEB: https://example.com]"
        header = f"\n[{item['type'].upper()}: {item['source']}]\n"
        text = item["text"]
        
        chunk = header + text + "\n"
        combined.append(chunk)
        total_len += len(chunk)
        
        if total_len > max_chars:
            break
            
    return "".join(combined)[:max_chars]
