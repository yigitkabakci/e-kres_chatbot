"""
e-Kreş Chatbot API — Base Abstractions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
BaseTool (Tool Pattern) ve BaseMemory (Session Management) ABC'leri.
Tüm servisler bu soyutlamaları miras alır.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  BASE TOOL — Tool Design Pattern
# ═══════════════════════════════════════════════════════════════

class BaseTool(ABC):
    """
    Tüm araçlar (mock_database, pdf_analysis, vision_analysis)
    için ortak arayüz.

    Yeni bir araç eklemek için:
      1. Bu sınıfı miras al
      2. name, description ve run() metodunu implement et
      3. ChatService'e register et
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Araç adı (ToolName enum'u ile eşleşmeli)."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Araç açıklaması (LLM'in aracı seçmesi için)."""
        ...

    @abstractmethod
    async def run(self, query: str, **kwargs: Any) -> dict[str, Any]:
        """
        Aracı çalıştır.

        Args:
            query: Kullanıcı sorgusu veya işlenecek metin.
            **kwargs: Ek parametreler (session_id, attachments, vb.).

        Returns:
            dict: Aracın ürettiği sonuç verisi.
        """
        ...

    def get_info(self) -> dict[str, str]:
        """Araç meta bilgisini döndür."""
        return {"name": self.name, "description": self.description}


# ═══════════════════════════════════════════════════════════════
#  BASE MEMORY — Session Management
# ═══════════════════════════════════════════════════════════════

class BaseMemory(ABC):
    """
    Oturum yönetimi soyutlaması.
    Şu an InMemoryStorage ile çalışır, ileride RedisMemory olarak
    swap edilebilecek şekilde tasarlanmıştır.
    """

    @abstractmethod
    async def get_history(self, session_id: str) -> list[dict]:
        """Oturuma ait mesaj geçmişini getir."""
        ...

    @abstractmethod
    async def add_message(
        self, session_id: str, role: str, content: str
    ) -> None:
        """Oturuma mesaj ekle."""
        ...

    @abstractmethod
    async def clear_session(self, session_id: str) -> None:
        """Oturumu temizle."""
        ...

    @abstractmethod
    async def session_exists(self, session_id: str) -> bool:
        """Oturumun var olup olmadığını kontrol et."""
        ...


# ═══════════════════════════════════════════════════════════════
#  IN-MEMORY STORAGE — Geliştirme için varsayılan implementasyon
# ═══════════════════════════════════════════════════════════════

class InMemoryStorage(BaseMemory):
    """
    dict tabanlı oturum deposu.

    Özellikler:
      - TTL bazlı otomatik temizlik
      - Maksimum geçmiş uzunluğu sınırı
      - Thread-safe değil (tek worker için uygundur)
    """

    def __init__(self) -> None:
        # {session_id: {"messages": [...], "last_access": datetime}}
        self._store: dict[str, dict] = {}

    def _get_or_create(self, session_id: str) -> dict:
        """Oturumu getir veya yeni oluştur, TTL kontrolü yap."""
        now = datetime.utcnow()
        ttl = timedelta(minutes=settings.SESSION_TTL_MINUTES)

        if session_id in self._store:
            session = self._store[session_id]
            # TTL aşıldıysa sıfırla
            if now - session["last_access"] > ttl:
                logger.info("Session TTL expired, resetting: %s", session_id)
                session = {"messages": [], "last_access": now}
                self._store[session_id] = session
            else:
                session["last_access"] = now
        else:
            session = {"messages": [], "last_access": now}
            self._store[session_id] = session

        return session

    async def get_history(self, session_id: str) -> list[dict]:
        session = self._get_or_create(session_id)
        return list(session["messages"])

    async def add_message(
        self, session_id: str, role: str, content: str
    ) -> None:
        session = self._get_or_create(session_id)
        session["messages"].append(
            {"role": role, "content": content, "timestamp": datetime.utcnow().isoformat()}
        )
        # Max geçmiş uzunluğunu aşarsa eski mesajları at
        max_len = settings.MAX_HISTORY_LENGTH
        if len(session["messages"]) > max_len:
            session["messages"] = session["messages"][-max_len:]

    async def clear_session(self, session_id: str) -> None:
        self._store.pop(session_id, None)
        logger.info("Session cleared: %s", session_id)

    async def session_exists(self, session_id: str) -> bool:
        return session_id in self._store

    @property
    def active_session_count(self) -> int:
        """Aktif oturum sayısı."""
        return len(self._store)
