from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class DailyMenu(BaseModel):
    tarih: date = Field(..., description="Menu tarihi")
    kahvalti: list[str] = Field(..., description="Kahvalti yemekleri")
    ogle: list[str] = Field(..., description="Ogle yemegi listesi")
    ikindi: list[str] = Field(..., description="Ikindi ogunu")
    ara_ogun: list[str] = Field(..., description="Ara ogun")
    aciklama: str | None = Field(default=None, description="Ek aciklama")


class DailyReport(BaseModel):
    tarih: date
    ogrenci_adi: str
    kahvalti: str
    kahvalti_aciklama: str | None = None
    ogle_yemegi: str
    ikindi: str
    ikindi_aciklama: str | None = None
    uyku: str
    duygu_durumu: str
    etkinliklere_katilim: str
    arkadaslari_ile_iletisim: str
    genel_uyum: str


class PaymentItem(BaseModel):
    tarih: date
    tutar: float
    tur: str
    durum: str
    odeme_bilgisi: str | None = None


class PaymentSummary(BaseModel):
    donem: str
    ogrenci_adi: str
    toplam_adet: int
    odendi_adet: int
    odenmedi_adet: int
    kismi_adet: int = 0
    toplam_tutar: float
    odenen: float
    kalan: float
    odemeler: list[PaymentItem] = Field(default_factory=list)


class ScheduleItem(BaseModel):
    saat: str
    etkinlik: str


class DailySchedule(BaseModel):
    gun: str
    dersler: list[ScheduleItem]


class Attachment(BaseModel):
    type: Literal["image", "pdf"]
    url: str
    filename: str | None = None


class MessageItem(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    message: str = Field(..., min_length=1, max_length=4096)
    attachments: list[Attachment] | None = None
    parent_phone: str | None = Field(default=None, max_length=32)
    password: str | None = Field(default=None, max_length=128)
    active_student_id: str | None = Field(default=None, max_length=128)


class ChatResponse(BaseModel):
    session_id: str
    response: str
    intent: str | None = None
    tool_used: str | None = None
    source: str | None = None
    page: int | None = None
    metadata: dict = Field(default_factory=dict)


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[MessageItem] = Field(default_factory=list)
    total_messages: int = 0


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    status_code: int
