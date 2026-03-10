from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, HttpUrl

from app.core.config import settings
from app.core.security import verify_api_key
from app.schemas.chat import ChatRequest, ChatResponse, ErrorResponse, HealthResponse, HistoryResponse, MessageItem
from app.services.chat_service import ChatService
from app.services.mock_database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])

_chat_service: ChatService | None = None


class ParentAuthRequest(BaseModel):
    phone: str
    session_id: str | None = None


class ParentAuthResponse(BaseModel):
    parent_id: str
    parent_name: str
    phone: str
    student_id: str
    student_name: str
    student_ids: list[str] = []
    student_names: list[str] = []
    children_count: int = 1
    greeting: str


class ClientConfigResponse(BaseModel):
    api_key: str
    app_name: str


def get_chat_service() -> ChatService:
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service


def init_chat_service() -> None:
    global _chat_service
    _chat_service = ChatService()
    logger.info("ChatService baslatildi (lifespan)")


@router.get("/client-config", response_model=ClientConfigResponse, summary="Istemci config bilgisi")
async def client_config() -> ClientConfigResponse:
    return ClientConfigResponse(api_key=settings.API_KEY or "", app_name=settings.APP_NAME)


@router.post(
    "",
    response_model=ChatResponse,
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Mesaj gonder",
    description="Kullanici mesajini isle ve yanit dondur.",
)
async def chat(
    request: ChatRequest,
    http_request: Request,
    _api_key: str | None = Depends(verify_api_key),
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    try:
        attachments = [att.model_dump() for att in request.attachments] if request.attachments else None
        result = await service.process_message(
            session_id=request.session_id,
            message=request.message,
            attachments=attachments,
            parent_phone=request.parent_phone,
            password=request.password,
            active_student_id=request.active_student_id,
        )
        http_request.state.intent = result.get("intent")
        return ChatResponse(
            session_id=request.session_id,
            response=result["response"],
            intent=result.get("intent"),
            tool_used=result.get("tool_used"),
            source=result.get("source"),
            page=result.get("page"),
            metadata=result.get("metadata", {}),
        )
    except Exception as exc:
        logger.exception("Chat isleme hatasi")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Mesaj islenirken hata olustu: {exc}")


@router.post("/parent-auth", response_model=ParentAuthResponse, summary="Veli girisini dogrula")
async def parent_auth(
    request: ParentAuthRequest,
    _api_key: str | None = Depends(verify_api_key),
    service: ChatService = Depends(get_chat_service),
) -> ParentAuthResponse:
    database = get_database()
    profile = database.authenticate_parent(request.phone)
    if not profile:
        reason = database.get_auth_failure_reason(request.phone)
        status_code = status.HTTP_404_NOT_FOUND if "kayitli veli bulunamadi" in reason.lower() else status.HTTP_401_UNAUTHORIZED
        raise HTTPException(status_code=status_code, detail=reason)
    if request.session_id:
        service.set_active_student(request.session_id, profile["student_id"])
    return ParentAuthResponse(**profile)


@router.get("/history/{session_id}", response_model=HistoryResponse, summary="Sohbet gecmisini getir")
async def get_history(session_id: str, _api_key: str | None = Depends(verify_api_key), service: ChatService = Depends(get_chat_service)) -> HistoryResponse:
    history = await service.get_history(session_id)
    messages = [
        MessageItem(role=msg["role"], content=msg["content"], timestamp=datetime.fromisoformat(msg.get("timestamp", datetime.utcnow().isoformat())))
        for msg in history
    ]
    return HistoryResponse(session_id=session_id, messages=messages, total_messages=len(messages))


@router.delete("/history/{session_id}", summary="Oturumu temizle", status_code=status.HTTP_204_NO_CONTENT)
async def clear_history(session_id: str, _api_key: str | None = Depends(verify_api_key), service: ChatService = Depends(get_chat_service)) -> None:
    await service.clear_session(session_id)


@router.get("/tools", summary="Kayitli araclari listele")
async def list_tools(service: ChatService = Depends(get_chat_service)) -> list[dict[str, str]]:
    return service.get_tools()


@router.post("/upload-pdf", summary="PDF dosyasi yukle", description="PDF dosyasini yukler, metnini cikarir ve oturum deposuna kaydeder.")
async def upload_pdf(file: UploadFile = File(..., description="Yuklenecek PDF dosyasi"), session_id: str = Form(..., description="Oturum ID'si"), _api_key: str | None = Depends(verify_api_key)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sadece PDF dosyalari kabul edilir.")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="PDF dosyasi 10MB'dan buyuk olamaz.")

    tmp_dir = os.path.join(tempfile.gettempdir(), "ekres_pdfs")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, file.filename)
    with open(tmp_path, "wb") as file_handle:
        file_handle.write(contents)

    logger.info("PDF yuklendi: %s (%d bytes) -> %s", file.filename, len(contents), tmp_path)

    from app.services.pdf_service import extract_text_from_pdf
    from app.services.rag_store import store_rag_context

    text, pages = extract_text_from_pdf(tmp_path)
    if not text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="PDF dosyasindan metin cikarilamadi.")

    store_rag_context(session_id, "pdf", file.filename, text, pages)
    return {
        "status": "ok",
        "filename": file.filename,
        "pages": pages,
        "characters": len(text),
        "message": f"{file.filename} basariyla yuklendi ({pages} sayfa). Artik bu PDF hakkinda sorular sorabilirsiniz.",
    }


class UrlRequest(BaseModel):
    url: HttpUrl
    session_id: str


@router.post("/upload-url", summary="Web URL Tara", description="URL'deki icerigi tarar ve oturum deposuna kaydeder.")
async def upload_url(request: UrlRequest, _api_key: str | None = Depends(verify_api_key)) -> dict:
    url_str = str(request.url)
    from app.services.web_scanner_service import extract_text_from_url
    from app.services.rag_store import store_rag_context

    text, word_count = extract_text_from_url(url_str)
    if not text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="URL okunamadi veya icerik cikarilamadi.")

    store_rag_context(request.session_id, "web", url_str, text, word_count)
    return {
        "status": "ok",
        "url": url_str,
        "words": word_count,
        "characters": len(text),
        "message": f"Bu web sayfasini analiz ettim ({word_count} kelime). Artik icerigi hakkinda sorular sorabilirsin.",
    }


@router.get("/announcements", summary="Yayindaki duyurulari getir")
async def public_announcements() -> dict[str, list[dict]]:
    announcements = get_database().get_announcements()
    return {"announcements": announcements}


health_router = APIRouter(tags=["Health"])


@health_router.get("/health", response_model=HealthResponse, summary="Saglik kontrolu")
async def health_check() -> HealthResponse:
    return HealthResponse(status="healthy", version=settings.APP_VERSION)
