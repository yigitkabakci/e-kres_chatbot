from __future__ import annotations

from datetime import date
from typing import Any

from app.schemas.chat import DailyMenu, DailyReport, DailySchedule, PaymentSummary, PaymentItem
from app.services.mock_database import get_database

DATA_SOURCE = "mock_database.json"


class KnowledgeService:
    """Chatbot sorgularini yerel JSON veritabanindan okur."""

    def __init__(self) -> None:
        self._db = get_database()

    def query_menu(self, target_date: date | None = None) -> dict[str, Any]:
        menu = self._db.get_menu_for_date(target_date)
        return {
            "type": "yemek_menusu",
            "data": menu.model_dump(mode="json"),
            "formatted": self._format_menu(menu),
            "source": DATA_SOURCE,
            "page": 5,
        }

    def query_report(self, target_date: date | None = None, parent_id: str | None = None, student_id: str | None = None) -> dict[str, Any]:
        report = self._db.get_report_for_date(target_date=target_date, parent_id=parent_id, student_id=student_id)
        schedule = self._db.get_schedule_for_date(target_date)
        finance = self._db.get_finance_summary(parent_id=parent_id, student_id=student_id)
        overdue = self._db.get_overdue_payments(student_id=student_id or self._db._student_id_by_parent_id(self._db.get_state(), parent_id))
        return {
            "type": "gun_sonu_raporu",
            "data": {
                "report": report.model_dump(mode="json"),
                "schedule": schedule.model_dump(mode="json"),
                "finance": finance.model_dump(mode="json"),
                "overdue": [item.model_dump(mode="json") for item in overdue],
            },
            "formatted": self._format_report(report, schedule, finance, overdue),
            "source": DATA_SOURCE,
            "page": 8,
        }

    def query_payments(self, parent_id: str | None = None, student_id: str | None = None) -> dict[str, Any]:
        summary = self._db.get_finance_summary(parent_id=parent_id, student_id=student_id)
        return {
            "type": "odeme_ozeti",
            "data": summary.model_dump(mode="json"),
            "formatted": self._format_payments(summary),
            "source": DATA_SOURCE,
            "page": 9,
        }

    def query_schedule(self, target_date: date | None = None) -> dict[str, Any]:
        schedule = self._db.get_schedule_for_date(target_date)
        return {
            "type": "ders_programi",
            "data": schedule.model_dump(mode="json"),
            "formatted": self._format_schedule(schedule),
            "source": DATA_SOURCE,
            "page": 4,
        }

    @staticmethod
    def _format_menu(menu: DailyMenu) -> str:
        message = (
            "Merhaba! Bugun menude su yemekler var:\n\n"
            f"Kahvalti: {', '.join(menu.kahvalti)}\n"
            f"Ogle: {', '.join(menu.ogle)}\n"
            f"Ikindi: {', '.join(menu.ikindi)}\n"
            f"Ara Ogun: {', '.join(menu.ara_ogun)}"
        )
        if menu.aciklama:
            message += f"\n\nNot: {menu.aciklama}"
        return message

    @staticmethod
    def _format_report(report: DailyReport, schedule: DailySchedule, finance: PaymentSummary, overdue: list[PaymentItem]) -> str:
        schedule_lines = "\n".join([f"- {item.saat}: {item.etkinlik}" for item in schedule.dersler[:4]])
        finance_lines = (
            f"Toplam borc: {finance.toplam_tutar:,.0f} ₺\n"
            f"Odenen: {finance.odenen:,.0f} ₺\n"
            f"Kalan: {finance.kalan:,.0f} ₺"
        )
        overdue_note = "- Gecikmis odeme bulunmuyor."
        if overdue:
            overdue_note = "\n".join([f"- {item.tarih.strftime('%d.%m.%Y')} | {item.tutar:,.0f} ₺ | {item.durum}" for item in overdue[:2]])
        return (
            f"Merhaba! {report.ogrenci_adi} icin bugunun ({report.tarih}) ozeti:\n\n"
            f"Genel durum:\n"
            f"- Uyku: {report.uyku}\n"
            f"- Duygu Durumu: {report.duygu_durumu}\n"
            f"- Etkinliklere Katilim: {report.etkinliklere_katilim}\n"
            f"- Arkadaslari ile Iletisim: {report.arkadaslari_ile_iletisim}\n"
            f"- Genel Uyum: {report.genel_uyum}\n\n"
            f"Bugun yapacagi etkinlikler:\n{schedule_lines}\n\n"
            f"Finans ozeti:\n{finance_lines}\n\n"
            f"Gecikmis odemeler:\n{overdue_note}"
        )

    @staticmethod
    def _format_payments(summary: PaymentSummary) -> str:
        message = (
            f"Merhaba! {summary.ogrenci_adi} icin {summary.donem} donemi odeme durumu:\n\n"
            f"Toplam borc: {summary.toplam_tutar:,.0f} ₺\n"
            f"Odenen: {summary.odenen:,.0f} ₺\n"
            f"Kalan: {summary.kalan:,.0f} ₺"
        )
        waiting_items = [item for item in summary.odemeler if item.durum != "Odendi"]
        if waiting_items:
            lines = [f"- {item.tarih.strftime('%d.%m.%Y')} | {item.tutar:,.0f} ₺ | {item.tur} | {item.durum}" for item in waiting_items[:3]]
            message += "\n\nBekleyen odemeler:\n" + "\n".join(lines)
        return message

    @staticmethod
    def _format_schedule(schedule: DailySchedule) -> str:
        lessons = "\n".join([f"- {item.saat}: {item.etkinlik}" for item in schedule.dersler])
        return f"Merhaba! Bugun ({schedule.gun}) ders programi:\n\n{lessons}"


