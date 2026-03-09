from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.core.constants import IntentType, SYSTEM_PROMPT
from app.services.stats_service import get_stats_service

logger = logging.getLogger(__name__)


class QuotaExceededError(Exception):
    """Gemini API kota asimi hatasi; fallback sebebi tasir."""

    def __init__(self, message: str, reason: str = "quota_exceeded") -> None:
        super().__init__(message)
        self.reason = reason


class AIService:
    def __init__(self) -> None:
        self._model = None
        self._is_mock = False
        self._stats = get_stats_service()
        self._initialize()

    def _initialize(self) -> None:
        api_key = settings.GOOGLE_API_KEY
        if not api_key:
            logger.warning("GOOGLE_API_KEY bulunamadi - mock modda calisiliyor.")
            self._is_mock = True
            self._stats.record_fallback(reason="mock_mode_no_api_key", operation="initialize")
            return

        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            self._model = genai.GenerativeModel(
                model_name=settings.LLM_MODEL_NAME,
                generation_config={
                    "temperature": settings.LLM_TEMPERATURE,
                    "max_output_tokens": settings.LLM_MAX_TOKENS,
                },
                system_instruction=SYSTEM_PROMPT,
            )
            logger.info("Gemini baslatildi: %s", settings.LLM_MODEL_NAME)
        except Exception as exc:
            logger.error("Gemini baslatilamadi: %s - mock moda geciliyor", exc)
            self._stats.record_ai_error(error_type="initialization_error", detail=str(exc))
            self._stats.record_fallback(reason="model_initialization_failed", operation="initialize")
            self._is_mock = True

    @staticmethod
    def _is_quota_error(exc: Exception) -> bool:
        err_str = str(exc).lower()
        return any(kw in err_str for kw in ["429", "quota", "resource exhausted", "rate limit", "resourceexhausted"])

    @staticmethod
    def _classify_error_type(exc: Exception) -> str:
        err_str = str(exc).lower()
        if any(token in err_str for token in ["resourceexhausted", "resource exhausted", "quota", "429"]):
            return "ResourceExhausted"
        if any(token in err_str for token in ["deadlineexceeded", "deadline exceeded", "timeout"]):
            return "DeadlineExceeded"
        if any(token in err_str for token in ["unavailable", "connection", "network"]):
            return "Unavailable"
        return exc.__class__.__name__

    def _record_usage(self, operation: str, response: Any) -> None:
        usage = getattr(response, "usage_metadata", None)
        input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
        self._stats.record_ai_usage(
            operation=operation,
            model=settings.LLM_MODEL_NAME,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        logger.info(
            "Gemini token kullanimi | operation=%s | model=%s | input_tokens=%d | output_tokens=%d",
            operation,
            settings.LLM_MODEL_NAME,
            input_tokens,
            output_tokens,
        )

    async def generate(self, prompt: str) -> str:
        if self._is_mock:
            self._stats.record_fallback(reason="mock_generate", operation="generate")
            return self._mock_response(prompt)

        try:
            response = await self._model.generate_content_async(prompt)
            self._record_usage("generate", response)
            return response.text
        except Exception as exc:
            error_type = self._classify_error_type(exc)
            self._stats.record_ai_error(error_type=error_type, detail=str(exc))
            if self._is_quota_error(exc):
                logger.warning("Gemini fallback | operation=generate | reason=quota_exceeded | detail=%s", exc)
                self._stats.record_fallback(reason="quota_exceeded", operation="generate")
                raise QuotaExceededError(str(exc), reason="quota_exceeded")
            logger.error("LLM generate hatasi | type=%s | detail=%s", error_type, exc)
            self._stats.record_fallback(reason="model_error", operation="generate")
            return f"Yanit uretilemedi: {exc}"

    async def classify_intent(self, message: str) -> str:
        pre_result = self._keyword_precheck(message)
        if pre_result:
            logger.info("Keyword pre-check intent: %s", pre_result)
            self._stats.record_fallback(reason="keyword_precheck", operation="classify_intent")
            return pre_result

        if self._is_mock:
            self._stats.record_fallback(reason="mock_classify", operation="classify_intent")
            return self._mock_classify(message)

        intent_names = [i.value for i in IntentType]
        classification_prompt = (
            f"Asagidaki kullanici mesajinin niyetini siniflandir.\n"
            f"Sadece su kategorilerden birini dondur: {intent_names}\n"
            f"Baska hicbir sey yazma, sadece kategori adini yaz.\n\n"
            f"Mesaj: \"{message}\""
        )

        try:
            response = await self._model.generate_content_async(classification_prompt)
            self._record_usage("classify_intent", response)
            intent = response.text.strip().lower().replace('"', "").replace("'", "")
            valid = {i.value for i in IntentType}
            if intent in valid:
                return intent
            logger.warning("Bilinmeyen intent '%s', keyword fallback", intent)
            self._stats.record_fallback(reason="invalid_intent_label", operation="classify_intent")
            return self._mock_classify(message)
        except Exception as exc:
            error_type = self._classify_error_type(exc)
            self._stats.record_ai_error(error_type=error_type, detail=str(exc))
            if self._is_quota_error(exc):
                logger.warning("Intent fallback | reason=quota_exceeded | detail=%s", exc)
                self._stats.record_fallback(reason="quota_exceeded", operation="classify_intent")
            else:
                logger.error("Intent siniflandirma hatasi | type=%s | detail=%s", error_type, exc)
                self._stats.record_fallback(reason="model_error", operation="classify_intent")
            return self._mock_classify(message)

    async def generate_with_context(self, user_message: str, history: list[dict], tool_result: dict[str, Any] | None = None) -> str:
        if self._is_mock:
            reason = "mock_mode_with_tool" if tool_result else "mock_mode_no_tool"
            self._stats.record_fallback(reason=reason, operation="generate_with_context")
            if tool_result:
                return tool_result.get("message", "Veri bulundu.")
            return self._mock_response(user_message)

        parts: list[str] = []
        recent = history[-10:] if len(history) > 10 else history
        for msg in recent:
            role_label = "Veli" if msg["role"] == "user" else "Asistan"
            parts.append(f"{role_label}: {msg['content']}")

        if tool_result:
            parts.append(f"\n[Sistem Verisi]\n{tool_result.get('message', str(tool_result))}\n")

        parts.append(f"Veli: {user_message}")
        parts.append("Asistan:")
        full_prompt = "\n".join(parts)

        try:
            response = await self._model.generate_content_async(full_prompt)
            self._record_usage("generate_with_context", response)
            return response.text
        except Exception as exc:
            error_type = self._classify_error_type(exc)
            self._stats.record_ai_error(error_type=error_type, detail=str(exc))
            if self._is_quota_error(exc):
                logger.warning("Yanit fallback | reason=quota_exceeded | detail=%s", exc)
                self._stats.record_fallback(reason="quota_exceeded", operation="generate_with_context")
                raise QuotaExceededError(str(exc), reason="quota_exceeded")

            logger.error("LLM context generate hatasi | type=%s | detail=%s", error_type, exc)
            if tool_result:
                logger.warning("Yanit fallback | reason=model_error_tool_fallback | detail=%s", exc)
                self._stats.record_fallback(reason="model_error_tool_fallback", operation="generate_with_context")
                return tool_result.get("message", "Veri bulundu ancak yanitlanamadi.")

            logger.warning("Yanit fallback | reason=model_error_no_tool | detail=%s", exc)
            self._stats.record_fallback(reason="model_error_no_tool", operation="generate_with_context")
            return "Uzgunum, su anda yanit uretemiyorum."

    @staticmethod
    def _keyword_precheck(message: str) -> str | None:
        msg = message.lower()
        if any(k in msg for k in ["iletisim", "telefon", "numara", "arayin"]):
            return IntentType.CONTACT_QUERY.value
        if any(k in msg for k in ["duyuru", "bilgilendirme"]):
            return IntentType.ANNOUNCEMENT_QUERY.value
        return None

    @staticmethod
    def _mock_response(prompt: str) -> str:
        return "Bu bir test yaniti. Gemini API baglantisi aktif degil. Mesajiniz alindi: '%s...'" % prompt[:80]

    @staticmethod
    def _mock_classify(message: str) -> str:
        msg = message.lower()
        if any(k in msg for k in ["yemek", "menu", "kahvalti", "ogle", "ikindi", "ara ogun"]):
            return IntentType.MEAL_QUERY.value
        if any(k in msg for k in ["rapor", "gun sonu", "uyku", "duygu", "uyum", "katilim"]):
            return IntentType.REPORT_QUERY.value
        if any(k in msg for k in ["odeme", "borc", "fatura", "aidat", "tutar", "kalan"]):
            return IntentType.FINANCE_QUERY.value
        if any(k in msg for k in ["ders", "program", "etkinlik", "takvim"]):
            return IntentType.SCHEDULE_QUERY.value
        if any(k in msg for k in ["iletisim", "telefon", "eposta", "adres", "numara", "arayin"]):
            return IntentType.CONTACT_QUERY.value
        if any(k in msg for k in ["duyuru", "haber", "bilgilendirme", "etkinlik duyuru"]):
            return IntentType.ANNOUNCEMENT_QUERY.value
        if any(k in msg for k in ["bulten", "pdf"]):
            return IntentType.BULLETIN_QUERY.value
        if any(k in msg for k in ["foto", "resim", "gorsel", "video"]):
            return IntentType.VISION_QUERY.value
        return IntentType.GENERAL.value
