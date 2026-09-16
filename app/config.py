import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""

    # Google Sheets
    GOOGLE_SHEETS_CREDENTIALS_B64: str = ""
    GOOGLE_SHEETS_CREDENTIALS_JSON: str = "credentials.json"
    GOOGLE_SHEET_NAME: str = "DraftWeave Content"
    GOOGLE_SHEET_ID: str = ""

    # Cloud LLM Providers (Gemini / Groq)
    GOOGLE_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    # Local Fallback LLM Provider (Ollama)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2:3b"

    # LLM Provider Configuration ('gemini', 'groq', or 'ollama')
    LLM_PROVIDER: str = "gemini"

    # SQLite Database
    SQLITE_DB_PATH: str = "data/style_memory.db"

    @property
    def effective_ollama_url(self) -> str:
        url = (self.OLLAMA_BASE_URL or "http://localhost:11434").rstrip("/")
        if os.path.exists("/.dockerenv") and "localhost" in url:
            return url.replace("localhost", "host.docker.internal")
        return url

    @property
    def db_path(self) -> Path:
        path = Path(self.SQLITE_DB_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
