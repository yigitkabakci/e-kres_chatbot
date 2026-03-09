from __future__ import annotations

import json
import logging
import time
from typing import Any, Awaitable, Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.services.stats_service import get_stats_service

logger = logging.getLogger("ekres.access")


class LoggingMiddleware:
    """ASGI tabanli, request body'yi bozmadan loglayan middleware."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        body_chunks: list[bytes] = []
        status_code = 500

        async def wrapped_receive() -> Message:
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                if body:
                    body_chunks.append(body)
            return message

        async def wrapped_send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, wrapped_receive, wrapped_send)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            body_preview = self._format_body(b"".join(body_chunks))
            intent = self._extract_intent(scope)
            endpoint_name = self._endpoint_name(scope)
            logger.exception(
                "%s %s | endpoint=%s | intent=%s | status=500 | %.1fms | client=%s | body=%s",
                scope.get("method"),
                scope.get("path"),
                endpoint_name,
                intent,
                duration_ms,
                client_ip,
                body_preview,
            )
            stats = get_stats_service()
            stats.record_request(
                method=str(scope.get("method", "GET")),
                path=str(scope.get("path", "")),
                endpoint=endpoint_name,
                status_code=500,
                latency_ms=duration_ms,
                intent=intent,
            )
            stats.record_http_error(
                method=str(scope.get("method", "GET")),
                path=str(scope.get("path", "")),
                status_code=500,
                body_preview=body_preview,
                intent=intent,
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        body_preview = self._format_body(b"".join(body_chunks))
        intent = self._extract_intent(scope)
        endpoint_name = self._endpoint_name(scope)
        log_method = logger.warning if status_code >= 400 else logger.info
        log_method(
            "%s %s | endpoint=%s | intent=%s | status=%d | latency=%.1fms | client=%s",
            scope.get("method"),
            scope.get("path"),
            endpoint_name,
            intent,
            status_code,
            duration_ms,
            client_ip,
        )

        stats = get_stats_service()
        stats.record_request(
            method=str(scope.get("method", "GET")),
            path=str(scope.get("path", "")),
            endpoint=endpoint_name,
            status_code=status_code,
            latency_ms=duration_ms,
            intent=intent,
        )
        if status_code >= 400:
            logger.warning(
                "HTTP hata govdesi | %s %s | status=%d | body=%s",
                scope.get("method"),
                scope.get("path"),
                status_code,
                body_preview,
            )
            stats.record_http_error(
                method=str(scope.get("method", "GET")),
                path=str(scope.get("path", "")),
                status_code=status_code,
                body_preview=body_preview,
                intent=intent,
            )

    @staticmethod
    def _endpoint_name(scope: Scope) -> str:
        endpoint = scope.get("endpoint")
        if endpoint is not None:
            return getattr(endpoint, "__name__", str(scope.get("path", "")))
        route = scope.get("route")
        return getattr(route, "path", str(scope.get("path", "")))

    @staticmethod
    def _extract_intent(scope: Scope) -> str | None:
        state = scope.get("state")
        if state is None:
            return None
        if isinstance(state, dict):
            return state.get("intent")
        return getattr(state, "intent", None)

    @staticmethod
    def _format_body(body_bytes: bytes) -> str:
        if not body_bytes:
            return "<empty>"
        try:
            payload = json.loads(body_bytes.decode("utf-8"))
            preview = json.dumps(payload, ensure_ascii=False)
        except Exception:
            preview = body_bytes.decode("utf-8", errors="ignore")
        preview = preview.strip().replace("\n", " ")
        return preview[:1000] + ("..." if len(preview) > 1000 else "")
