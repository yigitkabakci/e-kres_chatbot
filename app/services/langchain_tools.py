from __future__ import annotations

import logging
from typing import Any

from app.services.base_service import BaseTool
from app.services.knowledge_service import KnowledgeService
from app.services.mock_database import get_database

logger = logging.getLogger(__name__)

_knowledge: KnowledgeService | None = None
SECURITY_MESSAGE = "Uzgunum, sadece kendi ogrencilerinize ait bilgilere erisim yetkiniz bulunmaktadir. Baska bir ogrenci hakkinda bilgi almak icin lutfen o ogrenciye kayitli veli telefon numarasiyla tekrar giris yapin."


def get_knowledge() -> KnowledgeService:
    global _knowledge
    if _knowledge is None:
        _knowledge = KnowledgeService()
    return _knowledge


def _validate_student_access(kwargs: dict[str, Any]) -> dict[str, Any] | None:
    allowed_student_ids = set(kwargs.get("allowed_student_ids") or [])
    active_student_id = kwargs.get("active_student_id")
    if not allowed_student_ids or not active_student_id or active_student_id not in allowed_student_ids:
        return {
            "type": "security_block",
            "message": SECURITY_MESSAGE,
            "requires_reauth": True,
        }
    return None


class MealQueryTool(BaseTool):
    @property
    def name(self) -> str:
        return "meal_query"

    @property
    def description(self) -> str:
        return "Gunluk yemek menusunu sorgular."

    async def run(self, query: str, **kwargs: Any) -> dict[str, Any]:
        result = get_knowledge().query_menu()
        return {
            "type": result["type"],
            "data": result["data"],
            "message": result["formatted"],
            "source": result.get("source"),
            "page": result.get("page"),
        }


class ReportQueryTool(BaseTool):
    @property
    def name(self) -> str:
        return "report_query"

    @property
    def description(self) -> str:
        return "Ogrencinin gun sonu raporunu sorgular."

    async def run(self, query: str, **kwargs: Any) -> dict[str, Any]:
        blocked = _validate_student_access(kwargs)
        if blocked:
            return blocked
        result = get_knowledge().query_report(parent_id=kwargs.get("parent_id"), student_id=kwargs.get("active_student_id"))
        return {
            "type": result["type"],
            "data": result["data"],
            "message": result["formatted"],
            "source": result.get("source"),
            "page": result.get("page"),
        }


class PaymentQueryTool(BaseTool):
    @property
    def name(self) -> str:
        return "payment_query"

    @property
    def description(self) -> str:
        return "Odeme ve borc durumunu sorgular."

    async def run(self, query: str, **kwargs: Any) -> dict[str, Any]:
        blocked = _validate_student_access(kwargs)
        if blocked:
            return blocked
        result = get_knowledge().query_payments(parent_id=kwargs.get("parent_id"), student_id=kwargs.get("active_student_id"))
        return {
            "type": result["type"],
            "data": result["data"],
            "message": result["formatted"],
            "source": result.get("source"),
            "page": result.get("page"),
        }


class ScheduleQueryTool(BaseTool):
    @property
    def name(self) -> str:
        return "schedule_query"

    @property
    def description(self) -> str:
        return "Gunluk ders programini sorgular."

    async def run(self, query: str, **kwargs: Any) -> dict[str, Any]:
        result = get_knowledge().query_schedule()
        return {"type": result["type"], "data": result["data"], "message": result["formatted"]}


class ContactQueryTool(BaseTool):
    @property
    def name(self) -> str:
        return "contact_query"

    @property
    def description(self) -> str:
        return "e-Kres iletisim bilgilerini dondurur."

    async def run(self, query: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "type": "iletisim_bilgisi",
            "data": {
                "destek_hatti": "0850 550 50 41",
                "eposta": "destek@e-kres.com",
                "adres": "e-Kres Egitim Merkezi, Istanbul",
                "calisma_saatleri": "Hafta ici 07:30 - 18:00",
            },
            "message": (
                "Merhaba! e-Kres iletisim bilgileri:\n\n"
                "Destek Hatti: 0850 550 50 41\n"
                "E-posta: destek@e-kres.com\n"
                "Adres: e-Kres Egitim Merkezi, Istanbul\n"
                "Calisma Saatleri: Hafta ici 07:30 - 18:00"
            ),
        }


class AnnouncementQueryTool(BaseTool):
    @property
    def name(self) -> str:
        return "announcement_query"

    @property
    def description(self) -> str:
        return "Admin panelinden eklenen guncel duyurulari getirir."

    async def run(self, query: str, **kwargs: Any) -> dict[str, Any]:
        announcements = get_database().get_announcements()
        if not announcements:
            return {
                "type": "duyuru_listesi",
                "data": {"duyurular": []},
                "message": "Su anda yayinda aktif duyuru bulunmuyor.",
            }

        lines = []
        for item in announcements[:3]:
            line = f"{item['title']} ({item['date']}): {item['content']}"
            if item.get("pdf_url"):
                line += f" | PDF: {item['pdf_url']}"
            lines.append(line)

        return {
            "type": "duyuru_listesi",
            "data": {"duyurular": announcements},
            "message": "Merhaba! Guncel duyurularimiz:\n\n" + "\n\n".join(lines),
        }


def create_all_tools() -> list[BaseTool]:
    from app.services.file_service import FileQueryTool
    from app.services.pdf_service import PDFAnalysisTool
    from app.services.vision_service import VisionAnalysisTool
    from app.services.web_scanner_service import WebScannerTool

    return [
        MealQueryTool(),
        ReportQueryTool(),
        PaymentQueryTool(),
        ScheduleQueryTool(),
        ContactQueryTool(),
        AnnouncementQueryTool(),
        FileQueryTool(),
        PDFAnalysisTool(),
        VisionAnalysisTool(),
        WebScannerTool(),
    ]
