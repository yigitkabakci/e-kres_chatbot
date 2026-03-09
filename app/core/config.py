from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Ana uygulama konfigrasyonu."""

    APP_NAME: str = "e-Kres Chatbot API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    API_KEY: str = Field(
        default="",
        description="Istemci dogrulama icin API anahtari (X-API-Key header).",
    )
    ADMIN_API_KEY: str = Field(
        default="admin-panel-key",
        description="Admin paneli icin API anahtari (X-Admin-Key header).",
    )

    GOOGLE_API_KEY: str = Field(default="", description="Google AI Studio API anahtari")
    LLM_MODEL_NAME: str = Field(default="gemini-2.0-flash", description="Kullanilacak Gemini model adi")
    LLM_TEMPERATURE: float = Field(default=0.7, ge=0.0, le=2.0)
    LLM_MAX_TOKENS: int = Field(default=2048, ge=1)

    SESSION_TTL_MINUTES: int = Field(default=60, description="Oturum gecerlilik suresi (dakika).")
    MAX_HISTORY_LENGTH: int = Field(default=50, description="Oturum basina saklanacak maksimum mesaj sayisi")

    CORS_ORIGINS: list[str] = Field(default=["*"], description="Izin verilen origin listesi")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


settings = Settings()
