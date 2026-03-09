from __future__ import annotations

import logging
from typing import Any

from app.core.constants import IntentType
from app.services.ai_service import AIService, QuotaExceededError
from app.services.base_service import BaseTool, InMemoryStorage
from app.services.langchain_tools import create_all_tools
from app.services.mock_database import get_database
from app.services.stats_service import get_stats_service

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self) -> None:
        self._ai = AIService()
        self._memory = InMemoryStorage()
        self._stats = get_stats_service()
        self._db = get_database()
        self._tools: dict[str, BaseTool] = {}

        for tool in create_all_tools():
            self._tools[tool.name] = tool
            logger.info("Tool kaydedildi: %s", tool.name)

        self._intent_tool_map: dict[str, str] = {
            IntentType.MEAL_QUERY.value: "meal_query",
            IntentType.REPORT_QUERY.value: "report_query",
            IntentType.FINANCE_QUERY.value: "payment_query",
            IntentType.SCHEDULE_QUERY.value: "schedule_query",
            IntentType.BULLETIN_QUERY.value: "pdf_analysis",
            IntentType.VISION_QUERY.value: "vision_analysis",
            IntentType.CONTACT_QUERY.value: "contact_query",
            IntentType.ANNOUNCEMENT_QUERY.value: "announcement_query",
        }
        self._protected_intents = {IntentType.REPORT_QUERY.value, IntentType.FINANCE_QUERY.value}

        logger.info("ChatService v3 (fail-safe) - %d tool", len(self._tools))

    async def process_message(
        self,
        session_id: str,
        message: str,
        attachments: list[dict] | None = None,
        parent_phone: str | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        history = await self._memory.get_history(session_id)
        await self._memory.add_message(session_id, "user", message)

        intent = await self._resolve_intent(message)
        self._stats.record_intent(intent)
        parent_profile = self._db.authenticate_parent(parent_phone, password)
        logger.info(
            "Session %s | Intent: %s | Parent: %s | Mesaj: %.60s",
            session_id,
            intent,
            parent_profile["parent_id"] if parent_profile else "anonymous",
            message,
        )

        if intent in self._protected_intents and not parent_profile:
            response_text = self._db.get_auth_failure_reason(parent_phone)
            self._stats.record_failed_response(
                intent=intent,
                user_message=message,
                response_text=response_text,
                reason="parent_auth_required",
            )
            await self._memory.add_message(session_id, "assistant", response_text)
            return {
                "response": response_text,
                "intent": intent,
                "tool_used": None,
                "source": None,
                "page": None,
                "metadata": {
                    "session_id": session_id,
                    "history_length": len(history) + 2,
                    "has_tool_data": False,
                    "used_fallback": False,
                    "fallback_reason": None,
                    "parent_authenticated": False,
                },
            }

        tool_result: dict[str, Any] | None = None
        tool_name: str | None = None
        target_tool_name = self._intent_tool_map.get(intent)
        if target_tool_name and target_tool_name in self._tools:
            tool = self._tools[target_tool_name]
            tool_name = tool.name
            try:
                extra: dict[str, Any] = {"intent": intent, "session_id": session_id}
                if parent_profile:
                    extra["parent_id"] = parent_profile["parent_id"]
                    extra["student_name"] = parent_profile["student_name"]
                if attachments:
                    for att in attachments:
                        if att.get("type") == "pdf":
                            extra["file_url"] = att.get("url")
                        elif att.get("type") == "image":
                            extra["image_url"] = att.get("url")
                        elif att.get("type") == "url":
                            extra["url"] = att.get("url")
                tool_result = await tool.run(message, **extra)
                logger.info("Tool '%s' OK, tip: %s", tool_name, tool_result.get("type"))
            except Exception as exc:
                logger.error("Tool '%s' hatasi: %s", tool_name, exc)
                tool_result = {"type": "error", "message": f"Arac hatasi: {exc}"}

        from app.services.rag_store import get_combined_session_text

        rag_context = get_combined_session_text(session_id)
        enriched_result = tool_result or {}
        if not enriched_result and rag_context:
            enriched_result = {
                "type": "rag_context",
                "status": "ok",
                "message": f"Kullanicinin yukledigi belgeler asagidadir:\n{rag_context}",
            }

        response_text: str
        used_fallback = False
        fallback_reason: str | None = None

        try:
            response_text = await self._ai.generate_with_context(
                user_message=message,
                history=history,
                tool_result=enriched_result if enriched_result else None,
            )
        except QuotaExceededError as exc:
            used_fallback = True
            fallback_reason = exc.reason
            if tool_result and tool_result.get("message"):
                response_text = tool_result["message"]
                logger.warning("FAIL-SAFE aktif | reason=%s | tool verisi donuluyor", fallback_reason)
            else:
                response_text = "Su anda yapay zeka servisi yogun. Lutfen biraz sonra tekrar deneyin."
                logger.warning("FAIL-SAFE aktif | reason=%s | genel bekleme mesaji donuluyor", fallback_reason)

        if self._looks_like_failed_response(intent=intent, response_text=response_text, tool_used=tool_name):
            self._stats.record_failed_response(
                intent=intent,
                user_message=message,
                response_text=response_text,
                reason=fallback_reason or "low_confidence_or_out_of_scope",
            )

        await self._memory.add_message(session_id, "assistant", response_text)

        metadata = {
            "session_id": session_id,
            "history_length": len(history) + 2,
            "has_tool_data": tool_result is not None,
            "used_fallback": used_fallback,
            "fallback_reason": fallback_reason,
            "parent_authenticated": parent_profile is not None,
        }
        if parent_profile:
            metadata["parent_name"] = parent_profile["parent_name"]
            metadata["student_name"] = parent_profile["student_name"]
        if tool_result and tool_result.get("source"):
            metadata["source"] = tool_result.get("source")
        if tool_result and tool_result.get("page"):
            metadata["page"] = tool_result.get("page")

        return {
            "response": response_text,
            "intent": intent,
            "tool_used": tool_name,
            "source": tool_result.get("source") if tool_result else None,
            "page": tool_result.get("page") if tool_result else None,
            "metadata": metadata,
        }

    async def _resolve_intent(self, message: str) -> str:
        heuristic_intent = self._infer_intent_from_keywords(message)
        if heuristic_intent is not None:
            return heuristic_intent
        return await self._ai.classify_intent(message)

    @staticmethod
    def _infer_intent_from_keywords(message: str) -> str | None:
        normalized = message.casefold()
        if any(token in normalized for token in ["borcum", "borc", "ödeme", "odeme", "aidat", "kalan tutar"]):
            return IntentType.FINANCE_QUERY.value
        if any(token in normalized for token in ["çocuğum nasıl", "cocugum nasil", "gün sonu", "gun sonu", "rapor", "uyku durumu"]):
            return IntentType.REPORT_QUERY.value
        if any(token in normalized for token in ["yemek", "menü", "menu", "kahvaltı", "kahvalti"]):
            return IntentType.MEAL_QUERY.value
        if any(token in normalized for token in ["ders program", "etkinlik", "akış", "akis"]):
            return IntentType.SCHEDULE_QUERY.value
        return None

    @staticmethod
    def _looks_like_failed_response(intent: str, response_text: str, tool_used: str | None) -> bool:
        normalized = response_text.lower()
        markers = [
            "bilgi alanim disindadir",
            "bilmiyorum",
            "yanit uretemiyorum",
            "yapay zeka servisi yogun",
            "test yaniti",
            "uzgunum",
        ]
        return intent == IntentType.GENERAL.value or tool_used is None or any(marker in normalized for marker in markers)

    async def get_history(self, session_id: str) -> list[dict]:
        return await self._memory.get_history(session_id)

    async def clear_session(self, session_id: str) -> None:
        await self._memory.clear_session(session_id)

    def get_tools(self) -> list[dict[str, str]]:
        return [tool.get_info() for tool in self._tools.values()]

    @property
    def active_sessions(self) -> int:
        return self._memory.active_session_count
