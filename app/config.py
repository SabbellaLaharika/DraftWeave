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

    # Primary Cloud LLM Provider: NVIDIA
    NVIDIA_API_KEY: str = ""
    NVIDIA_MODEL: str = "nvidia/nemotron-3.5-lightning-30b"

    # Secondary Cloud LLM Providers
    GOOGLE_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    # Local Fallback LLM Provider: Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2:3b"

    # LLM Provider Configuration
    LLM_PROVIDER: str = "nvidia"

    # SQLite Database
    SQLITE_DB_PATH: str = "data/style_memory.db"

    @property
    def db_path(self) -> Path:
        path = Path(self.SQLITE_DB_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
