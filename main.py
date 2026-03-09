import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.admin_router import router as admin_router
from app.api.v1.chat_router import health_router, init_chat_service, router as chat_router
from app.core.config import settings
from app.core.constants import API_V1_PREFIX
from app.middlewares.cors import setup_cors
from app.middlewares.error_handler import setup_error_handlers
from app.middlewares.logging_middleware import LoggingMiddleware

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent
INDEX_HTML = BASE_DIR / "static" / "index.html"
ADMIN_HTML = BASE_DIR / "static" / "admin.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("e-Kres Chatbot API baslatiliyor...")
    logger.info("Model: %s | Debug: %s", settings.LLM_MODEL_NAME, settings.DEBUG)
    init_chat_service()
    logger.info("Uygulama hazir!")
    yield
    logger.info("Uygulama kapatiliyor...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "e-Kres anaokulu yonetim sistemi icin merkezi Chatbot API.\n\n"
        "Ozellikler:\n"
        "- Yemek Listesi sorgulama\n"
        "- Gun Sonu Raporu goruntuleme\n"
        "- Odeme / Borc takibi\n"
        "- Ders Programi\n"
        "- PDF bulten analizi\n"
        "- Gorsel (Vision) analizi\n"
        "- Admin paneli uzerinden veri guncelleme"
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

setup_cors(app)
app.add_middleware(LoggingMiddleware)
setup_error_handlers(app)

app.include_router(chat_router, prefix=API_V1_PREFIX)
app.include_router(admin_router, prefix=API_V1_PREFIX)
app.include_router(health_router, prefix=API_V1_PREFIX)


@app.get("/", include_in_schema=False)
async def serve_index():
    return FileResponse(INDEX_HTML, media_type="text/html; charset=utf-8")


@app.get("/admin", include_in_schema=False)
async def serve_admin():
    return FileResponse(ADMIN_HTML, media_type="text/html; charset=utf-8")


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )