"""
e-Kres Chatbot API — Error Handlers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Global exception handler'lar.
Tum hatalari yapilandirilmis JSON yanitina cevirir.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


def setup_error_handlers(app: FastAPI) -> None:
    """Global hata yakalayicilarini kaydet."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """HTTP hatalarini JSON formatinda dondur."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "HTTP Hatasi",
                "detail": str(exc.detail),
                "status_code": exc.status_code,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Pydantic dogrulama hatalarini JSON formatinda dondur."""
        errors = []
        for err in exc.errors():
            field = " → ".join(str(loc) for loc in err.get("loc", []))
            errors.append(f"{field}: {err.get('msg', 'gecersiz deger')}")

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "Dogrulama Hatasi",
                "detail": "; ".join(errors),
                "status_code": 422,
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Beklenmeyen hatalari yakala ve logla."""
        logger.exception("Beklenmeyen hata: %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Sunucu Hatasi",
                "detail": "Beklenmeyen bir hata olustu. Lutfen daha sonra tekrar deneyin.",
                "status_code": 500,
            },
        )
