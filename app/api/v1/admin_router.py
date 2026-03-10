from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.core.security import verify_admin_key
from app.schemas.chat import DailyMenu, DailySchedule, PaymentSummary
from app.services.file_service import FileService
from app.services.mock_database import UPLOAD_DIR, get_database
from app.services.pdf_service import extract_text_from_pdf
from app.services.rag_store import store_global_rag_context
from app.services.stats_service import get_stats_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])
file_service = FileService()


class MealUpdateRequest(BaseModel):
    meals: list[DailyMenu]


class ScheduleFlowItem(BaseModel):
    time: str = Field(..., min_length=1)
    activity: str = Field(..., min_length=1)


class ScheduleUpdateRequest(BaseModel):
    schedules: list[DailySchedule]
    daily_flow: list[ScheduleFlowItem]


class FinanceUpdateRequest(BaseModel):
    student_id: str
    finance: PaymentSummary


class ParentPayload(BaseModel):
    veli_id: str | None = None
    ad_soyad: str
    telefon: str


class StudentPayload(BaseModel):
    ogrenci_id: str | None = None
    ad_soyad: str


class FamilyUpsertRequest(BaseModel):
    parent: ParentPayload
    student: StudentPayload


class FamilyDeleteRequest(BaseModel):
    parent_id: str
    student_id: str


@router.get("/dashboard-data", summary="Admin paneli icin tum verileri getir")
async def dashboard_data(_admin_key: str = Depends(verify_admin_key)) -> dict[str, Any]:
    return get_database().get_dashboard_data()


@router.get("/stats", summary="Observability istatistiklerini getir")
async def stats_data(_admin_key: str = Depends(verify_admin_key)) -> dict[str, Any]:
    return get_stats_service().get_summary()


@router.post("/family-upsert", summary="Veli ve ogrenci kaydini ekle veya guncelle")
async def family_upsert(request: FamilyUpsertRequest, _admin_key: str = Depends(verify_admin_key)) -> dict[str, Any]:
    result = get_database().upsert_family(request.parent.model_dump(), request.student.model_dump())
    return {"status": "ok", **result, "dashboard": get_database().get_dashboard_data()}


@router.delete("/family", summary="Veli ve ogrenci kaydini sil")
async def family_delete(request: FamilyDeleteRequest, _admin_key: str = Depends(verify_admin_key)) -> dict[str, Any]:
    result = get_database().delete_family(request.parent_id, request.student_id)
    return {"status": "ok", **result, "dashboard": get_database().get_dashboard_data()}


@router.post("/meal-update", summary="Yemek listesini guncelle")
async def meal_update(request: MealUpdateRequest, _admin_key: str = Depends(verify_admin_key)) -> dict[str, Any]:
    result = get_database().update_meals([meal.model_dump(mode="json") for meal in request.meals])
    store_global_rag_context("admin_file", "meals_manual_update", str(result["meals"]), result["updated"])
    return {"status": "ok", "updated": result["updated"], "meals": result["meals"]}


@router.post("/finance-update", summary="Borc ve odeme bilgilerini ogrenci bazli guncelle")
async def finance_update(request: FinanceUpdateRequest, _admin_key: str = Depends(verify_admin_key)) -> dict[str, Any]:
    finance = get_database().update_finance(request.finance.model_dump(mode="json"), student_id=request.student_id)
    store_global_rag_context("admin_file", f"finance_{request.student_id}", str(finance), len(finance.get("odemeler", [])))
    return {"status": "ok", "finance": finance, "dashboard": get_database().get_dashboard_data()}


@router.delete("/finance/{student_id}", summary="Ogrenciye ait finans kaydini sil")
async def finance_delete(student_id: str, _admin_key: str = Depends(verify_admin_key)) -> dict[str, Any]:
    result = get_database().delete_finance(student_id)
    store_global_rag_context("admin_file", f"finance_{student_id}", "{}", 0)
    return {"status": "ok", **result, "dashboard": get_database().get_dashboard_data()}


@router.post("/schedule-update", summary="Gunluk akis ve ders programini guncelle")
async def schedule_update(request: ScheduleUpdateRequest, _admin_key: str = Depends(verify_admin_key)) -> dict[str, Any]:
    result = get_database().update_schedules(
        [schedule.model_dump(mode="json") for schedule in request.schedules],
        [item.model_dump() for item in request.daily_flow],
    )
    store_global_rag_context("admin_file", "schedule_manual_update", str(result), len(result["schedules"]))
    return {"status": "ok", **result}


@router.post("/import-structured-data", summary="Excel, CSV veya PDF ile veri iceri aktar")
async def import_structured_data(
    section: Literal["meals", "schedule"] = Form(...),
    file: UploadFile = File(...),
    _admin_key: str = Depends(verify_admin_key),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dosya adi bulunamadi.")
    suffix = file.filename.lower().rsplit(".", 1)[-1]
    if suffix not in {"pdf", "csv", "xlsx", "xlsm", "xltx", "xltm"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sadece PDF, CSV veya Excel dosyalari kabul edilir.")

    content = await file.read()
    filepath = file_service.save_upload(file.filename, content)
    parsed = file_service.parse_admin_data_file(filepath, section)

    if section == "meals":
        result = get_database().update_meals(parsed["meals"])
    else:
        result = get_database().update_schedules(parsed.get("schedules", []), parsed.get("daily_flow", []))

    store_global_rag_context("admin_file", filepath.name, parsed["text"], parsed.get("metric", 0))
    return {"status": "ok", "section": section, "filename": filepath.name, "dashboard": get_database().get_dashboard_data(), "result": result}


@router.post("/upload-announcement", summary="Yeni duyuru ve PDF bulten yukle")
async def upload_announcement(
    title: str = Form(...),
    content: str = Form(...),
    priority: str = Form("normal"),
    pdf_file: UploadFile | None = File(default=None),
    _admin_key: str = Depends(verify_admin_key),
) -> dict[str, Any]:
    pdf_filename = None
    pdf_url = None

    if pdf_file:
        if not pdf_file.filename or not pdf_file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sadece PDF dosyalari kabul edilir.")
        contents = await pdf_file.read()
        if len(contents) > 10 * 1024 * 1024:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="PDF dosyasi 10MB'dan buyuk olamaz.")
        pdf_filename, pdf_url = get_database().save_uploaded_pdf(pdf_file.filename, contents)
        text, pages = extract_text_from_pdf(str(UPLOAD_DIR / pdf_filename))
        if text:
            store_global_rag_context("pdf", pdf_filename, text, pages)

    announcement = get_database().add_announcement(
        title=title,
        content=content,
        pdf_filename=pdf_filename,
        pdf_url=pdf_url,
        priority=priority,
    )
    store_global_rag_context("admin_file", f"announcement_{announcement['id']}", f"{title}\n{content}\n{pdf_url or ''}", 1)
    return {"status": "ok", "announcement": announcement}

