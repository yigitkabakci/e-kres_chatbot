from __future__ import annotations

import json
import logging
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any

from app.core.constants import ToolName
from app.schemas.chat import DailyMenu, DailyReport, DailySchedule, PaymentItem, PaymentSummary, ScheduleItem
from app.services.base_service import BaseTool

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DATA_DIR / "mock_database.json"
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "static" / "uploads"
WEEKDAYS = ["Pazartesi", "Sali", "Carsamba", "Persembe", "Cuma"]
DEFAULT_PARENT = {
    "veli_id": "veli-1",
    "ad_soyad": "Meral Koç",
    "telefon": "05051234567",
    "sifre": "1234",
}
DEFAULT_STUDENT = {
    "ogrenci_id": "ogrenci-1",
    "ad_soyad": "e-kreş öğrenci deneme",
    "veli_id": "veli-1",
}


class LocalJSONDatabase:
    def __init__(self) -> None:
        self._lock = Lock()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        if not DB_PATH.exists():
            self._write_state(self._default_state())

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            state = deepcopy(self._read_state())
        return self._ensure_state_schema(state)

    def get_parent_by_phone(self, phone: str | None) -> dict[str, Any] | None:
        if not phone:
            return None
        state = self.get_state()
        return next((parent for parent in state["parents"] if parent["telefon"] == phone), None)

    def get_auth_failure_reason(self, phone: str | None) -> str:
        if not phone:
            return "Lutfen once telefon numaranizi girin."
        parent = self.get_parent_by_phone(phone)
        if not parent:
            return "Bu numara ile kayitli veli bulunamadi."
        return "Giris bilgileri dogrulanamadi."

    def authenticate_parent(self, phone: str | None, password: str | None = None) -> dict[str, Any] | None:
        if not phone:
            return None
        parent = self.get_parent_by_phone(phone)
        if not parent:
            return None
        state = self.get_state()
        student = next((item for item in state["students"] if item["veli_id"] == parent["veli_id"]), None)
        if not student:
            return None
        parent_first_name = (parent["ad_soyad"] or "Velimiz").split()[0]
        return {
            "parent_id": parent["veli_id"],
            "parent_name": parent["ad_soyad"],
            "phone": parent["telefon"],
            "student_id": student["ogrenci_id"],
            "student_name": student["ad_soyad"],
            "greeting": f"Hos geldiniz {parent_first_name} Hanim, {student['ad_soyad']} hakkinda size nasil yardimci olabilirim?",
        }

    def delete_family(self, parent_id: str, student_id: str) -> dict[str, Any]:
        state = self.get_state()
        state["students"] = [item for item in state["students"] if item["ogrenci_id"] != student_id]
        state["parents"] = [item for item in state["parents"] if item["veli_id"] != parent_id]
        finance_records = state.get("finance_records", {})
        finance_records.pop(student_id, None)
        state["finance_records"] = finance_records
        if state["students"]:
            fallback_student_id = state["students"][0]["ogrenci_id"]
            state["finance"] = state["finance_records"].get(
                fallback_student_id,
                self._default_finance_summary(state["students"][0]["ad_soyad"]).model_dump(mode="json"),
            )
        else:
            state["finance"] = self._default_finance_summary(DEFAULT_STUDENT["ad_soyad"]).model_dump(mode="json")
        self._write_state(state)
        return {"parent_id": parent_id, "student_id": student_id}

    def delete_finance(self, student_id: str) -> dict[str, Any]:
        state = self.get_state()
        student = self._get_student_by_id(state, student_id)
        if not student:
            raise ValueError("Finans kaydi silinecek ogrenci bulunamadi.")
        empty_finance = {
            "donem": "",
            "ogrenci_adi": student["ad_soyad"],
            "toplam_adet": 0,
            "odendi_adet": 0,
            "odenmedi_adet": 0,
            "kismi_adet": 0,
            "toplam_tutar": 0,
            "odenen": 0,
            "kalan": 0,
            "odemeler": [],
        }
        state.setdefault("finance_records", {})[student_id] = empty_finance
        state["finance"] = empty_finance
        self._write_state(state)
        return {"student_id": student_id}

    def upsert_family(self, parent: dict[str, Any], student: dict[str, Any]) -> dict[str, Any]:
        state = self.get_state()
        parent_id = parent.get("veli_id") or f"veli-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"
        student_id = student.get("ogrenci_id") or f"ogrenci-{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"

        parent_record = {
            "veli_id": parent_id,
            "ad_soyad": parent["ad_soyad"],
            "telefon": parent["telefon"],
            "sifre": parent.get("sifre") or "0000",
        }
        student_record = {
            "ogrenci_id": student_id,
            "ad_soyad": student["ad_soyad"],
            "veli_id": parent_id,
        }

        parents = [item for item in state["parents"] if item["veli_id"] != parent_id]
        students = [item for item in state["students"] if item["ogrenci_id"] != student_id]
        parents.append(parent_record)
        students.append(student_record)
        state["parents"] = parents
        state["students"] = students

        finance_records = state.get("finance_records", {})
        if student_id not in finance_records:
            finance_records[student_id] = self._default_finance_summary(student_record["ad_soyad"]).model_dump(mode="json")
        state["finance_records"] = finance_records
        state["finance"] = finance_records[student_id]
        self._write_state(state)
        return {
            "parent": parent_record,
            "student": student_record,
            "finance": finance_records[student_id],
        }

    def update_meals(self, meals: list[dict[str, Any]]) -> dict[str, Any]:
        validated = [DailyMenu.model_validate(item) for item in meals]
        state = self.get_state()
        state["meals"] = [meal.model_dump(mode="json") for meal in validated]
        self._write_state(state)
        return {"updated": len(validated), "meals": state["meals"]}

    def update_finance(self, finance: dict[str, Any], student_id: str | None = None) -> dict[str, Any]:
        state = self.get_state()
        resolved_student_id = student_id or self._resolve_student_id(state, finance.get("ogrenci_adi"))
        student = self._get_student_by_id(state, resolved_student_id)
        if not student:
            raise ValueError("Finans guncellemesi icin ogrenci bulunamadi.")

        normalized_finance = dict(finance)
        normalized_finance["ogrenci_adi"] = student["ad_soyad"]
        summary = PaymentSummary.model_validate(normalized_finance)
        state.setdefault("finance_records", {})[resolved_student_id] = summary.model_dump(mode="json")
        state["finance"] = state["finance_records"][resolved_student_id]
        self._write_state(state)
        return state["finance_records"][resolved_student_id]

    def update_schedules(self, schedules: list[dict[str, Any]], daily_flow: list[dict[str, str]]) -> dict[str, Any]:
        validated_schedules = [DailySchedule.model_validate(item) for item in schedules]
        state = self.get_state()
        state["schedules"] = [item.model_dump(mode="json") for item in validated_schedules]
        state["daily_flow"] = daily_flow
        self._write_state(state)
        return {"schedules": state["schedules"], "daily_flow": state["daily_flow"]}

    def add_announcement(self, title: str, content: str, pdf_filename: str | None = None, pdf_url: str | None = None, priority: str = "normal") -> dict[str, Any]:
        state = self.get_state()
        announcement = {
            "id": datetime.utcnow().strftime("%Y%m%d%H%M%S%f"),
            "title": title,
            "content": content,
            "date": datetime.utcnow().date().isoformat(),
            "priority": priority,
            "pdf_filename": pdf_filename,
            "pdf_url": pdf_url,
        }
        state["announcements"].insert(0, announcement)
        self._write_state(state)
        return announcement

    def get_dashboard_data(self) -> dict[str, Any]:
        state = self.get_state()
        finance_records = self._build_finance_records(state)
        selected_finance = finance_records[0]["finance"] if finance_records else self._default_finance_summary(DEFAULT_STUDENT["ad_soyad"]).model_dump(mode="json")
        return {
            "meals": state["meals"],
            "finance": selected_finance,
            "finance_records": finance_records,
            "schedules": state["schedules"],
            "daily_flow": state["daily_flow"],
            "announcements": state["announcements"],
            "analytics": state["analytics"],
            "overdue_payments": self._get_all_overdue_payments(state),
            "parents": state["parents"],
            "students": state["students"],
            "family_directory": self._build_family_directory(state),
        }

    def get_menu_for_date(self, target_date: date | None = None) -> DailyMenu:
        state = self.get_state()
        menus = [DailyMenu.model_validate(item) for item in state["meals"]]
        selected_date = target_date or date.today()
        for menu in menus:
            if menu.tarih == selected_date:
                return menu
        return menus[selected_date.weekday() % len(menus)]

    def get_report_for_date(self, target_date: date | None = None, parent_id: str | None = None) -> DailyReport:
        profile = self._profile_by_parent_id(parent_id)
        reports = [DailyReport.model_validate(item) for item in self.get_state()["reports"]]
        selected_date = target_date or date.today()
        for report in reports:
            if report.tarih == selected_date:
                return report.model_copy(update={"ogrenci_adi": profile["student_name"]})
        return reports[0].model_copy(update={"ogrenci_adi": profile["student_name"]})

    def get_finance_summary(self, parent_id: str | None = None, student_id: str | None = None) -> PaymentSummary:
        state = self.get_state()
        resolved_student_id = student_id or self._student_id_by_parent_id(state, parent_id) or DEFAULT_STUDENT["ogrenci_id"]
        student = self._get_student_by_id(state, resolved_student_id) or DEFAULT_STUDENT
        finance_records = state.get("finance_records", {})
        raw = finance_records.get(resolved_student_id)
        if not raw:
            raw = self._default_finance_summary(student["ad_soyad"]).model_dump(mode="json")
            finance_records[resolved_student_id] = raw
            state["finance_records"] = finance_records
            self._write_state(state)
        return PaymentSummary.model_validate(raw).model_copy(update={"ogrenci_adi": student["ad_soyad"]})

    def get_schedule_for_date(self, target_date: date | None = None) -> DailySchedule:
        schedules = [DailySchedule.model_validate(item) for item in self.get_state()["schedules"]]
        target = target_date or date.today()
        weekday = WEEKDAYS[target.weekday() % len(WEEKDAYS)]
        for schedule in schedules:
            if schedule.gun == weekday:
                return schedule
        return schedules[0]

    def get_announcements(self) -> list[dict[str, Any]]:
        return self.get_state()["announcements"]

    def get_overdue_payments(self, student_id: str | None = None) -> list[PaymentItem]:
        summary = self.get_finance_summary(student_id=student_id)
        today = date.today()
        overdue: list[PaymentItem] = []
        for item in summary.odemeler:
            is_paid = item.durum.lower() == "odendi"
            is_late = "gecik" in item.durum.lower() or (item.tarih < today and not is_paid)
            if is_late:
                overdue.append(item)
        return overdue

    def save_uploaded_pdf(self, filename: str, content: bytes) -> tuple[str, str]:
        safe_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{Path(filename).name}"
        target = UPLOAD_DIR / safe_name
        target.write_bytes(content)
        return safe_name, f"/static/uploads/{safe_name}"

    def _build_family_directory(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        directory: list[dict[str, Any]] = []
        for student in state["students"]:
            parent = next((item for item in state["parents"] if item["veli_id"] == student["veli_id"]), None)
            directory.append(
                {
                    "parent_id": student["veli_id"],
                    "parent_name": parent["ad_soyad"] if parent else "-",
                    "phone": parent["telefon"] if parent else "-",
                    "student_id": student["ogrenci_id"],
                    "student_name": student["ad_soyad"],
                }
            )
        return directory

    def _build_finance_records(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for student in state["students"]:
            finance = self.get_finance_summary(student_id=student["ogrenci_id"]).model_dump(mode="json")
            parent = next((item for item in state["parents"] if item["veli_id"] == student["veli_id"]), None)
            records.append(
                {
                    "student_id": student["ogrenci_id"],
                    "student_name": student["ad_soyad"],
                    "parent_id": student["veli_id"],
                    "parent_name": parent["ad_soyad"] if parent else "-",
                    "finance": finance,
                }
            )
        return records

    def _get_all_overdue_payments(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for student in state["students"]:
            for item in self.get_overdue_payments(student_id=student["ogrenci_id"]):
                rows.append({
                    **item.model_dump(mode="json"),
                    "student_id": student["ogrenci_id"],
                    "student_name": student["ad_soyad"],
                })
        return rows

    def _resolve_student_id(self, state: dict[str, Any], student_name: str | None) -> str:
        if student_name:
            for student in state["students"]:
                if student["ad_soyad"] == student_name:
                    return student["ogrenci_id"]
        return DEFAULT_STUDENT["ogrenci_id"]

    @staticmethod
    def _get_student_by_id(state: dict[str, Any], student_id: str | None) -> dict[str, Any] | None:
        if not student_id:
            return None
        return next((item for item in state["students"] if item["ogrenci_id"] == student_id), None)

    @staticmethod
    def _student_id_by_parent_id(state: dict[str, Any], parent_id: str | None) -> str | None:
        if not parent_id:
            return None
        student = next((item for item in state["students"] if item["veli_id"] == parent_id), None)
        return student["ogrenci_id"] if student else None

    def _profile_by_parent_id(self, parent_id: str | None) -> dict[str, str]:
        state = self.get_state()
        student_id = self._student_id_by_parent_id(state, parent_id) or DEFAULT_STUDENT["ogrenci_id"]
        student = self._get_student_by_id(state, student_id) or DEFAULT_STUDENT
        return {"student_name": student["ad_soyad"]}

    def _default_finance_summary(self, student_name: str) -> PaymentSummary:
        return PaymentSummary(
            donem="2025-2026",
            ogrenci_adi=student_name,
            toplam_adet=6,
            odendi_adet=1,
            odenmedi_adet=5,
            kismi_adet=0,
            toplam_tutar=30380000,
            odenen=380000,
            kalan=30000000,
            odemeler=[
                PaymentItem(tarih=date(2025, 7, 8), tutar=380000, tur="Aidat", durum="Odendi", odeme_bilgisi="Odendi(08.07.2025)"),
                PaymentItem(tarih=date(2025, 9, 1), tutar=5000000, tur="Aidat", durum="Odenmedi", odeme_bilgisi="Odenmedi"),
                PaymentItem(tarih=date(2025, 10, 1), tutar=5000000, tur="Aidat", durum="Odenmedi", odeme_bilgisi="Odenmedi"),
                PaymentItem(tarih=date(2025, 11, 1), tutar=5000000, tur="Aidat", durum="Gecikmis", odeme_bilgisi="Odenmedi - vadesi gecmis"),
                PaymentItem(tarih=date(2025, 12, 1), tutar=5000000, tur="Aidat", durum="Odenmedi", odeme_bilgisi="Odenmedi"),
                PaymentItem(tarih=date(2026, 1, 1), tutar=10000000, tur="Aidat", durum="Odenmedi", odeme_bilgisi="Odenmedi"),
            ],
        )

    def _read_state(self) -> dict[str, Any]:
        with DB_PATH.open("r", encoding="utf-8-sig") as file:
            return json.load(file)

    def _write_state(self, state: dict[str, Any]) -> None:
        with self._lock:
            with DB_PATH.open("w", encoding="utf-8") as file:
                json.dump(state, file, ensure_ascii=False, indent=2)

    def _ensure_state_schema(self, state: dict[str, Any]) -> dict[str, Any]:
        changed = False
        if "parents" not in state:
            state["parents"] = [DEFAULT_PARENT]
            changed = True
        if "students" not in state:
            state["students"] = [DEFAULT_STUDENT]
            changed = True
        if not state.get("meals"):
            state["meals"] = self._default_state()["meals"]
            changed = True
        if not state.get("reports"):
            state["reports"] = self._default_state()["reports"]
            changed = True
        if not state.get("schedules"):
            state["schedules"] = self._default_state()["schedules"]
            changed = True
        if "daily_flow" not in state:
            state["daily_flow"] = self._default_state()["daily_flow"]
            changed = True
        if "announcements" not in state:
            state["announcements"] = self._default_state()["announcements"]
            changed = True
        if "analytics" not in state:
            state["analytics"] = self._default_state()["analytics"]
            changed = True

        finance_records = state.get("finance_records")
        if not isinstance(finance_records, dict) or not finance_records:
            finance_records = {}
            legacy_finance = state.get("finance")
            target_student_id = self._resolve_student_id(state, (legacy_finance or {}).get("ogrenci_adi"))
            if legacy_finance:
                finance_records[target_student_id] = PaymentSummary.model_validate(legacy_finance).model_dump(mode="json")
            else:
                finance_records[target_student_id] = self._default_finance_summary(DEFAULT_STUDENT["ad_soyad"]).model_dump(mode="json")
            state["finance_records"] = finance_records
            changed = True

        for student in state["students"]:
            if student["ogrenci_id"] not in state["finance_records"]:
                state["finance_records"][student["ogrenci_id"]] = self._default_finance_summary(student["ad_soyad"]).model_dump(mode="json")
                changed = True

        if "finance" not in state or not state["finance"]:
            first_student_id = state["students"][0]["ogrenci_id"]
            state["finance"] = state["finance_records"][first_student_id]
            changed = True

        if changed:
            self._write_state(state)
        return state

    def _default_state(self) -> dict[str, Any]:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        meals = [
            DailyMenu(tarih=monday, kahvalti=["Yagli balli ekmek dilimleri", "Peynir", "Zeytin", "Maydanoz", "Sut"], ogle=["Alaca corbasi", "Kofteli patates oturtma", "Mevsim salata"], ikindi=["Mercimekli kofte"], ara_ogun=["Meyve"], aciklama="Alerjisi olan ogrenciler icin alternatif menu hazirdir."),
            DailyMenu(tarih=monday + timedelta(days=1), kahvalti=["Menemen", "Beyaz peynir", "Domates", "Salatalik", "Sut"], ogle=["Sehriye corbasi", "Firinda tavuk but", "Bulgur pilavi", "Cacik"], ikindi=["Pogaca"], ara_ogun=["Muz"], aciklama=None),
            DailyMenu(tarih=monday + timedelta(days=2), kahvalti=["Kasar peynirli tost", "Domates", "Salatalik", "Sut"], ogle=["Mercimek corbasi", "Etli nohut", "Pirinc pilavi", "Ayran"], ikindi=["Cevizli kek"], ara_ogun=["Portakal"], aciklama=None),
            DailyMenu(tarih=monday + timedelta(days=3), kahvalti=["Omlet", "Bal", "Kaymak", "Ekmek", "Sut"], ogle=["Domates corbasi", "Izgara kofte", "Makarna", "Yogurt"], ikindi=["Kurabiye"], ara_ogun=["Elma"], aciklama=None),
            DailyMenu(tarih=monday + timedelta(days=4), kahvalti=["Sucuklu yumurta", "Peynir", "Zeytin", "Domates", "Sut"], ogle=["Tavuk suyu corbasi", "Sebzeli guvec", "Pirinc pilavi", "Salata"], ikindi=["Acma"], ara_ogun=["Armut"], aciklama="Hafta sonu icin evde su tuketimi hatirlatmasi yapildi."),
        ]
        reports = [
            DailyReport(tarih=today, ogrenci_adi=DEFAULT_STUDENT["ad_soyad"], kahvalti="Iyi", kahvalti_aciklama="Kahvaltisini duzenli yapti.", ogle_yemegi="Iyi", ikindi="Iyi", ikindi_aciklama="Meyvesini severek yedi.", uyku="Iyi", duygu_durumu="Mutlu", etkinliklere_katilim="Katildi", arkadaslari_ile_iletisim="Basarili", genel_uyum="Uyumlu")
        ]
        default_finance = self._default_finance_summary(DEFAULT_STUDENT["ad_soyad"]).model_dump(mode="json")
        schedules = [
            DailySchedule(gun="Pazartesi", dersler=[ScheduleItem(saat="09:00-09:30", etkinlik="Turkce Dil Etkinligi"), ScheduleItem(saat="09:30-10:00", etkinlik="Serbest Oyun Zamani"), ScheduleItem(saat="10:00-10:30", etkinlik="Muzik"), ScheduleItem(saat="10:30-11:00", etkinlik="Sanat Atolyesi")]),
            DailySchedule(gun="Sali", dersler=[ScheduleItem(saat="09:00-09:30", etkinlik="Matematik / Fen"), ScheduleItem(saat="09:30-10:00", etkinlik="Ingilizce"), ScheduleItem(saat="10:00-10:30", etkinlik="Drama"), ScheduleItem(saat="10:30-11:00", etkinlik="Bahce Etkinligi")]),
            DailySchedule(gun="Carsamba", dersler=[ScheduleItem(saat="09:00-09:30", etkinlik="Okuma Yazma Hazirligi"), ScheduleItem(saat="09:30-10:00", etkinlik="Fen Doga"), ScheduleItem(saat="10:00-10:30", etkinlik="Muzik"), ScheduleItem(saat="10:30-11:00", etkinlik="Sanat Etkinligi")]),
            DailySchedule(gun="Persembe", dersler=[ScheduleItem(saat="09:00-09:30", etkinlik="Turkce Dil Etkinligi"), ScheduleItem(saat="09:30-10:00", etkinlik="Ingilizce"), ScheduleItem(saat="10:00-10:30", etkinlik="Drama"), ScheduleItem(saat="10:30-11:00", etkinlik="Beden Egitimi")]),
            DailySchedule(gun="Cuma", dersler=[ScheduleItem(saat="09:00-09:30", etkinlik="Matematik / Fen"), ScheduleItem(saat="09:30-10:00", etkinlik="Okuma Etkinligi"), ScheduleItem(saat="10:00-10:30", etkinlik="Film / Animasyon"), ScheduleItem(saat="10:30-11:00", etkinlik="Hafta Sonu Hazirligi")]),
        ]
        return {
            "parents": [DEFAULT_PARENT],
            "students": [DEFAULT_STUDENT],
            "meals": [item.model_dump(mode="json") for item in meals],
            "reports": [item.model_dump(mode="json") for item in reports],
            "finance": default_finance,
            "finance_records": {DEFAULT_STUDENT["ogrenci_id"]: default_finance},
            "schedules": [item.model_dump(mode="json") for item in schedules],
            "daily_flow": [{"time": "08:30", "activity": "Karsilama ve serbest oyun"}, {"time": "09:00", "activity": "Kahvalti"}, {"time": "10:00", "activity": "Ders ve atolyeler"}, {"time": "12:00", "activity": "Ogle yemegi"}, {"time": "13:00", "activity": "Dinlenme ve uyku"}, {"time": "15:00", "activity": "Ikindi ve gun sonu toparlanma"}],
            "announcements": [{"id": "sample-announcement-1", "title": "Mart Ayi Bulteni", "content": "Mart ayi etkinlik bulteni yayinda. Bahar etkinlikleri ve gezi takvimi guncellendi.", "date": today.isoformat(), "priority": "yuksek", "pdf_filename": None, "pdf_url": None}],
            "analytics": {"labels": ["Yemek", "Odeme", "Gun sonu", "Duyuru", "Program"], "values": [42, 31, 26, 19, 14]},
        }


_database: LocalJSONDatabase | None = None


def get_database() -> LocalJSONDatabase:
    global _database
    if _database is None:
        _database = LocalJSONDatabase()
    return _database


class MockDatabaseTool(BaseTool):
    @property
    def name(self) -> str:
        return ToolName.MOCK_DATABASE.value

    @property
    def description(self) -> str:
        return "Yerel JSON veritabanindan yemek, rapor, odeme, program ve duyuru verilerini getirir."

    async def run(self, query: str, **kwargs: Any) -> dict[str, Any]:
        db = get_database()
        intent = kwargs.get("intent", "")
        parent_id = kwargs.get("parent_id")
        q = query.lower()

        if intent == "meal_query" or any(token in q for token in ["yemek", "menu", "kahvalti", "ogle"]):
            menu = db.get_menu_for_date()
            return {"type": "meal_menu", "data": menu.model_dump(mode="json"), "message": f"Tarih: {menu.tarih}\nKahvalti: {', '.join(menu.kahvalti)}\nOgle: {', '.join(menu.ogle)}\nIkindi: {', '.join(menu.ikindi)}\nAra Ogun: {', '.join(menu.ara_ogun)}"}

        if intent == "report_query" or any(token in q for token in ["rapor", "gun sonu", "uyku", "duygu"]):
            report = db.get_report_for_date(parent_id=parent_id)
            return {"type": "daily_report", "data": report.model_dump(mode="json"), "message": f"Gun Sonu Raporu - {report.ogrenci_adi} ({report.tarih})\nUyku: {report.uyku}\nDuygu Durumu: {report.duygu_durumu}\nGenel Uyum: {report.genel_uyum}"}

        if intent == "finance_query" or any(token in q for token in ["odeme", "borc", "tutar", "aidat"]):
            summary = db.get_finance_summary(parent_id=parent_id)
            return {"type": "payment_summary", "data": summary.model_dump(mode="json"), "message": f"Odeme Ozeti - {summary.ogrenci_adi} ({summary.donem})\nToplam Tutar: {summary.toplam_tutar:,.2f} TL\nOdenen: {summary.odenen:,.2f} TL\nKalan Borc: {summary.kalan:,.2f} TL"}

        if intent == "schedule_query" or any(token in q for token in ["ders", "program", "etkinlik"]):
            schedule = db.get_schedule_for_date()
            return {"type": "daily_schedule", "data": schedule.model_dump(mode="json"), "message": "\n".join([f"Ders Programi - {schedule.gun}", *[f"  {item.saat}: {item.etkinlik}" for item in schedule.dersler]])}

        announcements = db.get_announcements()
        return {"type": "announcements", "data": {"announcements": announcements}, "message": "\n\n".join([f"{item['title']} ({item['date']}): {item['content']}" for item in announcements[:3]])}


